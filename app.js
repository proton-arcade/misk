const WORD_MASK = 0xffff;
const RAM_SIZE = 256;
const EXAMPLE = `; Add the numbers 1 through 5 and show the result (15).\n        LDI  R0, 0       ; running total\n        LDI  R1, 1       ; current number\n        LDI  R2, 6       ; stop before six\nloop:   CMP  R1, R2\n        JZ   done\n        ADD  R0, R0, R1\n        ADDI R1, R1, 1\n        JMP  loop\ndone:   OUT  R0\n        HALT`;
const state = { regs: Array(8).fill(0), pc: 0, z: 0, n: 0, c: 0, input: 0, output: null, program: [], memory: Array(RAM_SIZE).fill(0), memoryPage: 0, halted: false };
const $ = id => document.getElementById(id);

function toWord(value) { return Number(value) & WORD_MASK; }
function signed(value) { return (value & 0x8000) ? value - 0x10000 : value; }
function numberValue(token, labels = {}) {
  const raw = token.trim();
  if (Object.prototype.hasOwnProperty.call(labels, raw.toUpperCase())) return labels[raw.toUpperCase()];
  if (/^[-+]?0x[\da-f]+$/i.test(raw)) return Number.parseInt(raw.replace(/^\+/, ''), 16);
  if (/^#[-+]?\d+$/.test(raw)) return Number(raw.slice(1));
  if (/^[-+]?\d+$/.test(raw)) return Number(raw);
  throw new Error(`Expected a number or label, got “${raw}”.`);
}
function cleanLines(source) {
  return source.split(/\r?\n/).map((original, index) => {
    const text = original.replace(/(;|\/\/).*$/, '').trim();
    return { line: index + 1, text };
  }).filter(row => row.text);
}
const arity = { LDI: 2, MOV: 2, ADD: 3, ADDI: 3, SUB: 3, AND: 3, OR: 3, XOR: 3, XNOR: 3, NAND: 3, NOR: 3, NOT: 2, CMP: 2, LOAD: 2, STORE: 2, JMP: 1, JZ: 1, JNZ: 1, IN: 1, OUT: 1, HALT: 0 };
function assemble(source) {
  const lines = cleanLines(source);
  const labels = {};
  let address = 0;
  const instructions = [];
  for (const row of lines) {
    let text = row.text;
    const labelMatch = text.match(/^([A-Za-z_][\w]*):/);
    if (labelMatch) {
      const label = labelMatch[1].toUpperCase();
      if (Object.prototype.hasOwnProperty.call(labels, label)) throw new Error(`Line ${row.line}: duplicate label “${labelMatch[1]}”.`);
      labels[label] = address;
      text = text.slice(labelMatch[0].length).trim();
      if (!text) continue;
    }
    const match = text.match(/^([A-Za-z]+)\b\s*(.*)$/);
    if (!match) throw new Error(`Line ${row.line}: expected an instruction or label.`);
    const op = match[1].toUpperCase();
    if (!(op in arity)) throw new Error(`Line ${row.line}: unknown instruction “${op}”.`);
    const args = match[2].trim() ? match[2].split(/\s*,\s*|\s+/).filter(Boolean) : [];
    if (args.length !== arity[op]) throw new Error(`Line ${row.line}: ${op} takes ${arity[op]} operand${arity[op] === 1 ? '' : 's'}, got ${args.length}.`);
    if (address >= RAM_SIZE) throw new Error('Program is larger than 256 instruction words.');
    instructions.push({ op, args, line: row.line, text: row.text, address });
    address++;
  }
  const reg = (token, row) => {
    const m = token.toUpperCase().match(/^R([0-7])$/);
    if (!m) throw new Error(`Line ${row.line}: expected a register R0–R7, got “${token}”.`);
    return Number(m[1]);
  };
  const immediate = (token, row) => {
    try { const n = numberValue(token, labels); if (!Number.isInteger(n) || n < -32768 || n > 65535) throw new Error('outside 16-bit range'); return toWord(n); }
    catch (e) { throw new Error(`Line ${row.line}: invalid 16-bit value “${token}” (${e.message}).`); }
  };
  const compiled = instructions.map(row => {
    const a = row.args;
    let x;
    switch (row.op) {
      case 'LDI': return { ...row, d: reg(a[0], row), value: immediate(a[1], row) };
      case 'MOV': case 'NOT': case 'IN': case 'OUT': return { ...row, d: reg(a[0], row), s: a[1] ? reg(a[1], row) : null };
      case 'ADD': case 'SUB': case 'AND': case 'OR': case 'XOR': case 'XNOR': case 'NAND': case 'NOR': return { ...row, d: reg(a[0], row), x: reg(a[1], row), y: reg(a[2], row) };
      case 'ADDI': return { ...row, d: reg(a[0], row), x: reg(a[1], row), value: immediate(a[2], row) };
      case 'CMP': return { ...row, x: reg(a[0], row), y: reg(a[1], row) };
      case 'LOAD': {
        const m = a[1].match(/^\[\s*(R[0-7])\s*\]$/i); if (!m) throw new Error(`Line ${row.line}: LOAD address must be [R0] through [R7].`);
        return { ...row, d: reg(a[0], row), x: reg(m[1], row) };
      }
      case 'STORE': {
        const m = a[0].match(/^\[\s*(R[0-7])\s*\]$/i); if (!m) throw new Error(`Line ${row.line}: STORE address must be [R0] through [R7].`);
        return { ...row, x: reg(m[1], row), y: reg(a[1], row) };
      }
      case 'JMP': case 'JZ': case 'JNZ': return { ...row, target: immediate(a[0], row) };
      default: return row;
    }
  });
  return compiled;
}
function setResultFlags(value, carry = 0) { const v = toWord(value); state.z = Number(v === 0); state.n = Number(Boolean(v & 0x8000)); state.c = Number(Boolean(carry)); }
function step() {
  if (!state.program.length) { message('No program loaded. Assemble MPL into RAM first.', true); return; }
  if (state.halted) { message('Processor is halted. Reset to start again.'); return; }
  const address = state.pc & 0xff;
  const ins = state.program[address];
  if (!ins) { state.halted = true; message(`No instruction at program address ${address}. Processor halted.`, true); render(); return; }
  state.pc = (address + 1) & 0xff;
  const a = ins;
  const write = (r, v) => { state.regs[r] = toWord(v); };
  switch (a.op) {
    case 'LDI': write(a.d, a.value); setResultFlags(a.value); break;
    case 'MOV': write(a.d, state.regs[a.s]); setResultFlags(state.regs[a.s]); break;
    case 'ADD': { const sum = state.regs[a.x] + state.regs[a.y]; write(a.d, sum); setResultFlags(sum, sum > WORD_MASK); break; }
    case 'ADDI': { const sum = state.regs[a.x] + a.value; write(a.d, sum); setResultFlags(sum, sum > WORD_MASK); break; }
    case 'SUB': { const x = state.regs[a.x], y = state.regs[a.y], diff = x - y; write(a.d, diff); setResultFlags(diff, x >= y); break; }
    case 'AND': write(a.d, state.regs[a.x] & state.regs[a.y]); setResultFlags(state.regs[a.x] & state.regs[a.y]); break;
    case 'OR': write(a.d, state.regs[a.x] | state.regs[a.y]); setResultFlags(state.regs[a.x] | state.regs[a.y]); break;
    case 'XOR': write(a.d, state.regs[a.x] ^ state.regs[a.y]); setResultFlags(state.regs[a.x] ^ state.regs[a.y]); break;
    case 'XNOR': write(a.d, ~(state.regs[a.x] ^ state.regs[a.y])); setResultFlags(~(state.regs[a.x] ^ state.regs[a.y])); break;
    case 'NAND': write(a.d, ~(state.regs[a.x] & state.regs[a.y])); setResultFlags(~(state.regs[a.x] & state.regs[a.y])); break;
    case 'NOR': write(a.d, ~(state.regs[a.x] | state.regs[a.y])); setResultFlags(~(state.regs[a.x] | state.regs[a.y])); break;
    case 'NOT': { const result = ~state.regs[a.d]; write(a.d, result); setResultFlags(result); break; }
    case 'CMP': { const x = state.regs[a.x], y = state.regs[a.y], diff = toWord(x - y); state.z = Number(x === y); state.n = Number(Boolean(diff & 0x8000)); state.c = Number(x >= y); break; }
    case 'LOAD': write(a.d, state.memory[state.regs[a.x] & 0xff]); setResultFlags(state.regs[a.d]); break;
    case 'STORE': state.memory[state.regs[a.x] & 0xff] = state.regs[a.y]; break;
    case 'JMP': state.pc = a.target & 0xff; break;
    case 'JZ': if (state.z) state.pc = a.target & 0xff; break;
    case 'JNZ': if (!state.z) state.pc = a.target & 0xff; break;
    case 'IN': write(a.d, state.input); setResultFlags(state.input); break;
    case 'OUT': state.output = state.regs[a.d]; break;
    case 'HALT': state.halted = true; break;
  }
  message(`Executed ${a.op} at ${address.toString().padStart(3, '0')} · source line ${a.line}${state.halted ? ' · halted' : ''}`);
  render();
}
function message(text, error = false) { $('machineMessage').textContent = text; $('machineMessage').style.color = error ? '#f0a19b' : ''; }
function render() {
  const regRoot = $('registers');
  regRoot.innerHTML = state.regs.map((value, i) => `<div class="reg-card"><label for="reg${i}">R${i}</label><input id="reg${i}" type="number" min="0" max="65535" value="${value}" aria-label="Register R${i} value"></div>`).join('');
  state.regs.forEach((_, i) => { $(`reg${i}`).addEventListener('change', e => { state.regs[i] = toWord(e.target.value); e.target.value = state.regs[i]; }); });
  $('pcInput').value = state.pc;
  $('flagsValue').textContent = `${state.z} · ${state.n} · ${state.c}`;
  $('outputValue').textContent = state.output === null ? '—' : `${state.output} / ${signed(state.output)}`;
  $('programCount').textContent = `${state.program.length} INSTRUCTION${state.program.length === 1 ? '' : 'S'}`;
  const list = $('programMemory');
  if (!state.program.length) { list.className = 'memory-list empty'; list.textContent = 'Assemble a program to write instructions into RAM.'; }
  else {
    list.className = 'memory-list';
    list.innerHTML = state.program.map(ins => `<div class="instruction-row ${ins.address === (state.pc & 0xff) && !state.halted ? 'active' : ''}"><span class="addr">${ins.address.toString().padStart(3, '0')}</span><span>${escapeHtml(ins.text.trim())}</span><span class="word">${ins.op}</span></div>`).join('');
    const active = list.querySelector('.active'); if (active) active.scrollIntoView({ block: 'nearest' });
  }
  const first = state.memoryPage * 16;
  $('memoryPage').value = state.memoryPage;
  $('memoryRange').textContent = `0x${first.toString(16).toUpperCase().padStart(2, '0')}–0x${(first + 15).toString(16).toUpperCase().padStart(2, '0')}`;
  $('dataMemory').innerHTML = Array.from({ length: 16 }, (_, offset) => {
    const address = first + offset;
    return `<label class="mem-cell"><span>${address.toString(16).toUpperCase().padStart(2, '0')}</span><input data-memory="${address}" type="number" min="0" max="65535" value="${state.memory[address]}" aria-label="Data RAM address ${address}"></label>`;
  }).join('');
  $('dataMemory').querySelectorAll('input').forEach(input => input.addEventListener('change', e => { const i = Number(e.target.dataset.memory); state.memory[i] = toWord(e.target.value); e.target.value = state.memory[i]; }));
  $('stepBtn').textContent = state.halted ? 'PROCESSOR HALTED' : 'STEP INSTRUCTION';
  $('stepBtn').disabled = state.halted;
}
function escapeHtml(s) { return s.replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])); }
function assembleToRAM() {
  try {
    const program = assemble($('source').value);
    if (!program.length) throw new Error('There are no instructions to load.');
    state.program = program;
    state.pc = 0; state.halted = false; state.output = null; state.z = 0; state.n = 0; state.c = 0;
    $('assemblyStatus').textContent = `Assembled ${program.length} instruction${program.length === 1 ? '' : 's'} · written to program RAM`;
    message(`Program loaded into writable RAM · ${program.length} instruction${program.length === 1 ? '' : 's'}.`);
    render();
  } catch (err) {
    $('assemblyStatus').textContent = 'Assembly error';
    message(err.message, true);
  }
}
$('source').value = EXAMPLE;
$('source').addEventListener('input', () => { const count = $('source').value.split('\n').length; $('lineNumbers').textContent = Array.from({ length: count }, (_, i) => i + 1).join('\n'); });
$('source').dispatchEvent(new Event('input'));
$('exampleBtn').addEventListener('click', () => { $('source').value = EXAMPLE; $('source').dispatchEvent(new Event('input')); $('assemblyStatus').textContent = 'Example loaded · ready to assemble'; });
$('assembleBtn').addEventListener('click', assembleToRAM);
$('stepBtn').addEventListener('click', step);
$('pcInput').addEventListener('change', e => { state.pc = toWord(e.target.value) & 0xff; render(); });
$('inputValue').addEventListener('change', e => { state.input = toWord(e.target.value); e.target.value = state.input; });
$('memoryPage').addEventListener('change', e => { state.memoryPage = Math.max(0, Math.min(15, Number(e.target.value) || 0)); render(); });
$('memoryPrev').addEventListener('click', () => { state.memoryPage = Math.max(0, state.memoryPage - 1); render(); });
$('memoryNext').addEventListener('click', () => { state.memoryPage = Math.min(15, state.memoryPage + 1); render(); });
$('resetBtn').addEventListener('click', () => { state.regs.fill(0); state.pc = 0; state.z = state.n = state.c = 0; state.output = null; state.halted = false; state.memory.fill(0); $('inputValue').value = 0; state.input = 0; message('Registers, flags, data RAM, and output reset. Program RAM was kept.'); render(); });
render();
