# MISK-16 · Text Computer Workbench

A programmable 16-bit computer with a Linux-inspired text interface. The app opens in **MISK Linux** mode: use the terminal screen, shell input, virtual files, and built-in nano-style editor, then switch to the **Workbench** to inspect registers and RAM. MPL programs edited in the virtual filesystem can be assembled and run directly on the MISK-16 CPU emulator. This is an educational shell simulation—not a Linux kernel or host command prompt.

The computer can also be used as a programmable 16-bit teaching workbench. Write MPL assembly into a writable 256-instruction program RAM, directly edit CPU registers, and execute one instruction per deliberate button press—or use RUN/PAUSE for software-stepped execution. The machine has **8 KiB of writable data RAM**: 4,096 word-addressed locations, each 16 bits wide. The example program exercises the top data-RAM address (`0xFFF`).

The workbench includes binary/hex word conversion, a 4-to-16 decoder and 16-to-4 encoder, a seven-segment hex display, program file import/export, and raw RAM image import/export. The ready-to-open Digital Logic Sim project at [`MISK16-DLS/`](MISK16-DLS/) (also packaged as [`MISK16-DLS.zip`](MISK16-DLS.zip)) opens to an integrated clocked `MISK16_COMPUTER` panel with NAND-built PC/register/flag state, reset/step keys, and a carry-lookahead ALU. A separate [`MISK16-GATE-LEVEL-DLS/`](MISK16-GATE-LEVEL-DLS/) project (also packaged as [`MISK16-GATE-LEVEL-DLS.zip`](MISK16-GATE-LEVEL-DLS.zip)) is a raw-NAND keyboard text-pad prototype: a clock, DLS keys, the built-in dot screen, and 1,735 individual NAND gates implement a four-character scratchpad. It reuses none of the computer/logic chips from the first project. The text-pad is a small gate-level hardware demonstration, not the Linux-inspired browser shell or a Linux kernel. See [DIGITAL-LOGIC-SIM.md](DIGITAL-LOGIC-SIM.md) for both project boundaries and import notes. The complete MPL reference is in [MPL.md](MPL.md).

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

## MISK Linux terminal mode

The app opens to the green-screen **MISK Linux** console. Type at the prompt, use Up/Down for shell history, Tab for command/file completion, Ctrl+L to clear, and Ctrl+C to cancel the current input. Common commands include `help`, `ls`, `cd`, `pwd`, `cat`, `mkdir`, `touch`, `echo "text" > file`, `nano file`, `lscpu`, `free`, `compile file.mpl`, `run file.mpl`, `reboot`, and `exit`.

`nano` is an inline terminal editor: Ctrl+S saves, Ctrl+X exits a clean file, and the editor has explicit Save & Exit / Discard controls. The virtual disk (1 MiB quota) is stored in this browser's local storage; its files do not touch your host filesystem. `run hello.mpl` assembles the virtual file and executes it on the same MISK-16 emulated CPU used by the workbench. The sample writes `42` to OUT. `reboot` resets emulated CPU/data RAM but preserves virtual files.

This is a small, original Linux-inspired userland for learning—not the Linux kernel, a Linux distribution, or a host shell. Only the simulated commands are available. See [MISK-OS.md](MISK-OS.md) for command and editor details. The linked [PC.zip](https://github.com/proton-arcade/misk/raw/refs/heads/main/PC.zip) provided additional circuit context (gates, latches, registers, and adders); the terminal screen and keyboard input are browser UI around the software machine, not DLS display hardware.

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
python3 tools/validate_dls_text_terminal.py
```

The DLS validator checks project/chip references, pin widths/directions, point-to-point wiring, raw-NAND latch structure, reset/step state behavior, the CPU core, and the carry-lookahead adder. DLS itself must be used for the final application import/save.

## What's included

- `index.html`, `style.css`, `app.js`: MISK Linux terminal screen, machine UI, assembler/debugger, and conversion tools.
- `miskos.js`, `terminal-os.js`: Linux-inspired shell, browser-local virtual filesystem, command history/completion, text editor UI, and bridge to run MPL on MISK-16.
- `misk16.js`: assembler, 16-bit machine core, word encoders/decoders, and RAM image helpers.
- `MPL.md`: language and ISA reference with examples.
- `MISK-OS.md`: shell command guide, virtual filesystem/editor behavior, and the OS simulation boundary.
- `DIGITAL-LOGIC-SIM.md`: DLS project format, import instructions, memory caveat, chip hierarchy, and validation vectors.
- `MISK16-DLS/`: native-format DLS 2.1.6 CPU project with clocked raw-NAND architectural state and manual instruction/memory interfaces.
- `MISK16-DLS.zip`: zipped copy of that CPU project for import.
- `MISK16-GATE-LEVEL-DLS/`: separate native-format DLS 2.1.6 text-pad circuit built from raw NAND gates, plus only the permitted clock, keys, and dot display (and a wiring-only address adapter).
- `MISK16-GATE-LEVEL-DLS.zip`: zipped copy of the raw-gate text-pad project for import.
- `tools/build_dls_project.py`, `tools/validate_dls_project.py`: regenerate and structurally/behaviorally validate the clocked CPU project.
- `tools/build_dls_text_terminal.py`, `tools/validate_dls_text_terminal.py`: generate and enforce the raw-gate project's component whitelist and point-to-point wiring.
- `test/misk16.test.js`, `test/miskos.test.js`: dependency-free CPU, shell, editor, virtual filesystem, MPL integration, codec, and memory tests (`node --test`).

**Native DLS note:** Digital Logic Sim saves projects as a directory containing `ProjectDescription.json` and a `Chips/` directory, not as a single `.dls` file. Copy/extract `MISK16-DLS/` into the DLS user-data `Projects` folder, open it in DLS 2.1.6, then choose **MISK16_COMPUTER** in **00 · Open this first** and use DLS's normal Save command. This first project's integrated top-level has a DLS CLOCK, KEY 0 synchronous reset, KEY 2 one-instruction step, 139 NAND-built master/slave state cells, current/next-state outputs, memory/I/O interfaces, and both execution-result and PC seven-segment displays. Its 49-chip library includes `MISK16_CLA16`, a four-stage raw-NAND carry-lookahead adder used by ALU ADD/SUB. It does not include on-chip program ROM or data RAM; instruction/data-memory interfaces remain manual.

**Raw-gate text-pad note:** Copy/extract `MISK16-GATE-LEVEL-DLS/` into the DLS `Projects` folder and open **MISK16_GATE_TEXT_PAD** in **00 · Open this first**. Resume DLS simulation, then press A–Z to enter uppercase glyphs, **1** for a blank, or **0** to clear. The hand-built NAND latch and scanner logic drives a 16×16 DLS dot display. This is a four-character gate-level input/display demo, not the MISK Linux shell or a Linux-capable CPU. It uses only primitive NAND gates, DLS CLOCK/KEY/DOT DISPLAY components, and the DLS 1-8BIT wiring adapter needed for the screen address.
