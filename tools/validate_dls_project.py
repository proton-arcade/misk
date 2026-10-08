#!/usr/bin/env python3
"""Validate the generated DLS project structure and simulate its combinational chips."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "MISK16-DLS"
FORBIDDEN = {"CLOCK", "PULSE", "3-STATE BUFFER", "BUS-1", "BUS-4", "BUS-8", "BUS-TERMINUS-1", "BUS-TERMINUS-4", "BUS-TERMINUS-8", "ROM 256×16", "dev.RAM-8"}


def load_project():
    manifest = json.loads((PROJECT / "ProjectDescription.json").read_text(encoding="utf-8"))
    chips = {name: json.loads((PROJECT / "Chips" / f"{name}.json").read_text(encoding="utf-8")) for name in manifest["AllCustomChipNames"]}
    return manifest, chips


# (input pin IDs, output pin IDs, input bit counts, output bit counts)
BUILTINS = {
    "NAND": ([0, 1], [2], [1, 1], [1]),
    "4-1BIT": ([0], [1, 2, 3, 4], [4], [1, 1, 1, 1]),
    "8-1BIT": ([0], list(range(1, 9)), [8], [1] * 8),
    "1-4BIT": (list(range(4)), [4], [1] * 4, [4]),
    "1-8BIT": (list(range(8)), [8], [1] * 8, [8]),
    "IN-1": ([], [0], [], [1]),
    "IN-4": ([], [0], [], [4]),
    "IN-8": ([], [0], [], [8]),
    "OUT-1": ([0], [], [1], []),
    "OUT-4": ([0], [], [4], []),
    "OUT-8": ([0], [], [8], []),
}


def port_table(chip_name: str, chips: dict[str, dict], output: bool):
    if chip_name in chips:
        key = "OutputPins" if output else "InputPins"
        pins = chips[chip_name][key]
        return {p["ID"]: p["BitCount"] for p in pins}
    if chip_name not in BUILTINS:
        raise KeyError(f"Unknown child chip {chip_name}")
    iids, oids, ibits, obits = BUILTINS[chip_name]
    ids, bits = (oids, obits) if output else (iids, ibits)
    return dict(zip(ids, bits))


def validate_structure(manifest: dict, chips: dict[str, dict]) -> int:
    errors = []
    custom_names = set(chips)
    wire_count = 0
    required_manifest_fields = {
        "ProjectName", "DLSVersion_LastSaved", "DLSVersion_EarliestCompatible", "CreationTime", "LastSaveTime",
        "Prefs_MainPinNamesDisplayMode", "Prefs_ChipPinNamesDisplayMode", "Prefs_GridDisplayMode", "Prefs_Snapping",
        "Prefs_StraightWires", "Prefs_SimPaused", "Prefs_SimTargetStepsPerSecond", "Prefs_SimStepsPerClockTick",
        "AllCustomChipNames", "StarredList", "ChipCollections",
    }
    missing = required_manifest_fields - set(manifest)
    if missing:
        errors.append(f"manifest missing fields: {sorted(missing)}")
    if manifest.get("ProjectName") != PROJECT.name:
        errors.append("ProjectName must match the project directory name")
    if set(manifest.get("AllCustomChipNames", [])) != custom_names:
        errors.append("AllCustomChipNames does not match the Chips directory")
    folded_names = [name.casefold() for name in manifest.get("AllCustomChipNames", [])]
    if len(folded_names) != len(set(folded_names)):
        errors.append("custom chip names are not unique case-insensitively")
    for collection in manifest.get("ChipCollections", []):
        missing_chips = set(collection.get("Chips", [])) - custom_names
        if missing_chips:
            errors.append(f"collection {collection.get('Name')} references missing chips: {sorted(missing_chips)}")

    for name, chip in chips.items():
        expected = {"DLSVersion", "Name", "NameLocation", "ChipType", "Size", "Colour", "InputPins", "OutputPins", "SubChips", "Wires", "Displays"}
        missing = expected - set(chip)
        if missing:
            errors.append(f"{name}: missing chip fields {sorted(missing)}")
        if chip.get("Name") != name or chip.get("ChipType") != 0 or chip.get("DLSVersion") != "2.1.6":
            errors.append(f"{name}: wrong chip identity/version/type")
        ext = {}
        for p in chip["InputPins"]:
            if p["ID"] in ext:
                errors.append(f"{name}: duplicate external pin ID {p['ID']}")
            ext[p["ID"]] = ("source", p["BitCount"], p["Name"])
        for p in chip["OutputPins"]:
            if p["ID"] in ext:
                errors.append(f"{name}: duplicate external pin ID {p['ID']}")
            ext[p["ID"]] = ("target", p["BitCount"], p["Name"])
        children = {c["ID"]: c for c in chip["SubChips"]}
        if len(children) != len(chip["SubChips"]):
            errors.append(f"{name}: duplicate subchip IDs")
        child_owner_ids = set(children)
        if child_owner_ids & set(ext):
            errors.append(f"{name}: a subchip ID collides with an external pin owner ID")
        for child in chip["SubChips"]:
            if child["Name"] in FORBIDDEN:
                errors.append(f"{name}: prohibited component {child['Name']}")
            if child["Name"] not in custom_names and child["Name"] not in BUILTINS:
                errors.append(f"{name}: missing referenced chip {child['Name']}")
            expected_colours = set(port_table(child["Name"], chips, True))
            actual_colours = {item["PinID"] for item in (child.get("OutputPinColourInfo") or [])}
            if expected_colours != actual_colours:
                errors.append(f"{name}/{child['Name']}: output colour map mismatch")

        target_seen = set()
        for wire in chip["Wires"]:
            wire_count += 1
            if wire["ConnectionType"] != 0 or wire["ConnectedWireIndex"] != -1 or wire["ConnectedWireSegmentIndex"] != -1:
                errors.append(f"{name}: non-point-to-point wire metadata")
            src, dst = wire["SourcePinAddress"], wire["TargetPinAddress"]
            so, sp = src["PinOwnerID"], src["PinID"]
            to, tp = dst["PinOwnerID"], dst["PinID"]

            def endpoint(owner: int, pin_id: int, is_source: bool) -> int:
                if owner in ext:
                    direction, bits, pin_name = ext[owner]
                    if (direction == "source") != is_source or pin_id != 0:
                        raise ValueError(f"wrong external endpoint direction/id for {pin_name}")
                    return bits
                if owner not in children:
                    raise ValueError(f"unknown pin owner {owner}")
                child_name = children[owner]["Name"]
                return port_table(child_name, chips, is_source)[pin_id]

            try:
                src_bits = endpoint(so, sp, True)
                dst_bits = endpoint(to, tp, False)
                if src_bits != dst_bits:
                    errors.append(f"{name}: {src_bits}-bit wire connected to {dst_bits}-bit pin")
                if (to, tp) in target_seen:
                    errors.append(f"{name}: input pin {to}/{tp} has multiple drivers")
                target_seen.add((to, tp))
            except Exception as error:
                errors.append(f"{name}: invalid wire: {error}")

        for child_id, child in children.items():
            if child["Name"] in ("IN-1", "IN-4", "IN-8"):
                continue
            for pin_id in port_table(child["Name"], chips, False):
                if (child_id, pin_id) not in target_seen:
                    errors.append(f"{name}: unconnected input {child['Name']}:{pin_id} ({child.get('Label', '')})")

    if errors:
        raise AssertionError("DLS structure validation failed:\n" + "\n".join(errors[:50]))
    return wire_count


class CircuitSimulator:
    """Small pure-combinational evaluator for the DLS subset used in this project."""

    def __init__(self, chips: dict[str, dict]):
        self.chips = chips
        self.memo: dict[tuple[str, tuple[tuple[str, int], ...]], dict[str, int]] = {}

    @staticmethod
    def _mask(bits: int) -> int:
        return (1 << bits) - 1

    def evaluate(self, chip_name: str, inputs: dict[str, int], manual_inputs: dict[str, int] | None = None) -> dict[str, int]:
        manual_inputs = manual_inputs or {}
        key = (chip_name, tuple(sorted((name, int(value)) for name, value in inputs.items())))
        if not manual_inputs and key in self.memo:
            return dict(self.memo[key])
        desc = self.chips[chip_name]
        input_pins = desc["InputPins"]
        output_pins = desc["OutputPins"]
        outer_values = {}
        for pin in input_pins:
            value = int(inputs.get(pin["Name"], 0)) & self._mask(pin["BitCount"])
            outer_values[pin["ID"]] = value

        children = {child["ID"]: child for child in desc["SubChips"]}
        incoming = {owner_id: {} for owner_id in children}
        outgoing_to_outer = {}
        dependencies = {owner_id: set() for owner_id in children}
        for wire in desc["Wires"]:
            src = wire["SourcePinAddress"]
            dst = wire["TargetPinAddress"]
            if dst["PinOwnerID"] in children:
                incoming[dst["PinOwnerID"]][dst["PinID"]] = (src["PinOwnerID"], src["PinID"])
                if src["PinOwnerID"] in children:
                    dependencies[dst["PinOwnerID"]].add(src["PinOwnerID"])
            else:
                outgoing_to_outer[(dst["PinOwnerID"], dst["PinID"])] = (src["PinOwnerID"], src["PinID"])

        values: dict[tuple[int, int], int] = {}
        pending = set(children)
        while pending:
            progressed = False
            for owner_id in list(pending):
                if any(dep in pending for dep in dependencies[owner_id]):
                    continue
                child = children[owner_id]
                name = child["Name"]
                input_spec = port_table(name, self.chips, False)
                child_inputs = {}
                ready = True
                for pin_id, bits in input_spec.items():
                    source = incoming[owner_id].get(pin_id)
                    if source is None:
                        ready = False
                        break
                    source_owner, source_pin = source
                    if source_owner in outer_values:
                        value = outer_values[source_owner]
                    elif (source_owner, source_pin) in values:
                        value = values[(source_owner, source_pin)]
                    else:
                        ready = False
                        break
                    child_inputs[pin_id] = value & self._mask(bits)
                if not ready:
                    # Input components have no input pins; their output comes from the
                    # manually editable value shown by their instance label.
                    if name in ("IN-1", "IN-4", "IN-8") and not input_spec:
                        pass
                    elif not input_spec:
                        pass
                    else:
                        continue

                child_outputs = self._eval_child(name, child_inputs, child.get("Label", ""), manual_inputs)
                for pin_id, value in child_outputs.items():
                    values[(owner_id, pin_id)] = value & self._mask(port_table(name, self.chips, True)[pin_id])
                pending.remove(owner_id)
                progressed = True
            if not progressed:
                raise AssertionError(f"Combinational loop or unresolved inputs in {chip_name}: {[children[o]['Name'] for o in list(pending)[:12]]}")

        results = {}
        for pin in output_pins:
            source = outgoing_to_outer.get((pin["ID"], 0))
            if source is None:
                results[pin["Name"]] = 0
                continue
            source_owner, source_pin = source
            value = outer_values.get(source_owner) if source_owner in outer_values else values[(source_owner, source_pin)]
            results[pin["Name"]] = value & self._mask(pin["BitCount"])
        if not manual_inputs:
            self.memo[key] = dict(results)
        return results

    def _eval_child(self, name: str, inputs_by_id: dict[int, int], label: str, manual_inputs: dict[str, int]) -> dict[int, int]:
        if name in self.chips:
            desc = self.chips[name]
            inputs = {pin["Name"]: inputs_by_id.get(pin["ID"], 0) for pin in desc["InputPins"]}
            outputs = self.evaluate(name, inputs, manual_inputs)
            return {pin["ID"]: outputs.get(pin["Name"], 0) for pin in desc["OutputPins"]}
        iids, oids, ibits, obits = BUILTINS[name]
        if name.startswith("IN-"):
            value = int(manual_inputs.get(label, 0)) & self._mask(obits[0])
            return {oids[0]: value}
        if name.startswith("OUT-"):
            return {}
        if name == "NAND":
            return {2: 1 ^ (inputs_by_id.get(0, 0) & inputs_by_id.get(1, 0))}
        if name == "4-1BIT":
            value = inputs_by_id.get(0, 0) & 0xF
            return {1: (value >> 3) & 1, 2: (value >> 2) & 1, 3: (value >> 1) & 1, 4: value & 1}
        if name == "8-1BIT":
            value = inputs_by_id.get(0, 0) & 0xFF
            return {i + 1: (value >> (7 - i)) & 1 for i in range(8)}
        if name == "1-4BIT":
            value = sum((inputs_by_id.get(i, 0) & 1) << (3 - i) for i in range(4))
            return {4: value}
        if name == "1-8BIT":
            value = sum((inputs_by_id.get(i, 0) & 1) << (7 - i) for i in range(8))
            return {8: value}
        raise AssertionError(f"Unsupported DLS built-in in evaluator: {name}")


def set_opcode(values: dict[str, int], opcode_id: int, prefix: int = 0) -> None:
    values["TAG_PREFIX"] = prefix
    values["OP_ID_HI"] = (opcode_id >> 8) & 0xF
    values["OP_ID_MID"] = (opcode_id >> 4) & 0xF
    values["OP_ID_LO"] = opcode_id & 0xF


def test_logic(sim: CircuitSimulator) -> int:
    checks = 0
    for a in (0, 1):
        for b in (0, 1):
            assert sim.evaluate("INV", {"A": a})["Y"] == (a ^ 1)
            assert sim.evaluate("AND", {"A": a, "B": b})["Y"] == (a & b)
            assert sim.evaluate("OR", {"A": a, "B": b})["Y"] == (a | b)
            assert sim.evaluate("XOR", {"A": a, "B": b})["Y"] == (a ^ b)
            assert sim.evaluate("XNOR", {"A": a, "B": b})["Y"] == (1 ^ (a ^ b))
            assert sim.evaluate("NOR", {"A": a, "B": b})["Y"] == (1 ^ (a | b))
            checks += 6
    for value in range(16):
        decoded = sim.evaluate("DECODER4TO16", {"NIBBLE": value})
        assert sum(decoded[f"D{i:02X}"] for i in range(16)) == 1
        assert decoded[f"D{value:02X}"] == 1
        encoded = sim.evaluate("ENCODER16TO4", {f"D{i:02X}": int(i == value) for i in range(16)})
        assert encoded["NIBBLE"] == value
        checks += 2
    for value in range(256):
        out = sim.evaluate("INC8", {"IN": value})["OUT"]
        assert out == ((value + 1) & 0xFF)
        checks += 1
    return checks


def test_opcode_decoder(sim: CircuitSimulator) -> int:
    operations = ["ADD", "SUB", "AND", "OR", "XOR", "XNOR", "NAND", "NOR", "NOT", "MOV", "LDI", "ADDI", "CMP", "LOAD", "STORE", "JMP", "JZ", "JNZ", "IN", "OUT", "HALT"]
    checks = 0
    for opcode_id, operation in enumerate(operations, 1):
        state = {"PREFIX": 0xA, "ID_HI": (opcode_id >> 8) & 0xF, "ID_MID": (opcode_id >> 4) & 0xF, "ID_LO": opcode_id & 0xF}
        result = sim.evaluate("OPCODE_DECODER", state)
        assert result["VALID"] == 1
        assert result["PREFIX_OUT"] == 0xA
        assert result[f"S_{operation}"] == 1
        assert sum(result[f"S_{op}"] for op in operations) == 1
        checks += 4
    result = sim.evaluate("OPCODE_DECODER", {"PREFIX": 3, "ID_HI": 0, "ID_MID": 1, "ID_LO": 6})
    assert result["VALID"] == 0 and sum(result[f"S_{op}"] for op in operations) == 0
    checks += 1
    return checks


def test_adders_and_alu(sim: CircuitSimulator) -> int:
    checks = 0
    for width in (1, 2, 4, 8, 16):
        mask = (1 << width) - 1
        inputs, outputs = [], []
        for a in (0, 1, mask, mask >> 1):
            for b in (0, 1, mask, mask >> 1):
                for cin in (0, 1):
                    state = {f"A{i}": (a >> i) & 1 for i in range(width)}
                    state.update({f"B{i}": (b >> i) & 1 for i in range(width)})
                    state["CIN"] = cin
                    result = sim.evaluate(f"ADDER_{width}", state)
                    expected = a + b + cin
                    actual = sum(result[f"S{i}"] << i for i in range(width))
                    assert actual == (expected & mask), (width, a, b, cin, actual, expected & mask)
                    assert result["COUT"] == (expected >> width)
                    checks += 2

    mask16 = 0xFFFF
    vectors = [(0, 0), (0xFFFF, 1), (7, 5), (5, 5), (4, 5), (0xAAAA, 0x0F0F), (0x1234, 0xABCD)]
    op_names = ("ADD", "SUB", "AND", "OR", "XOR", "XNOR", "NAND", "NOR", "NOT")
    for a, b in vectors:
        for operation in op_names:
            state = {"A_LO": a & 0xFF, "A_HI": a >> 8, "B_LO": b & 0xFF, "B_HI": b >> 8}
            state.update({f"SEL_{op}": int(op == operation) for op in op_names})
            result = sim.evaluate("ALU16", state)
            y = result["Y_LO"] | (result["Y_HI"] << 8)
            if operation == "ADD":
                expected, carry = (a + b) & mask16, int(a + b > mask16)
            elif operation == "SUB":
                expected, carry = (a - b) & mask16, int(a >= b)
            elif operation == "AND": expected, carry = a & b, 0
            elif operation == "OR": expected, carry = a | b, 0
            elif operation == "XOR": expected, carry = a ^ b, 0
            elif operation == "XNOR": expected, carry = (~(a ^ b)) & mask16, 0
            elif operation == "NAND": expected, carry = (~(a & b)) & mask16, 0
            elif operation == "NOR": expected, carry = (~(a | b)) & mask16, 0
            else: expected, carry = (~a) & mask16, 0
            assert y == expected, (operation, hex(a), hex(b), hex(y), hex(expected))
            assert result["COUT"] == carry, (operation, result["COUT"], carry)
            assert result["ZERO"] == int(expected == 0)
            assert result["NEGATIVE"] == ((expected >> 15) & 1)
            checks += 4
    return checks


def test_register_file(sim: CircuitSimulator) -> int:
    inputs = {}
    for i in range(8):
        inputs[f"R{i}_LO"] = (i * 17 + 3) & 0xFF
        inputs[f"R{i}_HI"] = (i * 29 + 9) & 0xFF
    checks = 0
    for a in range(8):
        for d in range(8):
            state = dict(inputs, READ_A=a, READ_B=(7 - a), READ_D=d, WRITE_DEST=d, WRITE_EN=1,
                         WRITE_LO=0xA5, WRITE_HI=0x5A)
            result = sim.evaluate("REGISTER_FILE_MANUAL", state)
            assert result["A_LO"] == inputs[f"R{a}_LO"]
            assert result["A_HI"] == inputs[f"R{a}_HI"]
            assert result["B_LO"] == inputs[f"R{7-a}_LO"]
            assert result["B_HI"] == inputs[f"R{7-a}_HI"]
            assert result["D_LO"] == inputs[f"R{d}_LO"]
            assert result["D_HI"] == inputs[f"R{d}_HI"]
            for i in range(8):
                expected_lo = 0xA5 if i == d else inputs[f"R{i}_LO"]
                expected_hi = 0x5A if i == d else inputs[f"R{i}_HI"]
                assert result[f"R{i}_NEXT_LO"] == expected_lo
                assert result[f"R{i}_NEXT_HI"] == expected_hi
                checks += 2
    return checks


def test_cpu_step(sim: CircuitSimulator) -> int:
    state = {f"R{i}_{half}": 0 for i in range(8) for half in ("LO", "HI")}
    state.update({"RA": 1, "RB": 2, "RD": 0, "PC": 9, "BRANCH_TARGET": 0x72,
                  "IMM_LO": 0, "IMM_HI": 0, "DATA_READ_LO": 0, "DATA_READ_HI": 0,
                  "INPUT_LO": 0, "INPUT_HI": 0, "FLAG_Z": 0, "FLAG_N": 0, "FLAG_C": 0})
    checks = 0

    # ADD R0, R1, R2: result, manual next register values, and flags.
    state["R1_LO"], state["R1_HI"] = 0xFF, 0xFF
    state["R2_LO"], state["R2_HI"] = 0x01, 0x00
    set_opcode(state, 1, 3)
    out = sim.evaluate("MISK16_CPU_STEP", state)
    assert out["VALID"] == 1 and out["REG_WRITE_EN"] == 1
    assert out["TAG_PREFIX_OUT"] == 3
    assert out["EXEC_LO"] == 0 and out["EXEC_HI"] == 0
    assert out["R0_NEXT_LO"] == 0 and out["R0_NEXT_HI"] == 0
    assert out["FLAG_Z_NEXT"] == 1 and out["FLAG_C_NEXT"] == 1
    assert out["PC_NEXT"] == 10
    checks += 8

    # SUB with no-borrow and negative-result cases.
    set_opcode(state, 2)
    state["R1_LO"], state["R1_HI"] = 5, 0
    state["R2_LO"], state["R2_HI"] = 5, 0
    out = sim.evaluate("MISK16_CPU_STEP", state)
    assert out["EXEC_LO"] == 0 and out["FLAG_Z_NEXT"] == 1 and out["FLAG_C_NEXT"] == 1
    state["R1_LO"], state["R2_LO"] = 4, 5
    out = sim.evaluate("MISK16_CPU_STEP", state)
    assert out["EXEC_LO"] == 0xFF and out["EXEC_HI"] == 0xFF
    assert out["FLAG_N_NEXT"] == 1 and out["FLAG_C_NEXT"] == 0
    checks += 6

    # ADDI, all logical opcodes, MOV, and unary NOT.
    state["R1_LO"], state["R1_HI"] = 0xFE, 0xFF
    state.update({"RD": 5, "IMM_LO": 3, "IMM_HI": 0})
    set_opcode(state, 12)
    out = sim.evaluate("MISK16_CPU_STEP", state)
    assert out["EXEC_LO"] == 1 and out["EXEC_HI"] == 0 and out["FLAG_C_NEXT"] == 1
    checks += 3
    a, operand = 0xA55A, 0x0FF0
    state.update({"R1_LO": a & 0xFF, "R1_HI": a >> 8, "R2_LO": operand & 0xFF, "R2_HI": operand >> 8, "RA": 1, "RB": 2, "RD": 5})
    logic_expected = {3: a & operand, 4: a | operand, 5: a ^ operand, 6: (~(a ^ operand)) & 0xFFFF,
                      7: (~(a & operand)) & 0xFFFF, 8: (~(a | operand)) & 0xFFFF}
    for opcode, expected in logic_expected.items():
        set_opcode(state, opcode)
        out = sim.evaluate("MISK16_CPU_STEP", state)
        assert (out["EXEC_HI"] << 8 | out["EXEC_LO"]) == expected
        assert out["R5_NEXT_HI"] == (expected >> 8) and out["R5_NEXT_LO"] == (expected & 0xFF)
        checks += 2
    state.update({"R6_LO": 0xFF, "R6_HI": 0, "RD": 6})
    set_opcode(state, 9)
    out = sim.evaluate("MISK16_CPU_STEP", state)
    assert out["EXEC_HI"] == 0xFF and out["EXEC_LO"] == 0
    checks += 1
    set_opcode(state, 10)
    state.update({"RA": 1, "RD": 6})
    out = sim.evaluate("MISK16_CPU_STEP", state)
    assert out["EXEC_HI"] == (a >> 8) and out["EXEC_LO"] == (a & 0xFF)
    checks += 1

    # CMP updates flags without writing; IN/OUT and all branch forms expose control.
    set_opcode(state, 13)
    state.update({"RA": 1, "RB": 2, "RD": 7})
    out = sim.evaluate("MISK16_CPU_STEP", state)
    assert out["REG_WRITE_EN"] == 0 and out["FLAG_WRITE_EN"] == 1
    assert out["FLAG_C_NEXT"] == int(a >= operand)
    checks += 2
    set_opcode(state, 19)
    state.update({"RD": 7, "INPUT_LO": 0xC7, "INPUT_HI": 0x61})
    out = sim.evaluate("MISK16_CPU_STEP", state)
    assert out["R7_NEXT_LO"] == 0xC7 and out["R7_NEXT_HI"] == 0x61
    set_opcode(state, 20)
    state.update({"RA": 1})
    out = sim.evaluate("MISK16_CPU_STEP", state)
    assert out["OUT_EN"] == 1 and out["OUT_LO"] == (a & 0xFF) and out["OUT_HI"] == (a >> 8)
    checks += 4

    # LDI reads immediate data, LOAD/STORE expose the 12-bit external memory interface.
    set_opcode(state, 11)
    state.update({"RD": 3, "IMM_LO": 0xA5, "IMM_HI": 0xC3})
    out = sim.evaluate("MISK16_CPU_STEP", state)
    assert out["EXEC_LO"] == 0xA5 and out["EXEC_HI"] == 0xC3
    assert out["R3_NEXT_LO"] == 0xA5 and out["R3_NEXT_HI"] == 0xC3
    state["R3_LO"], state["R3_HI"] = 0xA5, 0xC3  # manual state re-entry after the LDI transition
    set_opcode(state, 14)
    state.update({"RA": 3, "RD": 4, "DATA_READ_LO": 0x34, "DATA_READ_HI": 0x12})
    out = sim.evaluate("MISK16_CPU_STEP", state)
    assert out["MEM_READ_EN"] == 1 and out["MEM_ADDR_LO"] == 0xA5
    assert out["MEM_ADDR_HI"] == 0x3
    assert out["R4_NEXT_LO"] == 0x34 and out["R4_NEXT_HI"] == 0x12
    state["R4_LO"], state["R4_HI"] = 0x34, 0x12  # manually apply LOAD's next-state result
    set_opcode(state, 15)
    state.update({"RA": 3, "RB": 4})
    out = sim.evaluate("MISK16_CPU_STEP", state)
    assert out["MEM_WRITE_EN"] == 1 and out["MEM_WRITE_LO"] == 0x34 and out["MEM_WRITE_HI"] == 0x12
    checks += 10

    # Branch and halt controls.
    set_opcode(state, 17)
    state.update({"PC": 1, "FLAG_Z": 1})
    out = sim.evaluate("MISK16_CPU_STEP", state)
    assert out["BRANCH_TAKEN"] == 1 and out["PC_NEXT"] == 0x72
    set_opcode(state, 18)
    state["FLAG_Z"] = 1
    out = sim.evaluate("MISK16_CPU_STEP", state)
    assert out["BRANCH_TAKEN"] == 0 and out["PC_NEXT"] == 2
    state["FLAG_Z"] = 0
    out = sim.evaluate("MISK16_CPU_STEP", state)
    assert out["BRANCH_TAKEN"] == 1 and out["PC_NEXT"] == 0x72
    set_opcode(state, 16)
    state["FLAG_Z"] = 1
    out = sim.evaluate("MISK16_CPU_STEP", state)
    assert out["BRANCH_TAKEN"] == 1 and out["PC_NEXT"] == 0x72
    set_opcode(state, 21)
    out = sim.evaluate("MISK16_CPU_STEP", state)
    assert out["HALT"] == 1 and out["PC_NEXT"] == 2
    checks += 9
    return checks


def main() -> None:
    manifest, chips = load_project()
    wire_count = validate_structure(manifest, chips)
    sim = CircuitSimulator(chips)
    checks = test_logic(sim) + test_opcode_decoder(sim) + test_adders_and_alu(sim) + test_register_file(sim) + test_cpu_step(sim)
    print(f"Validated DLS 2.1.6 project: {len(chips)} custom chips, {wire_count} point-to-point wires, {checks} logic checks.")


if __name__ == "__main__":
    main()
