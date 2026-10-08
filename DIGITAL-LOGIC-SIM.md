# MISK-16 in Seb Lague's Digital Logic Sim

This repository includes a browser workbench and two native Digital Logic Sim projects. [`MISK16-DLS/`](MISK16-DLS/) is the integrated clocked MISK-16 CPU panel: its PC, eight registers, and flags use master/slave flip-flops assembled from raw NAND gates, with a reset key, single-step key, carry-lookahead ALU, and seven-segment displays. Instruction and data-memory interfaces remain manual inputs/outputs; this is not on-chip program/data RAM. [`MISK16-GATE-LEVEL-DLS/`](MISK16-GATE-LEVEL-DLS/) is a separate raw-gate four-character keyboard text pad built from individual NANDs with a clock, DLS keys, and dot-display screen. The browser workbench separately models writable 256-entry instruction storage and **8 KiB of writable data RAM** (4,096 × 16-bit words, addresses `0x000`–`0xFFF`). DLS stores projects as a directory with `ProjectDescription.json` and `Chips/*.json`; both included projects target DLS 2.1.6.

## Raw-gate DLS text pad

The new [`MISK16-GATE-LEVEL-DLS/`](MISK16-GATE-LEVEL-DLS/) project is the gate-level conversion of the screen/input part, not a converted Linux OS. Import the whole project folder into DLS 2.1.6, open **MISK16_GATE_TEXT_PAD** in **00 · Open this first**, and resume simulation. Press **A–Z** to write uppercase 3×5 glyphs, **1** to write a blank cell, and **0** to clear the buffer. The display holds four characters; after four positions, additional letters wrap and overwrite from the first cell.

Its entire logic network is a single custom panel containing 1,735 individual NAND gates, 28 alphanumeric KEY components (A–Z, 0, 1), one CLOCK, one built-in DOT DISPLAY, and one 1-8BIT address-width adapter. The adapter only joins eight separate address wires to the screen's required 8-bit pin. The cursor, four 5-bit text cells, keypress edge detector, pixel counter, and character glyph decode are NAND-level logic; there are no prebuilt CPU/ALU/mux/register/RAM/ROM blocks from this repository or DLS. The pixel buffer lives only inside the explicitly allowed screen device. The text pad is a small hardware input/display demo, not the MISK Linux shell or a Linux kernel. Build and check it with:

```sh
python3 tools/build_dls_text_terminal.py
python3 tools/validate_dls_text_terminal.py
```

The CPU panel keeps explicit external instruction and memory interfaces; its register/PC/flag state is now clocked using raw NAND latches. The circuit library and architecture notes follow below.

Reference project format and examples: [Seb Lague / Digital-Logic-Sim](https://github.com/SebLague/Digital-Logic-Sim) (MIT licensed). I also inspected the user-provided [`ZHT92Pong.zip`](https://github.com/proton-arcade/misk/blob/main/ZHT92Pong.zip) project (DLS 2.1.6). It contains `ZHT92/ProjectDescription.json` plus `ZHT92/Chips/*.json`. The description stores project/version settings, custom-chip names, and named collections; for example, its `SPLIT`, `BASIC`, `MEM`, and `CALC` collections sort reusable chips. A custom-chip JSON records its `Name`, `DLSVersion`, `InputPins`, `OutputPins`, `SubChips`, `Wires`, and `Displays`. Pins have IDs and bit counts; a wire connects a source and target by their owner/pin IDs. The example's `16-4` custom chip composes five reusable subchips and 17 wires, showing how to build hierarchy; it is a splitter/combiner, not an adder. Its `ALU-8` uses 152 subchips and 311 wires, a useful working reference but much flatter than the recursive adder hierarchy specified here. The sample also contains clocks, ROMs, buses, and tri-state buffers; those are examples of DLS features, not components to copy into this design.

## Import the ready-to-open project

DLS uses a project directory, not a single `.dls` file. The included [`MISK16-DLS/`](MISK16-DLS/) folder contains `ProjectDescription.json`, `Chips/*.json`, and a project-local README. The same folder is packaged as [`MISK16-DLS.zip`](MISK16-DLS.zip).

1. Extract/copy the whole `MISK16-DLS` folder into the DLS user-data `Projects` directory (the directory containing your other DLS project folders, such as `ZHT92`).
2. Restart DLS or refresh the project list and open `MISK16-DLS`.
3. Open the **00 · Open this first** collection, then open **MISK16_COMPUTER**. `MISK16_TESTBENCH` remains as a compatibility alias.
4. After importing/opening, use DLS's regular **Save** command. DLS can update the save timestamps/version metadata in its own application.

The files target DLS 2.1.6. The CPU project contains 49 custom chips and 8,823 point-to-point wires, including a 2,103-NAND top panel with 139 architectural-state DFFs plus one step-key history DFF. Arithmetic, muxing, and state storage use raw NAND gates; DLS split/join parts are wiring adapters, and labeled IN/OUT parts are manual interfaces. The validator structurally checks every chip and simulates combinational circuits plus reset/step operation through the NAND state network. The Unity application itself is not available here, so final GUI import/save should be performed by DLS on your machine.

## Included chip collections

DLS collections sort reusable chips; they do not alter circuit behavior. The generated project organizes its library as follows:

1. **00 · Open this first:** `MISK16_COMPUTER`, `MISK16_CPU_STEP`, and the compatibility alias `MISK16_TESTBENCH`.
2. **01 · Logic gates:** `INV`, `AND`, `OR`, `XOR`, `XNOR`, `NOR`, `AND3`, `AND4`, `OR_REDUCE8`, plus `AND16`, `OR16`, `XOR16`, `XNOR16`, `NAND16`, `NOR16`, and `NOT16` (built-in NAND is the 1-bit primitive).
3. **02 · Arithmetic and compare:** `HALF_ADDER_1`, `FULL_ADDER_1`, hierarchical `ADDER_1/2/4/8/16`, byte-oriented `ADD16`/`SUB16`, `INC8`/`INC16`, `COMPARE16`, `ZERO16`, and `ALU16`.
4. **03 · Multiplexers and data routing:** `MUX2_1/8/16`, `MUX8_1/8/16`, and `RESULT_MUX5_8`.
5. **04 · CPU core and interfaces:** `OPCODE_DECODER`, `REGISTER_FILE_READ`, `REGISTER_FILE_NEXT`, `REGISTER_FILE_MANUAL`, `INC8`, and `MISK16_CPU_STEP`.
6. **05 · Decode and displays:** `DECODER4TO16`, `ENCODER16TO4`, `HEX7SEG`, and `HEX_DISPLAY16`.

`MISK16_COMPUTER` ties the CPU step core to a NAND-built clocked PC/register/flag path, labeled manual instruction/memory inputs, named output probes, and physical execution/PC displays. The ALU uses the four-stage Kogge–Stone block for ADD/SUB; hierarchical ripple adders remain separate comparison tools. The reusable word-level chips and comparator are optional combinational tools and do not add opcodes to the MISK-16 ISA.

## Hard constraints and storage caveat

- The CPU project uses one DLS CLOCK and two KEYs only to run raw-NAND master/slave latches, step one instruction, and reset state. The separate text pad also uses a clock, keys, and its explicitly allowed display. Neither project uses DLS's prebuilt DFF/register/ALU/mux/RAM/ROM components, PULSE, BUS, tri-state wiring, or shared multi-driver wires. The CPU's reusable custom logic modules are themselves composed from primitive NAND gates. DLS input/output and split/join components are interfaces/adapters, not compute/storage blocks.
- In the browser workbench, assembled code resides in **256-entry writable program RAM** (8-bit PC), separate from **4,096 × 16-bit writable data RAM** (8 KiB, word addresses `0x000`–`0xFFF`). The DLS CPU clocks its 8-bit PC, eight 16-bit registers, and Z/N/C flags, but the current instruction and memory values are external manual inputs; `MISK16_CPU_STEP` exposes memory read/write enables, the low-12-bit data address, and write data. The reset key clears architectural state synchronously on the next rising clock edge. The raw-gate text pad does not use DLS RAM/ROM; its four 5-bit character cells are made from individual clocked NAND latches, while the allowed DOT DISPLAY holds the pixels.
- The raw-gate project permits only primitive NAND gates, CLOCK, alphanumeric KEY devices, DOT DISPLAY, and the 1-8BIT wiring adapter required to form the display address. Do not substitute any prebuilt CPU, ALU, multiplexer, register, memory, or ROM chips. Its clocked state is built from individual NAND gates; its screen's internal pixel buffer is part of the explicitly permitted screen device.
- Browser STEP and RUN/PAUSE are software state transitions, not circuit clock pulses. The DLS text pad is a separate hardware demo with its own clock, and does not execute shell commands or MPL.

## Circuit collections and equations

The following are gate-level implementation equations/reference. The imported project contains the reusable logic chips listed above. Its architectural registers, PC, and flags are clocked NAND-latch state; program and data memory remain external manual interfaces. Use bit index `i = 0…15`. `A_i`, `B_i`, and `Y_i` are individual wires; there is no shared multi-driver wire.

### `GATE16`

Inputs: A[15:0], B[15:0]. Each output is the indicated one-bit gate, repeated once per bit. Use the widest native gate available when the same signal fan-in exceeds two; do not tie unused input pins to floating wires.

- `Y_AND[i] = A[i] AND B[i]`
- `Y_NAND[i] = NOT(A[i] AND B[i])` (or NAND)
- `Y_OR[i] = A[i] OR B[i]`
- `Y_NOR[i] = NOT(A[i] OR B[i])` (or NOR)
- `Y_XOR[i] = A[i] XOR B[i]`
- `Y_XNOR[i] = NOT(A[i] XOR B[i])` (or XNOR)
- `Y_NOT_A[i] = NOT A[i]`

### Hierarchical adders: `FULL_ADDER_1` → `ADDER_2` → `ADDER_4` → `ADDER_8` → `ADDER_16`

Build and test complete smaller circuits, then compose them into larger named chips. Do **not** place sixteen unrelated 1-bit adders directly in the CPU. Every adder chip has the same contract: inputs A[W−1:0], B[W−1:0], carry-in `Cin`; outputs SUM[W−1:0], carry-out `Cout`. Bit zero is the least significant bit. Use separate point-to-point wires for each named pin; there is no shared bus or tri-state output.

#### 1-bit foundation: `FULL_ADDER_1`

Inputs A, B, Cin; outputs SUM, Cout. Use XOR, AND, and OR gates:

```
P    = A XOR B
SUM  = P XOR Cin
Cout = (A AND B) OR (P AND Cin)
```

Test all eight input combinations against binary addition before composing this cell.

#### Compose two equal-width children

For any width W in {2, 4, 8}, make `ADDER_2W` by placing exactly two `ADDER_W` child chips, named `LOWER` and `UPPER`. Connect A[W−1:0], B[W−1:0], and top-level Cin to LOWER. Connect LOWER.Cout directly to UPPER.Cin. Connect the top-level high halves A[2W−1:W], B[2W−1:W] to UPPER. Join the two SUM slices as separate output pins and expose UPPER.Cout as top-level Cout:

```
LOWER: SUM[W−1:0], Cout = ADDER_W(A[W−1:0], B[W−1:0], Cin)
UPPER: SUM[2W−1:W], Cout = ADDER_W(A[2W−1:W], B[2W−1:W], LOWER.Cout)
```

This is a ripple-carry hierarchy: the carry path crosses the child boundary as one wire. Keep pin names and slice order explicit in the DLS chip labels.

#### Required hierarchy

1. `FULL_ADDER_1`: primitive XOR/AND/OR gates.
2. `ADDER_2`: two `FULL_ADDER_1` instances (`LOWER`, `UPPER`).
3. `ADDER_4`: two `ADDER_2` instances.
4. `ADDER_8`: two `ADDER_4` instances.
5. `ADDER_16`: two `ADDER_8` instances.

`ADD16` in the ALU is an instance of `ADDER_16` with Cin tied to 0. For subtraction, put a 16-bit NOT collection on B and set Cin to 1; this computes A + NOT(B) + 1. Cout then means no borrow. Keep the 1/2/4/8/16-bit circuits as reusable named collection entries, and test each finished width before building the next. If DLS's largest gate input count is greater than two for another part of the design, prefer it there; an adder's one-bit full-adder stages still need their explicit carry structure.

### `COMPARE16`

For equality, each bit uses XNOR and the equality result is the AND of all 16 XNOR outputs. Build the reduction from the largest available AND input count; if only two inputs are available, use a named balanced `AND_REDUCE16` collection. For `CMP`, also use `ADD16(A, NOT(B), C0=1)` to derive the difference sign (bit 15) and no-borrow carry; equality is Z.

### `ALU16`

Inputs A, B, and operation selects. Compute these results in parallel in separate named gate collections: ADD16, SUB16, AND16, OR16, XOR16, XNOR16, NAND16, NOR16, and NOT16. A decoder generates one mutually exclusive select wire per operation; the output for bit `i` is the OR of each operation result gated by its select. Use AND gates for each result/select pair and a tree of OR gates for the final bit. This is explicit logic, not a shared bus or tri-state selection. Export result[15:0], carry, zero (16-bit equality-to-zero reduction), and negative (result bit 15).

### `DECODER4TO16`

Build 16 one-hot outputs from NOT and AND gates (or the widest matching gates): each output `D[n]` is true only for the corresponding four-bit address. Label each output `D00`…`D15` and group the outputs into four collections by high address bits if that helps layout. The included `DECODER4TO16` is used for opcode/register selections. A raw-gate 4,096-word physical RAM would need a much larger address-selection and state array; that RAM is **not** part of the current DLS computer.

### `ENCODER16TO4` and `HEX7SEG`

`ENCODER16TO4` accepts one-hot inputs `D00`…`D15` and returns the selected index as `B3`…`B0`. Its equations are OR reductions of the active one-hot lines:

```
B3 = D08 OR D09 OR D10 OR D11 OR D12 OR D13 OR D14 OR D15
B2 = D04 OR D05 OR D06 OR D07 OR D12 OR D13 OR D14 OR D15
B1 = D02 OR D03 OR D06 OR D07 OR D10 OR D11 OR D14 OR D15
B0 = D01 OR D03 OR D05 OR D07 OR D09 OR D11 OR D13 OR D15
```

The input contract is exactly one asserted D line; zero-hot or multi-hot input is invalid (optionally expose a `VALID` output). `HEX7SEG` takes one 4-bit nibble and drives active-high segments `a`…`g` for hexadecimal 0–F. The browser panel chains nibble → one-hot decode → 4-bit encode and also displays a 16-bit word on four seven-segment digits. Binary and hex are two notations for the same underlying word; the software word converter formats values, while the DLS decoder/encoder chips operate on electrical bits.

### Clocked registers, PC, flags, and memory interfaces

`MISK16_COMPUTER` now holds the architectural CPU state in raw-NAND master/slave latches:

- Eight 16-bit registers, an 8-bit PC, and Z/N/C flags persist while DLS simulation runs; no prebuilt register/DFF component is used.
- Press **0** to reset the PC, register file, and flags synchronously on the next rising edge of the DLS `CLOCK`.
- Press/release **2** to execute one instruction. A NAND-built key-history/edge-detect path prevents a held key from executing repeatedly.
- The resettable 8-bit PC increments or loads a branch target from `MISK16_CPU_STEP`. Its current value is available as `PC_CURRENT` and on the two-digit PC display.
- Instruction/tag/operand, external input, and data-memory values remain labeled manual input chips. The browser workbench provides 256-entry program storage and 4,096 × 16-bit data RAM, but those memories are not implemented inside this DLS panel.
- `MEM_READ_EN`, `MEM_WRITE_EN`, `MEM_ADDR_*`, and `MEM_WRITE_*` remain the explicit external data-memory interface. Z is zero-result, N is bit 15, and C is addition carry or subtraction no-borrow.

`ALU16` ADD/SUB uses `MISK16_CLA16`, a four-stage NAND Kogge–Stone prefix adder. It computes carry groups at distances 1, 2, 4, and 8, reducing logic depth versus a serial 16-bit ripple carry path. The original hierarchical ripple-adder chips remain available for comparison.

The user-supplied reset is synchronous: hold **0** until the clock next rises. Browser STEP/RUN remain software state transitions and are distinct from the hardware CLOCK in this DLS design.

## Central computer and CPU-step hierarchy

`MISK16_COMPUTER` is the top-level DLS panel. It contains one `MISK16_CPU_STEP`, NAND-built clocked state for PC/registers/flags, editable labeled `IN-1/4/8` chips for structured instruction and external memory inputs, `OUT-1/4/8` probes, a four-digit result display, and a two-digit PC display. Current/next state and CPU outputs are exposed as output pins. The `MISK16_TESTBENCH` custom-chip name is retained as an alias.

`MISK16_CPU_STEP` composes `OPCODE_DECODER`, `REGISTER_FILE_READ`, `REGISTER_FILE_NEXT`, `ALU16`, `INC8`, branch logic, flags, and external memory/I/O controls. On each step-key edge, its next-state outputs clock into the raw NAND register file, flags, and PC. The instruction decoder selects the ALU operation, destination register, memory action, output action, and branch condition. Wires are point-to-point; no shared tri-state line is used.

To try the integrated panel, reset with **0**. Load R1=5 by entering LDI (`OP_ID_HI/MID/LO=0/0/11`), `RD=1`, `IMM_LO=5`, `IMM_HI=0`, then press/release **2**. Repeat with `RD=2`, `IMM_LO=7`. Enter ADD (`OP_ID_LO=1`, `RA=1`, `RB=2`, `RD=0`) and press/release **2**. The execution display shows `000C`, `R0_LO_CURRENT` becomes 12, and the PC advances once per instruction.

## Testing checklist

1. In `ALU16`, set `A=0xAAAA`, `B=0x0F0F`: AND=`0x0A0A`, OR=`0xAFAF`, XOR=`0xA5A5`, XNOR=`0x5A5A`.
2. In `MISK16_CLA16`, test `0xFFFF + 1`: result `0x0000`, carry 1; test `7 + 5`: `12`, carry 0. The ALU uses this four-stage prefix adder instead of a 16-bit ripple chain.
3. Select ALU subtraction: `5 - 5` gives zero 1/no-borrow carry 1; `4 - 5` gives `0xFFFF`/no-borrow carry 0.
4. Test `ZERO16`: all result bits zero → Z=1; set any one bit → Z=0.
5. Verify the `ALU16` one-hot operation select enables exactly one result family at a time.
6. Use `MISK16_COMPUTER` to reset, load R1/R2 with LDI, add them, verify persistent R0/PC state, and confirm the reset key clears them. Test branch flags and external memory/I/O controls with the labeled manual inputs.
7. In the utility library, verify `ADD16`, `SUB16`, `INC16`, `COMPARE16`, the 16-bit word gates, and 16-bit muxes against the repository's deterministic vectors. These tools do not change the CPU ISA.
8. Use the browser workbench to store distinct values at data-word addresses `0x000`, `0x100`, and `0xFFF`, then LOAD them back to verify the full 12-bit, 4,096-word RAM.
9. Test all 16 `DECODER4TO16` inputs: exactly one D output should be high, and `ENCODER16TO4` should reproduce the input nibble. Confirm `HEX7SEG` displays 0–F and `HEX_DISPLAY16` maps each word nibble to the correct digit/segments.
