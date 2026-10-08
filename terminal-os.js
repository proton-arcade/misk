(() => {
  'use strict';

  const $ = id => document.getElementById(id);
  const fileSystem = window.MISKOS.createFileSystem();
  const shell = window.MISKOS.createShell({
    fileSystem,
    computer: {
      assembleMPL: (source, path) => window.MISKWorkbench.assembleMPL(source, path),
      runMPL: (source, path) => window.MISKWorkbench.runMPL(source, path),
      reset: () => window.MISKWorkbench.reset(),
      snapshot: () => window.MISKWorkbench.snapshot(),
    },
  });

  const output = $('osOutput');
  const input = $('osCommandInput');
  const prompt = $('osPrompt');
  const commandForm = $('osCommandForm');
  const editorPanel = $('osEditorPanel');
  const editor = $('osEditor');
  const editorLines = $('osEditorLines');
  const editorStatus = $('osEditorStatus');
  let historyIndex = 0;
  let activeEditorPath = null;
  let savedEditorContent = '';
  let editorDirty = false;
  let osHalted = false;

  function appendLine(text, kind = 'output') {
    if (text === '') return;
    const line = document.createElement('div');
    line.className = `terminal-line ${kind}`;
    line.textContent = String(text);
    output.appendChild(line);
    output.scrollTop = output.scrollHeight;
  }

  function refreshPrompt() {
    prompt.textContent = shell.prompt();
  }

  function bootMessage() {
    osHalted = false;
    input.disabled = false;
    input.placeholder = '';
    appendLine('MISK Linux 0.1 · MISK-16 virtual text console', 'accent');
    appendLine('Linux-inspired educational shell — not the Linux kernel.', 'system');
    try {
      appendLine(fileSystem.readFile('/etc/motd', '/').trimEnd(), 'system');
    } catch (_error) {
      appendLine('System ready. Type help to get started.', 'system');
    }
    const warning = fileSystem.getPersistenceWarning();
    if (warning) appendLine(`storage notice: ${warning}`, 'error');
    refreshPrompt();
  }

  function clearScreen() {
    output.replaceChildren();
    output.scrollTop = 0;
  }

  function updateEditorStatus(text, modified = false) {
    editorStatus.textContent = text;
    editorStatus.classList.toggle('modified', modified);
  }

  function updateEditorLines() {
    const count = Math.max(1, editor.value.split('\n').length);
    editorLines.textContent = Array.from({ length: count }, (_, index) => index + 1).join('\n');
    editorLines.scrollTop = editor.scrollTop;
  }

  function openEditor(path, text, isNew = false) {
    activeEditorPath = path;
    savedEditorContent = text;
    editorDirty = false;
    $('osEditorPath').textContent = path;
    editor.value = text;
    updateEditorLines();
    updateEditorStatus(isNew ? 'New file · Ctrl+S saves' : 'File loaded · Ctrl+S saves', false);
    output.hidden = true;
    commandForm.hidden = true;
    editorPanel.hidden = false;
    editor.focus();
  }

  function saveEditor(closeAfter = false) {
    if (!activeEditorPath) return;
    try {
      fileSystem.writeFile(activeEditorPath, editor.value, '/');
      savedEditorContent = editor.value;
      editorDirty = false;
      updateEditorStatus(`Saved ${activeEditorPath}`, false);
      if (closeAfter) closeEditor(false);
    } catch (error) {
      updateEditorStatus(error.message, true);
    }
  }

  function closeEditor(discard = false) {
    if (editorDirty && !discard) {
      updateEditorStatus('Unsaved changes — use SAVE & EXIT or DISCARD & EXIT.', true);
      return;
    }
    const closedPath = activeEditorPath;
    editorDirty = false;
    activeEditorPath = null;
    editorPanel.hidden = true;
    output.hidden = false;
    commandForm.hidden = false;
    if (discard && editor.value !== savedEditorContent) appendLine(`[discarded unsaved edits to ${closedPath}]`, 'system');
    else if (closedPath) appendLine(`[editor closed: ${closedPath}]`, 'system');
    editor.value = '';
    updateEditorLines();
    refreshPrompt();
    input.focus();
  }

  function executeLine(line) {
    if (!line.trim() || osHalted) return;
    const promptText = shell.prompt();
    appendLine(`${promptText} ${line}`, 'command');
    const result = shell.execute(line);
    input.value = '';
    historyIndex = shell.history().length;

    if (result.type === 'clear') {
      clearScreen();
    } else if (result.type === 'editor') {
      openEditor(result.path, result.text, result.isNew);
      return;
    } else if (result.type === 'reboot') {
      clearScreen();
      appendLine(result.text, 'system');
      appendLine('[ OK ] CPU state reset · browser-local virtual disk mounted', 'accent');
      bootMessage();
      return;
    } else if (result.type === 'shutdown') {
      appendLine(result.text, 'system');
      osHalted = true;
      input.disabled = true;
      input.placeholder = 'shell halted · press REBOOT OS';
    } else if (result.type === 'exit') {
      appendLine(result.text, 'system');
      window.MISKWorkbench.setMode('workbench');
      return;
    } else if (result.type === 'error') {
      appendLine(result.text, 'error');
    } else if (result.text) {
      appendLine(result.text, result.status === 1 ? 'system' : 'output');
    }

    refreshPrompt();
    if (!osHalted) input.focus();
  }

  commandForm.addEventListener('submit', event => {
    event.preventDefault();
    executeLine(input.value);
  });

  input.addEventListener('keydown', event => {
    const history = shell.history();
    if (event.key === 'ArrowUp') {
      event.preventDefault();
      if (history.length) {
        historyIndex = Math.max(0, historyIndex - 1);
        input.value = history[historyIndex] || '';
      }
    } else if (event.key === 'ArrowDown') {
      event.preventDefault();
      historyIndex = Math.min(history.length, historyIndex + 1);
      input.value = history[historyIndex] || '';
    } else if (event.key === 'Tab') {
      event.preventDefault();
      const matches = shell.complete(input.value);
      if (matches.length === 1) {
        input.value = `${matches[0]}${input.value.includes(' ') ? '' : ' '}`;
      } else if (matches.length > 1) {
        appendLine(matches.join('   '), 'system');
      }
    } else if (event.ctrlKey && event.key.toLowerCase() === 'l') {
      event.preventDefault();
      clearScreen();
    } else if (event.ctrlKey && event.key.toLowerCase() === 'c') {
      event.preventDefault();
      appendLine(`${shell.prompt()} ${input.value}^C`, 'system');
      input.value = '';
    }
  });

  editor.addEventListener('input', () => {
    editorDirty = editor.value !== savedEditorContent;
    updateEditorLines();
    updateEditorStatus(editorDirty ? 'Modified · Ctrl+S saves' : 'No unsaved changes', editorDirty);
  });
  editor.addEventListener('scroll', updateEditorLines);
  editor.addEventListener('keydown', event => {
    if (event.ctrlKey && (event.key.toLowerCase() === 's' || event.key.toLowerCase() === 'o')) {
      event.preventDefault();
      saveEditor(false);
    } else if (event.ctrlKey && event.key.toLowerCase() === 'x') {
      event.preventDefault();
      if (editorDirty) updateEditorStatus('Unsaved changes — save or choose DISCARD & EXIT.', true);
      else closeEditor(false);
    } else if (event.key === 'Tab') {
      event.preventDefault();
      const start = editor.selectionStart;
      const end = editor.selectionEnd;
      editor.setRangeText('  ', start, end, 'end');
      editor.dispatchEvent(new Event('input'));
    }
  });

  $('osEditorSaveBtn').addEventListener('click', () => saveEditor(false));
  $('osEditorSaveExitBtn').addEventListener('click', () => saveEditor(true));
  $('osEditorCancelBtn').addEventListener('click', () => closeEditor(true));
  $('osRebootBtn').addEventListener('click', () => {
    const result = shell.execute('reboot');
    clearScreen();
    appendLine(result.text, 'system');
    appendLine('[ OK ] CPU state reset · browser-local virtual disk mounted', 'accent');
    bootMessage();
    input.focus();
  });

  document.querySelectorAll('[data-os-command]').forEach(button => {
    button.addEventListener('click', () => {
      input.value = button.dataset.osCommand;
      input.focus();
    });
  });

  window.addEventListener('misk:mode', event => {
    if (event.detail && event.detail.mode === 'os') window.setTimeout(() => input.focus(), 0);
  });

  bootMessage();
  window.setTimeout(() => {
    if (document.body.classList.contains('os-mode')) input.focus();
  }, 0);
})();
