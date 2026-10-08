# MISK-16 DLS project (Digital Logic Sim 2.1.6)

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
