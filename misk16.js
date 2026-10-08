(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.MISK16 = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  const WORD_MASK = 0xffff;
  const PROGRAM_RAM_WORDS = 256;
  const PROGRAM_ADDRESS_MASK = PROGRAM_RAM_WORDS - 1;
  const DATA_RAM_WORDS = 4096;
  const DATA_RAM_BYTES = DATA_RAM_WORDS * 2;
  const DATA_ADDRESS_MASK = DATA_RAM_WORDS - 1;
  const DATA_MEMORY_PAGE_WORDS = 16;
  const DATA_MEMORY_PAGE_COUNT = DATA_RAM_WORDS / DATA_MEMORY_PAGE_WORDS;

  const DEFAULT_PROGRAM = `; Sum 1 through 5, then round-trip the result through the last data RAM word.\n        LDI  R0, 0       ; running total\n        LDI  R1, 1       ; current number\n        LDI  R2, 6       ; stop before six\nloop:   CMP  R1, R2\n        JZ   done\n        ADD  R0, R0, R1\n        ADDI R1, R1, 1\n        JMP  loop\ndone:   LDI  R3, 0x0FFF  ; last address in 8 KiB data RAM\n        STORE [R3], R0\n        LDI  R0, 0\n        LOAD R0, [R3]\n        OUT  R0\n        HALT`;

  const arity = {
    LDI: 2, MOV: 2, ADD: 3, ADDI: 3, SUB: 3,
    AND: 3, OR: 3, XOR: 3, XNOR: 3, NAND: 3, NOR: 3,
    NOT: 1, CMP: 2, LOAD: 2, STORE: 2,
    JMP: 1, JZ: 1, JNZ: 1, IN: 1, OUT: 1, HALT: 0,
  };
  const OPCODE_IDS = Object.freeze({
    ADD: 1, SUB: 2, AND: 3, OR: 4, XOR: 5, XNOR: 6, NAND: 7, NOR: 8,
    NOT: 9, MOV: 10, LDI: 11, ADDI: 12, CMP: 13, LOAD: 14, STORE: 15,
    JMP: 16, JZ: 17, JNZ: 18, IN: 19, OUT: 20, HALT: 21,
  });
  const OPCODES_BY_ID = Object.freeze(Object.fromEntries(
    Object.entries(OPCODE_IDS).map(([operation, opcode]) => [opcode, operation]),
  ));

  function toWord(value) {
    return Number(value) & WORD_MASK;
  }

  function signed(value) {
    const word = toWord(value);
    return word & 0x8000 ? word - 0x10000 : word;
  }

  function parseWordLiteral(token) {
    const value = numberValue(String(token));
    if (!Number.isInteger(value) || value < -32768 || value > WORD_MASK) {
      throw new Error('Enter a value from -32768 through 65535.');
    }
    return toWord(value);
  }

  function parseBinaryWord(token) {
    const bits = String(token).trim().replace(/[\s_]/g, '').replace(/^0b/i, '');
    if (!/^[01]{1,16}$/.test(bits)) throw new Error('Enter 1 to 16 binary digits (0 or 1).');
    return Number.parseInt(bits, 2);
  }

  function parseHexWord(token) {
    const digits = String(token).trim().replace(/[\s_]/g, '').replace(/^0x/i, '');
    if (!/^[\da-f]{1,4}$/i.test(digits)) throw new Error('Enter 1 to 4 hexadecimal digits (0–F).');
    return Number.parseInt(digits, 16);
  }

  function formatBinaryWord(value) {
    const bits = toWord(value).toString(2).padStart(16, '0');
    return bits.match(/.{4}/g).join(' ');
  }

  function formatHexWord(value) {
    return `0x${toWord(value).toString(16).toUpperCase().padStart(4, '0')}`;
  }

  function encodeOpcodeWord(operation, addressOrNumber = 0) {
    const opcode = typeof operation === 'string' ? OPCODE_IDS[operation.toUpperCase()] : Number(operation);
    const prefix = Number(addressOrNumber);
    if (!Number.isInteger(opcode) || !Object.values(OPCODE_IDS).includes(opcode)) {
      throw new Error(`Unknown MPL operation code “${operation}”.`);
    }
    if (!Number.isInteger(prefix) || prefix < 0 || prefix > 15) {
      throw new RangeError('The leading address/number field must be a 4-bit value from 0 to 15.');
    }
    return ((prefix << 12) | opcode) & WORD_MASK;
  }

  function decodeOpcodeWord(word) {
    const code = toWord(word);
    const opcodeId = code & 0x0fff;
    return {
      addressOrNumber: code >>> 12,
      opcodeId,
      operation: OPCODES_BY_ID[opcodeId] || null,
    };
  }

  function decode4to16(value) {
    const digit = Number(value);
    if (!Number.isInteger(digit) || digit < 0 || digit > 15) {
      throw new RangeError('A 4-to-16 decoder input must be between 0 and 15.');
    }
    return Array.from({ length: 16 }, (_, output) => output === digit);
  }

  function encode16to4(oneHot) {
    let selected;
    if (Array.isArray(oneHot)) {
      if (oneHot.length !== 16) throw new RangeError('A 16-to-4 encoder requires 16 input lines.');
      selected = oneHot.flatMap((value, index) => value ? [index] : []);
    } else {
      const mask = Number(oneHot);
      if (!Number.isInteger(mask) || mask < 0 || mask > 0xffff) {
        throw new RangeError('A one-hot encoder mask must be a 16-bit unsigned value.');
      }
      selected = Array.from({ length: 16 }, (_, bit) => (mask >> bit) & 1 ? [bit] : []).flat();
    }
    if (selected.length !== 1) throw new Error('Exactly one encoder input must be high.');
    return selected[0];
  }

  const SEGMENT_PATTERNS = [
    'abcdef', 'bc', 'abdeg', 'abcdg', 'bcfg', 'acdfg', 'acdefg', 'abc',
    'abcdefg', 'abcdfg', 'abcefg', 'cdefg', 'adef', 'bcdeg', 'adefg', 'aefg',
  ];

  function decodeHexDigitSegments(value) {
    const digit = Number(value);
    if (!Number.isInteger(digit) || digit < 0 || digit > 15) {
      throw new RangeError('A seven-segment hex decoder input must be between 0 and 15.');
    }
    return Object.fromEntries('abcdefg'.split('').map(segment => [segment, SEGMENT_PATTERNS[digit].includes(segment)]));
  }

  function exportDataRam(machine) {
    const bytes = new Uint8Array(DATA_RAM_BYTES);
    for (let address = 0; address < DATA_RAM_WORDS; address++) {
      const word = machine.memory[address];
      bytes[address * 2] = word & 0xff;
      bytes[address * 2 + 1] = word >>> 8;
    }
    return bytes;
  }

  function importDataRam(machine, source) {
    const bytes = source instanceof Uint8Array ? source : new Uint8Array(source);
    if (bytes.byteLength !== DATA_RAM_BYTES) {
      throw new Error(`RAM image must be exactly ${DATA_RAM_BYTES} bytes.`);
    }
    for (let address = 0; address < DATA_RAM_WORDS; address++) {
      machine.memory[address] = bytes[address * 2] | (bytes[address * 2 + 1] << 8);
    }
    return machine.memory;
  }

  function createMachine() {
    return {
      regs: Array(8).fill(0),
      pc: 0,
      z: 0,
      n: 0,
      c: 0,
      input: 0,
      output: null,
      program: [],
      memory: new Uint16Array(DATA_RAM_WORDS),
      memoryPage: 0,
      halted: false,
    };
  }

  function numberValue(token, labels = {}) {
    const raw = token.trim();
    if (Object.prototype.hasOwnProperty.call(labels, raw.toUpperCase())) return labels[raw.toUpperCase()];
    const compact = raw.replace(/_/g, '');
    const binary = compact.match(/^([+-]?)0b([01]+)$/i);
    if (binary) return Number.parseInt(binary[2], 2) * (binary[1] === '-' ? -1 : 1);
    const hexadecimal = compact.match(/^([+-]?)0x([\da-f]+)$/i);
    if (hexadecimal) return Number.parseInt(hexadecimal[2], 16) * (hexadecimal[1] === '-' ? -1 : 1);
    if (/^#[-+]?\d+$/.test(raw)) return Number(raw.slice(1));
    if (/^[-+]?\d+$/.test(raw)) return Number(raw);
    throw new Error(`Expected a decimal, binary, hexadecimal number, or label, got “${raw}”.`);
  }

  function cleanLines(source) {
    return source.split(/\r?\n/).map((original, index) => {
      const text = original.replace(/(;|\/\/).*$/, '').trim();
      return { line: index + 1, text };
    }).filter(row => row.text);
  }

  function assemble(source) {
    if (typeof source !== 'string') throw new Error('Program source must be text.');

    const lines = cleanLines(source);
    const labels = {};
    let address = 0;
    const instructions = [];

    for (const row of lines) {
      let text = row.text;
      const labelMatch = text.match(/^([A-Za-z_][\w]*):/);
      if (labelMatch) {
        const label = labelMatch[1].toUpperCase();
        if (Object.prototype.hasOwnProperty.call(labels, label)) {
          throw new Error(`Line ${row.line}: duplicate label “${labelMatch[1]}”.`);
        }
        labels[label] = address;
        text = text.slice(labelMatch[0].length).trim();
        if (!text) continue;
      }

      const match = text.match(/^([A-Za-z]+)\b\s*(.*)$/);
      if (!match) throw new Error(`Line ${row.line}: expected an instruction or label.`);
      const op = match[1].toUpperCase();
      if (!Object.prototype.hasOwnProperty.call(arity, op)) {
        throw new Error(`Line ${row.line}: unknown instruction “${op}”.`);
      }
      const args = match[2].trim() ? match[2].split(/\s*,\s*|\s+/).filter(Boolean) : [];
      if (args.length !== arity[op]) {
        throw new Error(`Line ${row.line}: ${op} takes ${arity[op]} operand${arity[op] === 1 ? '' : 's'}, got ${args.length}.`);
      }
      if (address >= PROGRAM_RAM_WORDS) {
        throw new Error(`Program is larger than ${PROGRAM_RAM_WORDS} instruction words.`);
      }
      instructions.push({ op, args, line: row.line, text: row.text, address });
      address++;
    }

    const reg = (token, row) => {
      const match = token.toUpperCase().match(/^R([0-7])$/);
      if (!match) throw new Error(`Line ${row.line}: expected a register R0–R7, got “${token}”.`);
      return Number(match[1]);
    };

    const immediate = (token, row) => {
      try {
        const value = numberValue(token, labels);
        if (!Number.isInteger(value) || value < -32768 || value > WORD_MASK) {
          throw new Error('outside 16-bit range');
        }
        return toWord(value);
      } catch (error) {
        throw new Error(`Line ${row.line}: invalid 16-bit value “${token}” (${error.message}).`);
      }
    };

    const branchTarget = (token, row) => {
      let value;
      try {
        value = numberValue(token, labels);
      } catch (error) {
        throw new Error(`Line ${row.line}: invalid branch target “${token}” (${error.message}).`);
      }
      if (!Number.isInteger(value) || value < 0 || value >= PROGRAM_RAM_WORDS) {
        throw new Error(`Line ${row.line}: branch target must be an address from 0 to ${PROGRAM_ADDRESS_MASK}.`);
      }
      return value;
    };

    const compiled = instructions.map(row => {
      const args = row.args;
      switch (row.op) {
        case 'LDI': return { ...row, d: reg(args[0], row), value: immediate(args[1], row) };
        case 'MOV': return { ...row, d: reg(args[0], row), s: reg(args[1], row) };
        case 'NOT': case 'IN': case 'OUT': return { ...row, d: reg(args[0], row) };
        case 'ADD': case 'SUB': case 'AND': case 'OR': case 'XOR': case 'XNOR': case 'NAND': case 'NOR':
          return { ...row, d: reg(args[0], row), x: reg(args[1], row), y: reg(args[2], row) };
        case 'ADDI': return { ...row, d: reg(args[0], row), x: reg(args[1], row), value: immediate(args[2], row) };
        case 'CMP': return { ...row, x: reg(args[0], row), y: reg(args[1], row) };
        case 'LOAD': {
          const match = args[1].match(/^\[\s*(R[0-7])\s*\]$/i);
          if (!match) throw new Error(`Line ${row.line}: LOAD address must be [R0] through [R7].`);
          return { ...row, d: reg(args[0], row), x: reg(match[1], row) };
        }
        case 'STORE': {
          const match = args[0].match(/^\[\s*(R[0-7])\s*\]$/i);
          if (!match) throw new Error(`Line ${row.line}: STORE address must be [R0] through [R7].`);
          return { ...row, x: reg(match[1], row), y: reg(args[1], row) };
        }
        case 'JMP': case 'JZ': case 'JNZ': return { ...row, target: branchTarget(args[0], row) };
        default: return row;
      }
    });

    return compiled.map(instruction => ({
      ...instruction,
      opcodeId: OPCODE_IDS[instruction.op],
      opcodeWord: encodeOpcodeWord(instruction.op),
    }));
  }

  function loadProgram(machine, source) {
    const program = assemble(source);
    if (!program.length) throw new Error('There are no instructions to load.');
    machine.program = program;
    machine.pc = 0;
    machine.halted = false;
    machine.output = null;
    machine.z = 0;
    machine.n = 0;
    machine.c = 0;
    return program;
  }

  function setResultFlags(machine, value, carry = 0) {
    const word = toWord(value);
    machine.z = Number(word === 0);
    machine.n = Number(Boolean(word & 0x8000));
    machine.c = Number(Boolean(carry));
  }

  function executeInstruction(machine) {
    if (!machine.program.length) {
      return { type: 'error', message: 'No program loaded. Assemble MPL into RAM first.' };
    }
    if (machine.halted) {
      return { type: 'halted', message: 'Processor is halted. Reset to start again.' };
    }

    const address = machine.pc & PROGRAM_ADDRESS_MASK;
    const instruction = machine.program[address];
    if (!instruction) {
      machine.halted = true;
      return {
        type: 'missing',
        address,
        message: `No instruction at program address ${address}. Processor halted.`,
      };
    }

    machine.pc = (address + 1) & PROGRAM_ADDRESS_MASK;
    const write = (register, value) => { machine.regs[register] = toWord(value); };
    const a = instruction;

    switch (a.op) {
      case 'LDI': write(a.d, a.value); setResultFlags(machine, a.value); break;
      case 'MOV': write(a.d, machine.regs[a.s]); setResultFlags(machine, machine.regs[a.s]); break;
      case 'ADD': {
        const sum = machine.regs[a.x] + machine.regs[a.y];
        write(a.d, sum);
        setResultFlags(machine, sum, sum > WORD_MASK);
        break;
      }
      case 'ADDI': {
        const sum = machine.regs[a.x] + a.value;
        write(a.d, sum);
        setResultFlags(machine, sum, sum > WORD_MASK);
        break;
      }
      case 'SUB': {
        const x = machine.regs[a.x];
        const y = machine.regs[a.y];
        const difference = x - y;
        write(a.d, difference);
        setResultFlags(machine, difference, x >= y);
        break;
      }
      case 'AND': {
        const value = machine.regs[a.x] & machine.regs[a.y];
        write(a.d, value); setResultFlags(machine, value); break;
      }
      case 'OR': {
        const value = machine.regs[a.x] | machine.regs[a.y];
        write(a.d, value); setResultFlags(machine, value); break;
      }
      case 'XOR': {
        const value = machine.regs[a.x] ^ machine.regs[a.y];
        write(a.d, value); setResultFlags(machine, value); break;
      }
      case 'XNOR': {
        const value = ~(machine.regs[a.x] ^ machine.regs[a.y]);
        write(a.d, value); setResultFlags(machine, value); break;
      }
      case 'NAND': {
        const value = ~(machine.regs[a.x] & machine.regs[a.y]);
        write(a.d, value); setResultFlags(machine, value); break;
      }
      case 'NOR': {
        const value = ~(machine.regs[a.x] | machine.regs[a.y]);
        write(a.d, value); setResultFlags(machine, value); break;
      }
      case 'NOT': {
        const value = ~machine.regs[a.d];
        write(a.d, value); setResultFlags(machine, value); break;
      }
      case 'CMP': {
        const x = machine.regs[a.x];
        const y = machine.regs[a.y];
        const difference = toWord(x - y);
        machine.z = Number(x === y);
        machine.n = Number(Boolean(difference & 0x8000));
        machine.c = Number(x >= y);
        break;
      }
      case 'LOAD': {
        const dataAddress = machine.regs[a.x] & DATA_ADDRESS_MASK;
        const value = machine.memory[dataAddress];
        write(a.d, value);
        setResultFlags(machine, value);
        break;
      }
      case 'STORE': {
        const dataAddress = machine.regs[a.x] & DATA_ADDRESS_MASK;
        machine.memory[dataAddress] = machine.regs[a.y];
        break;
      }
      case 'JMP': machine.pc = a.target & PROGRAM_ADDRESS_MASK; break;
      case 'JZ': if (machine.z) machine.pc = a.target & PROGRAM_ADDRESS_MASK; break;
      case 'JNZ': if (!machine.z) machine.pc = a.target & PROGRAM_ADDRESS_MASK; break;
      case 'IN': write(a.d, machine.input); setResultFlags(machine, machine.input); break;
      case 'OUT': machine.output = machine.regs[a.d]; break;
      case 'HALT': machine.halted = true; break;
      default: throw new Error(`Unsupported instruction ${a.op}.`);
    }

    return { type: 'executed', address, instruction, halted: machine.halted };
  }

  function resetMachine(machine) {
    machine.regs.fill(0);
    machine.pc = 0;
    machine.z = 0;
    machine.n = 0;
    machine.c = 0;
    machine.output = null;
    machine.halted = false;
    machine.memory.fill(0);
    machine.input = 0;
  }

  return {
    WORD_MASK,
    PROGRAM_RAM_WORDS,
    PROGRAM_ADDRESS_MASK,
    DATA_RAM_WORDS,
    DATA_RAM_BYTES,
    DATA_ADDRESS_MASK,
    DATA_MEMORY_PAGE_WORDS,
    DATA_MEMORY_PAGE_COUNT,
    DEFAULT_PROGRAM,
    OPCODE_IDS,
    OPCODES_BY_ID,
    toWord,
    signed,
    parseWordLiteral,
    parseBinaryWord,
    parseHexWord,
    formatBinaryWord,
    formatHexWord,
    encodeOpcodeWord,
    decodeOpcodeWord,
    decode4to16,
    encode16to4,
    decodeHexDigitSegments,
    exportDataRam,
    importDataRam,
    createMachine,
    assemble,
    loadProgram,
    executeInstruction,
    resetMachine,
  };
});
