# MPL — Misk Programming Language

MPL is the programming language for MISK-16. It is a deliberately small, assembly-first language: each source instruction corresponds to one computer instruction, so beginners can see how a program changes registers and memory. Its readable mnemonics, `;` comments, hexadecimal literals, and familiar arithmetic/bitwise operations borrow from C/C++ without requiring braces, types, a compiler toolchain, or pointer syntax. MPL is **not** a C++ compiler and does not currently have C++ statements such as `if`, `while`, functions, or `cout`; use labels and branch instructions instead.

## Quick start

```asm
; Sum 1 + 2 + 3 + 4 + 5, then output 15
        LDI  R0, 0       ; total
        LDI  R1, 1       ; current value
        LDI  R2, 6       ; end value (exclusive)
loop:   CMP  R1, R2
        JZ   done
        ADD  R0, R0, R1
        ADDI R1, R1, 1
        JMP  loop
done:   OUT  R0
        HALT
```

In the workbench, choose **ASSEMBLE → RAM**, then press **STEP INSTRUCTION** repeatedly. The result appears in OUTPUT as unsigned and signed decimal (`15 / 15`). Change any R0–R7 value or PC directly in the register panel before or between steps. Assembly replaces program RAM; reset clears CPU/data state but keeps the loaded program.

## Machine model

- **Word size:** 16 bits. Values wrap modulo 65,536; the user interface shows unsigned values 0–65,535. Signed interpretation is two's complement (−32,768 to 32,767).
- **Registers:** R0–R7 are general-purpose 16-bit registers; PC is an 8-bit instruction address (0–255). All registers can be edited directly in the interface.
- **Program RAM:** up to 256 instructions, writable when a program is assembled. It is RAM, not a ROM. Instructions occupy one address each; labels resolve to instruction addresses.
- **Data RAM:** 256 words. LOAD and STORE use the low 8 bits of an address held in a register.
- **Execution:** one click on STEP performs one instruction. There is no free-running clock, clock chip, pulse generator, shared bus, or tri-state output. The app is a behavioral workbench; the DLS build notes describe the corresponding gate collections and the limits of implementing manual state edits in a gate simulator.
- **Flags:** Z is set when a result is zero; N is the result's bit 15; C is carry-out for addition and no-borrow for subtraction/compare. Instructions that produce a value update Z and N. CMP updates Z/N/C without changing its input registers. STORE and branches do not change flags.
- **Input/output:** edit INPUT VALUE, then execute `IN Rn` to sample it. `OUT Rn` copies the register to OUTPUT.

## Source format

- One instruction per line; spaces and tabs are interchangeable. Commas between operands are optional.
- A label is an identifier followed by a colon at the start of a line. Labels are case-insensitive, must be unique, and can share a line with an instruction.
- Comments begin with `;` or `//` and run to the end of the line.
- Register names are `R0` through `R7`.
- Integers are decimal (`42`, `-3`), hexadecimal (`0x2A`), or prefixed decimal (`#42`). A value must fit −32,768 through 65,535; it is stored as a 16-bit word.
- Brackets in memory operands mean “address contained in this register”: `[R3]`.
- Branch destinations are labels or numeric program addresses.

## Instruction reference

`d`, `a`, and `b` name registers; `value` is a 16-bit immediate; `target` is a label/address.

| Instruction | Effect |
|---|---|
| `LDI d, value` | Load immediate value into `d`; update Z/N. |
| `MOV d, a` | Copy `a` into `d`; update Z/N. |
| `ADD d, a, b` | `d = a + b` (16-bit wrap); set carry, Z, N. |
| `ADDI d, a, value` | `d = a + value`; set carry, Z, N. |
| `SUB d, a, b` | `d = a - b`; C means no borrow; update Z/N. |
| `AND d, a, b` | Bitwise AND; update Z/N. |
| `OR d, a, b` | Bitwise OR; update Z/N. |
| `XOR d, a, b` | Bitwise exclusive OR; update Z/N. |
| `XNOR d, a, b` | Bitwise NOT of XOR; update Z/N. |
| `NAND d, a, b` | Bitwise NOT of AND; update Z/N. |
| `NOR d, a, b` | Bitwise NOT of OR; update Z/N. |
| `NOT d` | Invert all bits of `d` in place; update Z/N. |
| `CMP a, b` | Compare by computing `a - b` for flags only. |
| `LOAD d, [a]` | Read data RAM at address `a` into `d`; update Z/N. |
| `STORE [a], b` | Write `b` to data RAM at address `a`. |
| `JMP target` | Set PC to target. |
| `JZ target` | Branch when Z=1. |
| `JNZ target` | Branch when Z=0. |
| `IN d` | Read INPUT VALUE into `d`; update Z/N. |
| `OUT a` | Show register `a` at OUTPUT. |
| `HALT` | Stop stepping until reset. |

There is no implicit stack, assembler directive, macro, multiplication/division instruction, or C++ expression parser. Use registers and the instructions above; arithmetic and bitwise operators are applied one instruction at a time. Branching to an address that has no loaded instruction halts with a diagnostic.

## More examples

### Read a value, add ten, output it

```asm
        IN   R0
        ADDI R0, R0, 10
        OUT  R0
        HALT
```

### Store and reload a word

```asm
        LDI  R0, 42       ; data address 0x2A
        LDI  R1, 1234
        STORE [R0], R1
        LDI  R1, 0
        LOAD R1, [R0]
        OUT  R1            ; outputs 1234
        HALT
```

### Bit masks

```asm
        LDI  R0, 0x00F0
        LDI  R1, 0x0FF0
        AND  R2, R0, R1   ; keep bits present in both
        XOR  R3, R0, R1   ; bits that differ
        OUT  R2
        HALT
```

## Beginner tips

1. Start with `LDI`, then inspect a register; one instruction per step makes cause and effect visible.
2. Use `CMP` immediately before `JZ`/`JNZ`, since any later result-producing instruction changes Z.
3. Registers and data RAM are independent: `STORE` copies a register to memory; `LOAD` copies memory back to a register.
4. Hex is convenient for masks (`0x00FF`); decimal is convenient for counts (`#10`).
5. Labels make loops easier to read than numeric addresses. The assembler checks invalid instructions, operand counts, register names, duplicate labels, and RAM size before writing the program.
