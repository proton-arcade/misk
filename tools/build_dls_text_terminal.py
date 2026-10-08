#!/usr/bin/env python3
"""Build a raw-gate MISK text-pad demo for Digital Logic Sim 2.1.6.

The only active DLS devices are a free-running CLOCK, alphanumeric KEY inputs,
a DOT DISPLAY, the display's wiring-only 1-to-8 adapter, and primitive NAND
chips. Character storage, cursor, edge detection, scan counter, font decoder,
and screen writer are all built from individual NAND gates.
"""
from __future__ import annotations

import json
import random
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "MISK16-GATE-LEVEL-DLS"
CHIPS_DIR = PROJECT / "Chips"
VERSION = "2.1.6"
_rng = random.Random(0x4D49534B)
_used_ids: set[int] = set()


def uid() -> int:
    while True:
        value = _rng.randint(10_000_000, 2_000_000_000)
        if value not in _used_ids:
            _used_ids.add(value)
            return value


def pos(x: float, y: float) -> dict[str, float]:
    return {"x": round(x, 4), "y": round(y, 4)}


class GateTerminal:
    def __init__(self) -> None:
        self.subchips: list[dict] = []
        self.wires: list[dict] = []
        self.displays: list[dict] = []
        self.target_set: set[tuple[int, int]] = set()
        self.gate_count = 0
        self._inv_cache: dict[tuple[int, int], tuple[int, int]] = {}
        self._zero: tuple[int, int] | None = None
        self._one: tuple[int, int] | None = None
        self.clock = self.add_component("CLOCK", "SYSTEM CLOCK", (-59, -30))
        self.clock_out = (self.clock, 0)
        self.clock_not = self.inv(self.clock_out, "CLOCK BAR")
        self.keys: dict[str, tuple[int, int]] = {}
        for index, character in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ01"):
            key = self.add_component("KEY", f"KEY {character}", (-62 + (index % 8) * 1.8, 34 - (index // 8) * 2.0), [ord(character)])
            self.keys[character] = (key, 0)
        self.display = self.add_component("DOT DISPLAY", "16×16 TEXT SCREEN", (55, 20))
        self.display_address = self.add_component("1-8BIT", "SCREEN ADDRESS WIRES", (45, 8))

    def _gate_position(self) -> tuple[float, float]:
        index = self.gate_count
        self.gate_count += 1
        columns = 36
        x = -35 + (index % columns) * 1.8
        y = 34 - (index // columns) * 1.45
        return x, y

    def add_component(self, name: str, label: str, position: tuple[float, float], internal_data=None) -> int:
        owner = uid()
        if name == "NAND":
            outputs = [("OUT", 1, 2)]
        elif name in {"CLOCK", "KEY"}:
            outputs = [("CLK" if name == "CLOCK" else "OUT", 1, 0)]
        elif name == "1-8BIT":
            outputs = [("OUT", 8, 8)]
        elif name == "DOT DISPLAY":
            outputs = [("PIXEL OUT", 1, 6)]
        else:
            raise ValueError(f"Unsupported component: {name}")
        self.subchips.append({
            "Name": name,
            "ID": owner,
            "Label": label,
            "Position": pos(*position),
            "OutputPinColourInfo": [{"PinColour": 0, "PinID": pin_id} for _pin, _bits, pin_id in outputs],
            "InternalData": internal_data,
        })
        return owner

    def add_nand(self, label: str = "") -> int:
        x, y = self._gate_position()
        owner = self.add_component("NAND", label, (x, y))
        self.gate_count += 0
        return owner

    def connect(self, source: tuple[int, int], target_owner: int, target_pin: int) -> None:
        target = (target_owner, target_pin)
        if target in self.target_set:
            raise ValueError(f"Multiple drivers for pin {target_owner}/{target_pin}")
        self.target_set.add(target)
        self.wires.append({
            "SourcePinAddress": {"PinID": source[1], "PinOwnerID": source[0]},
            "TargetPinAddress": {"PinID": target_pin, "PinOwnerID": target_owner},
            "ConnectionType": 0,
            "ConnectedWireIndex": -1,
            "ConnectedWireSegmentIndex": -1,
            "Points": [pos(0, 0), pos(0, 0)],
        })

    def nand_instance(self, a: tuple[int, int] | None, b: tuple[int, int] | None, label: str = "") -> tuple[int, int]:
        owner = self.add_nand(label)
        if a is not None:
            self.connect(a, owner, 1)  # NAND IN A
        if b is not None:
            self.connect(b, owner, 0)  # NAND IN B
        return owner, 2

    def nand(self, a: tuple[int, int], b: tuple[int, int], label: str = "") -> tuple[int, int]:
        return self.nand_instance(a, b, label)

    def inv(self, a: tuple[int, int], label: str = "") -> tuple[int, int]:
        if a not in self._inv_cache:
            self._inv_cache[a] = self.nand(a, a, label or "NOT")
        return self._inv_cache[a]

    def and2(self, a: tuple[int, int], b: tuple[int, int], label: str = "") -> tuple[int, int]:
        return self.inv(self.nand(a, b, label or "AND/NAND"), f"{label} INV" if label else "AND")

    def or2(self, a: tuple[int, int], b: tuple[int, int], label: str = "") -> tuple[int, int]:
        return self.nand(self.inv(a), self.inv(b), label or "OR")

    def xor2(self, a: tuple[int, int], b: tuple[int, int], label: str = "") -> tuple[int, int]:
        ab_n = self.nand(a, b, f"{label} XOR 1" if label else "XOR 1")
        a_term = self.nand(a, ab_n, f"{label} XOR 2" if label else "XOR 2")
        b_term = self.nand(b, ab_n, f"{label} XOR 3" if label else "XOR 3")
        return self.nand(a_term, b_term, f"{label} XOR OUT" if label else "XOR OUT")

    def and_many(self, values: list[tuple[int, int]], label: str = "") -> tuple[int, int]:
        if not values:
            return self.zero()
        work = values[:]
        while len(work) > 1:
            nxt = []
            for index in range(0, len(work), 2):
                if index + 1 == len(work):
                    nxt.append(work[index])
                else:
                    nxt.append(self.and2(work[index], work[index + 1], f"{label} AND" if label else "AND"))
            work = nxt
        return work[0]

    def or_many(self, values: list[tuple[int, int]], label: str = "") -> tuple[int, int]:
        if not values:
            return self.zero()
        work = values[:]
        while len(work) > 1:
            nxt = []
            for index in range(0, len(work), 2):
                if index + 1 == len(work):
                    nxt.append(work[index])
                else:
                    nxt.append(self.or2(work[index], work[index + 1], f"{label} OR" if label else "OR"))
            work = nxt
        return work[0]

    def and3(self, a: tuple[int, int], b: tuple[int, int], c: tuple[int, int], label: str = "") -> tuple[int, int]:
        return self.and_many([a, b, c], label or "AND3")

    def zero(self) -> tuple[int, int]:
        if self._zero is None:
            signal = next(iter(self.keys.values()))
            self._zero = self.and2(signal, self.inv(signal), "LOGIC ZERO")
        return self._zero

    def one(self) -> tuple[int, int]:
        if self._one is None:
            self._one = self.inv(self.zero(), "LOGIC ONE")
        return self._one

    def mux(self, select: tuple[int, int], a: tuple[int, int], b: tuple[int, int], label: str = "") -> tuple[int, int]:
        n0 = self.nand(a, self.inv(select), f"{label} MUX A" if label else "MUX A")
        n1 = self.nand(b, select, f"{label} MUX B" if label else "MUX B")
        return self.nand(n0, n1, f"{label} MUX OUT" if label else "MUX OUT")

    def latch(self, data: tuple[int, int], enable: tuple[int, int], label: str) -> tuple[tuple[int, int], tuple[int, int]]:
        data_n = self.inv(data, f"{label} D BAR")
        set_bar = self.nand(data, enable, f"{label} SET BAR")
        reset_bar = self.nand(data_n, enable, f"{label} RESET BAR")
        q_gate = self.add_nand(f"{label} Q")
        qb_gate = self.add_nand(f"{label} Q BAR")
        q = (q_gate, 2)
        qb = (qb_gate, 2)
        self.connect(set_bar, q_gate, 1)
        self.connect(qb, q_gate, 0)
        self.connect(reset_bar, qb_gate, 1)
        self.connect(q, qb_gate, 0)
        return q, qb

    def dff_placeholder(self, label: str) -> dict:
        """Allocate a master/slave DFF, then connect its D input after using Q."""
        dbar_gate = self.add_nand(f"{label} D BAR")
        dbar = (dbar_gate, 2)
        setbar_gate = self.add_nand(f"{label} MASTER SET BAR")
        resetbar = self.nand(dbar, self.clock_not, f"{label} MASTER RESET BAR")
        self.connect(self.clock_not, setbar_gate, 0)
        master_q_gate = self.add_nand(f"{label} MASTER Q")
        master_qbar_gate = self.add_nand(f"{label} MASTER Q BAR")
        master_q = (master_q_gate, 2)
        master_qbar = (master_qbar_gate, 2)
        self.connect((setbar_gate, 2), master_q_gate, 1)
        self.connect(master_qbar, master_q_gate, 0)
        self.connect(resetbar, master_qbar_gate, 1)
        self.connect(master_q, master_qbar_gate, 0)
        slave_q, _slave_qbar = self.latch(master_q, self.clock_out, f"{label} SLAVE")
        return {"q": slave_q, "dbar_gate": dbar_gate, "setbar_gate": setbar_gate, "label": label}

    def set_dff_data(self, dff: dict, data: tuple[int, int]) -> None:
        self.connect(data, dff["dbar_gate"], 0)
        self.connect(data, dff["dbar_gate"], 1)
        self.connect(data, dff["setbar_gate"], 1)

    def dff(self, data: tuple[int, int], label: str) -> tuple[int, int]:
        handle = self.dff_placeholder(label)
        self.set_dff_data(handle, data)
        return handle["q"]

    def eq_const(self, bits_lsb: list[tuple[int, int]], value: int, label: str) -> tuple[int, int]:
        terms = [bit if (value >> index) & 1 else self.inv(bit) for index, bit in enumerate(bits_lsb)]
        return self.and_many(terms, label)

    def make_display(self, scan_bits: list[tuple[int, int]], pixel: tuple[int, int], reset: tuple[int, int]) -> None:
        merger = self.display_address
        for bit_index, signal in enumerate(scan_bits):
            letter = chr(ord("A") + bit_index)
            pin_id = 7 - bit_index
            self.connect(signal, merger, pin_id)
        screen_address = (merger, 8)
        pin_ids = {"ADDRESS": 0, "PIXEL IN": 1, "RESET": 2, "WRITE": 3, "REFRESH": 4, "CLOCK": 5}
        self.connect(screen_address, self.display, pin_ids["ADDRESS"])
        self.connect(pixel, self.display, pin_ids["PIXEL IN"])
        self.connect(reset, self.display, pin_ids["RESET"])
        # The screen writes and refreshes its own buffer on each CLOCK rising edge.
        for name in ("WRITE", "REFRESH", "CLOCK"):
            self.connect(self.clock_out, self.display, pin_ids[name])
        self.displays.append({"SubChipID": self.display, "Position": pos(25, 22), "Scale": 5.0})

    def build(self) -> dict:
        zero_key = self.keys["0"]
        space_key = self.keys["1"]
        letter_keys = [self.keys[character] for character in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"]
        key_active = self.or_many(letter_keys + [zero_key, space_key], "ANY KEY")
        key_previous = self.dff(key_active, "KEY PREVIOUS")
        key_event = self.and2(key_active, self.inv(key_previous), "KEY PRESS EDGE")
        clear_event = self.and2(key_event, zero_key, "CLEAR EVENT")
        text_event = self.and2(key_event, self.inv(zero_key), "LETTER OR SPACE EVENT")

        # A–Z become 5-bit glyph IDs 1–26; key 1 writes a blank cell, key 0 clears.
        code_bits: list[tuple[int, int]] = []
        for bit in range(5):
            code_bits.append(self.or_many([
                letter_keys[index]
                for index in range(26)
                if ((index + 1) >> bit) & 1
            ], f"KEYCODE BIT {bit}"))

        cursor_ffs = [self.dff_placeholder(f"CURSOR BIT {bit}") for bit in range(2)]
        cursor = [ff["q"] for ff in cursor_ffs]
        cursor_clear_n = self.inv(clear_event, "CURSOR CLEAR BAR")
        cursor0_next = self.and2(cursor_clear_n, self.xor2(cursor[0], text_event, "CURSOR BIT 0"), "CURSOR NEXT 0")
        cursor_carry = self.and2(cursor[0], text_event, "CURSOR CARRY")
        cursor1_next = self.and2(cursor_clear_n, self.xor2(cursor[1], cursor_carry, "CURSOR BIT 1"), "CURSOR NEXT 1")
        self.set_dff_data(cursor_ffs[0], cursor0_next)
        self.set_dff_data(cursor_ffs[1], cursor1_next)

        cell_ffs = [[self.dff_placeholder(f"CELL {cell} BIT {bit}") for bit in range(5)] for cell in range(4)]
        cells = [[ff["q"] for ff in row] for row in cell_ffs]
        for cell in range(4):
            selected = self.and2(text_event, self.eq_const(cursor, cell, f"CURSOR CELL {cell}"), f"WRITE CELL {cell}")
            selected_n = self.inv(selected, f"CELL {cell} WRITE BAR")
            for bit in range(5):
                previous = cells[cell][bit]
                loaded = self.or2(
                    self.and2(selected, code_bits[bit], f"CELL {cell} LOAD {bit}"),
                    self.and2(selected_n, previous, f"CELL {cell} HOLD {bit}"),
                    f"CELL {cell} D {bit}",
                )
                next_value = self.and2(cursor_clear_n, loaded, f"CELL {cell} CLEAR {bit}")
                self.set_dff_data(cell_ffs[cell][bit], next_value)

        # An 8-bit free-running pixel address scans the built-in 16x16 screen.
        scan_ffs = [self.dff_placeholder(f"SCAN BIT {bit}") for bit in range(8)]
        scan = [ff["q"] for ff in scan_ffs]
        carry = self.one()
        for bit in range(8):
            if bit == 0:
                summed = self.inv(scan[bit], "SCAN INC BIT 0")
                carry = scan[bit]
            else:
                summed = self.xor2(scan[bit], carry, f"SCAN SUM {bit}")
                carry = self.and2(scan[bit], carry, f"SCAN CARRY {bit}")
            scan_next = self.and2(cursor_clear_n, summed, f"SCAN CLEAR {bit}")
            self.set_dff_data(scan_ffs[bit], scan_next)

        # Select a 5-bit character by screen column; cells occupy columns 0–2, 4–6, 8–10, 12–14.
        column_cell = [scan[2], scan[3]]
        cell_select = [self.eq_const(column_cell, value, f"SCREEN CELL {value}") for value in range(4)]
        selected_code = [
            self.or_many([self.and2(cell_select[cell], cells[cell][bit], f"SCREEN MUX {cell}/{bit}") for cell in range(4)], f"SCREEN CHAR BIT {bit}")
            for bit in range(5)
        ]

        patterns = {
            "A": ("111", "101", "111", "101", "101"), "B": ("110", "101", "110", "101", "110"),
            "C": ("111", "100", "100", "100", "111"), "D": ("110", "101", "101", "101", "110"),
            "E": ("111", "100", "110", "100", "111"), "F": ("111", "100", "110", "100", "100"),
            "G": ("111", "100", "101", "101", "111"), "H": ("101", "101", "111", "101", "101"),
            "I": ("111", "010", "010", "010", "111"), "J": ("111", "001", "001", "101", "111"),
            "K": ("101", "101", "110", "101", "101"), "L": ("100", "100", "100", "100", "111"),
            "M": ("101", "111", "111", "101", "101"), "N": ("101", "111", "111", "111", "101"),
            "O": ("111", "101", "101", "101", "111"), "P": ("111", "101", "111", "100", "100"),
            "Q": ("111", "101", "101", "111", "001"), "R": ("110", "101", "110", "101", "101"),
            "S": ("111", "100", "111", "001", "111"), "T": ("111", "010", "010", "010", "010"),
            "U": ("101", "101", "101", "101", "111"), "V": ("101", "101", "101", "101", "010"),
            "W": ("101", "101", "111", "111", "101"), "X": ("101", "101", "010", "101", "101"),
            "Y": ("101", "101", "010", "010", "010"), "Z": ("111", "001", "010", "100", "111"),
        }
        char_matches = {
            index + 1: self.eq_const(selected_code, index + 1, f"FONT CHAR {character}")
            for index, character in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
        }
        row_select = [self.eq_const(scan[4:8], row, f"FONT ROW {row}") for row in range(5)]
        x_select = [self.eq_const(scan[0:2], col, f"FONT COLUMN {col}") for col in range(3)]
        pixel_terms: list[tuple[int, int]] = []
        for row in range(5):
            for col in range(3):
                lit_codes = [
                    char_matches[index + 1]
                    for index, character in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
                    if patterns[character][row][col] == "1"
                ]
                glyph_pixel = self.or_many(lit_codes, f"FONT PIXEL SET {row}/{col}")
                pixel_terms.append(self.and3(row_select[row], x_select[col], glyph_pixel, f"SCREEN PIXEL {row}/{col}"))
        pixel = self.or_many(pixel_terms, "SCREEN PIXEL OR")

        self.make_display(scan, pixel, clear_event)

        max_x = max(float(item["Position"]["x"]) for item in self.subchips)
        min_y = min(float(item["Position"]["y"]) for item in self.subchips)
        height = max(80.0, 45 - min_y)
        width = max(145.0, max_x + 65)
        return {
            "DLSVersion": VERSION,
            "Name": "MISK16_GATE_TEXT_PAD",
            "NameLocation": 0,
            "ChipType": 0,
            "Size": {"x": width, "y": height},
            "Colour": {"r": 0.11, "g": 0.27, "b": 0.22, "a": 1.0},
            "InputPins": [],
            "OutputPins": [],
            "SubChips": self.subchips,
            "Wires": self.wires,
            "Displays": self.displays,
        }


def main() -> None:
    if PROJECT.exists():
        shutil.rmtree(PROJECT)
    CHIPS_DIR.mkdir(parents=True, exist_ok=True)
    circuit = GateTerminal()
    description = circuit.build()
    (CHIPS_DIR / "MISK16_GATE_TEXT_PAD.json").write_text(json.dumps(description, indent=2) + "\n", encoding="utf-8")
    now = datetime.now(timezone.utc).astimezone().isoformat(timespec="milliseconds")
    project = {
        "ProjectName": PROJECT.name,
        "DLSVersion_LastSaved": VERSION,
        "DLSVersion_EarliestCompatible": "2.0.0",
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
        "AllCustomChipNames": ["MISK16_GATE_TEXT_PAD"],
        "StarredList": [{"Name": "00 · Open this first", "IsCollection": True}],
        "ChipCollections": [{"Name": "00 · Open this first", "Chips": ["MISK16_GATE_TEXT_PAD"], "IsToggledOpen": True}],
    }
    (PROJECT / "ProjectDescription.json").write_text(json.dumps(project, indent=2) + "\n", encoding="utf-8")
    readme = f"""# MISK16 raw-gate text pad for Digital Logic Sim 2.1.6

This separate DLS project is a small gate-level hardware text-entry demonstration. Open the **MISK16_GATE_TEXT_PAD** chip, start the DLS simulator, then press the letter keys A–Z. Press **1** to write a blank cell and **0** to clear the four-character buffer. The 16×16 dot display shows four 3×5 uppercase glyphs in a one-line scratchpad; new letters wrap and overwrite from the first cell.

## Circuit policy

- All logic, character storage, cursor state, key-edge detection, font decoding, and screen scanning is made from individual primitive DLS NAND gates.
- The only other DLS components are one **CLOCK**, alphanumeric **KEY** components, the permitted **DOT DISPLAY**, and one **1-8BIT** signal-width adapter used solely to join the eight address wires required by the display.
- There are no DLS custom CPU/ALU/register/RAM/ROM chips, no prebuilt DLS logic blocks, no PULSE, BUS, or tri-state wiring. The only stored display pixels are inside the explicitly permitted DOT DISPLAY; the four text cells are raw NAND-gate clocked latches.
- The DLS screen is a four-character hardware text-pad demo, not a Linux kernel, full operating system, or hardware version of the browser shell. The browser's MISK Linux remains an educational software simulation. DLS is used here for the hand-built digital input, state, font and screen-IO logic.

The DLS built-in NAND is the primitive logic gate; DLS's CLOCK, KEY and DOT DISPLAY are the expressly permitted interface devices. Character cells and control state use hand-wired master/slave NAND latches clocked by the DLS CLOCK. Hold one key through a clock edge so the press is sampled, then release it before the next key. The simulator starts paused; resume it to scan the screen.

Generated contents: {len(circuit.subchips)} subchips total, including {circuit.gate_count} individual NAND gates, 28 KEY chips, one CLOCK, one DOT DISPLAY, and one 1-8BIT address adapter. `tools/build_dls_text_terminal.py` rebuilds this project. DLS's own GUI import/save remains the final compatibility check.
"""
    (PROJECT / "README.md").write_text(readme, encoding="utf-8")
    print(f"Built {PROJECT}: {len(circuit.subchips)} components, {circuit.gate_count} NAND gates, {len(circuit.wires)} point-to-point wires")


if __name__ == "__main__":
    main()
