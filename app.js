const {
  PROGRAM_RAM_WORDS,
  PROGRAM_ADDRESS_MASK,
  DATA_RAM_WORDS,
  DATA_RAM_BYTES,
  DATA_MEMORY_PAGE_WORDS,
  DATA_MEMORY_PAGE_COUNT,
  DEFAULT_PROGRAM,
  toWord,
  signed,
  parseWordLiteral,
  parseBinaryWord,
  parseHexWord,
  formatBinaryWord,
  formatHexWord,
  decode4to16,
  encode16to4,
  decodeHexDigitSegments,
  exportDataRam,
  importDataRam,
  createMachine,
  loadProgram,
  executeInstruction,
  resetMachine,
} = window.MISK16;

const state = createMachine();
const $ = id => document.getElementById(id);
const RUN_DELAY_MS = 45;
const RUN_STEP_LIMIT = 100000;
let converterWord = 0;
let runTimer = null;
let runActive = false;
let runSteps = 0;

function message(text, error = false) {
  $('machineMessage').textContent = text;
  $('machineMessage').style.color = error ? '#f0a19b' : '';
}

function formatDataAddress(address) {
  return address.toString(16).toUpperCase().padStart(3, '0');
}

function render() {
  const regRoot = $('registers');
  regRoot.innerHTML = state.regs.map((value, index) => `
    <div class="reg-card">
      <label for="reg${index}">R${index}</label>
      <input id="reg${index}" type="number" min="0" max="65535" value="${value}" aria-label="Register R${index} value">
    </div>`).join('');
  state.regs.forEach((_, index) => {
    $(`reg${index}`).addEventListener('change', event => {
      state.regs[index] = toWord(event.target.value);
      if (runActive) stopProgram(false);
      else event.target.value = state.regs[index];
    });
  });

  const dataRamKiB = DATA_RAM_BYTES / 1024;
  $('dataRamSpec').textContent = `${dataRamKiB.toLocaleString()} KiB`;
  $('dataRamDetails').textContent = `${DATA_RAM_WORDS.toLocaleString()} × 16 · ${dataRamKiB.toLocaleString()} KiB · EDITABLE`;
  $('pcInput').value = state.pc;
  $('flagZ').checked = Boolean(state.z);
  $('flagN').checked = Boolean(state.n);
  $('flagC').checked = Boolean(state.c);
  $('outputValue').textContent = state.output === null ? '—' : `${state.output} / ${signed(state.output)}`;
  $('outputHex').textContent = state.output === null ? 'HEX —' : `HEX ${formatHexWord(state.output)}`;
  $('outputBinary').textContent = state.output === null ? 'BIN —' : `BIN ${formatBinaryWord(state.output)}`;
  $('programCount').textContent = `${state.program.length} / ${PROGRAM_RAM_WORDS} INSTRUCTIONS`;

  const programList = $('programMemory');
  if (!state.program.length) {
    programList.className = 'memory-list empty';
    programList.textContent = 'Assemble a program to write instructions into writable program RAM.';
  } else {
    programList.className = 'memory-list';
    programList.innerHTML = state.program.map(instruction => `
      <div class="instruction-row ${instruction.address === (state.pc & PROGRAM_ADDRESS_MASK) && !state.halted ? 'active' : ''}">
        <span class="addr">${instruction.address.toString().padStart(3, '0')}</span>
        <span>${escapeHtml(instruction.text.trim())}</span>
        <span class="word" title="Binary opcode: ${formatBinaryWord(instruction.opcodeWord)}">${formatHexWord(instruction.opcodeWord)}</span>
      </div>`).join('');
    const active = programList.querySelector('.active');
    if (active) active.scrollIntoView({ block: 'nearest' });
  }

  const firstAddress = state.memoryPage * DATA_MEMORY_PAGE_WORDS;
  const lastAddress = firstAddress + DATA_MEMORY_PAGE_WORDS - 1;
  $('memoryPage').value = state.memoryPage;
  $('memoryRange').textContent = `0x${formatDataAddress(firstAddress)}–0x${formatDataAddress(lastAddress)}`;
  $('memoryPrev').disabled = state.memoryPage === 0;
  $('memoryNext').disabled = state.memoryPage === DATA_MEMORY_PAGE_COUNT - 1;
  $('dataMemory').innerHTML = Array.from({ length: DATA_MEMORY_PAGE_WORDS }, (_, offset) => {
    const address = firstAddress + offset;
    return `<label class="mem-cell"><span>${formatDataAddress(address)}</span><input data-memory="${address}" type="number" min="0" max="65535" value="${state.memory[address]}" aria-label="Data RAM word address ${formatDataAddress(address)}"></label>`;
  }).join('');
  $('dataMemory').querySelectorAll('input').forEach(input => input.addEventListener('change', event => {
    const address = Number(event.target.dataset.memory);
    state.memory[address] = toWord(event.target.value);
    if (runActive) stopProgram(false);
    else event.target.value = state.memory[address];
  }));

  $('stepBtn').textContent = state.halted ? 'PROCESSOR HALTED' : 'STEP INSTRUCTION';
  $('stepBtn').disabled = state.halted || runActive;
  $('runBtn').disabled = state.halted || runActive || state.program.length === 0;
  $('pauseBtn').disabled = !runActive;
  $('executionModeLabel').textContent = runActive ? 'RUNNING · SOFTWARE STEPS' : 'MANUAL STEP MODE';
  $('executionMode').classList.toggle('is-running', runActive);
}

function escapeHtml(text) {
  return text.replace(/[&<>"']/g, character => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[character]));
}

function downloadFile(filename, content, mimeType) {
  const url = URL.createObjectURL(new Blob([content], { type: mimeType }));
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

function renderWordConverter(sourceId = null) {
  const binaryInput = $('binaryWord');
  const hexInput = $('hexWord');
  if (!(sourceId === 'binaryWord' && document.activeElement === binaryInput)) {
    binaryInput.value = formatBinaryWord(converterWord);
  }
  if (!(sourceId === 'hexWord' && document.activeElement === hexInput)) {
    hexInput.value = formatHexWord(converterWord);
  }

  $('wordUnsigned').textContent = String(converterWord);
  $('wordSigned').textContent = String(signed(converterWord));
  $('wordHexReadout').textContent = formatHexWord(converterWord);
  $('wordBits').querySelectorAll('[data-bit]').forEach(button => {
    const bit = Number(button.dataset.bit);
    const high = Boolean(converterWord & (1 << bit));
    button.classList.toggle('is-one', high);
    button.setAttribute('aria-pressed', String(high));
    button.querySelector('.bit-value').textContent = high ? '1' : '0';
  });

  const hexDigits = converterWord.toString(16).toUpperCase().padStart(4, '0');
  $('hexDisplay').innerHTML = [...hexDigits].map((character, position) => {
    const digit = Number.parseInt(character, 16);
    const segments = decodeHexDigitSegments(digit);
    const segmentMarkup = Object.entries(segments).map(([name, active]) =>
      `<i class="segment segment-${name}${active ? ' on' : ''}" aria-hidden="true"></i>`).join('');
    return `<div class="seven-seg-cell"><span class="seven-seg-position">${3 - position}</span><div class="seven-seg-digit" aria-label="Hex digit ${character}">${segmentMarkup}</div><b>${character}</b></div>`;
  }).join('');
}

function handleConverterInput(inputId, parser, baseName) {
  const value = $(inputId).value.trim();
  if (!value) {
    $('wordStatus').textContent = `Enter a ${baseName} word to encode or decode.`;
    $('wordStatus').classList.remove('error');
    return;
  }
  try {
    converterWord = parser(value);
    renderWordConverter(inputId);
    $('wordStatus').textContent = `${baseName} decoded to ${formatHexWord(converterWord)} · ${formatBinaryWord(converterWord)}.`;
    $('wordStatus').classList.remove('error');
  } catch (error) {
    $('wordStatus').textContent = error.message;
    $('wordStatus').classList.add('error');
  }
}

function renderDecoder() {
  const value = Number($('decoderInput').value);
  const decoded = decode4to16(value);
  const encoded = encode16to4(decoded);
  const binary = value.toString(2).padStart(4, '0');
  $('decoderBinary').textContent = binary;
  $('encodedDigit').textContent = `0x${encoded.toString(16).toUpperCase()} · ${encoded.toString(2).padStart(4, '0')}`;
  $('decoderOutputs').querySelectorAll('[data-output]').forEach(output => {
    const index = Number(output.dataset.output);
    output.classList.toggle('active', decoded[index]);
    output.setAttribute('aria-label', `D${String(index).padStart(2, '0')}: ${decoded[index] ? 'high' : 'low'}`);
  });
  $('decoderStatus').textContent = `D${String(value).padStart(2, '0')} is the only high line; the 16-to-4 encoder returns ${binary}.`;
}

function initializeLogicTools() {
  $('wordBits').innerHTML = Array.from({ length: 16 }, (_, column) => {
    const bit = 15 - column;
    return `<button type="button" class="word-bit" data-bit="${bit}" aria-pressed="false" aria-label="Toggle bit ${bit}"><span> b${String(bit).padStart(2, '0')}</span><b class="bit-value">0</b></button>`;
  }).join('');
  $('wordBits').querySelectorAll('[data-bit]').forEach(button => button.addEventListener('click', () => {
    converterWord ^= 1 << Number(button.dataset.bit);
    renderWordConverter();
    $('wordStatus').textContent = `Bit toggled · ${formatHexWord(converterWord)} · ${formatBinaryWord(converterWord)}.`;
    $('wordStatus').classList.remove('error');
  }));

  $('wordRegister').innerHTML = `${state.regs.map((_, register) => `<option value="${register}">R${register}</option>`).join('')}<option value="pc">PC · 8-bit</option>`;
  $('decoderInput').innerHTML = Array.from({ length: 16 }, (_, value) => {
    const hex = value.toString(16).toUpperCase();
    const binary = value.toString(2).padStart(4, '0');
    return `<option value="${value}">${hex} · ${binary}</option>`;
  }).join('');
  $('decoderOutputs').innerHTML = Array.from({ length: 16 }, (_, output) =>
    `<div class="decoder-led" data-output="${output}"><span>D${String(output).padStart(2, '0')}</span><i aria-hidden="true"></i></div>`).join('');
  $('decoderInput').addEventListener('change', renderDecoder);
  $('readRegisterBtn').addEventListener('click', () => {
    stopProgram(false);
    const target = $('wordRegister').value;
    converterWord = target === 'pc' ? state.pc : state.regs[Number(target)];
    renderWordConverter();
    const name = target === 'pc' ? 'PC' : `R${target}`;
    $('wordStatus').textContent = `Read ${name} · ${formatHexWord(converterWord)} · ${formatBinaryWord(converterWord)}.`;
    $('wordStatus').classList.remove('error');
  });
  $('writeRegisterBtn').addEventListener('click', () => {
    stopProgram(false);
    const target = $('wordRegister').value;
    const value = converterWord;
    if (target === 'pc') {
      state.pc = value & PROGRAM_ADDRESS_MASK;
      converterWord = state.pc;
    } else {
      state.regs[Number(target)] = value;
    }
    const name = target === 'pc' ? 'PC' : `R${target}`;
    const writtenValue = formatHexWord(value);
    message(`Wrote ${writtenValue} to ${name}${target === 'pc' ? ` · 8-bit PC is ${formatHexWord(state.pc)}.` : '.'}`);
    renderWordConverter();
    $('wordStatus').textContent = `Wrote ${writtenValue} to ${name}${target === 'pc' ? `; PC keeps the low 8 bits (${formatHexWord(state.pc)}).` : '.'}`;
    $('wordStatus').classList.remove('error');
    render();
  });
  renderWordConverter();
  renderDecoder();
}

function stopProgram(showMessage = true) {
  if (runTimer !== null) window.clearTimeout(runTimer);
  runTimer = null;
  if (!runActive) return;
  runActive = false;
  if (showMessage) message(`Paused after ${runSteps.toLocaleString()} software instruction steps.`);
  render();
}

function runProgramTick() {
  if (!runActive) return;
  runTimer = null;
  const result = executeInstruction(state);
  if (result.type !== 'executed') {
    runActive = false;
    message(result.message, result.type === 'error' || result.type === 'missing');
    render();
    return;
  }

  runSteps++;
  if (state.halted) {
    runActive = false;
    message(`Program halted after ${runSteps.toLocaleString()} software instruction steps.`);
    render();
    return;
  }
  if (runSteps >= RUN_STEP_LIMIT) {
    runActive = false;
    message(`Run stopped at the ${RUN_STEP_LIMIT.toLocaleString()}-step safety limit. Press RUN to continue or edit the program.`);
    render();
    return;
  }

  message(`Running · ${result.instruction.op} at ${result.address.toString().padStart(3, '0')} · step ${runSteps.toLocaleString()}`);
  render();
  runTimer = window.setTimeout(runProgramTick, RUN_DELAY_MS);
}

function startProgram() {
  if (!state.program.length) {
    message('No program loaded. Assemble MPL into RAM first.', true);
    return;
  }
  if (state.halted) {
    message('Processor is halted. Reset to start again.');
    return;
  }
  runSteps = 0;
  runActive = true;
  message('Program running · software steps, no simulated clock.');
  render();
  runTimer = window.setTimeout(runProgramTick, 0);
}

function step() {
  stopProgram(false);
  const result = executeInstruction(state);
  if (result.type === 'error' || result.type === 'halted') {
    message(result.message, result.type === 'error');
    return;
  }
  if (result.type === 'missing') {
    message(result.message, true);
    render();
    return;
  }

  const { instruction, address } = result;
  message(`Executed ${instruction.op} at ${address.toString().padStart(3, '0')} · source line ${instruction.line}${state.halted ? ' · halted' : ''}`);
  render();
}

function assembleToRAM() {
  stopProgram(false);
  try {
    const program = loadProgram(state, $('source').value);
    $('assemblyStatus').textContent = `Assembled ${program.length} / ${PROGRAM_RAM_WORDS} instructions · written to program RAM`;
    message(`Program loaded into writable RAM · ${program.length} instruction${program.length === 1 ? '' : 's'}.`);
    render();
  } catch (error) {
    $('assemblyStatus').textContent = 'Assembly error';
    message(error.message, true);
  }
}

function openProgramFile(event) {
  const file = event.target.files[0];
  if (!file) return;
  stopProgram(false);
  file.text().then(text => {
    $('source').value = text;
    $('source').dispatchEvent(new Event('input'));
    $('assemblyStatus').textContent = `Opened ${file.name} · assemble to load into RAM`;
    message(`Loaded source file “${file.name}” into the editor.`);
  }).catch(error => message(`Could not read program file: ${error.message}`, true)).finally(() => {
    event.target.value = '';
  });
}

function importRamFile(event) {
  const file = event.target.files[0];
  if (!file) return;
  stopProgram(false);
  file.arrayBuffer().then(buffer => {
    importDataRam(state, new Uint8Array(buffer));
    message(`Imported ${DATA_RAM_BYTES.toLocaleString()} bytes of data RAM from “${file.name}” (little-endian words).`);
    render();
  }).catch(error => message(`RAM import failed: ${error.message}`, true)).finally(() => {
    event.target.value = '';
  });
}

$('source').value = DEFAULT_PROGRAM;
$('source').addEventListener('input', () => {
  if (runActive) stopProgram(false);
  const count = $('source').value.split('\n').length;
  $('lineNumbers').textContent = Array.from({ length: count }, (_, index) => index + 1).join('\n');
});
$('source').dispatchEvent(new Event('input'));
$('exampleBtn').addEventListener('click', () => {
  $('source').value = DEFAULT_PROGRAM;
  $('source').dispatchEvent(new Event('input'));
  $('assemblyStatus').textContent = 'Example loaded · ready to assemble';
});
$('assembleBtn').addEventListener('click', assembleToRAM);
$('stepBtn').addEventListener('click', step);
$('runBtn').addEventListener('click', startProgram);
$('pauseBtn').addEventListener('click', () => stopProgram(true));
$('resetBtn').addEventListener('click', () => {
  stopProgram(false);
  resetMachine(state);
  $('inputValue').value = '0';
  message('Registers, flags, data RAM, input, and output reset. Program RAM was kept.');
  render();
});
$('pcInput').addEventListener('change', event => {
  state.pc = toWord(event.target.value) & PROGRAM_ADDRESS_MASK;
  stopProgram(false);
  render();
});
[['flagZ', 'z'], ['flagN', 'n'], ['flagC', 'c']].forEach(([id, flag]) => {
  $(id).addEventListener('change', event => {
    state[flag] = Number(event.target.checked);
    if (runActive) stopProgram(false);
  });
});
$('inputValue').addEventListener('change', event => {
  try {
    const inputWord = parseWordLiteral(event.target.value);
    stopProgram(false);
    state.input = inputWord;
    message(`Input set to ${formatHexWord(state.input)} · ${formatBinaryWord(state.input)}.`);
  } catch (error) {
    message(error.message, true);
    event.target.value = String(state.input);
  }
});
$('memoryPage').addEventListener('change', event => {
  const requestedPage = Math.trunc(Number(event.target.value) || 0);
  state.memoryPage = Math.max(0, Math.min(DATA_MEMORY_PAGE_COUNT - 1, requestedPage));
  render();
});
$('memoryPrev').addEventListener('click', () => {
  state.memoryPage = Math.max(0, state.memoryPage - 1);
  render();
});
$('memoryNext').addEventListener('click', () => {
  state.memoryPage = Math.min(DATA_MEMORY_PAGE_COUNT - 1, state.memoryPage + 1);
  render();
});
$('exportRamBtn').addEventListener('click', () => {
  downloadFile('misk16-data-ram-8k.bin', exportDataRam(state), 'application/octet-stream');
});
$('importRamBtn').addEventListener('click', () => $('ramFile').click());
$('ramFile').addEventListener('change', importRamFile);
$('openProgramBtn').addEventListener('click', () => $('programFile').click());
$('saveProgramBtn').addEventListener('click', () => {
  downloadFile('misk16-program.mpl', $('source').value, 'text/plain;charset=utf-8');
});
$('programFile').addEventListener('change', openProgramFile);
$('binaryWord').addEventListener('input', () => handleConverterInput('binaryWord', parseBinaryWord, 'binary'));
$('hexWord').addEventListener('input', () => handleConverterInput('hexWord', parseHexWord, 'hexadecimal'));

initializeLogicTools();
render();
