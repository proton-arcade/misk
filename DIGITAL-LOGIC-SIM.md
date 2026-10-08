# MISK-16 in Seb Lague's Digital Logic Sim

This repository includes a working browser workbench, a DLS circuit specification, and a native-format Digital Logic Sim project folder at [`MISK16-DLS/`](MISK16-DLS/). The browser workbench models a 16-bit CPU with 256 writable instruction entries and **8 KiB of writable data RAM** (4,096 × 16-bit words, addresses `0x000`–`0xFFF`), stored separately. The DLS project is a combinational manual-step implementation of the CPU datapath; it does not pretend that clockless feedback stores state or that DLS's clocked RAM is allowed. Accordingly, the DLS project exposes register/PC next-state values and program/data memory as external manual interfaces. DLS stores projects as a directory with `ProjectDescription.json` and `Chips/*.json`; the included project targets DLS 2.1.6 and can be saved by DLS after opening.

Reference project format and examples: [Seb Lague / Digital-Logic-Sim](https://github.com/SebLague/Digital-Logic-Sim) (MIT licensed). I also inspected the user-provided [`ZHT92Pong.zip`](https://github.com/proton-arcade/misk/blob/main/ZHT92Pong.zip) project (DLS 2.1.6). It contains `ZHT92/ProjectDescription.json` plus `ZHT92/Chips/*.json`. The description stores project/version settings, custom-chip names, and named collections; for example, its `SPLIT`, `BASIC`, `MEM`, and `CALC` collections sort reusable chips. A custom-chip JSON records its `Name`, `DLSVersion`, `InputPins`, `OutputPins`, `SubChips`, `Wires`, and `Displays`. Pins have IDs and bit counts; a wire connects a source and target by their owner/pin IDs. The example's `16-4` custom chip composes five reusable subchips and 17 wires, showing how to build hierarchy; it is a splitter/combiner, not an adder. Its `ALU-8` uses 152 subchips and 311 wires, a useful working reference but much flatter than the recursive adder hierarchy specified here. The sample also contains clocks, ROMs, buses, and tri-state buffers; those are examples of DLS features, not components to copy into this design.

## Import the ready-to-open project

DLS uses a project directory, not a single `.dls` file. The included [`MISK16-DLS/`](MISK16-DLS/) folder contains `ProjectDescription.json`, `Chips/*.json`, and a project-local README. The same folder is packaged as [`MISK16-DLS.zip`](MISK16-DLS.zip).

1. Extract/copy the whole `MISK16-DLS` folder into the DLS user-data `Projects` directory (the directory containing your other DLS project folders, such as `ZHT92`).
2. Restart DLS or refresh the project list and open `MISK16-DLS`.
3. Open the **00 · Open this first** collection, then open `MISK16_TESTBENCH`.
4. After importing/opening, use DLS's regular **Save** command. DLS can update the save timestamps/version metadata in its own application.

The files target DLS 2.1.6. The project contains 32 reusable custom chips and uses only NAND, split/merge, and manual IN/OUT components. It was validated against the DLS 2.1.6 JSON schema and circuit pin wiring, and its combinational circuits were simulated with a validator in this repository. The Unity application itself is not available in this environment, so the final import/save should be performed by DLS on your machine.

## Included chip collections

DLS collections sort reusable chips; they do not alter circuit behavior. The generated project organizes its library as follows:

1. **00 · Open this first:** `MISK16_TESTBENCH`, `MISK16_CPU_STEP`.
2. **01 · Primitive logic:** `INV`, `AND`, `OR`, `XOR`, `XNOR`, `NOR`, `AND3`, `AND4`, `OR_REDUCE8` (built-in NAND is the primitive).
3. **02 · Adders:** `FULL_ADDER_1`, `ADDER_1`, `ADDER_2`, `ADDER_4`, `ADDER_8`, `ADDER_16`.
4. **03 · Word logic and tools:** `MUX2_1`, `MUX2_8`, `MUX8_1`, `MUX8_8`, `ZERO16`, `ALU16`, `DECODER4TO16`, `ENCODER16TO4`, `HEX7SEG`, `RESULT_MUX5_8`.
5. **04 · CPU:** `OPCODE_DECODER`, `REGISTER_FILE_READ`, `REGISTER_FILE_NEXT`, `REGISTER_FILE_MANUAL`, `INC8`, `MISK16_CPU_STEP`.

The design uses a hierarchical ripple-carry adder rather than scattering unrelated bit-adders. Larger custom chips are composed from named smaller blocks for inspection and reuse.

## Hard constraints and storage caveat

- Do not place CLOCK, PULSE, BUS, 3-STATE BUFFER, or ROM chips. Do not build shared tri-state wiring. Connect each source to its destination with separate point-to-point wires, and split multi-bit signals into individual bit connections if that is clearer.
- In the browser workbench, assembled code resides in **256-entry writable program RAM** (8-bit PC), separate from **4,096 × 16-bit writable data RAM** (8 KiB, word addresses `0x000`–`0xFFF`). In the included DLS project, the current instruction and memory values are external manual inputs; `MISK16_CPU_STEP` exposes memory read/write enables, the low-12-bit data address, and write data. These are interfaces, not hidden storage. No DLS program/data RAM array is included because the available native RAM requires a prohibited clock. If a future DLS version supplies manually editable non-clocked memory, use 16 banks of 256 × 16-bit words for data RAM and decode all 12 address bits.
- Digital Logic Sim's built-in edge-triggered registers generally expose a CLOCK input. A physical DLS implementation cannot both use those chips and obey the no-clock constraint. For this specification, state is entered/edited manually at the register panel between evaluation steps. Implement each register as an externally editable 16-bit input bank feeding a register-state boundary in your chosen DLS version, or treat register values as manual test inputs/outputs while validating combinational blocks. Do not quietly substitute a clock, pulse, or three-state component. The browser workbench provides actual manual register editing and single-instruction state transitions.
- Browser STEP and RUN/PAUSE are explicit software operations that apply one or many state transitions; they are not a simulated circuit clock or pulse. The combinational circuit recipe below can be validated separately from state storage.

## Circuit collections and equations

The following are gate-level implementation equations/reference. The imported project contains the reusable logic chips listed above; its RAM storage is intentionally external/manual under the no-clock constraint. Use bit index `i = 0…15`. `A_i`, `B_i`, and `Y_i` are individual wires; there is no shared multi-driver wire.

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

Build 16 one-hot outputs from NOT and AND gates (or the widest matching gates): each output `D[n]` is true only for the corresponding four-bit address. Label each output `D00`…`D15` and group the outputs into four collections by high address bits if that helps layout. The included `DECODER4TO16` is used for opcode/register selections. A future clock-permitted 4,096-word physical RAM would split the 12-bit address into three nibbles, predecode each with this chip, then combine the one-hot outputs; that RAM selection array is **not** part of this no-clock project.

### `ENCODER16TO4` and `HEX7SEG`

`ENCODER16TO4` accepts one-hot inputs `D00`…`D15` and returns the selected index as `B3`…`B0`. Its equations are OR reductions of the active one-hot lines:

```
B3 = D08 OR D09 OR D10 OR D11 OR D12 OR D13 OR D14 OR D15
B2 = D04 OR D05 OR D06 OR D07 OR D12 OR D13 OR D14 OR D15
B1 = D02 OR D03 OR D06 OR D07 OR D10 OR D11 OR D14 OR D15
B0 = D01 OR D03 OR D05 OR D07 OR D09 OR D11 OR D13 OR D15
```

The input contract is exactly one asserted D line; zero-hot or multi-hot input is invalid (optionally expose a `VALID` output). `HEX7SEG` takes one 4-bit nibble and drives active-high segments `a`…`g` for hexadecimal 0–F. The browser panel chains nibble → one-hot decode → 4-bit encode and also displays a 16-bit word on four seven-segment digits. Binary and hex are two notations for the same underlying word; the software word converter formats values, while the DLS decoder/encoder chips operate on electrical bits.

### Manual registers, PC, flags, and memory interfaces

The generated DLS project makes state explicit instead of storing it in a prohibited clockless loop:

- `REGISTER_FILE_READ` reads one of eight externally entered 16-bit register values using 4-bit `RA`, `RB`, and `RD` selectors.
- `REGISTER_FILE_NEXT` produces `R0_NEXT`…`R7_NEXT` values from the current editable register inputs, destination, write-enable, and result word. The user manually copies those outputs back to the corresponding testbench inputs between evaluation steps.
- `INC8` calculates `PC + 1`; `MISK16_CPU_STEP` selects that value or the branch target and exposes `PC_NEXT`. The current PC is an editable input.
- Z/N/C are editable inputs with explicit next-flag outputs and a flag-write enable. Z is zero-result, N is bit 15, C is addition carry or subtraction no-borrow.
- In the browser workbench, `PROGRAM_RAM` is 256 writable instruction entries and `DATA_RAM` is 4,096 × 16-bit words (8 KiB). In DLS, the current instruction/opcode/operands and data-memory read word are supplied through editable testbench inputs. `MEM_READ_EN`, `MEM_WRITE_EN`, `MEM_ADDR_*`, and `MEM_WRITE_*` are external memory-control/data outputs; they are not persistent RAM chips.

Do not add DLS's clocked RAM/registers or claim that an unclocked combinational feedback loop stores state. Browser STEP/RUN are software state transitions; the DLS testbench requires manual re-entry of next-state values.

## `MISK16_CPU_STEP` hierarchy

The included `MISK16_CPU_STEP` composes `OPCODE_DECODER`, `REGISTER_FILE_READ`, `REGISTER_FILE_NEXT`, `ALU16`, `INC8`, branch logic, and memory/I/O interfaces. `MISK16_TESTBENCH` provides editable DLS `IN-1/4/8` chips for the current state, opcode and separate operand fields, plus `OUT-1/4/8` probes for results and next state. Enter an opcode ID and operands, inspect its outputs, then manually transfer the `NEXT` register/PC/flag values back to the editable inputs to perform another software-style step. The instruction decoder selects the ALU operation, destination register, memory action, output action, and branch condition. All wires are direct pin-to-pin connections; no shared tri-state line is used.

## Testing checklist

1. In `ALU16`, set `A=0xAAAA`, `B=0x0F0F`: AND=`0x0A0A`, OR=`0xAFAF`, XOR=`0xA5A5`, XNOR=`0x5A5A`.
2. In `ADDER_16`, test `0xFFFF + 1`: result `0x0000`, carry 1; test `7 + 5`: `12`, carry 0.
3. Select ALU subtraction: `5 - 5` gives zero 1/no-borrow carry 1; `4 - 5` gives `0xFFFF`/no-borrow carry 0.
4. Test `ZERO16`: all result bits zero → Z=1; set any one bit → Z=0.
5. Verify the `ALU16` one-hot operation select enables exactly one result family at a time.
6. Use `MISK16_TESTBENCH` to test the opcode decoder, manual register reads/next values, PC branches, and external memory/I/O controls. Re-enter NEXT values manually between transitions.
7. Use the browser workbench to store distinct values at data-word addresses `0x000`, `0x100`, and `0xFFF`, then LOAD them back to verify the full 12-bit, 4,096-word RAM.
8. Test all 16 `DECODER4TO16` inputs: exactly one D output should be high, and `ENCODER16TO4` should reproduce the input nibble. Confirm `HEX7SEG` displays 0–F.
