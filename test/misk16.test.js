'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const {
  PROGRAM_RAM_WORDS,
  DATA_RAM_WORDS,
  DATA_RAM_BYTES,
  DATA_ADDRESS_MASK,
  DEFAULT_PROGRAM,
  createMachine,
  assemble,
  loadProgram,
  executeInstruction,
  parseWordLiteral,
  parseBinaryWord,
  parseHexWord,
  formatBinaryWord,
  formatHexWord,
  OPCODE_IDS,
  encodeOpcodeWord,
  decodeOpcodeWord,
  decode4to16,
  encode16to4,
  decodeHexDigitSegments,
  exportDataRam,
  importDataRam,
} = require('../misk16.js');

function runToHalt(machine, limit = PROGRAM_RAM_WORDS) {
  let steps = 0;
  while (!machine.halted && steps < limit) {
    const result = executeInstruction(machine);
    assert.notEqual(result.type, 'error', result.message);
    assert.notEqual(result.type, 'missing', result.message);
    steps++;
  }
  assert.equal(machine.halted, true, `program did not halt within ${limit} steps`);
  return steps;
}

test('data RAM is exactly 8 KiB and independently word-addressed', () => {
  const machine = createMachine();
  assert.equal(DATA_RAM_WORDS, 4096);
  assert.equal(DATA_RAM_BYTES, 8192);
  assert.equal(DATA_ADDRESS_MASK, 0x0fff);
  assert.equal(machine.memory.length, 4096);
  assert.equal(machine.memory.byteLength, 8192);
  assert.ok(machine.memory instanceof Uint16Array);
  assert.equal(PROGRAM_RAM_WORDS, 256);
  assert.equal(machine.program.length, 0);
});

test('binary and hexadecimal encoders round-trip 16-bit values', () => {
  assert.equal(parseBinaryWord('1010 0101 1111 0000'), 0xa5f0);
  assert.equal(parseBinaryWord('0b1010_0101'), 0xa5);
  assert.equal(parseHexWord('0xA5_F0'), 0xa5f0);
  assert.equal(parseWordLiteral('0b1111_0000_0000_0001'), 0xf001);
  assert.equal(parseWordLiteral('-1'), 0xffff);
  const addInstruction = assemble('ADD R0, R1, R2')[0];
  assert.equal(addInstruction.opcodeId, OPCODE_IDS.ADD);
  assert.equal(addInstruction.opcodeWord, 0x0001);
  assert.equal(formatHexWord(0xa5f0), '0xA5F0');
  assert.equal(formatBinaryWord(0xa5f0), '1010 0101 1111 0000');
  assert.throws(() => parseBinaryWord('1'.repeat(17)), /1 to 16 binary digits/);
  assert.throws(() => parseHexWord('10000'), /1 to 4 hexadecimal digits/);
});

test('MPL assembler accepts binary, hexadecimal, and grouped numeric literals', () => {
  const machine = createMachine();
  loadProgram(machine, `LDI R0, 0b1010_0101\nLDI R1, 0x00A5\nHALT`);
  runToHalt(machine);
  assert.equal(machine.regs[0], 0x00a5);
  assert.equal(machine.regs[1], 0x00a5);
});

test('MPL opcode words round-trip with the leading 4-bit address/number field', () => {
  assert.equal(encodeOpcodeWord('ADD'), 0x0001);
  assert.equal(encodeOpcodeWord('SUB'), 0x0002);
  assert.equal(encodeOpcodeWord('ADD', 3), 0x3001);
  assert.deepEqual(decodeOpcodeWord(0x3001), { addressOrNumber: 3, opcodeId: 1, operation: 'ADD' });
  for (const [operation, opcodeId] of Object.entries(OPCODE_IDS)) {
    const word = encodeOpcodeWord(operation);
    assert.equal(word, opcodeId);
    assert.equal(decodeOpcodeWord(word).operation, operation);
  }
  assert.throws(() => encodeOpcodeWord('UNKNOWN'), /Unknown MPL operation code/);
  assert.throws(() => encodeOpcodeWord('ADD', 16), /4-bit value/);
});

test('4-to-16 decoder and 16-to-4 encoder round-trip every hex digit', () => {
  for (let digit = 0; digit < 16; digit++) {
    const outputs = decode4to16(digit);
    assert.equal(outputs.length, 16);
    assert.equal(outputs.filter(Boolean).length, 1);
    assert.equal(outputs[digit], true);
    assert.equal(encode16to4(outputs), digit);
  }
  assert.throws(() => encode16to4(Array(16).fill(false)), /Exactly one/);
  assert.throws(() => encode16to4([true, true, ...Array(14).fill(false)]), /Exactly one/);
});

test('hex digit decoder generates valid seven-segment patterns', () => {
  assert.deepEqual(decodeHexDigitSegments(8), { a: true, b: true, c: true, d: true, e: true, f: true, g: true });
  assert.deepEqual(decodeHexDigitSegments(1), { a: false, b: true, c: true, d: false, e: false, f: false, g: false });
  assert.throws(() => decodeHexDigitSegments(16), /between 0 and 15/);
});

test('8 KiB data RAM images export and import as little-endian 16-bit words', () => {
  const original = createMachine();
  original.memory[0] = 0x1234;
  original.memory[0x0fff] = 0xabcd;
  const image = exportDataRam(original);
  assert.equal(image.byteLength, DATA_RAM_BYTES);
  assert.deepEqual([...image.slice(0, 2)], [0x34, 0x12]);
  assert.deepEqual([...image.slice(-2)], [0xcd, 0xab]);

  const restored = createMachine();
  importDataRam(restored, image);
  assert.equal(restored.memory[0], 0x1234);
  assert.equal(restored.memory[0x0fff], 0xabcd);
  assert.throws(() => importDataRam(restored, new Uint8Array(10)), /exactly 8192 bytes/);
});

test('default MPL program loops, writes the last data word, reads it back, and outputs 15', () => {
  const machine = createMachine();
  const loaded = loadProgram(machine, DEFAULT_PROGRAM);
  assert.ok(loaded.length <= PROGRAM_RAM_WORDS);
  runToHalt(machine);
  assert.equal(machine.output, 15);
  assert.equal(machine.memory[0x0fff], 15);
  assert.equal(machine.regs[0], 15);
});

test('LOAD and STORE reach the top 12-bit address without aliasing word zero', () => {
  const machine = createMachine();
  machine.memory[0] = 0x1234;
  loadProgram(machine, `
    LDI R0, 0xFFFF
    LDI R1, 0xBEEF
    STORE [R0], R1
    LDI R2, 0x0FFF
    LOAD R3, [R2]
    HALT
  `);
  runToHalt(machine);
  assert.equal(machine.memory[0x0fff], 0xbeef);
  assert.equal(machine.memory[0], 0x1234);
  assert.equal(machine.regs[3], 0xbeef);
});

test('ADD wraps at 16 bits and reports zero and carry', () => {
  const machine = createMachine();
  loadProgram(machine, `LDI R0, 0xFFFF\nLDI R1, 1\nADD R2, R0, R1\nHALT`);
  executeInstruction(machine);
  executeInstruction(machine);
  executeInstruction(machine);
  assert.equal(machine.regs[2], 0);
  assert.equal(machine.z, 1);
  assert.equal(machine.n, 0);
  assert.equal(machine.c, 1);
});

test('SUB reports no-borrow carry and wraps negative results', () => {
  const machine = createMachine();
  loadProgram(machine, `LDI R0, 4\nLDI R1, 5\nSUB R2, R0, R1`);
  executeInstruction(machine);
  executeInstruction(machine);
  executeInstruction(machine);
  assert.equal(machine.regs[2], 0xffff);
  assert.equal(machine.z, 0);
  assert.equal(machine.n, 1);
  assert.equal(machine.c, 0);
});

test('NOT is a unary instruction and uses 16-bit complement semantics', () => {
  const machine = createMachine();
  loadProgram(machine, `LDI R0, 0x00FF\nNOT R0\nHALT`);
  executeInstruction(machine);
  executeInstruction(machine);
  assert.equal(machine.regs[0], 0xff00);
});

test('16-bit bitwise operations match the MISK logic vectors', () => {
  const machine = createMachine();
  loadProgram(machine, `
    LDI R0, 0xAAAA
    LDI R1, 0x0F0F
    AND R2, R0, R1
    OR R3, R0, R1
    XOR R4, R0, R1
    XNOR R5, R0, R1
    NAND R6, R0, R1
    NOR R7, R0, R1
    HALT
  `);
  runToHalt(machine);
  assert.equal(machine.regs[2], 0x0a0a);
  assert.equal(machine.regs[3], 0xafaf);
  assert.equal(machine.regs[4], 0xa5a5);
  assert.equal(machine.regs[5], 0x5a5a);
  assert.equal(machine.regs[6], 0xf5f5);
  assert.equal(machine.regs[7], 0x5050);
});

test('IN samples the editable input value and OUT exposes the register', () => {
  const machine = createMachine();
  machine.input = 0xcafe;
  loadProgram(machine, 'IN R0\nOUT R0\nHALT');
  runToHalt(machine);
  assert.equal(machine.regs[0], 0xcafe);
  assert.equal(machine.output, 0xcafe);
});

test('assembler enforces the writable 256-entry program capacity and 8-bit branch targets', () => {
  assert.equal(assemble(Array(PROGRAM_RAM_WORDS).fill('HALT').join('\n')).length, PROGRAM_RAM_WORDS);
  assert.throws(() => assemble(Array(PROGRAM_RAM_WORDS + 1).fill('HALT').join('\n')), /larger than 256/);
  assert.throws(() => assemble('JMP 256'), /branch target must be an address from 0 to 255/);
});

test('branch labels resolve and conditional branch executes against Z', () => {
  const machine = createMachine();
  loadProgram(machine, `
    LDI R0, 7
    CMP R0, R0
    JZ success
    LDI R1, 99
    JMP done
success: LDI R1, 42
done: HALT
  `);
  runToHalt(machine);
  assert.equal(machine.regs[1], 42);
  assert.equal(machine.pc, 7);
});
