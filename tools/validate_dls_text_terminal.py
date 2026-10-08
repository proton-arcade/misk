#!/usr/bin/env python3
"""Validate the raw-NAND MISK keyboard/text-screen DLS project."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "MISK16-GATE-LEVEL-DLS"
CHIPS = PROJECT / "Chips"
ALLOWED_COMPONENTS = {"NAND", "CLOCK", "KEY", "DOT DISPLAY", "1-8BIT"}

SPECS = {
    "NAND": ({0: 1, 1: 1}, {2: 1}),
    "CLOCK": ({}, {0: 1}),
    "KEY": ({}, {0: 1}),
    "1-8BIT": ({**{i: 1 for i in range(8)}}, {8: 8}),
    "DOT DISPLAY": ({0: 8, 1: 1, 2: 1, 3: 1, 4: 1, 5: 1}, {6: 1}),
}


def fail(message: str) -> None:
    raise SystemExit(f"INVALID: {message}")


def main() -> None:
    project_file = PROJECT / "ProjectDescription.json"
    if not project_file.exists():
        fail("missing project description; run tools/build_dls_text_terminal.py first")
    project = json.loads(project_file.read_text(encoding="utf-8"))
    if project.get("DLSVersion_LastSaved") != "2.1.6":
        fail("project is not marked as DLS 2.1.6")
    custom_names = project.get("AllCustomChipNames", [])
    if custom_names != ["MISK16_GATE_TEXT_PAD"]:
        fail(f"expected only the raw-gate text-pad custom chip, got {custom_names}")
    circuit_path = CHIPS / "MISK16_GATE_TEXT_PAD.json"
    if not circuit_path.exists():
        fail("missing top-level raw-gate circuit")
    circuit = json.loads(circuit_path.read_text(encoding="utf-8"))
    chips = circuit.get("SubChips", [])
    ids = [chip.get("ID") for chip in chips]
    if len(ids) != len(set(ids)):
        fail("duplicate subchip IDs")
    counts: dict[str, int] = {}
    owner_specs: dict[int, tuple[str, dict[int, int], dict[int, int]]] = {}
    for chip in chips:
        name = chip.get("Name")
        if name not in ALLOWED_COMPONENTS:
            fail(f"disallowed prebuilt component {name!r}")
        counts[name] = counts.get(name, 0) + 1
        inputs, outputs = SPECS[name]
        owner_specs[chip["ID"]] = (name, inputs, outputs)
        if name == "KEY":
            internal = chip.get("InternalData") or []
            if len(internal) != 1 or chr(internal[0]) not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ01":
                fail(f"invalid keyboard binding on {chip.get('Label')}")
    if counts.get("NAND", 0) < 1000:
        fail("raw circuit is missing its gate-level implementation")
    if counts.get("CLOCK") != 1 or counts.get("DOT DISPLAY") != 1 or counts.get("1-8BIT") != 1:
        fail(f"expected one clock, dot display, and address-width adapter, got {counts}")
    if counts.get("KEY") != 28:
        fail(f"expected A-Z plus 0/1 key chips, got {counts.get('KEY', 0)}")
    if circuit.get("InputPins") or circuit.get("OutputPins"):
        fail("the text pad should be operated entirely by its permitted keyboard/screen interface")

    targets: set[tuple[int, int]] = set()
    sources: set[tuple[int, int]] = set()
    for wire in circuit.get("Wires", []):
        source = wire["SourcePinAddress"]
        target = wire["TargetPinAddress"]
        source_owner, source_pin = source["PinOwnerID"], source["PinID"]
        target_owner, target_pin = target["PinOwnerID"], target["PinID"]
        if source_owner not in owner_specs or target_owner not in owner_specs:
            fail("wire refers to an unknown component")
        source_name, _source_inputs, source_outputs = owner_specs[source_owner]
        target_name, target_inputs, _target_outputs = owner_specs[target_owner]
        if source_pin not in source_outputs or target_pin not in target_inputs:
            fail(f"wire has invalid pin direction or ID ({source_name} -> {target_name})")
        if source_outputs[source_pin] != target_inputs[target_pin]:
            fail(f"wire bit-width mismatch ({source_name} -> {target_name})")
        target_key = (target_owner, target_pin)
        if target_key in targets:
            fail("input pin has more than one driver")
        targets.add(target_key)
        sources.add((source_owner, source_pin))
    for chip in chips:
        name = chip["Name"]
        for pin_id in SPECS[name][0]:
            if (chip["ID"], pin_id) not in targets:
                fail(f"unwired input pin {name}/{pin_id}")
    display_ids = {chip["ID"] for chip in chips if chip["Name"] == "DOT DISPLAY"}
    if not any(item.get("SubChipID") in display_ids for item in circuit.get("Displays", [])):
        fail("the permitted DOT DISPLAY is not surfaced on the top-level panel")
    if len(circuit.get("Wires", [])) < 2500:
        fail("expected a point-to-point gate-level network, found too few wires")
    print(
        "Validated raw-gate DLS terminal: "
        f"{counts['NAND']} NAND gates, {counts['KEY']} key inputs, "
        f"1 CLOCK, 1 DOT DISPLAY, 1 wiring-only 1-8BIT adapter, "
        f"{len(circuit['Wires'])} point-to-point wires; no other prebuilt chips."
    )


if __name__ == "__main__":
    main()
