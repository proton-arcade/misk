#!/usr/bin/env python3
"""Validate the generated DLS project structure, combinational logic, and NAND state."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "MISK16-DLS"
FORBIDDEN = {"PULSE", "3-STATE BUFFER", "BUS-1", "BUS-4", "BUS-8", "BUS-TERMINUS-1", "BUS-TERMINUS-4", "BUS-TERMINUS-8", "ROM 256×16", "dev.RAM-8"}


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
    "CLOCK": ([], [0], [], [1]),
    "KEY": ([], [0], [], [1]),
    "7-SEGMENT": (list(range(8)), [], [1] * 8, []),
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
    collected_chips = set()
    for collection in manifest.get("ChipCollections", []):
        listed = set(collection.get("Chips", []))
        missing_chips = listed - custom_names
        if missing_chips:
            errors.append(f"collection {collection.get('Name')} references missing chips: {sorted(missing_chips)}")
        collected_chips |= listed
    unlisted_chips = custom_names - collected_chips
    if unlisted_chips:
        errors.append(f"custom chips are not discoverable in any collection: {sorted(unlisted_chips)}")
    if "MISK16_COMPUTER" not in custom_names:
        errors.append("the integrated MISK16_COMPUTER top-level chip is missing")
    elif not manifest.get("ChipCollections") or "MISK16_COMPUTER" not in manifest["ChipCollections"][0].get("Chips", []):
        errors.append("MISK16_COMPUTER must be the first chip in the open-first collection")

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
        display_ids = {display.get("SubChipID") for display in chip.get("Displays", [])}
        if len(display_ids) != len(chip.get("Displays", [])):
            errors.append(f"{name}: duplicate display metadata entries")
        for display in chip.get("Displays", []):
            display_child = children.get(display.get("SubChipID"))
            if display_child is None or display_child.get("Name") != "7-SEGMENT":
                errors.append(f"{name}: display metadata must reference a 7-SEGMENT child")
            if not isinstance(display.get("Scale"), (int, float)) or display["Scale"] <= 0:
                errors.append(f"{name}: invalid display scale")
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
        if name == "CLOCK":
            return {oids[0]: int(bool(manual_inputs.get("$CLOCK", 0)))}
        if name == "KEY":
            return {oids[0]: int(bool(manual_inputs.get(label, 0)))}
        if name == "7-SEGMENT":
            return {}
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


class ClockedGateSimulator:
    """Small event/settle simulator for the top NAND-only synchronous state network."""

    def __init__(self, chips: dict[str, dict], combinational: CircuitSimulator):
        self.chips = chips
        self.combinational = combinational
        self.desc = chips["MISK16_COMPUTER"]
        self.children = {child["ID"]: child for child in self.desc["SubChips"]}
        self.incoming = {owner_id: {} for owner_id in self.children}
        self.outputs_to_outer = {}
        for wire in self.desc["Wires"]:
            source = wire["SourcePinAddress"]
            target = wire["TargetPinAddress"]
            if target["PinOwnerID"] in self.children:
                self.incoming[target["PinOwnerID"]][target["PinID"]] = (source["PinOwnerID"], source["PinID"])
            else:
                self.outputs_to_outer[(target["PinOwnerID"], target["PinID"])] = (source["PinOwnerID"], source["PinID"])
        self.values: dict[tuple[int, int], int] = {}
        # Seed every raw NAND latch into a valid complementary state before reset.
        for owner_id, child in self.children.items():
            label = child.get("Label", "")
            if label.endswith(("MASTER Q BAR", "SLAVE Q BAR")):
                self.values[(owner_id, 2)] = 1
            elif label.endswith(("MASTER Q", "SLAVE Q")):
                self.values[(owner_id, 2)] = 0

    def settle(self, *, clock: int, keys: dict[str, int], manual_inputs: dict[str, int] | None = None) -> dict[str, int]:
        """Settle one fixed clock phase; update state only through the raw NAND netlist."""
        manual = dict(manual_inputs or {})
        manual["$CLOCK"] = int(bool(clock))
        for child in self.children.values():
            if child["Name"] == "KEY":
                manual[child.get("Label", "")] = int(bool(keys.get(child.get("Label", ""), 0)))
        max_sweeps = 500
        for _sweep in range(max_sweeps):
            changed = False
            for owner_id, child in self.children.items():
                name = child["Name"]
                in_table = port_table(name, self.chips, False)
                input_values = {}
                ready = True
                for pin_id, bits in in_table.items():
                    source = self.incoming[owner_id].get(pin_id)
                    if source is None:
                        ready = False
                        break
                    source_owner, source_pin = source
                    value = self.values.get((source_owner, source_pin), 0)
                    input_values[pin_id] = value & ((1 << bits) - 1)
                if not ready:
                    raise AssertionError(f"Clocked circuit has unresolved input on {name}:{child.get('Label', '')}")

                if name in self.chips:
                    desc = self.chips[name]
                    named_inputs = {pin["Name"]: input_values.get(pin["ID"], 0) for pin in desc["InputPins"]}
                    named_outputs = self.combinational.evaluate(name, named_inputs)
                    outputs = {pin["ID"]: named_outputs.get(pin["Name"], 0) for pin in desc["OutputPins"]}
                else:
                    outputs = self.combinational._eval_child(name, input_values, child.get("Label", ""), manual)
                out_table = port_table(name, self.chips, True)
                for pin_id, value in outputs.items():
                    value &= (1 << out_table[pin_id]) - 1
                    if self.values.get((owner_id, pin_id)) != value:
                        self.values[(owner_id, pin_id)] = value
                        changed = True
            if not changed:
                return self.outputs()
        raise AssertionError(f"NAND state circuit did not settle at clock={clock}")

    def outputs(self) -> dict[str, int]:
        result = {}
        for pin in self.desc["OutputPins"]:
            source = self.outputs_to_outer.get((pin["ID"], 0))
            if source is None:
                result[pin["Name"]] = 0
            else:
                result[pin["Name"]] = self.values.get(source, 0) & ((1 << pin["BitCount"]) - 1)
        return result


def validate_clocked_computer(chips: dict[str, dict]) -> tuple[int, int]:
    """Check raw-gate DFF topology, explicit reset/step paths, and allowed hardware."""
    if "MISK16_COMPUTER" not in chips:
        raise AssertionError("MISK16_COMPUTER is missing")
    computer = chips["MISK16_COMPUTER"]
    children = computer["SubChips"]
    child_names = [child["Name"] for child in children]
    if child_names.count("CLOCK") != 1 or child_names.count("KEY") != 2:
        raise AssertionError("MISK16_COMPUTER must contain one CLOCK and exactly two KEY controls")
    if child_names.count("7-SEGMENT") != 6 or len(computer["Displays"]) != 6:
        raise AssertionError("MISK16_COMPUTER must expose six physical seven-segment digits")
    if len(computer["InputPins"]) != 0:
        raise AssertionError("the computer control panel should use its labeled IN chips and keys, not hidden external input pins")

    allowed_builtin = {"NAND", "4-1BIT", "8-1BIT", "1-4BIT", "1-8BIT", "IN-1", "IN-4", "IN-8", "OUT-1", "OUT-4", "OUT-8", "CLOCK", "KEY", "7-SEGMENT"}
    custom_names = set(chips)
    for name, desc in chips.items():
        for child in desc["SubChips"]:
            if child["Name"] not in custom_names and child["Name"] not in allowed_builtin:
                raise AssertionError(f"{name} uses an unapproved built-in component: {child['Name']}")
            if child["Name"] == "CLOCK" and name != "MISK16_COMPUTER":
                raise AssertionError(f"CLOCK is only allowed at the clocked computer top level, not in {name}")
            if child["Name"] in ("KEY", "7-SEGMENT") and name != "MISK16_COMPUTER":
                raise AssertionError(f"{child['Name']} is only allowed at the top display/control panel, not in {name}")

    labels: dict[str, list[dict]] = {}
    for child in children:
        labels.setdefault(child.get("Label", ""), []).append(child)
    gates = [child for child in children if child["Name"] == "NAND"]
    if len(gates) < 2000:
        raise AssertionError(f"expected a substantial NAND-built CPU state network, found {len(gates)} gates")

    dff_suffixes = ("D BAR", "MASTER SET BAR", "MASTER RESET BAR", "MASTER Q", "MASTER Q BAR",
                    "SLAVE DATA BAR", "SLAVE SET BAR", "SLAVE RESET BAR", "SLAVE Q", "SLAVE Q BAR")
    dff_prefixes = ["STEP KEY HISTORY"]
    for register in [f"R{i}_{half}" for i in range(8) for half in ("LO", "HI")] + ["PC"]:
        dff_prefixes.extend(f"{register} BIT {bit}" for bit in range(8))
    dff_prefixes.extend(f"{flag} STATE" for flag in ("FLAG_Z", "FLAG_N", "FLAG_C"))
    if len(dff_prefixes) != 140:
        raise AssertionError("validator state-bit accounting is inconsistent")
    for prefix in dff_prefixes:
        for suffix in dff_suffixes:
            matches = labels.get(f"{prefix} {suffix}", [])
            if len(matches) != 1 or matches[0]["Name"] != "NAND":
                raise AssertionError(f"missing raw-NAND DFF stage {prefix} {suffix}")

    for register in [f"R{i}_{half}" for i in range(8) for half in ("LO", "HI")] + ["PC"]:
        for bit in range(8):
            prefix = f"{register} BIT {bit}"
            for suffix in (f"{prefix} HOLD", f"{prefix} LOAD", f"{prefix} MUX", f"{register} RESET {bit} NAND", f"{register} RESET {bit} INV"):
                if len(labels.get(suffix, [])) != 1:
                    raise AssertionError(f"missing clocked {register} step/reset gate {suffix}")
    for flag in ("FLAG_Z", "FLAG_N", "FLAG_C"):
        for suffix in (f"{flag} STEP HOLD", f"{flag} STEP LOAD", f"{flag} STEP MUX", f"{flag} RESET NAND", f"{flag} RESET INV"):
            if len(labels.get(suffix, [])) != 1:
                raise AssertionError(f"missing clocked flag step/reset gate {suffix}")

    # Verify each cross-coupled NAND latch actually feeds back both complementary outputs.
    child_by_id = {child["ID"]: child for child in children}
    pin_source = {}
    for wire in computer["Wires"]:
        src, dst = wire["SourcePinAddress"], wire["TargetPinAddress"]
        pin_source[(dst["PinOwnerID"], dst["PinID"])] = (src["PinOwnerID"], src["PinID"])
    nand_inputs = {"IN B": 0, "IN A": 1}
    for prefix in dff_prefixes:
        for latch in ("MASTER", "SLAVE"):
            q = labels[f"{prefix} {latch} Q"][0]["ID"]
            qb = labels[f"{prefix} {latch} Q BAR"][0]["ID"]
            for owner_id, pin_name, expected in (
                (q, "IN B", qb),
                (qb, "IN B", q),
            ):
                source = pin_source.get((owner_id, nand_inputs[pin_name]))
                if source is None or source[0] != expected:
                    raise AssertionError(f"{prefix} {latch} latch is missing its cross-coupled NAND feedback")

    for pin_name in ("PC_CURRENT", "R0_LO_CURRENT", "R7_HI_CURRENT", "FLAG_Z_CURRENT", "FLAG_N_CURRENT", "FLAG_C_CURRENT"):
        if pin_name not in {pin["Name"] for pin in computer["OutputPins"]}:
            raise AssertionError(f"clocked state output {pin_name} is missing")
    if "PC_NEXT" not in {pin["Name"] for pin in computer["OutputPins"]}:
        raise AssertionError("CPU next-PC output is missing")
    return len(gates), len(dff_prefixes)


def set_opcode(values: dict[str, int], opcode_id: int, prefix: int = 0) -> None:
    values["TAG_PREFIX"] = prefix
    values["OP_ID_HI"] = (opcode_id >> 8) & 0xF
    values["OP_ID_MID"] = (opcode_id >> 4) & 0xF
    values["OP_ID_LO"] = opcode_id & 0xF


def test_fast_cla16(sim: CircuitSimulator) -> int:
    import random

    rng = random.Random(0x16CA)
    vectors = [(0, 0, 0), (0xFFFF, 1, 0), (0xFFFF, 0, 1), (0x5555, 0xAAAA, 1),
               (0x7FFF, 1, 0), (0x8000, 0x8000, 0)]
    vectors.extend((rng.randrange(0x10000), rng.randrange(0x10000), rng.randrange(2)) for _ in range(96))
    for a, b, cin in vectors:
        inputs = {f"A{i}": (a >> i) & 1 for i in range(16)}
        inputs.update({f"B{i}": (b >> i) & 1 for i in range(16)})
        inputs["CIN"] = cin
        result = sim.evaluate("MISK16_CLA16", inputs)
        total = a + b + cin
        actual = sum(result[f"S{i}"] << i for i in range(16))
        assert actual == (total & 0xFFFF), ("MISK16_CLA16", hex(a), hex(b), cin, hex(actual), hex(total & 0xFFFF))
        assert result["COUT"] == (total >> 16)
    return 2 * len(vectors)


def test_clocked_state(chips: dict[str, dict], combinational: CircuitSimulator) -> int:
    validate_clocked_computer(chips)
    sim = ClockedGateSimulator(chips, combinational)
    reset_label = "RESET PC / REGISTERS · 0"
    step_label = "STEP ONE INSTRUCTION · 2"
    manual = {"TAG_PREFIX": 0, "OP_ID_HI": 0, "OP_ID_MID": 0, "OP_ID_LO": 1,
              "RA": 1, "RB": 2, "RD": 0, "IMM_LO": 0, "IMM_HI": 0}
    keys = {reset_label: 1, step_label: 0}
    checks = 0

    # Synchronous reset clears the 8-bit PC, all 16-bit registers, and flags.
    result = sim.settle(clock=0, keys=keys, manual_inputs=manual)
    result = sim.settle(clock=1, keys=keys, manual_inputs=manual)
    for name in [f"R{i}_{half}_CURRENT" for i in range(8) for half in ("LO", "HI")] + ["PC_CURRENT"]:
        assert result[name] == 0, ("reset", name, result[name])
    for name in ("FLAG_Z_CURRENT", "FLAG_N_CURRENT", "FLAG_C_CURRENT"):
        assert result[name] == 0, ("reset", name, result[name])
    checks += 20
    sim.settle(clock=0, keys=keys, manual_inputs=manual)
    keys[reset_label] = 0

    def execute_one_instruction() -> dict[str, int]:
        keys[step_label] = 1
        sim.settle(clock=0, keys=keys, manual_inputs=manual)
        result = sim.settle(clock=1, keys=keys, manual_inputs=manual)
        # A low phase followed by a rising edge with KEY 2 released rearms the edge detector.
        sim.settle(clock=0, keys=keys, manual_inputs=manual)
        keys[step_label] = 0
        sim.settle(clock=0, keys=keys, manual_inputs=manual)
        sim.settle(clock=1, keys=keys, manual_inputs=manual)
        sim.settle(clock=0, keys=keys, manual_inputs=manual)
        return result

    # Load two registers via LDI, then add them to prove PC and register state persist.
    manual.update({"OP_ID_LO": 11, "RD": 1, "IMM_LO": 5})
    result = execute_one_instruction()
    assert result["R1_LO_CURRENT"] == 5 and result["PC_CURRENT"] == 1
    checks += 2
    manual.update({"RD": 2, "IMM_LO": 7})
    result = execute_one_instruction()
    assert result["R2_LO_CURRENT"] == 7 and result["PC_CURRENT"] == 2
    checks += 2
    manual.update({"OP_ID_LO": 1, "RD": 0, "RA": 1, "RB": 2})
    result = execute_one_instruction()
    assert result["EXEC_LO"] == 12 and result["R0_LO_CURRENT"] == 12
    assert result["R0_HI_CURRENT"] == 0 and result["PC_CURRENT"] == 3
    checks += 4

    # A held key causes one instruction step total, not one per clock edge.
    keys[step_label] = 1
    sim.settle(clock=0, keys=keys, manual_inputs=manual)
    result = sim.settle(clock=1, keys=keys, manual_inputs=manual)
    assert result["PC_CURRENT"] == 4
    sim.settle(clock=0, keys=keys, manual_inputs=manual)
    result = sim.settle(clock=1, keys=keys, manual_inputs=manual)
    assert result["PC_CURRENT"] == 4, "held step key must not execute repeatedly"
    checks += 2

    # Branch the 8-bit PC to 255, then verify the next sequential instruction wraps it to 0.
    keys[step_label] = 0
    sim.settle(clock=0, keys=keys, manual_inputs=manual)
    sim.settle(clock=1, keys=keys, manual_inputs=manual)
    sim.settle(clock=0, keys=keys, manual_inputs=manual)
    manual.update({"OP_ID_MID": 1, "OP_ID_LO": 0, "BRANCH_TARGET": 255})
    result = execute_one_instruction()
    assert result["PC_CURRENT"] == 255
    manual.update({"OP_ID_MID": 0, "OP_ID_LO": 11, "RD": 3, "IMM_LO": 1})
    result = execute_one_instruction()
    assert result["PC_CURRENT"] == 0 and result["R3_LO_CURRENT"] == 1
    checks += 3

    # Pressing the explicit reset key returns the PC, registers, and flags to zero.
    keys[step_label] = 0
    keys[reset_label] = 1
    sim.settle(clock=0, keys=keys, manual_inputs=manual)
    result = sim.settle(clock=1, keys=keys, manual_inputs=manual)
    assert result["PC_CURRENT"] == 0 and result["R0_LO_CURRENT"] == 0
    assert result["R1_LO_CURRENT"] == 0 and result["R2_LO_CURRENT"] == 0
    assert result["R0_HI_CURRENT"] == 0 and result["FLAG_C_CURRENT"] == 0
    checks += 6
    return checks


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


def test_extended_computing_library(sim: CircuitSimulator) -> int:
    checks = 0
    mask = 0xFFFF
    vectors = (0x0000, 0xFFFF, 0xA55A, 0x0FF0, 0x8001)
    logic = {
        "AND16": lambda a, b: a & b,
        "OR16": lambda a, b: a | b,
        "XOR16": lambda a, b: a ^ b,
        "XNOR16": lambda a, b: (~(a ^ b)) & mask,
        "NAND16": lambda a, b: (~(a & b)) & mask,
        "NOR16": lambda a, b: (~(a | b)) & mask,
    }
    for a in vectors:
        for b in vectors:
            state = {"A_LO": a & 0xFF, "A_HI": a >> 8, "B_LO": b & 0xFF, "B_HI": b >> 8}
            for chip, operation in logic.items():
                out = sim.evaluate(chip, state)
                actual = out["Y_LO"] | (out["Y_HI"] << 8)
                assert actual == operation(a, b), (chip, hex(a), hex(b), hex(actual))
                checks += 1
            out = sim.evaluate("NOT16", {"A_LO": a & 0xFF, "A_HI": a >> 8})
            actual = out["Y_LO"] | (out["Y_HI"] << 8)
            assert actual == ((~a) & mask), ("NOT16", hex(a), hex(actual))
            checks += 1

    for a in (0, 1):
        for b in (0, 1):
            out = sim.evaluate("HALF_ADDER_1", {"A": a, "B": b})
            assert out["SUM"] == (a ^ b)
            assert out["COUT"] == (a & b)
            checks += 2

    arithmetic_vectors = ((0, 0), (mask, 1), (0x1234, 0xABCD), (0x8000, 0x8000), (7, 5))
    for a, b in arithmetic_vectors:
        for cin in (0, 1):
            state = {"A_LO": a & 0xFF, "A_HI": a >> 8, "B_LO": b & 0xFF, "B_HI": b >> 8, "CIN": cin}
            out = sim.evaluate("ADD16", state)
            total = a + b + cin
            actual = out["SUM_LO"] | (out["SUM_HI"] << 8)
            assert actual == (total & mask), ("ADD16", hex(a), hex(b), cin, hex(actual))
            assert out["COUT"] == (total >> 16)
            checks += 2

        state = {"A_LO": a & 0xFF, "A_HI": a >> 8, "B_LO": b & 0xFF, "B_HI": b >> 8}
        out = sim.evaluate("SUB16", state)
        actual = out["DIFF_LO"] | (out["DIFF_HI"] << 8)
        assert actual == ((a - b) & mask), ("SUB16", hex(a), hex(b), hex(actual))
        assert out["NO_BORROW"] == int(a >= b)
        checks += 2

    inc_values = {0, 1, 0x00FF, 0x0100, 0x7FFF, 0x8000, 0xFFFF, *range(256)}
    inc_values.update(((i * 40503 + 17) & mask) for i in range(64))
    for value in sorted(inc_values):
        out = sim.evaluate("INC16", {"IN_LO": value & 0xFF, "IN_HI": value >> 8})
        actual = out["OUT_LO"] | (out["OUT_HI"] << 8)
        assert actual == ((value + 1) & mask), ("INC16", hex(value), hex(actual))
        checks += 1

    compare_values = (0, 1, 0x7FFF, 0x8000, 0xFFFF, 0xFFFF - 7, 0x1234, 0xABCD)
    signed = lambda value: value - 0x10000 if value & 0x8000 else value
    for a in compare_values:
        for b in compare_values:
            state = {"A_LO": a & 0xFF, "A_HI": a >> 8, "B_LO": b & 0xFF, "B_HI": b >> 8}
            out = sim.evaluate("COMPARE16", state)
            expected = {
                "EQ": int(a == b), "NE": int(a != b),
                "LT_U": int(a < b), "LE_U": int(a <= b), "GT_U": int(a > b), "GE_U": int(a >= b),
                "LT_S": int(signed(a) < signed(b)), "LE_S": int(signed(a) <= signed(b)),
                "GT_S": int(signed(a) > signed(b)), "GE_S": int(signed(a) >= signed(b)),
            }
            assert out == expected, ("COMPARE16", hex(a), hex(b), out, expected)
            checks += len(expected)

    for a, b, select in ((0xA55A, 0x0FF0, 0), (0xA55A, 0x0FF0, 1), (0, mask, 0), (0, mask, 1)):
        state = {"A_LO": a & 0xFF, "A_HI": a >> 8, "B_LO": b & 0xFF, "B_HI": b >> 8, "SEL": select}
        out = sim.evaluate("MUX2_16", state)
        actual = out["Y_LO"] | (out["Y_HI"] << 8)
        assert actual == (b if select else a)
        checks += 1

    for select in range(8):
        state = {"SEL": select}
        values = []
        for index in range(8):
            value = ((index * 7919) ^ (select * 0x1234)) & mask
            values.append(value)
            state[f"D{index}_LO"] = value & 0xFF
            state[f"D{index}_HI"] = value >> 8
        out = sim.evaluate("MUX8_16", state)
        actual = out["Y_LO"] | (out["Y_HI"] << 8)
        assert actual == values[select], ("MUX8_16", select, hex(actual), hex(values[select]))
        checks += 1

    segment_patterns = {
        0: "abcdef", 1: "bc", 2: "abdeg", 3: "abcdg", 4: "bcfg", 5: "acdfg", 6: "acdefg", 7: "abc",
        8: "abcdefg", 9: "abcdfg", 10: "abcefg", 11: "cdefg", 12: "adef", 13: "bcdeg", 14: "adefg", 15: "aefg",
    }
    for digit in range(4):
        for value in range(16):
            word = value << (digit * 4)
            out = sim.evaluate("HEX_DISPLAY16", {"WORD_LO": word & 0xFF, "WORD_HI": word >> 8})
            assert out[f"DIGIT_{digit}"] == value
            for display_digit in range(4):
                expected_nibble = (word >> (display_digit * 4)) & 0xF
                assert out[f"DIGIT_{display_digit}"] == expected_nibble
                for segment in "abcdefg":
                    assert out[f"SEG_D{display_digit}_{segment.upper()}"] == int(segment in segment_patterns[expected_nibble])
            checks += 4 + 28

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
    checks = (test_logic(sim) + test_fast_cla16(sim) + test_opcode_decoder(sim) + test_adders_and_alu(sim)
              + test_extended_computing_library(sim) + test_register_file(sim) + test_cpu_step(sim)
              + test_clocked_state(chips, sim))
    nand_count = sum(child["Name"] == "NAND" for child in chips["MISK16_COMPUTER"]["SubChips"])
    print(f"Validated DLS 2.1.6 project: {len(chips)} custom chips, {wire_count} point-to-point wires, "
          f"{nand_count} top-level NAND gates, {checks} logic/state checks.")


if __name__ == "__main__":
    main()
