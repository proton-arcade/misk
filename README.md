# MISK-16 · MPL Workbench

A programmable 16-bit computer teaching workbench. Write MPL assembly into a writable 256-instruction program RAM, directly edit CPU registers, and execute one instruction per deliberate button press—or use RUN/PAUSE for software-stepped execution. The machine has **8 KiB of writable data RAM**: 4,096 word-addressed locations, each 16 bits wide. The example program exercises the top data-RAM address (`0xFFF`).

The workbench includes binary/hex word conversion, a 4-to-16 decoder and 16-to-4 encoder, a seven-segment hex display, program file import/export, and raw RAM image import/export. A ready-to-open Digital Logic Sim project folder is included at [`MISK16-DLS/`](MISK16-DLS/), with a convenience archive [`MISK16-DLS.zip`](MISK16-DLS.zip). It contains the clock-free combinational single-step core and manual state panel; the strict no-clock constraint means the DLS version exposes program/data memory as external manual interfaces rather than pretending to implement persistent RAM. The DLS circuit notes are in [DIGITAL-LOGIC-SIM.md](DIGITAL-LOGIC-SIM.md). The complete MPL reference is in [MPL.md](MPL.md).

## Run the workbench

Open `index.html` in a modern browser, or serve the repository with a static server:

```sh
python3 -m http.server 8000
```

Then visit `http://localhost:8000`. There is no build step, package install, or backend.

1. Edit the MPL program (or open a `.mpl`/`.asm` file).
2. Choose **ASSEMBLE → RAM** to write the program into writable program RAM.
3. Use **STEP INSTRUCTION** or **RUN PROGRAM**; pause a run at any time.
4. Edit R0–R7 or PC directly; inspect/edit any data-RAM page (0–255) in the memory panel.
5. Use the binary/hex panel to edit a 16-bit word, toggle bits, and transfer it to or from a register or PC. The digit decoder/encoder shows one-hot and seven-segment logic.

The example sums 1 through 5, stores the result in data word `0xFFF`, reads it back, and shows `15 / 15` in OUTPUT. Reset clears registers, flags, data RAM, input, and output while keeping the loaded program.

## Computer specification

- **Word size:** 16 bits; eight editable general-purpose registers.
- **Program RAM:** 256 writable instruction entries, addressed by the 8-bit PC.
- **Data RAM:** 4,096 × 16-bit words = 8,192 bytes (8 KiB), addressed by the low 12 bits of a register.
- **MPL ISA:** arithmetic, bitwise logic, compare/conditional branches, load/store, input/output, and halt. Numeric literals accept decimal, hexadecimal (`0x`), and binary (`0b`).
- **Execution:** explicit single-step or user-started software stepping—no simulated clock or pulse.
- **Data RAM files:** raw 8,192-byte images, little-endian 16-bit words; import requires an exact-size image.

Program RAM and data RAM are separate, as in the workbench's teaching model. The 8 KiB figure is the data-RAM capacity; it does not count the program store. Program entries carry an opcode tag, but operands remain structured fields; the workbench does not claim to export a complete native machine-code image.

## Validate

```sh
node --test
python3 tools/validate_dls_project.py
```

The DLS validator checks project/chip references, pin widths/directions, one-driver point-to-point wiring, and simulates the combinational chips and manual-step CPU core. DLS itself must be used for the final application import/save.

## What's included

- `index.html`, `style.css`, `app.js`: interactive assembler, debugger, conversion tools, and computer workbench.
- `misk16.js`: assembler, 16-bit machine core, word encoders/decoders, and RAM image helpers.
- `MPL.md`: language and ISA reference with examples.
- `DIGITAL-LOGIC-SIM.md`: DLS project format, import instructions, memory caveat, chip hierarchy, and validation vectors.
- `MISK16-DLS/`: native-format DLS 2.1.6 project folder (`ProjectDescription.json` and `Chips/*.json`).
- `MISK16-DLS.zip`: zipped copy of the DLS project folder for import.
- `tools/build_dls_project.py`, `tools/validate_dls_project.py`: regenerate and structurally/behaviorally validate the DLS project.
- `test/misk16.test.js`: dependency-free CPU, codec, decoder/encoder, and memory tests (`node --test`).

**Native DLS note:** Digital Logic Sim saves projects as a directory containing `ProjectDescription.json` and a `Chips/` directory, not as a single `.dls` file. The repository now includes that project directory and a ZIP. Copy/extract `MISK16-DLS/` into the DLS user-data `Projects` folder, open it in DLS 2.1.6, and use DLS's normal Save command. The generated circuit uses only combinational gates and manual input/output chips; it does not include the stock clocked RAM/register components. Thus register/PC next-state is manually re-entered and program/data memory remain external manual interfaces, as required by the no-clock/no-feedback-storage constraints.
