# MPL — MISK-16 language summary

MPL is the assembly language for MISK-16. Write one mnemonic per line, assemble it into writable program RAM, then step or run the program. The CPU has 16-bit words, eight general registers (`R0`–`R7`), an 8-bit program counter, and 8 KiB of separate data RAM.

## Binary opcode words

MPL assigns each mnemonic a 12-bit operation code. For the 16-bit opcode word, the **first four bits** are an address/number field (`A`), and the **last twelve bits** are the operation code:

```text
AAAA OOOO OOOO OOOO
^^^^ ^^^^^^^^^^^^
address/number    operation code
4 bits            12 bits
```

With the address/number field set to `0000`, the first two opcode words are:

```text
0000 0000 0000 0001  ADD  - add two register values
0000 0000 0000 0010  SUB  - subtract one register value from another
```

For example, a leading field of `0011` combined with the ADD code is `0011 0000 0000 0001`. The field is an unsigned 4-bit value (0–15); it is **not** the full 12-bit data-RAM address.

**Important:** These are opcode words, not complete serialized instructions. Register operands, immediates, branch targets, and memory-address registers are separate fields in the workbench's instruction records. The browser assembles and executes MPL source; it does not load raw binary opcode words as executable programs. Opcode IDs are shown in the program panel as hexadecimal tags.

| Opcode word (field `0000`) | Mnemonic | Source form | Meaning |
|---|---|---|---|
| `0000 0000 0000 0001` | `ADD` | `ADD d, a, b` | `d = a + b`; set carry, Z, N. |
| `0000 0000 0000 0010` | `SUB` | `SUB d, a, b` | `d = a - b`; C means no borrow. |
| `0000 0000 0000 0011` | `AND` | `AND d, a, b` | Bitwise AND. |
| `0000 0000 0000 0100` | `OR` | `OR d, a, b` | Bitwise OR. |
| `0000 0000 0000 0101` | `XOR` | `XOR d, a, b` | Bitwise exclusive OR. |
| `0000 0000 0000 0110` | `XNOR` | `XNOR d, a, b` | Bitwise NOT of XOR. |
| `0000 0000 0000 0111` | `NAND` | `NAND d, a, b` | Bitwise NOT of AND. |
| `0000 0000 0000 1000` | `NOR` | `NOR d, a, b` | Bitwise NOT of OR. |
| `0000 0000 0000 1001` | `NOT` | `NOT d` | Invert `d` in place. |
| `0000 0000 0000 1010` | `MOV` | `MOV d, a` | Copy `a` to `d`. |
| `0000 0000 0000 1011` | `LDI` | `LDI d, value` | Load a constant into `d`. |
| `0000 0000 0000 1100` | `ADDI` | `ADDI d, a, value` | Add a constant to `a`. |
| `0000 0000 0000 1101` | `CMP` | `CMP a, b` | Set Z/N/C from `a - b`; do not write a register. |
| `0000 0000 0000 1110` | `LOAD` | `LOAD d, [a]` | Load from data RAM at the address in `a`. |
| `0000 0000 0000 1111` | `STORE` | `STORE [a], b` | Store `b` at the data-RAM address in `a`. |
| `0000 0000 0001 0000` | `JMP` | `JMP target` | Jump to program address `target`. |
| `0000 0000 0001 0001` | `JZ` | `JZ target` | Jump when Z is 1. |
| `0000 0000 0001 0010` | `JNZ` | `JNZ target` | Jump when Z is 0. |
| `0000 0000 0001 0011` | `IN` | `IN d` | Copy INPUT WORD into `d`. |
| `0000 0000 0001 0100` | `OUT` | `OUT a` | Copy register `a` to OUTPUT. |
| `0000 0000 0001 0101` | `HALT` | `HALT` | Stop execution. |

The core can encode and decode these opcode words. The address/number nibble defaults to zero in assembled opcode tags; normal MPL operands are stored separately and are not replaced by that nibble.

## Registers, memory, and flags

- **Registers:** `R0`–`R7` are editable 16-bit general-purpose registers. `PC` is an editable 8-bit program address from 0 to 255.
- **Program RAM:** up to 256 writable instruction entries. Each MPL source instruction occupies one program address; labels resolve to those addresses. Program RAM is separate from data RAM and is not ROM.
- **Data RAM:** 4,096 × 16-bit words = 8,192 bytes (8 KiB). It is word-addressed at `0x000`–`0xFFF`. `LOAD` and `STORE` use the low 12 bits of the address in a register.
- **Flags:** `Z` is set for a zero result; `N` is result bit 15; `C` is addition carry or subtraction/compare no-borrow. The UI flags can be edited for tests. `CMP` updates flags without changing its source registers.
- **Execution:** STEP executes one instruction. RUN repeats software steps until HALT, a missing instruction, the safety limit, or PAUSE. RUN is not a simulated clock or pulse.
- **Input/output:** INPUT WORD accepts decimal, hexadecimal, or binary. `IN` reads it; `OUT` displays unsigned/signed decimal, hex, and binary.

## MPL source rules

- One instruction per line. Commas between operands are optional.
- Labels use `name:` and can share a line with an instruction. Labels are case-insensitive.
- Comments start with `;` or `//`.
- Registers are `R0` through `R7`. Memory operands use brackets, such as `[R3]`.
- Numeric literals: decimal (`42`, `-3`, `#42`), hexadecimal (`0x2A`), or binary (`0b1010_0101`). Underscores can group digits. Values must fit −32,768 through 65,535 and are stored as 16-bit words.
- Branch targets are labels or program addresses from 0 through 255.

## Example program

This program adds 1 through 5, stores the result at the last data-RAM word, reloads it, and outputs 15.

```asm
        LDI  R0, 0
        LDI  R1, 1
        LDI  R2, 6
loop:   CMP  R1, R2
        JZ   done
        ADD  R0, R0, R1
        ADDI R1, R1, 1
        JMP  loop
done:   LDI  R3, 0x0FFF
        STORE [R3], R0
        LDI  R0, 0
        LOAD R0, [R3]
        OUT  R0
        HALT
```

**Start:** assemble into RAM, then press STEP or RUN. Output is `15 / 15`; data word `0xFFF` contains 15. Reset clears registers, flags, data RAM, input, and output while retaining the loaded program.

## Word and decoder tools

The word panel converts 16-bit binary and hex both ways, shows unsigned/signed decimal, displays four hex digits on seven-segment indicators, and lets you toggle bits or transfer a word to/from a register or PC. The 4-to-16 decoder selects one `D00`–`D15` line for a hex digit; the 16-to-4 encoder converts that one-hot line back to the nibble. The assembler also accepts binary immediates, for example `LDI R0, 0b1010_0101`.

MPL is a small assembly language, not a high-level language: it has no implicit stack, functions, multiplication/division, macros, or C-style control structures. Use labels and branch instructions for loops and decisions.
