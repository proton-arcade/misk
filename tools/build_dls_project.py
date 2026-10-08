#!/usr/bin/env python3
"""Build the clocked raw-NAND MISK-16 computer and reusable combinational chips.

The integrated DLS computer stores its 8-bit PC, eight 16-bit registers, and
three flags in master/slave NAND latches; DLS CLOCK and KEY chips provide clock,
step, and reset control. Instruction and external data-memory inputs remain
manual interfaces. No prebuilt DLS CPU/ALU/mux/register/RAM/ROM component is used;
custom logic modules are built from primitive NAND gates. The ALU's ADD/SUB paths
use a four-stage NAND Kogge-Stone adder.
"""
from __future__ import annotations

import json
import math
import random
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "MISK16-DLS"
CHIPS_DIR = PROJECT / "Chips"
DLS_VERSION = "2.1.6"
EARLIEST_VERSION = "2.0.0"

_rng = random.Random(161608)
_used_ids: set[int] = set()


def new_id() -> int:
    while True:
        value = _rng.randint(10_000_000, 2_000_000_000)
        if value not in _used_ids:
            _used_ids.add(value)
            return value


def pos(x: float, y: float) -> dict[str, float]:
    return {"x": round(x, 4), "y": round(y, 4)}


class Spec:
    def __init__(self, name: str, inputs: list[tuple[str, int, int]], outputs: list[tuple[str, int, int]]):
        self.name = name
        self.inputs = inputs
        self.outputs = outputs
        self.input_ids = {name: pin_id for name, _bits, pin_id in inputs}
        self.output_ids = {name: pin_id for name, _bits, pin_id in outputs}
        self.input_index = {name: i for i, (name, _bits, _id) in enumerate(inputs)}
        self.output_index = {name: i for i, (name, _bits, _id) in enumerate(outputs)}

    def in_port(self, name: str) -> tuple[int, int]:
        i = self.input_index[name]
        return self.inputs[i][2], self.inputs[i][1]

    def out_port(self, name: str) -> tuple[int, int]:
        i = self.output_index[name]
        return self.outputs[i][2], self.outputs[i][1]


# DLS 2.1.6 built-in descriptions. Pin IDs mirror BuiltinChipCreator.cs.
BUILTINS: dict[str, Spec] = {
    "NAND": Spec("NAND", [("IN B", 1, 0), ("IN A", 1, 1)], [("OUT", 1, 2)]),
    "4-1BIT": Spec("4-1BIT", [("IN", 4, 0)], [(f"OUT {c}", 1, i + 1) for i, c in enumerate("DCBA")]),
    "8-1BIT": Spec("8-1BIT", [("IN", 8, 0)], [(f"OUT {c}", 1, i + 1) for i, c in enumerate("HGFEDCBA")]),
    "1-4BIT": Spec("1-4BIT", [(f"IN {c}", 1, i) for i, c in enumerate("DCBA")], [("OUT", 4, 4)]),
    "1-8BIT": Spec("1-8BIT", [(f"IN {c}", 1, i) for i, c in enumerate("HGFEDCBA")], [("OUT", 8, 8)]),
    "IN-1": Spec("IN-1", [], [("OUT", 1, 0)]),
    "IN-4": Spec("IN-4", [], [("OUT", 4, 0)]),
    "IN-8": Spec("IN-8", [], [("OUT", 8, 0)]),
    "CLOCK": Spec("CLOCK", [], [("CLK", 1, 0)]),
    "KEY": Spec("KEY", [], [("OUT", 1, 0)]),
    "7-SEGMENT": Spec("7-SEGMENT", [(name, 1, i) for i, name in enumerate(("A", "B", "C", "D", "E", "F", "G", "COL"))], []),
    "OUT-1": Spec("OUT-1", [("IN", 1, 0)], []),
    "OUT-4": Spec("OUT-4", [("IN", 4, 0)], []),
    "OUT-8": Spec("OUT-8", [("IN", 8, 0)], []),
}

_specs: dict[str, Spec] = dict(BUILTINS)
_descriptions: dict[str, dict] = {}


def spec(name: str) -> Spec:
    try:
        return _specs[name]
    except KeyError as exc:
        raise KeyError(f"No DLS chip description registered for {name}") from exc


class ChipBuilder:
    def __init__(self, name: str, inputs: list[tuple[str, int]], outputs: list[tuple[str, int]], *, width: float = 16.0, height: float | None = None, colour: tuple[float, float, float] = (0.25, 0.39, 0.58)):
        self.name = name
        self.width = width
        self.input_pins: list[dict] = []
        self.output_pins: list[dict] = []
        self.input_id: dict[str, int] = {}
        self.output_id: dict[str, int] = {}
        self.input_bits: dict[str, int] = {}
        self.output_bits: dict[str, int] = {}
        self.subchips: list[dict] = []
        self.wires: list[dict] = []
        self.displays: list[dict] = []
        self.sub_spec: dict[int, Spec] = {}
        self._output_connection_count: dict[tuple[int, int], int] = {}
        self._target_connection_count: set[tuple[int, int]] = set()
        self._port_count = max(len(inputs), len(outputs), 1)
        self.height = height if height is not None else max(8.0, self._port_count * 0.75 + 2.0)

        for is_input, ports, collection, ids, bit_map in (
            (True, inputs, self.input_pins, self.input_id, self.input_bits),
            (False, outputs, self.output_pins, self.output_id, self.output_bits),
        ):
            count = len(ports)
            for index, (pin_name, bits) in enumerate(ports):
                if pin_name in ids:
                    raise ValueError(f"Duplicate pin name {pin_name} in {name}")
                pin_id = new_id()
                x = -self.width / 2 if is_input else self.width / 2
                y = (count - 1) * 0.375 - index * 0.75
                collection.append({
                    "Name": pin_name,
                    "ID": pin_id,
                    "Position": pos(x, y),
                    "BitCount": bits,
                    "Colour": 0,
                    "ValueDisplayMode": 3 if bits > 1 else 0,
                })
                ids[pin_name] = pin_id
                bit_map[pin_name] = bits

    def add_sub(self, chip_name: str, x: float, y: float, label: str = "", internal_data=None) -> int:
        child = spec(chip_name)
        owner_id = new_id()
        self.subchips.append({
            "Name": chip_name,
            "ID": owner_id,
            "Label": label,
            "Position": pos(x, y),
            "OutputPinColourInfo": [{"PinColour": 0, "PinID": pin_id} for _name, _bits, pin_id in child.outputs],
            "InternalData": internal_data,
        })
        self.sub_spec[owner_id] = child
        return owner_id

    def _endpoint(self, owner_id: int, pin_id: int, *, is_source: bool) -> tuple[int, int]:
        if owner_id in self.sub_spec:
            child = self.sub_spec[owner_id]
            valid = child.outputs if is_source else child.inputs
            if pin_id not in [p[2] for p in valid]:
                raise ValueError(f"Invalid {'output' if is_source else 'input'} pin ID {pin_id} on {child.name}")
            bits = next(p[1] for p in valid if p[2] == pin_id)
        elif owner_id in self.input_id.values() and is_source:
            if pin_id != 0:
                raise ValueError("External input endpoint pin IDs are zero")
            name = next(k for k, v in self.input_id.items() if v == owner_id)
            bits = self.input_bits[name]
        elif owner_id in self.output_id.values() and not is_source:
            if pin_id != 0:
                raise ValueError("External output endpoint pin IDs are zero")
            name = next(k for k, v in self.output_id.items() if v == owner_id)
            bits = self.output_bits[name]
        else:
            raise ValueError(f"Endpoint {owner_id}/{pin_id} has the wrong direction or unknown owner in {self.name}")
        return pin_id, bits

    def connect(self, source_owner: int, source_pin: int, target_owner: int, target_pin: int) -> None:
        _s_id, s_bits = self._endpoint(source_owner, source_pin, is_source=True)
        _t_id, t_bits = self._endpoint(target_owner, target_pin, is_source=False)
        if s_bits != t_bits:
            raise ValueError(f"Bit-count mismatch in {self.name}: {s_bits} -> {t_bits}")
        target = (target_owner, target_pin)
        if target in self._target_connection_count:
            raise ValueError(f"Input {target_owner}/{target_pin} has multiple drivers in {self.name}")
        self._target_connection_count.add(target)
        self._output_connection_count[(source_owner, source_pin)] = self._output_connection_count.get((source_owner, source_pin), 0) + 1
        self.wires.append({
            "SourcePinAddress": {"PinID": source_pin, "PinOwnerID": source_owner},
            "TargetPinAddress": {"PinID": target_pin, "PinOwnerID": target_owner},
            "ConnectionType": 0,
            "ConnectedWireIndex": -1,
            "ConnectedWireSegmentIndex": -1,
            "Points": [pos(0, 0), pos(0, 0)],
        })

    def port_to_sub(self, port: str, child_id: int, child_input: str) -> None:
        child = self.sub_spec[child_id]
        pin_id, _bits = child.in_port(child_input)
        self.connect(self.input_id[port], 0, child_id, pin_id)

    def sub_to_sub(self, source_id: int, source_output: str, target_id: int, target_input: str) -> None:
        source_spec = self.sub_spec[source_id]
        target_spec = self.sub_spec[target_id]
        source_pin, _bits = source_spec.out_port(source_output)
        target_pin, _bits = target_spec.in_port(target_input)
        self.connect(source_id, source_pin, target_id, target_pin)

    def sub_to_port(self, child_id: int, child_output: str, port: str) -> None:
        child = self.sub_spec[child_id]
        source_pin, _bits = child.out_port(child_output)
        self.connect(child_id, source_pin, self.output_id[port], 0)

    def input_to_output(self, source_port: str, target_port: str) -> None:
        self.connect(self.input_id[source_port], 0, self.output_id[target_port], 0)

    def save(self) -> Spec:
        all_ids = [p["ID"] for p in self.input_pins + self.output_pins]
        if len(all_ids) != len(set(all_ids)):
            raise ValueError(f"Duplicate dev-pin IDs in {self.name}")
        description = {
            "DLSVersion": DLS_VERSION,
            "Name": self.name,
            "NameLocation": 0,
            "ChipType": 0,
            "Size": {"x": self.width, "y": self.height},
            "Colour": {"r": self._colour[0], "g": self._colour[1], "b": self._colour[2], "a": 1.0},
            "InputPins": self.input_pins,
            "OutputPins": self.output_pins,
            "SubChips": self.subchips,
            "Wires": self.wires,
            "Displays": self.displays,
        }
        _descriptions[self.name] = description
        custom_spec = Spec(
            self.name,
            [(p["Name"], p["BitCount"], p["ID"]) for p in self.input_pins],
            [(p["Name"], p["BitCount"], p["ID"]) for p in self.output_pins],
        )
        _specs[self.name] = custom_spec
        return custom_spec

    @property
    def _colour(self):
        return getattr(self, "colour", (0.25, 0.39, 0.58))


def define(name: str, inputs: list[tuple[str, int]], outputs: list[tuple[str, int]], *, width=16.0, height=None, colour=(0.25, 0.39, 0.58)) -> ChipBuilder:
    builder = ChipBuilder(name, inputs, outputs, width=width, height=height)
    builder.colour = colour
    return builder


def sub(builder: ChipBuilder, name: str, index: int, columns: int = 5, label: str = "") -> int:
    col = index % columns
    row = index // columns
    return builder.add_sub(name, -4.0 + col * 2.0, ((columns - 1) / 2 - col) * 0.55 - row * 0.75, label)


def connect_nand_inputs(builder: ChipBuilder, nand: int, left_owner: int, left_pin: int, right_owner: int, right_pin: int) -> None:
    child = builder.sub_spec[nand]
    in_b = child.in_port("IN B")[0]
    in_a = child.in_port("IN A")[0]
    builder.connect(left_owner, left_pin, nand, in_b)
    builder.connect(right_owner, right_pin, nand, in_a)


def make_inv() -> None:
    b = define("INV", [("A", 1)], [("Y", 1)])
    n = b.add_sub("NAND", 0, 0)
    ns = spec("NAND")
    b.connect(b.input_id["A"], 0, n, ns.in_port("IN B")[0])
    b.connect(b.input_id["A"], 0, n, ns.in_port("IN A")[0])
    b.sub_to_port(n, "OUT", "Y")
    b.save()


def make_and() -> None:
    b = define("AND", [("A", 1), ("B", 1)], [("Y", 1)])
    n1 = b.add_sub("NAND", -2, 0)
    n2 = b.add_sub("NAND", 1, 0)
    connect_nand_inputs(b, n1, b.input_id["A"], 0, b.input_id["B"], 0)
    ns = spec("NAND")
    b.sub_to_sub(n1, "OUT", n2, "IN B")
    b.sub_to_sub(n1, "OUT", n2, "IN A")
    b.sub_to_port(n2, "OUT", "Y")
    b.save()


def make_or() -> None:
    b = define("OR", [("A", 1), ("B", 1)], [("Y", 1)])
    n_a = b.add_sub("NAND", -3, 0.8)
    n_b = b.add_sub("NAND", -3, -0.8)
    n_o = b.add_sub("NAND", 0, 0)
    ns = spec("NAND")
    for pin in ("IN B", "IN A"):
        b.connect(b.input_id["A"], 0, n_a, ns.in_port(pin)[0])
        b.connect(b.input_id["B"], 0, n_b, ns.in_port(pin)[0])
    b.sub_to_sub(n_a, "OUT", n_o, "IN B")
    b.sub_to_sub(n_b, "OUT", n_o, "IN A")
    b.sub_to_port(n_o, "OUT", "Y")
    b.save()


def make_xor() -> None:
    b = define("XOR", [("A", 1), ("B", 1)], [("Y", 1)])
    n1 = b.add_sub("NAND", -3, 0)
    n2 = b.add_sub("NAND", -1, 1)
    n3 = b.add_sub("NAND", -1, -1)
    n4 = b.add_sub("NAND", 1, 0)
    ns = spec("NAND")
    connect_nand_inputs(b, n1, b.input_id["A"], 0, b.input_id["B"], 0)
    b.connect(b.input_id["A"], 0, n2, ns.in_port("IN B")[0])
    b.sub_to_sub(n1, "OUT", n2, "IN A")
    b.connect(b.input_id["B"], 0, n3, ns.in_port("IN B")[0])
    b.sub_to_sub(n1, "OUT", n3, "IN A")
    b.sub_to_sub(n2, "OUT", n4, "IN B")
    b.sub_to_sub(n3, "OUT", n4, "IN A")
    b.sub_to_port(n4, "OUT", "Y")
    b.save()


def make_xnor() -> None:
    b = define("XNOR", [("A", 1), ("B", 1)], [("Y", 1)])
    x = b.add_sub("XOR", -1.5, 0)
    inv = b.add_sub("INV", 1.5, 0)
    b.port_to_sub("A", x, "A")
    b.port_to_sub("B", x, "B")
    b.sub_to_sub(x, "Y", inv, "A")
    b.sub_to_port(inv, "Y", "Y")
    b.save()


def make_nor() -> None:
    b = define("NOR", [("A", 1), ("B", 1)], [("Y", 1)])
    o = b.add_sub("OR", -1.5, 0)
    inv = b.add_sub("INV", 1.5, 0)
    b.port_to_sub("A", o, "A")
    b.port_to_sub("B", o, "B")
    b.sub_to_sub(o, "Y", inv, "A")
    b.sub_to_port(inv, "Y", "Y")
    b.save()


def make_word_logic_chips() -> None:
    """Make reusable 16-bit word-wide logic blocks from one-bit gates."""
    operations = (
        ("AND16", "AND", False),
        ("OR16", "OR", False),
        ("XOR16", "XOR", False),
        ("XNOR16", "XNOR", False),
        ("NAND16", "NAND", False),
        ("NOR16", "NOR", False),
        ("NOT16", "INV", True),
    )
    for chip_name, gate_name, unary in operations:
        inputs = [("A_LO", 8), ("A_HI", 8)]
        if not unary:
            inputs += [("B_LO", 8), ("B_HI", 8)]
        b = define(chip_name, inputs, [("Y_LO", 8), ("Y_HI", 8)], width=22, height=18, colour=(0.31, 0.48, 0.58))
        splits: dict[str, int] = {}
        for index, port in enumerate(("A_LO", "A_HI", "B_LO", "B_HI") if not unary else ("A_LO", "A_HI")):
            split = b.add_sub("8-1BIT", -7, 5 - index * 3, port)
            b.port_to_sub(port, split, "IN")
            splits[port] = split

        result_bits: dict[int, tuple[int, int]] = {}
        for bit in range(16):
            half = "LO" if bit < 8 else "HI"
            local = bit % 8
            a_source = (splits[f"A_{half}"], spec("8-1BIT").outputs[7 - local][2])
            gate = b.add_sub(gate_name, 0, 8 - bit, f"BIT {bit}")
            if unary:
                b.connect(*a_source, gate, spec(gate_name).in_port("A")[0])
            else:
                b_source = (splits[f"B_{half}"], spec("8-1BIT").outputs[7 - local][2])
                if gate_name == "NAND":
                    b.connect(*a_source, gate, spec(gate_name).in_port("IN B")[0])
                    b.connect(*b_source, gate, spec(gate_name).in_port("IN A")[0])
                else:
                    b.connect(*a_source, gate, spec(gate_name).in_port("A")[0])
                    b.connect(*b_source, gate, spec(gate_name).in_port("B")[0])
            gate_output = "OUT" if gate_name == "NAND" else "Y"
            result_bits[bit] = (gate, spec(gate_name).out_port(gate_output)[0])

        for half, low in (("LO", 0), ("HI", 8)):
            merge = b.add_sub("1-8BIT", 7, 2 if half == "LO" else -2, f"Y {half}")
            for local in range(8):
                pin_name = f"IN {'HGFEDCBA'[7 - local]}"
                b.connect(*result_bits[low + local], merge, spec("1-8BIT").in_port(pin_name)[0])
            b.sub_to_port(merge, "OUT", f"Y_{half}")
        b.save()


def make_and3_and4() -> None:
    for width in (3,):
        names = [f"A{i}" for i in range(width)]
        b = define(f"AND{width}", [(n, 1) for n in names], [("Y", 1)])
        prev_owner = None
        prev_pin = None
        for i in range(width - 1):
            gate = b.add_sub("AND", -2 + i * 1.8, (width - 2) * 0.3 - i * 0.6)
            if i == 0:
                b.port_to_sub(names[0], gate, "A")
                b.port_to_sub(names[1], gate, "B")
            else:
                b.connect(prev_owner, prev_pin, gate, spec("AND").in_port("A")[0])
                b.port_to_sub(names[i + 1], gate, "B")
            prev_owner = gate
            prev_pin = spec("AND").out_port("Y")[0]
        b.sub_to_port(prev_owner, "Y", "Y")
        b.save()


def make_or_reduce8() -> None:
    b = define("OR_REDUCE8", [(f"D{i}", 1) for i in range(8)], [("Y", 1)])
    level = [(b.input_id[f"D{i}"], 0, "external") for i in range(8)]
    gate_index = 0
    while len(level) > 1:
        next_level = []
        for j in range(0, len(level), 2):
            if j + 1 == len(level):
                next_level.append(level[j])
                continue
            g = b.add_sub("OR", -2 + (gate_index % 5) * 1.0, 2 - (gate_index // 5) * 0.6)
            for arg_i, signal in enumerate((level[j], level[j + 1])):
                owner, pin, kind = signal
                port = "A" if arg_i == 0 else "B"
                target = spec("OR").in_port(port)[0]
                if kind == "external":
                    b.connect(owner, pin, g, target)
                else:
                    b.connect(owner, pin, g, target)
            next_level.append((g, spec("OR").out_port("Y")[0], "sub"))
            gate_index += 1
        level = next_level
    owner, pin, kind = level[0]
    if kind == "external":
        b.connect(owner, pin, b.output_id["Y"], 0)
    else:
        b.connect(owner, pin, b.output_id["Y"], 0)
    b.save()


def make_and4() -> None:
    b = define("AND4", [(f"A{i}", 1) for i in range(4)], [("Y", 1)])
    a = b.add_sub("AND", -1.5, 0.6)
    c = b.add_sub("AND", -1.5, -0.6)
    out = b.add_sub("AND", 1.5, 0)
    b.port_to_sub("A0", a, "A")
    b.port_to_sub("A1", a, "B")
    b.port_to_sub("A2", c, "A")
    b.port_to_sub("A3", c, "B")
    b.sub_to_sub(a, "Y", out, "A")
    b.sub_to_sub(c, "Y", out, "B")
    b.sub_to_port(out, "Y", "Y")
    b.save()


def make_decoder4to16() -> None:
    b = define("DECODER4TO16", [("NIBBLE", 4)], [(f"D{i:02X}", 1) for i in range(16)], width=22.0, height=22.0, colour=(0.24, 0.48, 0.34))
    split = b.add_sub("4-1BIT", -7, 0, "B3..B0")
    b.port_to_sub("NIBBLE", split, "IN")
    split_spec = spec("4-1BIT")
    bit_ids = [split_spec.out_port(f"OUT {c}")[0] for c in "DCBA"]
    invs = [b.add_sub("INV", -4, 3 - i * 2) for i in range(4)]
    for bit_i, inv in enumerate(invs):
        b.connect(split, bit_ids[bit_i], inv, spec("INV").in_port("A")[0])
    for value in range(16):
        gate = b.add_sub("AND4", 0.5 + (value % 4) * 1.5, 5.5 - (value // 4) * 1.6, f"{value:02X}")
        and_spec = spec("AND4")
        for bit_i, bit_name in enumerate(("A0", "A1", "A2", "A3")):
            source_owner = split if ((value >> (3 - bit_i)) & 1) else invs[bit_i]
            if source_owner == split:
                source_pin = bit_ids[bit_i]
            else:
                source_pin = spec("INV").out_port("Y")[0]
            b.connect(source_owner, source_pin, gate, and_spec.in_port(bit_name)[0])
        b.sub_to_port(gate, "Y", f"D{value:02X}")
    b.save()


def make_encoder16to4() -> None:
    b = define("ENCODER16TO4", [(f"D{i:02X}", 1) for i in range(16)], [("NIBBLE", 4)], width=20.0, height=22.0, colour=(0.24, 0.48, 0.34))
    bit_sources: list[int] = []
    for bit in range(4):
        selected = [i for i in range(16) if (i >> (3 - bit)) & 1]
        layer = [(b.input_id[f"D{i:02X}"], 0, None) for i in selected]
        gate_index = 0
        while len(layer) > 1:
            nxt = []
            for j in range(0, len(layer), 2):
                if j + 1 == len(layer):
                    nxt.append(layer[j])
                    continue
                gate = b.add_sub("OR", -2 + (gate_index % 6) * 1.2, 3.5 - bit * 1.4 - (gate_index // 6) * 0.7)
                for k, signal in enumerate((layer[j], layer[j + 1])):
                    owner, pin, _kind = signal
                    b.connect(owner, pin, gate, spec("OR").in_port("A" if k == 0 else "B")[0])
                nxt.append((gate, spec("OR").out_port("Y")[0], gate))
                gate_index += 1
            layer = nxt
        owner, pin, _kind = layer[0]
        if owner == b.input_id.get(f"D{selected[0]:02X}"):
            # This case does not occur for the four encoded bits, but keeps the graph general.
            bit_sources.append((owner, pin))
        else:
            bit_sources.append((owner, pin))
    # Merge inputs D,C,B,A are nibble bits 3,2,1,0 respectively.
    merge = b.add_sub("1-4BIT", 4, 0)
    merge_spec = spec("1-4BIT")
    for bit, source in enumerate(bit_sources):
        owner, pin = source
        b.connect(owner, pin, merge, merge_spec.in_port(f"IN {'DCBA'[bit]}")[0])
    b.sub_to_port(merge, "OUT", "NIBBLE")
    b.save()


def make_hex7seg() -> None:
    b = define("HEX7SEG", [("NIBBLE", 4)], [(segment, 1) for segment in "abcdefg"], width=18.0, height=12.0, colour=(0.52, 0.28, 0.22))
    decoder = b.add_sub("DECODER4TO16", -4, 0, "HEX")
    b.port_to_sub("NIBBLE", decoder, "NIBBLE")
    patterns = {
        0: "abcdef", 1: "bc", 2: "abdeg", 3: "abcdg",
        4: "bcfg", 5: "acdfg", 6: "acdefg", 7: "abc",
        8: "abcdefg", 9: "abcdfg", 10: "abcefg", 11: "cdefg",
        12: "adef", 13: "bcdeg", 14: "adefg", 15: "aefg",
    }
    for segment in "abcdefg":
        selected = [value for value, lit in patterns.items() if segment in lit]
        # Reuse the 8-input reduction chip in groups if a segment has more than 8 terms.
        layer = [(decoder, spec("DECODER4TO16").out_port(f"D{value:02X}")[0]) for value in selected]
        while len(layer) > 1:
            nxt = []
            for j in range(0, len(layer), 2):
                if j + 1 == len(layer):
                    nxt.append(layer[j])
                    continue
                gate = b.add_sub("OR", 0, 4 - (len(b.subchips) % 11) * 0.6, f"{segment.upper()}-OR")
                b.connect(layer[j][0], layer[j][1], gate, spec("OR").in_port("A")[0])
                b.connect(layer[j + 1][0], layer[j + 1][1], gate, spec("OR").in_port("B")[0])
                nxt.append((gate, spec("OR").out_port("Y")[0]))
            layer = nxt
        owner, pin = layer[0]
        b.connect(owner, pin, b.output_id[segment], 0)
    b.save()


def make_hex_display16() -> None:
    """Split a 16-bit word into four hex digits and expose each 7-segment line."""
    outputs = [(f"DIGIT_{digit}", 4) for digit in range(4)]
    outputs += [(f"SEG_D{digit}_{segment.upper()}", 1) for digit in range(4) for segment in "abcdefg"]
    b = define("HEX_DISPLAY16", [("WORD_LO", 8), ("WORD_HI", 8)], outputs, width=26, height=24, colour=(0.52, 0.28, 0.22))
    split_lo = b.add_sub("8-1BIT", -8, 2, "WORD LO")
    split_hi = b.add_sub("8-1BIT", -8, -2, "WORD HI")
    b.port_to_sub("WORD_LO", split_lo, "IN")
    b.port_to_sub("WORD_HI", split_hi, "IN")
    split_spec = spec("8-1BIT")

    # Digit 0 is the least significant nibble; digit 3 is the most significant.
    digit_sources = (
        (split_lo, (4, 5, 6, 7)),
        (split_lo, (0, 1, 2, 3)),
        (split_hi, (4, 5, 6, 7)),
        (split_hi, (0, 1, 2, 3)),
    )
    for digit, (split, output_indices) in enumerate(digit_sources):
        merge = b.add_sub("1-4BIT", -3, 6 - digit * 4, f"DIGIT {digit} NIBBLE")
        merge_spec = spec("1-4BIT")
        for nibble_bit, output_index in zip(("D", "C", "B", "A"), output_indices):
            b.connect(split, split_spec.outputs[output_index][2], merge, merge_spec.in_port(f"IN {nibble_bit}")[0])
        b.sub_to_port(merge, "OUT", f"DIGIT_{digit}")
        decoder = b.add_sub("HEX7SEG", 4, 6 - digit * 4, f"DIGIT {digit}")
        b.sub_to_sub(merge, "OUT", decoder, "NIBBLE")
        for segment in "abcdefg":
            b.sub_to_port(decoder, segment, f"SEG_D{digit}_{segment.upper()}")
    b.save()


def make_full_adder() -> None:
    b = define("FULL_ADDER_1", [("A", 1), ("B", 1), ("CIN", 1)], [("SUM", 1), ("COUT", 1)], colour=(0.68, 0.39, 0.18))
    p = b.add_sub("XOR", -2.5, 0.8, "P=A XOR B")
    s = b.add_sub("XOR", 0.0, 1.2, "SUM")
    ab = b.add_sub("AND", -2.5, -0.8)
    pc = b.add_sub("AND", 0.0, -0.8)
    carry = b.add_sub("OR", 2.5, -0.2, "COUT")
    b.port_to_sub("A", p, "A")
    b.port_to_sub("B", p, "B")
    b.sub_to_sub(p, "Y", s, "A")
    b.port_to_sub("CIN", s, "B")
    b.sub_to_port(s, "Y", "SUM")
    b.port_to_sub("A", ab, "A")
    b.port_to_sub("B", ab, "B")
    b.sub_to_sub(p, "Y", pc, "A")
    b.port_to_sub("CIN", pc, "B")
    b.sub_to_sub(ab, "Y", carry, "A")
    b.sub_to_sub(pc, "Y", carry, "B")
    b.sub_to_port(carry, "Y", "COUT")
    b.save()


def make_half_adder() -> None:
    b = define("HALF_ADDER_1", [("A", 1), ("B", 1)], [("SUM", 1), ("COUT", 1)], colour=(0.68, 0.39, 0.18))
    xor = b.add_sub("XOR", -1.5, 0.8, "SUM")
    and_gate = b.add_sub("AND", -1.5, -0.8, "CARRY")
    b.port_to_sub("A", xor, "A")
    b.port_to_sub("B", xor, "B")
    b.port_to_sub("A", and_gate, "A")
    b.port_to_sub("B", and_gate, "B")
    b.sub_to_port(xor, "Y", "SUM")
    b.sub_to_port(and_gate, "Y", "COUT")
    b.save()


def adder_ports(width: int):
    inputs = [(f"A{i}", 1) for i in range(width)] + [(f"B{i}", 1) for i in range(width)] + [("CIN", 1)]
    outputs = [(f"S{i}", 1) for i in range(width)] + [("COUT", 1)]
    return inputs, outputs


def make_adder(width: int) -> None:
    inputs, outputs = adder_ports(width)
    b = define(f"ADDER_{width}", inputs, outputs, width=max(16.0, width * 1.3), height=max(14.0, len(inputs) * 0.7 + 2), colour=(0.68, 0.39, 0.18))
    if width == 1:
        # The named 1-bit foundation is a wrapper around the primitive full adder.
        fa = b.add_sub("FULL_ADDER_1", 0, 0, "FA")
        for outer, inner in (("A0", "A"), ("B0", "B"), ("CIN", "CIN")):
            b.port_to_sub(outer, fa, inner)
        b.sub_to_port(fa, "SUM", "S0")
        b.sub_to_port(fa, "COUT", "COUT")
    elif width == 2:
        for bit in range(2):
            fa = b.add_sub("FULL_ADDER_1", -1.5 + bit * 3, 0, f"BIT {bit}")
            b.port_to_sub(f"A{bit}", fa, "A")
            b.port_to_sub(f"B{bit}", fa, "B")
            if bit == 0:
                b.port_to_sub("CIN", fa, "CIN")
            else:
                b.sub_to_sub(prev, "COUT", fa, "CIN")
            b.sub_to_port(fa, "SUM", f"S{bit}")
            prev = fa
        b.sub_to_port(prev, "COUT", "COUT")
    else:
        half = width // 2
        child = b.add_sub(f"ADDER_{half}", -2.5, 0, "LOWER")
        upper = b.add_sub(f"ADDER_{half}", 2.5, 0, "UPPER")
        child_spec = spec(f"ADDER_{half}")
        for bit in range(half):
            b.port_to_sub(f"A{bit}", child, f"A{bit}")
            b.port_to_sub(f"B{bit}", child, f"B{bit}")
            b.sub_to_port(child, f"S{bit}", f"S{bit}")
            b.port_to_sub(f"A{bit + half}", upper, f"A{bit}")
            b.port_to_sub(f"B{bit + half}", upper, f"B{bit}")
            b.sub_to_port(upper, f"S{bit}", f"S{bit + half}")
        b.port_to_sub("CIN", child, "CIN")
        b.sub_to_sub(child, "COUT", upper, "CIN")
        b.sub_to_port(upper, "COUT", "COUT")
    b.save()


def make_add16() -> None:
    """Byte-oriented 16-bit adder wrapper around the explicit 1-bit hierarchy."""
    inputs = [(name, 8) for name in ("A_LO", "A_HI", "B_LO", "B_HI")] + [("CIN", 1)]
    b = define("ADD16", inputs, [("SUM_LO", 8), ("SUM_HI", 8), ("COUT", 1)], width=24, height=18, colour=(0.68, 0.39, 0.18))
    splitters = {}
    for index, port in enumerate(("A_LO", "A_HI", "B_LO", "B_HI")):
        split = b.add_sub("8-1BIT", -8, 5 - index * 2.6, port)
        b.port_to_sub(port, split, "IN")
        splitters[port] = split
    adder = b.add_sub("ADDER_16", 0, 0, "RIPPLE ADDER")
    for bit in range(16):
        half = "LO" if bit < 8 else "HI"
        local = bit % 8
        split_pin = spec("8-1BIT").outputs[7 - local][2]
        b.connect(splitters[f"A_{half}"], split_pin, adder, spec("ADDER_16").in_port(f"A{bit}")[0])
        b.connect(splitters[f"B_{half}"], split_pin, adder, spec("ADDER_16").in_port(f"B{bit}")[0])
    b.port_to_sub("CIN", adder, "CIN")
    for half, start in (("LO", 0), ("HI", 8)):
        merge = b.add_sub("1-8BIT", 7, 2 if half == "LO" else -2, f"SUM {half}")
        for local in range(8):
            target = f"IN {'HGFEDCBA'[7 - local]}"
            b.sub_to_sub(adder, f"S{start + local}", merge, target)
        b.sub_to_port(merge, "OUT", f"SUM_{half}")
    b.sub_to_port(adder, "COUT", "COUT")
    b.save()


def make_sub16() -> None:
    inputs = [(name, 8) for name in ("A_LO", "A_HI", "B_LO", "B_HI")]
    b = define("SUB16", inputs, [("DIFF_LO", 8), ("DIFF_HI", 8), ("NO_BORROW", 1)], width=24, height=18, colour=(0.68, 0.39, 0.18))
    invert_b = b.add_sub("NOT16", -5, 2, "ONES-COMPLEMENT B")
    b.port_to_sub("B_LO", invert_b, "A_LO")
    b.port_to_sub("B_HI", invert_b, "A_HI")
    adder = b.add_sub("ADD16", 3, 0, "A + NOT(B) + 1")
    for half in ("LO", "HI"):
        b.port_to_sub(f"A_{half}", adder, f"A_{half}")
        b.sub_to_sub(invert_b, f"Y_{half}", adder, f"B_{half}")

    # Build a constant one from A0 and its complement; no constant chip or state is needed.
    split_a = b.add_sub("8-1BIT", -8, -5, "A LO BITS")
    b.port_to_sub("A_LO", split_a, "IN")
    inv_a0 = b.add_sub("INV", -5, -6, "NOT A0")
    b.connect(split_a, spec("8-1BIT").out_port("OUT A")[0], inv_a0, spec("INV").in_port("A")[0])
    one = b.add_sub("NAND", -2, -7, "LOGIC ONE")
    b.connect(split_a, spec("8-1BIT").out_port("OUT A")[0], one, spec("NAND").in_port("IN B")[0])
    b.sub_to_sub(inv_a0, "Y", one, "IN A")
    b.sub_to_sub(one, "OUT", adder, "CIN")

    b.sub_to_port(adder, "SUM_LO", "DIFF_LO")
    b.sub_to_port(adder, "SUM_HI", "DIFF_HI")
    b.sub_to_port(adder, "COUT", "NO_BORROW")
    b.save()


def make_mux2_1() -> None:
    b = define("MUX2_1", [("A", 1), ("B", 1), ("SEL", 1)], [("Y", 1)])
    inv = b.add_sub("INV", -2.5, 1.1)
    a_gate = b.add_sub("AND", 0, 1.1)
    b_gate = b.add_sub("AND", 0, -1.1)
    out = b.add_sub("OR", 2.5, 0)
    b.port_to_sub("SEL", inv, "A")
    b.port_to_sub("A", a_gate, "A")
    b.sub_to_sub(inv, "Y", a_gate, "B")
    b.port_to_sub("B", b_gate, "A")
    b.port_to_sub("SEL", b_gate, "B")
    b.sub_to_sub(a_gate, "Y", out, "A")
    b.sub_to_sub(b_gate, "Y", out, "B")
    b.sub_to_port(out, "Y", "Y")
    b.save()


def make_mux2_8() -> None:
    b = define("MUX2_8", [("A", 8), ("B", 8), ("SEL", 1)], [("Y", 8)], width=18.0, height=14.0, colour=(0.54, 0.4, 0.2))
    split_a = b.add_sub("8-1BIT", -5, 2.5, "A")
    split_b = b.add_sub("8-1BIT", -5, -2.5, "B")
    b.port_to_sub("A", split_a, "IN")
    b.port_to_sub("B", split_b, "IN")
    sa, sb, merge = spec("8-1BIT"), spec("8-1BIT"), b.add_sub("1-8BIT", 5, 0, "Y")
    merge_spec = spec("1-8BIT")
    for bit in range(8):
        # Split outputs are ordered MSB to LSB; MUX/merge input names are also MSB to LSB.
        mux = b.add_sub("MUX2_1", 0, 3.0 - bit * 0.85, f"BIT {7-bit}")
        b.connect(split_a, sa.outputs[bit][2], mux, spec("MUX2_1").in_port("A")[0])
        b.connect(split_b, sb.outputs[bit][2], mux, spec("MUX2_1").in_port("B")[0])
        b.port_to_sub("SEL", mux, "SEL")
        b.sub_to_sub(mux, "Y", merge, f"IN {'HGFEDCBA'[bit]}")
    b.sub_to_port(merge, "OUT", "Y")
    b.save()


def make_mux2_16() -> None:
    inputs = [(name, 8) for name in ("A_LO", "A_HI", "B_LO", "B_HI")] + [("SEL", 1)]
    b = define("MUX2_16", inputs, [("Y_LO", 8), ("Y_HI", 8)], width=20, height=14, colour=(0.54, 0.4, 0.2))
    for half, y in (("LO", 2), ("HI", -2)):
        mux = b.add_sub("MUX2_8", 0, y, f"MUX {half}")
        b.port_to_sub(f"A_{half}", mux, "A")
        b.port_to_sub(f"B_{half}", mux, "B")
        b.port_to_sub("SEL", mux, "SEL")
        b.sub_to_port(mux, "Y", f"Y_{half}")
    b.save()


def make_mux8_1() -> None:
    b = define("MUX8_1", [(f"D{i}", 1) for i in range(8)] + [("SEL", 4)], [("Y", 1)], width=18.0, height=16.0, colour=(0.54, 0.4, 0.2))
    dec = b.add_sub("DECODER4TO16", -5, 0, "SELECT")
    b.port_to_sub("SEL", dec, "NIBBLE")
    terms = []
    for i in range(8):
        and_gate = b.add_sub("AND", -1, 3.0 - i * 0.85, f"D{i}")
        b.port_to_sub(f"D{i}", and_gate, "A")
        b.sub_to_sub(dec, f"D{i:02X}", and_gate, "B")
        terms.append((and_gate, "Y"))
    while len(terms) > 1:
        nxt = []
        for j in range(0, len(terms), 2):
            if j + 1 == len(terms):
                nxt.append(terms[j])
                continue
            gate = b.add_sub("OR", 2, 3.0 - (len(nxt) % 4) * 1.2, "OR")
            b.sub_to_sub(terms[j][0], terms[j][1], gate, "A")
            b.sub_to_sub(terms[j + 1][0], terms[j + 1][1], gate, "B")
            nxt.append((gate, "Y"))
        terms = nxt
    b.sub_to_port(terms[0][0], terms[0][1], "Y")
    b.save()


def make_mux8_8() -> None:
    b = define("MUX8_8", [(f"D{i}", 8) for i in range(8)] + [("SEL", 4)], [("Y", 8)], width=20.0, height=18.0, colour=(0.54, 0.4, 0.2))
    splits = []
    for i in range(8):
        split = b.add_sub("8-1BIT", -7, 5.0 - i * 1.3, f"D{i}")
        b.port_to_sub(f"D{i}", split, "IN")
        splits.append(split)
    merge = b.add_sub("1-8BIT", 7, 0, "Y")
    merge_spec = spec("1-8BIT")
    split_spec = spec("8-1BIT")
    for bit in range(8):
        mux = b.add_sub("MUX8_1", 0, 5.0 - bit * 1.3, f"BIT {7-bit}")
        for i, split in enumerate(splits):
            b.connect(split, split_spec.outputs[bit][2], mux, spec("MUX8_1").in_port(f"D{i}")[0])
        b.port_to_sub("SEL", mux, "SEL")
        b.sub_to_sub(mux, "Y", merge, f"IN {'HGFEDCBA'[bit]}")
    b.sub_to_port(merge, "OUT", "Y")
    b.save()


def make_mux8_16() -> None:
    inputs = [(f"D{i}_{half}", 8) for i in range(8) for half in ("LO", "HI")] + [("SEL", 4)]
    b = define("MUX8_16", inputs, [("Y_LO", 8), ("Y_HI", 8)], width=26, height=20, colour=(0.54, 0.4, 0.2))
    for half, y in (("LO", 2), ("HI", -2)):
        mux = b.add_sub("MUX8_8", 0, y, f"MUX {half}")
        for index in range(8):
            b.port_to_sub(f"D{index}_{half}", mux, f"D{index}")
        b.port_to_sub("SEL", mux, "SEL")
        b.sub_to_port(mux, "Y", f"Y_{half}")
    b.save()


def make_zero16() -> None:
    b = define("ZERO16", [("LO", 8), ("HI", 8)], [("ZERO", 1)], width=18.0, height=10.0)
    sl = b.add_sub("8-1BIT", -5, -1, "LO")
    sh = b.add_sub("8-1BIT", -5, 1, "HI")
    b.port_to_sub("LO", sl, "IN")
    b.port_to_sub("HI", sh, "IN")
    all_bits = []
    for index in range(8):
        all_bits.append((sl, spec("8-1BIT").outputs[index][2]))
        all_bits.append((sh, spec("8-1BIT").outputs[index][2]))
    layer = all_bits
    while len(layer) > 1:
        nxt = []
        for j in range(0, len(layer), 2):
            if j + 1 == len(layer):
                nxt.append(layer[j])
                continue
            gate = b.add_sub("OR", -1 + (len(nxt) % 4) * 1.0, 3 - len(nxt) * 0.6)
            b.connect(layer[j][0], layer[j][1], gate, spec("OR").in_port("A")[0])
            b.connect(layer[j + 1][0], layer[j + 1][1], gate, spec("OR").in_port("B")[0])
            nxt.append((gate, spec("OR").out_port("Y")[0]))
        layer = nxt
    inv = b.add_sub("INV", 3, 0)
    b.connect(layer[0][0], layer[0][1], inv, spec("INV").in_port("A")[0])
    b.sub_to_port(inv, "Y", "ZERO")
    b.save()


def make_compare16() -> None:
    """Unsigned and two's-complement signed comparisons from A - B."""
    inputs = [(name, 8) for name in ("A_LO", "A_HI", "B_LO", "B_HI")]
    outputs = [(name, 1) for name in ("EQ", "NE", "LT_U", "LE_U", "GT_U", "GE_U", "LT_S", "LE_S", "GT_S", "GE_S")]
    b = define("COMPARE16", inputs, outputs, width=26, height=22, colour=(0.43, 0.31, 0.58))
    sub = b.add_sub("SUB16", -2, 0, "A - B")
    for name in ("A_LO", "A_HI", "B_LO", "B_HI"):
        b.port_to_sub(name, sub, name)
    zero = b.add_sub("ZERO16", 2, 4, "EQUAL")
    b.sub_to_sub(sub, "DIFF_LO", zero, "LO")
    b.sub_to_sub(sub, "DIFF_HI", zero, "HI")
    b.sub_to_port(zero, "ZERO", "EQ")

    not_equal = b.add_sub("INV", 4, 4, "NOT EQUAL")
    b.sub_to_sub(zero, "ZERO", not_equal, "A")
    b.sub_to_port(not_equal, "Y", "NE")
    less_u = b.add_sub("INV", 2, 0, "UNSIGNED BORROW")
    b.sub_to_sub(sub, "NO_BORROW", less_u, "A")
    b.sub_to_port(less_u, "Y", "LT_U")
    b.sub_to_port(sub, "NO_BORROW", "GE_U")

    greater_u = b.add_sub("AND", 6, 1, "A > B unsigned")
    b.sub_to_sub(sub, "NO_BORROW", greater_u, "A")
    b.sub_to_sub(not_equal, "Y", greater_u, "B")
    b.sub_to_port(greater_u, "Y", "GT_U")
    less_equal_u = b.add_sub("OR", 6, 4, "A <= B unsigned")
    b.sub_to_sub(less_u, "Y", less_equal_u, "A")
    b.sub_to_sub(zero, "ZERO", less_equal_u, "B")
    b.sub_to_port(less_equal_u, "Y", "LE_U")

    sign_a = b.add_sub("8-1BIT", -6, -4, "A SIGN")
    sign_b = b.add_sub("8-1BIT", -6, -6, "B SIGN")
    sign_diff = b.add_sub("8-1BIT", 0, -6, "DIFFERENCE SIGN")
    b.port_to_sub("A_HI", sign_a, "IN")
    b.port_to_sub("B_HI", sign_b, "IN")
    b.sub_to_sub(sub, "DIFF_HI", sign_diff, "IN")
    signs_differ = b.add_sub("XOR", -2, -6, "SIGN A XOR SIGN B")
    b.connect(sign_a, spec("8-1BIT").out_port("OUT H")[0], signs_differ, spec("XOR").in_port("A")[0])
    b.connect(sign_b, spec("8-1BIT").out_port("OUT H")[0], signs_differ, spec("XOR").in_port("B")[0])
    less_s = b.add_sub("MUX2_1", 3, -5, "SIGNED LESS")
    b.connect(sign_diff, spec("8-1BIT").out_port("OUT H")[0], less_s, spec("MUX2_1").in_port("A")[0])
    b.connect(sign_a, spec("8-1BIT").out_port("OUT H")[0], less_s, spec("MUX2_1").in_port("B")[0])
    b.sub_to_sub(signs_differ, "Y", less_s, "SEL")
    b.sub_to_port(less_s, "Y", "LT_S")

    not_less_s = b.add_sub("INV", 6, -5, "SIGNED GE")
    b.sub_to_sub(less_s, "Y", not_less_s, "A")
    b.sub_to_port(not_less_s, "Y", "GE_S")
    greater_s = b.add_sub("AND", 8, -3, "A > B signed")
    b.sub_to_sub(not_less_s, "Y", greater_s, "A")
    b.sub_to_sub(not_equal, "Y", greater_s, "B")
    b.sub_to_port(greater_s, "Y", "GT_S")
    less_equal_s = b.add_sub("OR", 8, -6, "A <= B signed")
    b.sub_to_sub(less_s, "Y", less_equal_s, "A")
    b.sub_to_sub(zero, "ZERO", less_equal_s, "B")
    b.sub_to_port(less_equal_s, "Y", "LE_S")
    b.save()


def make_fast_cla16() -> None:
    """16-bit Kogge-Stone carry-lookahead adder, composed only of primitive NANDs."""
    inputs = [(f"A{i}", 1) for i in range(16)] + [(f"B{i}", 1) for i in range(16)] + [("CIN", 1)]
    outputs = [(f"S{i}", 1) for i in range(16)] + [("COUT", 1)]
    b = define("MISK16_CLA16", inputs, outputs, width=48, height=62, colour=(0.68, 0.39, 0.18))
    gate_index = 0

    def gate(label: str) -> int:
        nonlocal gate_index
        col = gate_index % 28
        row = gate_index // 28
        gate_index += 1
        return b.add_sub("NAND", -19 + col * 1.35, 27 - row * 1.15, label)

    def nand(a: tuple[int, int], rhs: tuple[int, int], label: str) -> tuple[int, int]:
        owner = gate(label)
        b.connect(a[0], a[1], owner, spec("NAND").in_port("IN A")[0])
        b.connect(rhs[0], rhs[1], owner, spec("NAND").in_port("IN B")[0])
        return owner, spec("NAND").out_port("OUT")[0]

    def inv(a: tuple[int, int], label: str) -> tuple[int, int]:
        return nand(a, a, label)

    def and2(a: tuple[int, int], rhs: tuple[int, int], label: str) -> tuple[int, int]:
        return inv(nand(a, rhs, f"{label} NAND"), f"{label} INV")

    def or2(a: tuple[int, int], rhs: tuple[int, int], label: str) -> tuple[int, int]:
        return nand(inv(a, f"{label} A BAR"), inv(rhs, f"{label} B BAR"), label)

    def xor2(a: tuple[int, int], rhs: tuple[int, int], label: str) -> tuple[int, int]:
        ab_n = nand(a, rhs, f"{label} P")
        a_term = nand(a, ab_n, f"{label} A")
        b_term = nand(rhs, ab_n, f"{label} B")
        return nand(a_term, b_term, f"{label} SUM")

    a = [(b.input_id[f"A{i}"], 0) for i in range(16)]
    bb = [(b.input_id[f"B{i}"], 0) for i in range(16)]
    cin = (b.input_id["CIN"], 0)
    propagate = [xor2(a[i], bb[i], f"BIT {i} PROPAGATE") for i in range(16)]
    generate = [and2(a[i], bb[i], f"BIT {i} GENERATE") for i in range(16)]

    # Four parallel-prefix stages compute group propagate/generate in logarithmic depth.
    prefix_p = propagate[:]
    prefix_g = generate[:]
    for stage, distance in enumerate((1, 2, 4, 8), start=1):
        prev_p, prev_g = prefix_p, prefix_g
        prefix_p, prefix_g = prev_p[:], prev_g[:]
        for bit in range(distance, 16):
            carried = and2(prev_p[bit], prev_g[bit - distance], f"S{stage} G{bit} TERM")
            prefix_g[bit] = or2(prev_g[bit], carried, f"S{stage} G{bit}")
            prefix_p[bit] = and2(prev_p[bit], prev_p[bit - distance], f"S{stage} P{bit}")

    carries = [cin]
    for bit in range(1, 16):
        prefix = bit - 1
        carry_in = or2(prefix_g[prefix], and2(prefix_p[prefix], cin, f"C{bit} CIN TERM"), f"CARRY {bit}")
        carries.append(carry_in)
    for bit in range(16):
        b.connect(*xor2(propagate[bit], carries[bit], f"BIT {bit} RESULT"), b.output_id[f"S{bit}"], 0)
    cout = or2(prefix_g[15], and2(prefix_p[15], cin, "COUT CIN TERM"), "CARRY OUT")
    b.connect(cout[0], cout[1], b.output_id["COUT"], 0)
    b.save()


def make_alu16() -> None:
    inputs = [("A_LO", 8), ("A_HI", 8), ("B_LO", 8), ("B_HI", 8)] + [(f"SEL_{op}", 1) for op in ("ADD", "SUB", "AND", "OR", "XOR", "XNOR", "NAND", "NOR", "NOT")]
    outputs = [("Y_LO", 8), ("Y_HI", 8), ("COUT", 1), ("ZERO", 1), ("NEGATIVE", 1)]
    b = define("ALU16", inputs, outputs, width=24.0, height=18.0, colour=(0.63, 0.28, 0.29))
    split_spec = spec("8-1BIT")
    input_splits: dict[str, int] = {}
    for port_i, port in enumerate(("A_LO", "A_HI", "B_LO", "B_HI")):
        split = b.add_sub("8-1BIT", -9, 5.0 - port_i * 3.0, port)
        b.port_to_sub(port, split, "IN")
        input_splits[port] = split
    def source(bit_name: str, bit: int) -> tuple[int, int]:
        bank = "LO" if bit < 8 else "HI"
        port = f"{bit_name}_{bank}"
        local_bit = bit % 8
        return input_splits[port], split_spec.outputs[7 - local_bit][2]

    inv_a: dict[int, int] = {}
    inv_b: dict[int, int] = {}
    not_a_bits: dict[int, tuple[int, int]] = {}
    not_b_bits: dict[int, tuple[int, int]] = {}
    for bit in range(16):
        ia = b.add_sub("INV", -5, 6 - bit * 0.75, f"NOT A{bit}")
        ib = b.add_sub("INV", -5, -7 - bit * 0.75, f"NOT B{bit}")
        b.connect(*source("A", bit), ia, spec("INV").in_port("A")[0])
        b.connect(*source("B", bit), ib, spec("INV").in_port("A")[0])
        inv_a[bit] = ia
        inv_b[bit] = ib
        not_a_bits[bit] = (ia, spec("INV").out_port("Y")[0])
        not_b_bits[bit] = (ib, spec("INV").out_port("Y")[0])

    # Derive constant 0 and 1 from A0 and NOT(A0), without extra input pins or feedback.
    const_inv = b.add_sub("INV", -2, 0, "A0 complement")
    b.connect(*source("A", 0), const_inv, spec("INV").in_port("A")[0])
    const0 = b.add_sub("AND", 0, 1, "constant 0")
    const1 = b.add_sub("NAND", 0, -1, "constant 1")
    b.connect(*source("A", 0), const0, spec("AND").in_port("A")[0])
    b.sub_to_sub(const_inv, "Y", const0, "B")
    b.connect(*source("A", 0), const1, spec("NAND").in_port("IN B")[0])
    b.sub_to_sub(const_inv, "Y", const1, "IN A")

    add = b.add_sub("MISK16_CLA16", 2, 5, "A + B · 4-STAGE CLA")
    sub = b.add_sub("MISK16_CLA16", 2, -7, "A + NOT(B) + 1 · 4-STAGE CLA")
    for bit in range(16):
        b.connect(*source("A", bit), add, spec("MISK16_CLA16").in_port(f"A{bit}")[0])
        b.connect(*source("B", bit), add, spec("MISK16_CLA16").in_port(f"B{bit}")[0])
        b.connect(*source("A", bit), sub, spec("MISK16_CLA16").in_port(f"A{bit}")[0])
        b.connect(*not_b_bits[bit], sub, spec("MISK16_CLA16").in_port(f"B{bit}")[0])
    b.sub_to_sub(const0, "Y", add, "CIN")
    b.sub_to_sub(const1, "OUT", sub, "CIN")

    logic_bits: dict[str, dict[int, tuple[int, int]]] = {op: {} for op in ("AND", "OR", "XOR", "XNOR", "NAND", "NOR", "NOT")}
    for bit in range(16):
        for op, gate_name in (("AND", "AND"), ("OR", "OR"), ("XOR", "XOR"), ("XNOR", "XNOR"), ("NOR", "NOR")):
            gate = b.add_sub(gate_name, 6 + (bit % 2) * 1.5, 6 - bit * 1.2, f"{op}{bit}")
            b.connect(*source("A", bit), gate, spec(gate_name).in_port("A")[0])
            b.connect(*source("B", bit), gate, spec(gate_name).in_port("B")[0])
            logic_bits[op][bit] = (gate, spec(gate_name).out_port("Y")[0])
        ng = b.add_sub("NAND", 6 + (bit % 2) * 1.5, -13 - bit * 1.2, f"NAND{bit}")
        b.connect(*source("A", bit), ng, spec("NAND").in_port("IN B")[0])
        b.connect(*source("B", bit), ng, spec("NAND").in_port("IN A")[0])
        logic_bits["NAND"][bit] = (ng, spec("NAND").out_port("OUT")[0])
        logic_bits["NOT"][bit] = not_a_bits[bit]

    select_ops = ("ADD", "SUB", "AND", "OR", "XOR", "XNOR", "NAND", "NOR", "NOT")
    result_sources: dict[str, dict[int, tuple[int, int]]] = {op: {} for op in select_ops}
    for bit in range(16):
        result_sources["ADD"][bit] = (add, spec("MISK16_CLA16").out_port(f"S{bit}")[0])
        result_sources["SUB"][bit] = (sub, spec("MISK16_CLA16").out_port(f"S{bit}")[0])
        for op in ("AND", "OR", "XOR", "XNOR", "NAND", "NOR", "NOT"):
            result_sources[op][bit] = logic_bits[op][bit]

    y_bits: dict[int, tuple[int, int]] = {}
    sel_specs = {op: b.input_id[f"SEL_{op}"] for op in select_ops}
    for bit in range(16):
        gated = []
        for op in select_ops:
            gate = b.add_sub("AND", 9, 8 - bit * 1.0 - select_ops.index(op) * 0.3, f"{op}-SEL")
            b.connect(*result_sources[op][bit], gate, spec("AND").in_port("A")[0])
            b.connect(sel_specs[op], 0, gate, spec("AND").in_port("B")[0])
            gated.append((gate, spec("AND").out_port("Y")[0]))
        layer = gated
        while len(layer) > 1:
            nxt = []
            for j in range(0, len(layer), 2):
                if j + 1 == len(layer):
                    nxt.append(layer[j])
                    continue
                gate = b.add_sub("OR", 12, 8 - bit * 1.0 - len(nxt) * 0.35, f"OR-SEL-{bit}")
                b.connect(layer[j][0], layer[j][1], gate, spec("OR").in_port("A")[0])
                b.connect(layer[j + 1][0], layer[j + 1][1], gate, spec("OR").in_port("B")[0])
                nxt.append((gate, spec("OR").out_port("Y")[0]))
            layer = nxt
        y_bits[bit] = layer[0]

    merge_lo = b.add_sub("1-8BIT", 17, 2.0, "Y LO")
    merge_hi = b.add_sub("1-8BIT", 17, -2.0, "Y HI")
    for bit in range(8):
        pin_name = f"IN {'HGFEDCBA'[7 - bit]}"
        # The built-in merge pin order is H..A (MSB..LSB); bit 7 goes to H, bit 0 to A.
        b.connect(y_bits[bit][0], y_bits[bit][1], merge_lo, spec("1-8BIT").in_port(pin_name)[0])
        b.connect(y_bits[bit + 8][0], y_bits[bit + 8][1], merge_hi, spec("1-8BIT").in_port(pin_name)[0])
    b.sub_to_port(merge_lo, "OUT", "Y_LO")
    b.sub_to_port(merge_hi, "OUT", "Y_HI")

    # Carry is meaningful only for ADD/SUB; logic-only selects produce zero carry.
    add_c = b.add_sub("AND", 9, -10, "ADD CARRY")
    sub_c = b.add_sub("AND", 9, -12, "SUB CARRY")
    carry_or = b.add_sub("OR", 12, -11, "CARRY")
    b.sub_to_sub(add, "COUT", add_c, "A")
    b.connect(sel_specs["ADD"], 0, add_c, spec("AND").in_port("B")[0])
    b.sub_to_sub(sub, "COUT", sub_c, "A")
    b.connect(sel_specs["SUB"], 0, sub_c, spec("AND").in_port("B")[0])
    b.sub_to_sub(add_c, "Y", carry_or, "A")
    b.sub_to_sub(sub_c, "Y", carry_or, "B")
    b.sub_to_port(carry_or, "Y", "COUT")

    # Zero is the NOR of all 16 result bits. Negative is result bit 15.
    zero_builder = b.add_sub("ZERO16", 18, 5, "ZERO")
    b.sub_to_sub(merge_lo, "OUT", zero_builder, "LO")
    b.sub_to_sub(merge_hi, "OUT", zero_builder, "HI")
    b.sub_to_port(zero_builder, "ZERO", "ZERO")
    split_y_hi = b.add_sub("8-1BIT", 18, -5, "Y HI bits")
    b.sub_to_sub(merge_hi, "OUT", split_y_hi, "IN")
    # Connect the most significant output bit directly to the NEGATIVE port.
    b.connect(split_y_hi, spec("8-1BIT").out_port("OUT H")[0], b.output_id["NEGATIVE"], 0)
    b.save()


def make_opcode_decoder() -> None:
    operations = ["ADD", "SUB", "AND", "OR", "XOR", "XNOR", "NAND", "NOR", "NOT", "MOV", "LDI", "ADDI", "CMP", "LOAD", "STORE", "JMP", "JZ", "JNZ", "IN", "OUT", "HALT"]
    inputs = [("PREFIX", 4), ("ID_HI", 4), ("ID_MID", 4), ("ID_LO", 4)]
    outputs = [(f"S_{op}", 1) for op in operations] + [("VALID", 1), ("PREFIX_OUT", 4)]
    b = define("OPCODE_DECODER", inputs, outputs, width=22, height=26, colour=(0.43, 0.31, 0.58))
    b.input_to_output("PREFIX", "PREFIX_OUT")
    decoders = []
    for index, nibble in enumerate(("ID_HI", "ID_MID", "ID_LO")):
        dec = b.add_sub("DECODER4TO16", -6 + index * 3, 0, nibble)
        b.port_to_sub(nibble, dec, "NIBBLE")
        decoders.append(dec)
    high_spec = spec("DECODER4TO16")
    selector_signals = []
    opcode_ids = {name: index + 1 for index, name in enumerate(operations)}
    for op in operations:
        opcode = opcode_ids[op]
        hi = (opcode >> 8) & 0xF
        mid = (opcode >> 4) & 0xF
        lo = opcode & 0xF
        and3 = b.add_sub("AND3", 3, 10 - operations.index(op) * 0.85, op)
        for decoder, value, input_name in ((decoders[0], hi, "A0"), (decoders[1], mid, "A1"), (decoders[2], lo, "A2")):
            b.sub_to_sub(decoder, f"D{value:02X}", and3, input_name)
        b.sub_to_port(and3, "Y", f"S_{op}")
        selector_signals.append((and3, spec("AND3").out_port("Y")[0]))
    layer = selector_signals
    while len(layer) > 1:
        nxt = []
        for j in range(0, len(layer), 2):
            if j + 1 == len(layer):
                nxt.append(layer[j])
                continue
            gate = b.add_sub("OR", 8, -5 + len(nxt) * 0.7, "VALID OR")
            b.connect(layer[j][0], layer[j][1], gate, spec("OR").in_port("A")[0])
            b.connect(layer[j + 1][0], layer[j + 1][1], gate, spec("OR").in_port("B")[0])
            nxt.append((gate, spec("OR").out_port("Y")[0]))
        layer = nxt
    b.sub_to_port(layer[0][0], "Y", "VALID")
    b.save()


def make_register_file_manual() -> None:
    inputs = [(f"R{i}_{half}", 8) for i in range(8) for half in ("LO", "HI")]
    inputs += [("READ_A", 4), ("READ_B", 4), ("READ_D", 4), ("WRITE_DEST", 4), ("WRITE_EN", 1), ("WRITE_LO", 8), ("WRITE_HI", 8)]
    outputs = [(f"A_{half}", 8) for half in ("LO", "HI")] + [(f"B_{half}", 8) for half in ("LO", "HI")] + [(f"D_{half}", 8) for half in ("LO", "HI")]
    outputs += [(f"R{i}_NEXT_{half}", 8) for i in range(8) for half in ("LO", "HI")]
    b = define("REGISTER_FILE_MANUAL", inputs, outputs, width=26, height=34, colour=(0.24, 0.5, 0.39))
    for port_name, select_name in (("A", "READ_A"), ("B", "READ_B"), ("D", "READ_D")):
        for half in ("LO", "HI"):
            mux = b.add_sub("MUX8_8", -2, 7 - (len(b.subchips) * 0.7), f"READ {port_name} {half}")
            for i in range(8):
                b.port_to_sub(f"R{i}_{half}", mux, f"D{i}")
            b.port_to_sub(select_name, mux, "SEL")
            b.sub_to_port(mux, "Y", f"{port_name}_{half}")

    decoder = b.add_sub("DECODER4TO16", -7, -10, "WRITE DEST")
    b.port_to_sub("WRITE_DEST", decoder, "NIBBLE")
    for i in range(8):
        enable = b.add_sub("AND", -3, -10 - i * 0.85, f"R{i} write")
        b.sub_to_sub(decoder, f"D{i:02X}", enable, "A")
        b.port_to_sub("WRITE_EN", enable, "B")
        for half in ("LO", "HI"):
            mux = b.add_sub("MUX2_8", 2, -10 - i * 1.6 - (0 if half == "LO" else 0.8), f"R{i} {half} NEXT")
            b.port_to_sub(f"R{i}_{half}", mux, "A")
            b.port_to_sub(f"WRITE_{half}", mux, "B")
            b.sub_to_sub(enable, "Y", mux, "SEL")
            b.sub_to_port(mux, "Y", f"R{i}_NEXT_{half}")
    b.save()


def make_register_file_read() -> None:
    inputs = [(f"R{i}_{half}", 8) for i in range(8) for half in ("LO", "HI")]
    inputs += [("READ_A", 4), ("READ_B", 4), ("READ_D", 4)]
    outputs = [(f"{name}_{half}", 8) for name in ("A", "B", "D") for half in ("LO", "HI")]
    b = define("REGISTER_FILE_READ", inputs, outputs, width=24, height=30, colour=(0.24, 0.5, 0.39))
    for name in ("A", "B", "D"):
        for half in ("LO", "HI"):
            mux = b.add_sub("MUX8_8", 0, 5 - len(b.subchips) * 0.8, f"READ {name} {half}")
            for i in range(8):
                b.port_to_sub(f"R{i}_{half}", mux, f"D{i}")
            b.port_to_sub(f"READ_{name}", mux, "SEL")
            b.sub_to_port(mux, "Y", f"{name}_{half}")
    b.save()


def make_register_file_next() -> None:
    inputs = [(f"R{i}_{half}", 8) for i in range(8) for half in ("LO", "HI")]
    inputs += [("WRITE_DEST", 4), ("WRITE_EN", 1), ("WRITE_LO", 8), ("WRITE_HI", 8)]
    outputs = [(f"R{i}_NEXT_{half}", 8) for i in range(8) for half in ("LO", "HI")]
    b = define("REGISTER_FILE_NEXT", inputs, outputs, width=24, height=30, colour=(0.24, 0.5, 0.39))
    decoder = b.add_sub("DECODER4TO16", -7, 0, "WRITE DEST")
    b.port_to_sub("WRITE_DEST", decoder, "NIBBLE")
    for i in range(8):
        enable = b.add_sub("AND", -3, 5 - i * 1.1, f"R{i} write enable")
        b.sub_to_sub(decoder, f"D{i:02X}", enable, "A")
        b.port_to_sub("WRITE_EN", enable, "B")
        for half in ("LO", "HI"):
            mux = b.add_sub("MUX2_8", 2, 5 - i * 1.4 - (0 if half == "LO" else 0.7), f"R{i} {half} NEXT")
            b.port_to_sub(f"R{i}_{half}", mux, "A")
            b.port_to_sub(f"WRITE_{half}", mux, "B")
            b.sub_to_sub(enable, "Y", mux, "SEL")
            b.sub_to_port(mux, "Y", f"R{i}_NEXT_{half}")
    b.save()


def make_inc8() -> None:
    b = define("INC8", [("IN", 8)], [("OUT", 8)], width=18, height=15, colour=(0.68, 0.39, 0.18))
    split = b.add_sub("8-1BIT", -5, 0, "PC")
    b.port_to_sub("IN", split, "IN")
    split_spec = spec("8-1BIT")
    bit_signals = {bit: (split, split_spec.outputs[7 - bit][2]) for bit in range(8)}
    outputs: dict[int, tuple[int, int]] = {}
    inv = b.add_sub("INV", -2, 3, "~PC0")
    b.connect(*bit_signals[0], inv, spec("INV").in_port("A")[0])
    outputs[0] = (inv, spec("INV").out_port("Y")[0])
    carry_signal: tuple[int, int] | None = bit_signals[0]
    for bit in range(1, 8):
        xor = b.add_sub("XOR", 1, 3 - bit * 0.85, f"PC{bit} XOR carry")
        b.connect(*bit_signals[bit], xor, spec("XOR").in_port("A")[0])
        b.connect(*carry_signal, xor, spec("XOR").in_port("B")[0])
        outputs[bit] = (xor, spec("XOR").out_port("Y")[0])
        if bit < 7:
            and_gate = b.add_sub("AND", -1, -3 - bit * 0.75, f"carry to bit {bit+1}")
            b.connect(*carry_signal, and_gate, spec("AND").in_port("A")[0])
            b.connect(*bit_signals[bit], and_gate, spec("AND").in_port("B")[0])
            carry_signal = (and_gate, spec("AND").out_port("Y")[0])
    merge = b.add_sub("1-8BIT", 5, 0, "OUT")
    for bit in range(8):
        b.connect(*outputs[bit], merge, spec("1-8BIT").in_port(f"IN {'HGFEDCBA'[7 - bit]}")[0])
    b.sub_to_port(merge, "OUT", "OUT")
    b.save()


def make_inc16() -> None:
    b = define("INC16", [("IN_LO", 8), ("IN_HI", 8)], [("OUT_LO", 8), ("OUT_HI", 8)], width=22, height=18, colour=(0.68, 0.39, 0.18))
    splits = {}
    for half, y in (("LO", 2), ("HI", -2)):
        split = b.add_sub("8-1BIT", -7, y, f"IN {half}")
        b.port_to_sub(f"IN_{half}", split, "IN")
        splits[half] = split
    bit_signals = {}
    for bit in range(16):
        half = "LO" if bit < 8 else "HI"
        local = bit % 8
        bit_signals[bit] = (splits[half], spec("8-1BIT").outputs[7 - local][2])
    result = {}
    inv = b.add_sub("INV", -4, 6, "NOT BIT 0")
    b.connect(*bit_signals[0], inv, spec("INV").in_port("A")[0])
    result[0] = (inv, spec("INV").out_port("Y")[0])
    carry = bit_signals[0]
    for bit in range(1, 16):
        xor = b.add_sub("XOR", -1, 7 - bit * 0.75, f"BIT {bit} SUM")
        b.connect(*bit_signals[bit], xor, spec("XOR").in_port("A")[0])
        b.connect(*carry, xor, spec("XOR").in_port("B")[0])
        result[bit] = (xor, spec("XOR").out_port("Y")[0])
        if bit < 15:
            and_gate = b.add_sub("AND", 1, -3 - bit * 0.65, f"CARRY {bit+1}")
            b.connect(*bit_signals[bit], and_gate, spec("AND").in_port("A")[0])
            b.connect(*carry, and_gate, spec("AND").in_port("B")[0])
            carry = (and_gate, spec("AND").out_port("Y")[0])
    for half, start in (("LO", 0), ("HI", 8)):
        merge = b.add_sub("1-8BIT", 6, 2 if half == "LO" else -2, f"OUT {half}")
        for local in range(8):
            b.connect(*result[start + local], merge, spec("1-8BIT").in_port(f"IN {'HGFEDCBA'[7 - local]}")[0])
        b.sub_to_port(merge, "OUT", f"OUT_{half}")
    b.save()


def or_tree(b: ChipBuilder, signals: list[tuple[int, int]], label: str = "OR") -> tuple[int, int]:
    layer = signals
    counter = 0
    while len(layer) > 1:
        nxt = []
        for j in range(0, len(layer), 2):
            if j + 1 == len(layer):
                nxt.append(layer[j])
                continue
            gate = b.add_sub("OR", 4 + (counter % 5) * 0.75, 2 - (counter // 5) * 0.55, label)
            b.connect(layer[j][0], layer[j][1], gate, spec("OR").in_port("A")[0])
            b.connect(layer[j + 1][0], layer[j + 1][1], gate, spec("OR").in_port("B")[0])
            nxt.append((gate, spec("OR").out_port("Y")[0]))
            counter += 1
        layer = nxt
    return layer[0]


def make_result_mux5_8() -> None:
    names = ["ALU", "MOV", "LDI", "LOAD", "IN"]
    inputs = [(f"{name}_DATA", 8) for name in names] + [(f"SEL_{name}", 1) for name in names]
    b = define("RESULT_MUX5_8", inputs, [("Y", 8)], width=20, height=16, colour=(0.54, 0.4, 0.2))
    splits = {}
    for i, name in enumerate(names):
        split = b.add_sub("8-1BIT", -7, 5 - i * 2.0, name)
        b.port_to_sub(f"{name}_DATA", split, "IN")
        splits[name] = split
    outputs = {}
    for bit in range(8):
        terms = []
        for i, name in enumerate(names):
            gate = b.add_sub("AND", -1, 5 - bit * 0.8 - i * 0.2, f"{name} select")
            b.connect(splits[name], spec("8-1BIT").outputs[7 - bit][2], gate, spec("AND").in_port("A")[0])
            b.port_to_sub(f"SEL_{name}", gate, "B")
            terms.append((gate, spec("AND").out_port("Y")[0]))
        outputs[bit] = or_tree(b, terms, "RESULT OR")
    merge = b.add_sub("1-8BIT", 8, 0, "Y")
    for bit, signal in outputs.items():
        b.connect(signal[0], signal[1], merge, spec("1-8BIT").in_port(f"IN {'HGFEDCBA'[7 - bit]}")[0])
    b.sub_to_port(merge, "OUT", "Y")
    b.save()


def make_cpu_step() -> None:
    inputs = [("TAG_PREFIX", 4), ("OP_ID_HI", 4), ("OP_ID_MID", 4), ("OP_ID_LO", 4)]
    inputs += [(f"R{i}_{half}", 8) for i in range(8) for half in ("LO", "HI")]
    inputs += [("RA", 4), ("RB", 4), ("RD", 4)]
    inputs += [("IMM_LO", 8), ("IMM_HI", 8), ("DATA_READ_LO", 8), ("DATA_READ_HI", 8), ("INPUT_LO", 8), ("INPUT_HI", 8)]
    inputs += [("PC", 8), ("BRANCH_TARGET", 8), ("FLAG_Z", 1), ("FLAG_N", 1), ("FLAG_C", 1)]
    outputs = [("TAG_PREFIX_OUT", 4)]
    outputs += [(f"R{i}_NEXT_{half}", 8) for i in range(8) for half in ("LO", "HI")]
    outputs += [("PC_NEXT", 8), ("BRANCH_TAKEN", 1), ("VALID", 1), ("HALT", 1)]
    outputs += [("REG_WRITE_EN", 1), ("REG_WRITE_DEST", 4), ("EXEC_LO", 8), ("EXEC_HI", 8)]
    outputs += [("FLAG_WRITE_EN", 1), ("FLAG_Z_NEXT", 1), ("FLAG_N_NEXT", 1), ("FLAG_C_NEXT", 1)]
    outputs += [("MEM_READ_EN", 1), ("MEM_WRITE_EN", 1), ("MEM_ADDR_LO", 8), ("MEM_ADDR_HI", 4), ("MEM_WRITE_LO", 8), ("MEM_WRITE_HI", 8)]
    outputs += [("OUT_EN", 1), ("OUT_LO", 8), ("OUT_HI", 8)]
    b = define("MISK16_CPU_STEP", inputs, outputs, width=32, height=56, colour=(0.2, 0.42, 0.66))

    dec = b.add_sub("OPCODE_DECODER", -12, 0, "12-bit OPCODE")
    for top_name, decoder_name in (("TAG_PREFIX", "PREFIX"), ("OP_ID_HI", "ID_HI"), ("OP_ID_MID", "ID_MID"), ("OP_ID_LO", "ID_LO")):
        b.port_to_sub(top_name, dec, decoder_name)
    b.sub_to_port(dec, "PREFIX_OUT", "TAG_PREFIX_OUT")
    b.sub_to_port(dec, "VALID", "VALID")

    reg_read = b.add_sub("REGISTER_FILE_READ", -3, 5, "REGISTER READ PORTS")
    reg_next = b.add_sub("REGISTER_FILE_NEXT", -3, -5, "MANUAL NEXT-STATE")
    register_inputs = [f"R{i}_{half}" for i in range(8) for half in ("LO", "HI")]
    for p in register_inputs:
        b.port_to_sub(p, reg_read, p)
        b.port_to_sub(p, reg_next, p)
    for top_name, child_name in (("RA", "READ_A"), ("RB", "READ_B"), ("RD", "READ_D")):
        b.port_to_sub(top_name, reg_read, child_name)
    for i in range(8):
        for half in ("LO", "HI"):
            b.sub_to_port(reg_next, f"R{i}_NEXT_{half}", f"R{i}_NEXT_{half}")

    # Opcode selection helpers.
    def sel(op: str) -> tuple[int, int]:
        return (dec, spec("OPCODE_DECODER").out_port(f"S_{op}")[0])
    def add_or(name: str, ops: list[str], y: float) -> tuple[int, int]:
        signals = [sel(op) for op in ops]
        sig = or_tree(b, signals, name)
        return sig

    # Read the selected register operands. NOT uses RD as its source; other ops use RA.
    not_sel = sel("NOT")
    a_lo = b.add_sub("MUX2_8", -5, 6, "A / NOT destination")
    a_hi = b.add_sub("MUX2_8", -5, 3.5, "A / NOT destination")
    for half, mux in (("LO", a_lo), ("HI", a_hi)):
        b.sub_to_sub(reg_read, f"A_{half}", mux, "A")
        b.sub_to_sub(reg_read, f"D_{half}", mux, "B")
        b.connect(not_sel[0], not_sel[1], mux, spec("MUX2_8").in_port("SEL")[0])
    b_lo = b.add_sub("MUX2_8", -5, 0, "B / ADDI immediate")
    b_hi = b.add_sub("MUX2_8", -5, -2.5, "B / ADDI immediate")
    addi_sel = sel("ADDI")
    for half, mux in (("LO", b_lo), ("HI", b_hi)):
        b.sub_to_sub(reg_read, f"B_{half}", mux, "A")
        b.port_to_sub(f"IMM_{half}", mux, "B")
        b.connect(addi_sel[0], addi_sel[1], mux, spec("MUX2_8").in_port("SEL")[0])

    # ALU control selects ADD for ADD/ADDI and SUB for SUB/CMP.
    add_control = add_or("ADD OR ADDI", ["ADD", "ADDI"], -1)
    sub_control = add_or("SUB OR CMP", ["SUB", "CMP"], -2)
    alu = b.add_sub("ALU16", 4, 4, "16-BIT ALU")
    for half, mux in (("LO", a_lo), ("HI", a_hi)):
        b.sub_to_sub(mux, "Y", alu, f"A_{half}")
    for half, mux in (("LO", b_lo), ("HI", b_hi)):
        b.sub_to_sub(mux, "Y", alu, f"B_{half}")
    for op in ("ADD", "SUB", "AND", "OR", "XOR", "XNOR", "NAND", "NOR", "NOT"):
        signal = add_control if op == "ADD" else sub_control if op == "SUB" else sel(op)
        b.connect(signal[0], signal[1], alu, spec("ALU16").in_port(f"SEL_{op}")[0])

    alu_result_ops = ["ADD", "SUB", "AND", "OR", "XOR", "XNOR", "NAND", "NOR", "NOT", "ADDI", "CMP"]
    alu_result_sel = add_or("ALU RESULT SELECT", alu_result_ops, -4)
    result_muxes = []
    for half in ("LO", "HI"):
        mux = b.add_sub("RESULT_MUX5_8", 9, 5 if half == "LO" else -5, f"RESULT {half}")
        for source_name, source_ref in (
            ("ALU", (alu, f"Y_{half}")),
            ("MOV", (reg_read, f"A_{half}")),
            ("LDI", ("input", f"IMM_{half}")),
            ("LOAD", ("input", f"DATA_READ_{half}")),
            ("IN", ("input", f"INPUT_{half}")),
        ):
            if source_ref[0] == "input":
                b.port_to_sub(source_ref[1], mux, f"{source_name}_DATA")
            else:
                b.sub_to_sub(source_ref[0], source_ref[1], mux, f"{source_name}_DATA")
        for source_name, signal in (("ALU", alu_result_sel), ("MOV", sel("MOV")), ("LDI", sel("LDI")), ("LOAD", sel("LOAD")), ("IN", sel("IN"))):
            b.connect(signal[0], signal[1], mux, spec("RESULT_MUX5_8").in_port(f"SEL_{source_name}")[0])
        b.sub_to_port(mux, "Y", f"EXEC_{half}")
        result_muxes.append(mux)

    # Register write enable excludes CMP, stores, branches, OUT and HALT.
    reg_write_ops = ["ADD", "SUB", "AND", "OR", "XOR", "XNOR", "NAND", "NOR", "NOT", "MOV", "LDI", "ADDI", "LOAD", "IN"]
    reg_write = add_or("REGISTER WRITE ENABLE", reg_write_ops, -6)
    b.connect(reg_write[0], reg_write[1], b.output_id["REG_WRITE_EN"], 0)
    b.input_to_output("RD", "REG_WRITE_DEST")
    for half in ("LO", "HI"):
        b.sub_to_sub(result_muxes[0 if half == "LO" else 1], "Y", reg_next, f"WRITE_{half}")
    b.connect(reg_write[0], reg_write[1], reg_next, spec("REGISTER_FILE_NEXT").in_port("WRITE_EN")[0])
    b.port_to_sub("RD", reg_next, "WRITE_DEST")

    # Flag update / next values. CMP writes flags but does not write a register.
    flag_write_ops = reg_write_ops + ["CMP"]
    flag_write = add_or("FLAGS WRITE ENABLE", flag_write_ops, -8)
    b.connect(flag_write[0], flag_write[1], b.output_id["FLAG_WRITE_EN"], 0)
    zero = b.add_sub("ZERO16", 14, 4, "RESULT ZERO")
    b.sub_to_sub(result_muxes[0], "Y", zero, "LO")
    b.sub_to_sub(result_muxes[1], "Y", zero, "HI")
    # Result sign is the high bit of EXEC_HI (split output H).
    sign_split = b.add_sub("8-1BIT", 14, -1, "RESULT HI BITS")
    b.sub_to_sub(result_muxes[1], "Y", sign_split, "IN")
    for flag_name, computed_owner, computed_pin in (
        ("Z", zero, spec("ZERO16").out_port("ZERO")[0]),
        ("N", sign_split, spec("8-1BIT").out_port("OUT H")[0]),
        ("C", alu, spec("ALU16").out_port("COUT")[0]),
    ):
        mux = b.add_sub("MUX2_1", 18, -1.5 + ("ZNC".index(flag_name) * 1.5), f"FLAG {flag_name}")
        b.port_to_sub(f"FLAG_{flag_name}", mux, "A")
        b.connect(computed_owner, computed_pin, mux, spec("MUX2_1").in_port("B")[0])
        b.connect(flag_write[0], flag_write[1], mux, spec("MUX2_1").in_port("SEL")[0])
        b.sub_to_port(mux, "Y", f"FLAG_{flag_name}_NEXT")

    # Data RAM and OUT are explicit external interfaces; storage is not simulated here.
    b.sub_to_port(reg_read, "A_LO", "MEM_ADDR_LO")
    a_hi_split = b.add_sub("8-1BIT", 13, -6, "A high nibble")
    b.sub_to_sub(reg_read, "A_HI", a_hi_split, "IN")
    mem_addr_merge = b.add_sub("1-4BIT", 17, -7, "MEM ADDR HI")
    for idx, out_name in enumerate(("OUT D", "OUT C", "OUT B", "OUT A")):
        # A_HI[3:0] are outputs E..H of the 8-to-1 splitter (positions 4..7).
        bit_out = spec("8-1BIT").outputs[idx + 4][2]
        target = spec("1-4BIT").in_port(f"IN {'DCBA'[idx]}")[0]
        b.connect(a_hi_split, bit_out, mem_addr_merge, target)
    b.sub_to_port(mem_addr_merge, "OUT", "MEM_ADDR_HI")
    b.sub_to_port(reg_read, "B_LO", "MEM_WRITE_LO")
    b.sub_to_port(reg_read, "B_HI", "MEM_WRITE_HI")
    b.sub_to_port(reg_read, "A_LO", "OUT_LO")
    b.sub_to_port(reg_read, "A_HI", "OUT_HI")
    for name, op in (("MEM_READ_EN", "LOAD"), ("MEM_WRITE_EN", "STORE"), ("OUT_EN", "OUT"), ("HALT", "HALT")):
        signal = sel(op)
        b.connect(signal[0], signal[1], b.output_id[name], 0)

    # Program counter is an externally edited 8-bit value; next value is combinational.
    inc = b.add_sub("INC8", 7, -10, "PC + 1")
    b.port_to_sub("PC", inc, "IN")
    is_jmp = sel("JMP")
    jz_and = b.add_sub("AND", 8, -13, "JZ & Z")
    b.connect(*sel("JZ"), jz_and, spec("AND").in_port("A")[0])
    b.port_to_sub("FLAG_Z", jz_and, "B")
    not_z = b.add_sub("INV", 8, -15, "NOT Z")
    b.port_to_sub("FLAG_Z", not_z, "A")
    jnz_and = b.add_sub("AND", 10, -15, "JNZ & NOT Z")
    b.connect(*sel("JNZ"), jnz_and, spec("AND").in_port("A")[0])
    b.sub_to_sub(not_z, "Y", jnz_and, "B")
    branch = b.add_sub("OR", 12, -13, "JZ or JNZ")
    b.sub_to_sub(jz_and, "Y", branch, "A")
    b.sub_to_sub(jnz_and, "Y", branch, "B")
    branch_all = b.add_sub("OR", 14, -13, "JMP or conditional")
    b.connect(*is_jmp, branch_all, spec("OR").in_port("A")[0])
    b.sub_to_sub(branch, "Y", branch_all, "B")
    b.sub_to_port(branch_all, "Y", "BRANCH_TAKEN")
    pc_mux = b.add_sub("MUX2_8", 18, -10, "PC NEXT")
    b.sub_to_sub(inc, "OUT", pc_mux, "A")
    b.port_to_sub("BRANCH_TARGET", pc_mux, "B")
    b.sub_to_sub(branch_all, "Y", pc_mux, "SEL")
    b.sub_to_port(pc_mux, "Y", "PC_NEXT")

    b.save()


def make_computer() -> None:
    """Assemble a clocked CPU panel with raw-NAND state, reset/step keys, and displays."""
    cpu = spec("MISK16_CPU_STEP")
    inputs = [(name, bits) for name, bits, _pin in cpu.inputs]
    state_bytes = [f"R{i}_{half}" for i in range(8) for half in ("LO", "HI")] + ["PC"]
    state_flags = ["FLAG_Z", "FLAG_N", "FLAG_C"]
    state_input_names = set(state_bytes + state_flags)
    outputs = [(name, bits) for name, bits, _pin in cpu.outputs]
    outputs += [(f"{name}_CURRENT", 8) for name in state_bytes]
    outputs += [(f"{name}_CURRENT", 1) for name in state_flags]
    outputs += [(f"HEX_DIGIT_{digit}", 4) for digit in range(4)]
    outputs += [(f"HEX_SEG_D{digit}_{segment.upper()}", 1) for digit in range(4) for segment in "abcdefg"]
    outputs += [(f"PC_HEX_DIGIT_{digit}", 4) for digit in range(2)]
    outputs += [(f"PC_HEX_SEG_D{digit}_{segment.upper()}", 1) for digit in range(2) for segment in "abcdefg"]
    b = define("MISK16_COMPUTER", [], outputs, width=230, height=125, colour=(0.17, 0.29, 0.43))
    cpu_id = b.add_sub("MISK16_CPU_STEP", -2, 2, "MISK-16 COMBINATIONAL EXECUTE DATAPATH")

    # Instruction and external-memory/I/O data remain editable input interfaces.
    # Registers, flags, and PC are held in clocked NAND-gate state below.
    for index, (name, bits) in enumerate(inputs):
        if name in state_input_names:
            continue
        input_chip = {1: "IN-1", 4: "IN-4", 8: "IN-8"}[bits]
        x = -47 + (index // 18) * 4
        y = 34 - (index % 18) * 3.5
        input_port = b.add_sub(input_chip, x, y, name)
        b.connect(input_port, spec(input_chip).out_port("OUT")[0], cpu_id, cpu.input_ids[name])

    # DLS clock and keyboard controls. Key 0 synchronously resets state; key 2 steps once.
    clock = b.add_sub("CLOCK", -47, -38, "CPU CLOCK · RESUME SIMULATION")
    clock_out = (clock, spec("CLOCK").out_port("CLK")[0])
    reset_key = b.add_sub("KEY", -43, -38, "RESET PC / REGISTERS · 0", [ord("0")])
    reset = (reset_key, spec("KEY").out_port("OUT")[0])
    step_key = b.add_sub("KEY", -39, -38, "STEP ONE INSTRUCTION · 2", [ord("2")])
    step_level = (step_key, spec("KEY").out_port("OUT")[0])

    raw_gate_index = 0
    inv_cache: dict[tuple[int, int], tuple[int, int]] = {}

    def raw_gate(label: str) -> int:
        nonlocal raw_gate_index
        column = raw_gate_index % 24
        row = raw_gate_index // 24
        raw_gate_index += 1
        return b.add_sub("NAND", 60 + column * 1.45, 39 - row * 1.2, label)

    def raw_nand(a: tuple[int, int], other: tuple[int, int], label: str) -> tuple[int, int]:
        owner = raw_gate(label)
        b.connect(a[0], a[1], owner, spec("NAND").in_port("IN A")[0])
        b.connect(other[0], other[1], owner, spec("NAND").in_port("IN B")[0])
        return owner, spec("NAND").out_port("OUT")[0]

    def inv(signal: tuple[int, int], label: str = "NOT") -> tuple[int, int]:
        if signal not in inv_cache:
            inv_cache[signal] = raw_nand(signal, signal, label)
        return inv_cache[signal]

    def and2(a: tuple[int, int], other: tuple[int, int], label: str = "AND") -> tuple[int, int]:
        return inv(raw_nand(a, other, f"{label} NAND"), f"{label} INV")

    def or2(a: tuple[int, int], other: tuple[int, int], label: str = "OR") -> tuple[int, int]:
        return raw_nand(inv(a, f"{label} A BAR"), inv(other, f"{label} B BAR"), label)

    def mux2(select: tuple[int, int], hold: tuple[int, int], new_value: tuple[int, int], label: str) -> tuple[int, int]:
        held = raw_nand(hold, inv(select, f"{label} STEP BAR"), f"{label} HOLD")
        loaded = raw_nand(new_value, select, f"{label} LOAD")
        return raw_nand(held, loaded, f"{label} MUX")

    clock_bar = inv(clock_out, "CLOCK BAR")

    def latch(data: tuple[int, int], enable: tuple[int, int], label: str) -> tuple[int, int]:
        data_bar = inv(data, f"{label} DATA BAR")
        set_bar = raw_nand(data, enable, f"{label} SET BAR")
        reset_bar = raw_nand(data_bar, enable, f"{label} RESET BAR")
        q_gate = raw_gate(f"{label} Q")
        qb_gate = raw_gate(f"{label} Q BAR")
        q = (q_gate, spec("NAND").out_port("OUT")[0])
        qb = (qb_gate, spec("NAND").out_port("OUT")[0])
        b.connect(set_bar[0], set_bar[1], q_gate, spec("NAND").in_port("IN A")[0])
        b.connect(qb[0], qb[1], q_gate, spec("NAND").in_port("IN B")[0])
        b.connect(reset_bar[0], reset_bar[1], qb_gate, spec("NAND").in_port("IN A")[0])
        b.connect(q[0], q[1], qb_gate, spec("NAND").in_port("IN B")[0])
        return q, qb

    def dff_placeholder(label: str) -> dict:
        """Master/slave DFF from NAND latches; connect D after Q is available."""
        dbar_gate = raw_gate(f"{label} D BAR")
        dbar = (dbar_gate, spec("NAND").out_port("OUT")[0])
        setbar_gate = raw_gate(f"{label} MASTER SET BAR")
        b.connect(clock_bar[0], clock_bar[1], setbar_gate, spec("NAND").in_port("IN B")[0])
        reset_bar = raw_nand(dbar, clock_bar, f"{label} MASTER RESET BAR")
        master_q_gate = raw_gate(f"{label} MASTER Q")
        master_qbar_gate = raw_gate(f"{label} MASTER Q BAR")
        master_q = (master_q_gate, spec("NAND").out_port("OUT")[0])
        master_qbar = (master_qbar_gate, spec("NAND").out_port("OUT")[0])
        b.connect(setbar_gate, spec("NAND").out_port("OUT")[0], master_q_gate, spec("NAND").in_port("IN A")[0])
        b.connect(master_qbar[0], master_qbar[1], master_q_gate, spec("NAND").in_port("IN B")[0])
        b.connect(reset_bar[0], reset_bar[1], master_qbar_gate, spec("NAND").in_port("IN A")[0])
        b.connect(master_q[0], master_q[1], master_qbar_gate, spec("NAND").in_port("IN B")[0])
        slave_q, _slave_qbar = latch(master_q, clock_out, f"{label} SLAVE")
        return {"q": slave_q, "dbar_gate": dbar_gate, "setbar_gate": setbar_gate, "label": label}

    def set_dff_data(dff: dict, data: tuple[int, int]) -> None:
        b.connect(data[0], data[1], dff["dbar_gate"], spec("NAND").in_port("IN B")[0])
        b.connect(data[0], data[1], dff["dbar_gate"], spec("NAND").in_port("IN A")[0])
        b.connect(data[0], data[1], dff["setbar_gate"], spec("NAND").in_port("IN A")[0])

    def one_bit_dff(data: tuple[int, int], label: str) -> tuple[int, int]:
        dff = dff_placeholder(label)
        set_dff_data(dff, data)
        return dff["q"]

    # One clock edge per held KEY 2 press (release before the next instruction).
    step_previous = one_bit_dff(step_level, "STEP KEY HISTORY")
    step_event = and2(step_level, inv(step_previous, "STEP HISTORY BAR"), "STEP EDGE")
    reset_bar = inv(reset, "RESET BAR")

    # Allocate every CPU state bit before wiring its next-state logic.
    state_ffs: dict[str, list[dict]] = {}
    state_q: dict[str, list[tuple[int, int]]] = {}
    for name in state_bytes:
        state_ffs[name] = [dff_placeholder(f"{name} BIT {bit}") for bit in range(8)]
        state_q[name] = [item["q"] for item in state_ffs[name]]
    for name in state_flags:
        state_ffs[name] = [dff_placeholder(f"{name} STATE")]
        state_q[name] = [state_ffs[name][0]["q"]]

    # Feed current state into the execute core and expose it as named outputs/probes.
    state_owners: dict[str, tuple[int, int]] = {}
    for index, name in enumerate(state_bytes):
        merge = b.add_sub("1-8BIT", 48, 34 - index * 2.2, f"{name} CURRENT")
        for bit, signal in enumerate(state_q[name]):
            pin = spec("1-8BIT").in_port(f"IN {'HGFEDCBA'[7 - bit]}")[0]
            b.connect(signal[0], signal[1], merge, pin)
        merged = (merge, spec("1-8BIT").out_port("OUT")[0])
        state_owners[name] = merged
        b.connect(merged[0], merged[1], cpu_id, cpu.input_ids[name])
        output_name = f"{name}_CURRENT"
        b.connect(merged[0], merged[1], b.output_id[output_name], 0)
        probe = b.add_sub("OUT-8", 45, 0, output_name)
        b.connect(merged[0], merged[1], probe, spec("OUT-8").in_port("IN")[0])

    for name in state_flags:
        signal = state_q[name][0]
        state_owners[name] = signal
        b.connect(signal[0], signal[1], cpu_id, cpu.input_ids[name])
        output_name = f"{name}_CURRENT"
        b.connect(signal[0], signal[1], b.output_id[output_name], 0)
        probe = b.add_sub("OUT-1", 45, -2 - state_flags.index(name) * 1.2, output_name)
        b.connect(signal[0], signal[1], probe, spec("OUT-1").in_port("IN")[0])

    # State updates are synchronous and reset-dominant. PC_NEXT already handles branches.
    for name in state_bytes:
        next_name = "PC_NEXT" if name == "PC" else f"{name.rsplit('_', 1)[0]}_NEXT_{name.rsplit('_', 1)[1]}"
        split = b.add_sub("8-1BIT", 48, 34 - state_bytes.index(name) * 2.2 - 1.0, f"{name} NEXT")
        b.connect(cpu_id, cpu.output_ids[next_name], split, spec("8-1BIT").in_port("IN")[0])
        for bit, dff in enumerate(state_ffs[name]):
            next_bit = (split, spec("8-1BIT").outputs[7 - bit][2])
            selected = mux2(step_event, state_q[name][bit], next_bit, f"{name} BIT {bit}")
            reset_value = and2(reset_bar, selected, f"{name} RESET {bit}")
            set_dff_data(dff, reset_value)
    for name in state_flags:
        next_name = f"{name}_NEXT"
        next_value = (cpu_id, cpu.output_ids[next_name])
        selected = mux2(step_event, state_q[name][0], next_value, f"{name} STEP")
        reset_value = and2(reset_bar, selected, f"{name} RESET")
        set_dff_data(state_ffs[name][0], reset_value)

    # Keep readable probes inside the computer and expose all combinational CPU outputs.
    for name, bits, pin_id in cpu.outputs:
        probe = b.add_sub({1: "OUT-1", 4: "OUT-4", 8: "OUT-8"}[bits], 45, 0, name)
        target_pin = spec({1: "OUT-1", 4: "OUT-4", 8: "OUT-8"}[bits]).in_port("IN")[0]
        b.connect(cpu_id, pin_id, probe, target_pin)
        b.connect(cpu_id, pin_id, b.output_id[name], 0)

    # A constant-zero 8-bit word is formed from a signal and its complement.
    reset_not = inv(reset, "SCREEN RESET BAR")
    logic_zero = and2(reset, reset_not, "SCREEN LOGIC ZERO")
    zero_bus = b.add_sub("1-8BIT", 48, -11, "PC HEX HIGH BYTE ZERO")
    for bit in range(8):
        b.connect(logic_zero[0], logic_zero[1], zero_bus, spec("1-8BIT").in_port(f"IN {'HGFEDCBA'[7 - bit]}")[0])

    hex_display = b.add_sub("HEX_DISPLAY16", 21, -23, "EXEC RESULT · HEX")
    b.sub_to_sub(cpu_id, "EXEC_LO", hex_display, "WORD_LO")
    b.sub_to_sub(cpu_id, "EXEC_HI", hex_display, "WORD_HI")
    pc_display = b.add_sub("HEX_DISPLAY16", 21, -38, "PROGRAM COUNTER · HEX")
    b.connect(state_owners["PC"][0], state_owners["PC"][1], pc_display, spec("HEX_DISPLAY16").in_port("WORD_LO")[0])
    b.connect(zero_bus, spec("1-8BIT").out_port("OUT")[0], pc_display, spec("HEX_DISPLAY16").in_port("WORD_HI")[0])

    display_probe_index = 0
    for display_name, display_owner, digit_indices, y in (
        ("EXEC", hex_display, range(4), 20),
        ("PC", pc_display, range(2), 12),
    ):
        for digit in digit_indices:
            digit_name = f"{display_name}_HEX_DIGIT_{digit}"
            probe = b.add_sub("OUT-4", 45, -18 - display_probe_index * 1.2, digit_name)
            display_probe_index += 1
            b.sub_to_sub(display_owner, f"DIGIT_{digit}", probe, "IN")
            b.sub_to_port(display_owner, f"DIGIT_{digit}", f"HEX_DIGIT_{digit}" if display_name == "EXEC" else digit_name)
            screen = b.add_sub("7-SEGMENT", 40 + digit * 3.2, y, f"{display_name} DISPLAY DIGIT {digit}")
            for segment in "abcdefg":
                segment_name = f"SEG_D{digit}_{segment.upper()}"
                b.sub_to_sub(display_owner, segment_name, screen, segment.upper())
                if display_name == "EXEC":
                    root_name = f"HEX_SEG_D{digit}_{segment.upper()}"
                    b.sub_to_port(display_owner, segment_name, root_name)
                else:
                    root_name = f"PC_HEX_SEG_D{digit}_{segment.upper()}"
                    b.sub_to_port(display_owner, segment_name, root_name)
            b.connect(logic_zero[0], logic_zero[1], screen, spec("7-SEGMENT").in_port("COL")[0])
            b.displays.append({"SubChipID": screen, "Position": pos(40 + digit * 3.2, y), "Scale": 2.0})

    # Keep output probe chips in separated rows; screen and state chips remain readable.
    probe_children = [child for child in b.subchips if child["Name"].startswith("OUT-")]
    for index, child in enumerate(probe_children):
        child["Position"] = pos(98 + (index // 28) * 4, 36 - (index % 28) * 2.7)
    b.width = 230
    b.height = max(125, 45 + math.ceil(raw_gate_index / 24) * 1.2)
    b.save()


def make_testbench() -> None:
    """Legacy collection name kept as a thin alias for older project instructions."""
    b = define("MISK16_TESTBENCH", [], [], width=36, height=20, colour=(0.17, 0.29, 0.43))
    b.add_sub("MISK16_COMPUTER", 0, 0, "OPEN THE CENTRAL MISK-16 COMPUTER")
    b.save()


def make_project_description() -> None:
    custom_names = list(_descriptions.keys())
    collections = [
        {"Name": "00 · Open this first", "Chips": ["MISK16_COMPUTER", "MISK16_CPU_STEP", "MISK16_TESTBENCH"], "IsToggledOpen": True},
        {"Name": "01 · Logic gates", "Chips": ["INV", "AND", "OR", "XOR", "XNOR", "NOR", "AND3", "AND4", "OR_REDUCE8", "AND16", "OR16", "XOR16", "XNOR16", "NAND16", "NOR16", "NOT16"], "IsToggledOpen": False},
        {"Name": "02 · Arithmetic and compare", "Chips": ["HALF_ADDER_1", "FULL_ADDER_1", "ADDER_1", "ADDER_2", "ADDER_4", "ADDER_8", "ADDER_16", "MISK16_CLA16", "ADD16", "SUB16", "INC8", "INC16", "COMPARE16", "ZERO16", "ALU16"], "IsToggledOpen": False},
        {"Name": "03 · Multiplexers and data routing", "Chips": ["MUX2_1", "MUX2_8", "MUX2_16", "MUX8_1", "MUX8_8", "MUX8_16", "RESULT_MUX5_8"], "IsToggledOpen": False},
        {"Name": "04 · CPU core and interfaces", "Chips": ["OPCODE_DECODER", "REGISTER_FILE_READ", "REGISTER_FILE_NEXT", "REGISTER_FILE_MANUAL", "INC8", "MISK16_CPU_STEP"], "IsToggledOpen": False},
        {"Name": "05 · Decode and displays", "Chips": ["DECODER4TO16", "ENCODER16TO4", "HEX7SEG", "HEX_DISPLAY16"], "IsToggledOpen": False},
    ]
    now = datetime.now(timezone.utc).astimezone().isoformat(timespec="milliseconds")
    description = {
        "ProjectName": PROJECT.name,
        "DLSVersion_LastSaved": DLS_VERSION,
        "DLSVersion_EarliestCompatible": EARLIEST_VERSION,
        "CreationTime": now,
        "LastSaveTime": now,
        "Prefs_MainPinNamesDisplayMode": 1,
        "Prefs_ChipPinNamesDisplayMode": 1,
        "Prefs_GridDisplayMode": 1,
        "Prefs_Snapping": 1,
        "Prefs_StraightWires": 1,
        "Prefs_SimPaused": True,
        "Prefs_SimTargetStepsPerSecond": 10000,
        "Prefs_SimStepsPerClockTick": 3,
        "AllCustomChipNames": custom_names,
        "StarredList": [{"Name": "00 · Open this first", "IsCollection": True}],
        "ChipCollections": collections,
    }
    (PROJECT / "ProjectDescription.json").write_text(json.dumps(description, indent=2) + "\n", encoding="utf-8")


def build() -> None:
    if PROJECT.exists():
        shutil.rmtree(PROJECT)
    CHIPS_DIR.mkdir(parents=True, exist_ok=True)

    make_inv()
    make_and()
    make_or()
    make_xor()
    make_xnor()
    make_nor()
    make_and3_and4()
    make_and4()  # AND4 is used by the nibble decoder.
    make_or_reduce8()
    make_decoder4to16()
    make_encoder16to4()
    make_hex7seg()
    make_full_adder()
    for width in (1, 2, 4, 8, 16):
        make_adder(width)
    make_mux2_1()
    make_mux2_8()
    make_mux8_1()
    make_mux8_8()
    make_zero16()
    make_fast_cla16()
    make_alu16()
    make_opcode_decoder()
    make_register_file_manual()
    make_register_file_read()
    make_register_file_next()
    make_inc8()
    make_result_mux5_8()
    make_cpu_step()

    # Optional reusable building blocks are generated after the original core so
    # existing DLS pin/chip IDs remain stable as the library grows.
    make_word_logic_chips()
    make_half_adder()
    make_add16()
    make_sub16()
    make_mux2_16()
    make_mux8_16()
    make_inc16()
    make_compare16()
    make_hex_display16()
    make_computer()
    make_testbench()

    for name, description in _descriptions.items():
        (CHIPS_DIR / f"{name}.json").write_text(json.dumps(description, indent=2) + "\n", encoding="utf-8")
    make_project_description()

    readme = """# MISK-16 clocked CPU in Digital Logic Sim 2.1.6

This is a native-format DLS project directory. Copy the whole `MISK16-DLS` folder into the DLS user-data `Projects` directory, restart/refresh DLS, and open the `MISK16-DLS` project. In **00 · Open this first**, open **MISK16_COMPUTER**. Use DLS's normal Save command after opening it.

## Clocked central computer

`MISK16_COMPUTER` combines the `MISK16_CPU_STEP` datapath/control core, NAND-built state, editable labeled DLS IN chips for the instruction and external memory/I/O interfaces, named output probes, a four-digit execution-result display, and a two-digit PC display. The top panel exposes current state and CPU outputs as custom-chip pins. `MISK16_TESTBENCH` remains as a backwards-compatible alias.

- **Start/resume DLS simulation** to run the `CLOCK` source.
- Press **0** for synchronous reset. Hold it until a rising clock edge clears the 8-bit PC, eight 16-bit registers, and Z/N/C flags.
- Press and release **2** to execute one instruction. The NAND-built edge detector prevents a held key from stepping repeatedly; release is sampled on a clock edge before the next press.
- Instruction/tag/operand, input data, and external data-memory read-word chips are still manually editable. There is no on-chip program ROM or data RAM; `MEM_READ_EN`, `MEM_WRITE_EN`, `MEM_ADDR_*`, and `MEM_WRITE_*` remain explicit external-memory signals.

The storage cells are 139 master/slave DFFs built from 1,390 individual NAND gates (PC + register file + flags), plus one NAND-built step-key-history DFF. The full top panel contains 2,103 NAND gates. No prebuilt DLS DFF/register/ALU/mux/RAM/ROM component is used; the custom CPU/ALU/mux modules are composed from primitive NAND gates. Built-in split/join components only adapt pin widths; DLS IN/OUT chips are manual interfaces. The only functional clock/control/display components are one `CLOCK`, two `KEY`s, and six `7-SEGMENT` displays.

## Faster ALU adder

The `ALU16` ADD and SUB paths use `MISK16_CLA16`, a 16-bit Kogge–Stone carry-lookahead network composed of raw NAND gates. Four parallel-prefix stages compute group propagate/generate signals at distances 1, 2, 4, and 8, reducing carry depth from a serial 16-bit ripple chain to logarithmic prefix depth. The reusable hierarchical ripple adder remains available as `ADDER_1/2/4/8/16` for comparison; the ALU uses the faster prefix block.

## Try a program

First reset with **0**. To load R1=5, set `OP_ID_HI=0`, `OP_ID_MID=0`, `OP_ID_LO=11` (LDI), `RD=1`, `IMM_LO=5`, and `IMM_HI=0`; press/release **2**. Change `RD=2`, `IMM_LO=7`, then press/release **2** again. For `ADD R0, R1, R2`, set `OP_ID_LO=1`, `RA=1`, `RB=2`, `RD=0`, then press/release **2**. The execution display shows `000C`, `R0_LO_CURRENT` is 12, and the PC display/count advances once per instruction. Reset **0** clears registered state without modifying the manual interface values.

The instruction tag remains `[ADDRESS/NUMBER:4][OPCODE ID:12]`; operands are separate structured fields, as in the browser workbench. Data RAM is an external 4,096 × 16-bit (8 KiB) interface in the browser CPU model and is not stored in this native DLS panel.

## Reusable library and checks

The 49 custom chips include primitive-NAND logic and word operators; half/full and hierarchical ripple adders; `MISK16_CLA16`; `ADD16`/`SUB16`; `INC8`/`INC16`; `COMPARE16`; `ZERO16`; the `ALU16`; multiplexers; opcode decoder; combinational CPU-step core; and hex decoders/displays. The signed comparator and utility logic are general blocks and do not add opcodes to the MISK-16 ISA.

Build and validate from the repository root:

```sh
python3 tools/build_dls_project.py
python3 tools/validate_dls_project.py
```

The validator checks project/chip references, point-to-point wiring, forbidden built-ins, NAND latch feedback topology, reset/step state behavior, CPU vectors, and the carry-lookahead adder. DLS itself is not installed in the build environment, so import/save in the Unity application should be performed after copying the project to the DLS user-data `Projects` folder.
"""
    (PROJECT / "README.md").write_text(readme, encoding="utf-8")

    # Keep the ready-to-import archive in sync with the generated project folder.
    archive = ROOT / "MISK16-DLS.zip"
    temporary_archive = ROOT / "MISK16-DLS.zip.tmp"
    with zipfile.ZipFile(temporary_archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        zf.writestr(f"{PROJECT.name}/", "")
        zf.writestr(f"{PROJECT.name}/Chips/", "")
        for path in sorted(PROJECT.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(ROOT).as_posix())
    temporary_archive.replace(archive)


if __name__ == "__main__":
    build()
    print(f"Built {len(_descriptions)} DLS custom chips in {PROJECT}")
