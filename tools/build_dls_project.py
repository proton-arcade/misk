#!/usr/bin/env python3
"""Build a DLS 2.1.6 project containing the clock-free MISK-16 manual-step core.

The generated DLS project is combinational. All machine state is presented as
editable IN chips and returned as NEXT outputs; no clock, pulse, feedback store,
ROM, bus, or tri-state component is used. Program/data RAM remain external
manual state because the required DLS memory primitive is clocked.
"""
from __future__ import annotations

import json
import math
import random
import shutil
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
            "Displays": [],
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

    # Derive constant 0 and 1 from A0 and NOT(A0), without a clock or feedback.
    const_inv = b.add_sub("INV", -2, 0, "A0 complement")
    b.connect(*source("A", 0), const_inv, spec("INV").in_port("A")[0])
    const0 = b.add_sub("AND", 0, 1, "constant 0")
    const1 = b.add_sub("NAND", 0, -1, "constant 1")
    b.connect(*source("A", 0), const0, spec("AND").in_port("A")[0])
    b.sub_to_sub(const_inv, "Y", const0, "B")
    b.connect(*source("A", 0), const1, spec("NAND").in_port("IN B")[0])
    b.sub_to_sub(const_inv, "Y", const1, "IN A")

    add = b.add_sub("ADDER_16", 2, 5, "A + B")
    sub = b.add_sub("ADDER_16", 2, -7, "A + NOT(B) + 1")
    for bit in range(16):
        b.connect(*source("A", bit), add, spec("ADDER_16").in_port(f"A{bit}")[0])
        b.connect(*source("B", bit), add, spec("ADDER_16").in_port(f"B{bit}")[0])
        b.connect(*source("A", bit), sub, spec("ADDER_16").in_port(f"A{bit}")[0])
        b.connect(*not_b_bits[bit], sub, spec("ADDER_16").in_port(f"B{bit}")[0])
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
        result_sources["ADD"][bit] = (add, spec("ADDER_16").out_port(f"S{bit}")[0])
        result_sources["SUB"][bit] = (sub, spec("ADDER_16").out_port(f"S{bit}")[0])
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


def make_testbench() -> None:
    cpu = spec("MISK16_CPU_STEP")
    inputs = [(p[0], p[1]) for p in cpu.inputs]
    outputs = [(p[0], p[1]) for p in cpu.outputs]
    b = define("MISK16_TESTBENCH", [], [], width=90, height=70, colour=(0.17, 0.29, 0.43))
    cpu_id = b.add_sub("MISK16_CPU_STEP", 0, 0, "CLOCK-FREE MANUAL STEP CORE")
    input_chips: dict[str, int] = {}
    for index, (name, bits) in enumerate(inputs):
        input_chip = {1: "IN-1", 4: "IN-4", 8: "IN-8"}[bits]
        x = -28 + (index // 22) * 4
        y = 28 - (index % 22) * 2.5
        port = b.add_sub(input_chip, x, y, name)
        input_chips[name] = port
        out_id = spec(input_chip).out_port("OUT")[0]
        target_id = cpu.input_ids[name]
        b.connect(port, out_id, cpu_id, target_id)
    for index, (name, bits) in enumerate(outputs):
        output_chip = {1: "OUT-1", 4: "OUT-4", 8: "OUT-8"}[bits]
        x = 28 + (index // 22) * 4
        y = 28 - (index % 22) * 2.5
        port = b.add_sub(output_chip, x, y, name)
        source_id = cpu.output_ids[name]
        target_pin = spec(output_chip).in_port("IN")[0]
        b.connect(cpu_id, source_id, port, target_pin)
    # The physical view is a manually-entered single-instruction transition panel.
    b.height = 76
    b.save()


def make_project_description() -> None:
    custom_names = list(_descriptions.keys())
    collections = [
        {"Name": "00 · Open this first", "Chips": ["MISK16_TESTBENCH", "MISK16_CPU_STEP"], "IsToggledOpen": True},
        {"Name": "01 · Primitive logic", "Chips": ["INV", "AND", "OR", "XOR", "XNOR", "NOR", "AND3", "AND4", "OR_REDUCE8"], "IsToggledOpen": False},
        {"Name": "02 · Adders", "Chips": ["FULL_ADDER_1", "ADDER_1", "ADDER_2", "ADDER_4", "ADDER_8", "ADDER_16"], "IsToggledOpen": False},
        {"Name": "03 · Word logic and tools", "Chips": ["MUX2_1", "MUX2_8", "MUX8_1", "MUX8_8", "ZERO16", "ALU16", "DECODER4TO16", "ENCODER16TO4", "HEX7SEG", "RESULT_MUX5_8"], "IsToggledOpen": False},
        {"Name": "04 · CPU", "Chips": ["OPCODE_DECODER", "REGISTER_FILE_READ", "REGISTER_FILE_NEXT", "REGISTER_FILE_MANUAL", "INC8", "MISK16_CPU_STEP"], "IsToggledOpen": False},
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
    make_alu16()
    make_opcode_decoder()
    make_register_file_manual()
    make_register_file_read()
    make_register_file_next()
    make_inc8()
    make_result_mux5_8()
    make_cpu_step()
    make_testbench()

    for name, description in _descriptions.items():
        (CHIPS_DIR / f"{name}.json").write_text(json.dumps(description, indent=2) + "\n", encoding="utf-8")
    make_project_description()

    readme = """# MISK-16 DLS project (Digital Logic Sim 2.1.6)

This is a native-format DLS project folder. Copy the whole `MISK16-DLS` folder into the Digital Logic Sim user-data `Projects` directory (the same directory that contains your existing DLS project folders), then restart/open the project named `MISK16-DLS`. Open the **00 · Open this first** collection and choose `MISK16_TESTBENCH`. Use DLS's normal Save command after opening it.

## What is implemented

- A hierarchical 16-bit logic datapath built from DLS's NAND primitive: `FULL_ADDER_1 → ADDER_2 → ADDER_4 → ADDER_8 → ADDER_16`, seven bitwise functions, `ALU16`, nibble decoder/encoder, and HEX seven-segment logic.
- The `MISK16_CPU_STEP` combinational single-instruction transition core. It decodes the 4-bit prefix + 12-bit opcode ID, reads from eight externally editable 16-bit register values, calculates ALU/flags/branch/memory/I/O controls, and produces each register's `NEXT` value and `PC_NEXT`.
- `MISK16_TESTBENCH` exposes editable DLS `IN-1/4/8` chips and `OUT-1/4/8` probes. Enter the current state and instruction operands, inspect the outputs, then manually copy NEXT values back to the matching IN chips for the next software-style step. There is no clock, pulse, feedback storage, shared bus, tri-state, ROM, or hidden state.

## Quick test: ADD R0, R1, R2

On the input chips, enter `TAG_PREFIX=0`, `OP_ID_HI=0`, `OP_ID_MID=0`, `OP_ID_LO=1`; set `RA=1`, `RB=2`, `RD=0`; set `R1_LO=5`, `R1_HI=0`, `R2_LO=7`, `R2_HI=0`. The output probes should show `EXEC_LO=12`, `R0_NEXT_LO=12`, `R0_NEXT_HI=0`, `PC_NEXT=1`, and Z/N/C all zero. The prefix plus opcode nibbles are the binary word `0000 0000 0000 0001` (ADD). Copy NEXT values to the input chips manually before the next instruction.

## Opcode / operand layout

The opcode tag is `[ADDRESS/NUMBER:4][OPCODE ID:12]`. For example, ADD has ID 1 and SUB has ID 2. The ALU and CPU use separate operand input fields (`RA`, `RB`, `RD`, immediate, branch target), matching the workbench's structured instruction records; the opcode tag alone is not a complete instruction encoding.

## State and memory limitation

This project deliberately obeys the no-clock/no-pulse rule. Therefore it does not use DLS's clocked `dev.RAM-8` or `ROM 256×16`, and it does not claim that unclocked feedback stores state. The eight registers and PC are manually editable input values; the logic returns next values for a user to re-enter. The program instruction, data-RAM read value, and external INPUT WORD are likewise supplied manually. `MEM_READ_EN`, `MEM_WRITE_EN`, `MEM_ADDR_*`, and `MEM_WRITE_*` are the explicit interface to a separately maintained data store. Consequently this is a DLS-importable combinational computer core/manual-step testbench, not a persistent 256-entry program RAM or 4,096-word on-chip data RAM. The browser workbench remains the persistent software machine.

All subcircuits use direct pin-to-pin wires. Multi-bit values are split into 1-, 4-, and 8-bit DLS connections; no DLS `BUS` chip is used.
"""
    (PROJECT / "README.md").write_text(readme, encoding="utf-8")


if __name__ == "__main__":
    build()
    print(f"Built {len(_descriptions)} DLS custom chips in {PROJECT}")
