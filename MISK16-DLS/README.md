# MISK-16 clocked CPU in Digital Logic Sim 2.1.6

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
