'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const MISKOS = require('../miskos.js');
const MISK16 = require('../misk16.js');

function memoryStorage() {
  const values = new Map();
  return {
    getItem(key) { return values.has(key) ? values.get(key) : null; },
    setItem(key, value) { values.set(key, String(value)); },
    removeItem(key) { values.delete(key); },
  };
}

test('virtual paths normalize home, relative paths, and parent traversal', () => {
  assert.equal(MISKOS.normalizePath('~/notes.txt'), '/home/guest/notes.txt');
  assert.equal(MISKOS.normalizePath('../etc/hostname', '/home/guest'), '/home/etc/hostname');
  assert.equal(MISKOS.normalizePath('../../etc/hostname', '/home/guest'), '/etc/hostname');
  assert.equal(MISKOS.normalizePath('/../../tmp/./x', '/home/guest'), '/tmp/x');
  assert.equal(MISKOS.normalizePath('', '/tmp'), '/tmp');
});

test('virtual disk supports directories, text files, safe removal, and browser persistence', () => {
  const storage = memoryStorage();
  const first = MISKOS.createFileSystem({ storage, now: () => 123 });
  first.mkdir('projects/demo', { recursive: true }, MISKOS.HOME);
  first.writeFile('projects/demo/readme.txt', 'hello disk\n', MISKOS.HOME);
  assert.equal(first.readFile('/home/guest/projects/demo/readme.txt'), 'hello disk\n');
  assert.deepEqual(first.list('/home/guest/projects/demo').map(entry => entry.name), ['readme.txt']);
  assert.throws(() => first.remove('/home/guest/projects/demo'), /Directory not empty/);
  assert.throws(() => first.remove('/'), /protected system path/);
  first.remove('projects/demo', { recursive: true }, MISKOS.HOME);
  assert.equal(first.exists('projects/demo', MISKOS.HOME), false);

  first.writeFile('saved.txt', 'persists', MISKOS.HOME);
  const restored = MISKOS.createFileSystem({ storage, now: () => 456 });
  assert.equal(restored.loadedFromStorage, true);
  assert.equal(restored.readFile('saved.txt', MISKOS.HOME), 'persists');
});

test('virtual disk enforces its configured capacity and reports real byte usage', () => {
  const fileSystem = MISKOS.createFileSystem({ storage: null });
  assert.equal(fileSystem.capacityBytes(), 1024 * 1024);
  fileSystem.writeFile('a.txt', 'a'.repeat(256 * 1024), MISKOS.HOME);
  fileSystem.writeFile('b.txt', 'b'.repeat(256 * 1024), MISKOS.HOME);
  fileSystem.writeFile('c.txt', 'c'.repeat(256 * 1024), MISKOS.HOME);
  assert.throws(() => fileSystem.writeFile('d.txt', 'd'.repeat(256 * 1024), MISKOS.HOME), /Virtual disk is full/);
  assert.ok(fileSystem.usedBytes() > 3 * 256 * 1024);
});

test('shell tokenizer handles quotes, escapes, and redirection operators', () => {
  assert.deepEqual(MISKOS.tokenize('echo "hello world" > notes.txt'), ['echo', 'hello world', '>', 'notes.txt']);
  assert.deepEqual(MISKOS.tokenize("echo 'two words' >> notes.txt"), ['echo', 'two words', '>>', 'notes.txt']);
  assert.deepEqual(MISKOS.tokenize('echo one\\ two'), ['echo', 'one two']);
  assert.throws(() => MISKOS.tokenize('echo "unfinished'), /Unclosed quote/);
});

test('shell provides Linux-inspired navigation, redirection, editor, and history commands', () => {
  const fileSystem = MISKOS.createFileSystem({ storage: null });
  const shell = MISKOS.createShell({ fileSystem, now: () => new Date('2026-10-08T12:00:00Z') });
  assert.equal(shell.prompt(), 'guest@misk16:~$');
  assert.match(shell.execute('ls').text, /hello\.mpl/);
  assert.equal(shell.execute('echo "first line" > scratch.txt').type, 'output');
  shell.execute('echo second >> scratch.txt');
  assert.equal(shell.execute('cat scratch.txt').text, 'first line\nsecond\n');
  assert.equal(shell.execute('mkdir -p work/src').type, 'output');
  shell.execute('cd work/src');
  assert.equal(shell.execute('pwd').text, '/home/guest/work/src');
  shell.execute('cd -');
  assert.equal(shell.execute('pwd').text, '/home/guest');
  const editor = shell.execute('nano scratch.txt');
  assert.equal(editor.type, 'editor');
  assert.equal(editor.path, '/home/guest/scratch.txt');
  assert.equal(editor.isNew, false);
  assert.equal(editor.text, 'first line\nsecond\n');
  const newEditor = shell.execute('nano draft.txt');
  assert.equal(newEditor.isNew, true);
  assert.equal(fileSystem.exists('draft.txt', MISKOS.HOME), false);
  assert.match(shell.execute('lscpu').text, /16-bit/);
  assert.match(shell.execute('uname -a').text, /MISK-16/);
  assert.equal(shell.execute('unknown-command').type, 'error');
  assert.ok(shell.history().includes('nano scratch.txt'));
});

test('run command assembles and executes MPL from the virtual disk on the MISK-16 CPU', () => {
  const fileSystem = MISKOS.createFileSystem({ storage: null });
  const machine = MISK16.createMachine();
  const computer = {
    runMPL(source) {
      const program = MISK16.loadProgram(machine, source);
      const outputs = [];
      let steps = 0;
      while (!machine.halted && steps < 100) {
        const result = MISK16.executeInstruction(machine);
        if (result.type !== 'executed') return { success: false, error: result.message };
        if (result.instruction.op === 'OUT') outputs.push(machine.output);
        steps++;
      }
      return { success: true, instructionCount: steps, programLength: program.length, outputs, halted: machine.halted };
    },
    assembleMPL(source) {
      const program = MISK16.loadProgram(machine, source);
      return { success: true, instructionCount: program.length };
    },
  };
  const shell = MISKOS.createShell({ fileSystem, computer });
  const result = shell.execute('run hello.mpl');
  assert.equal(result.type, 'output');
  assert.match(result.text, /MISK-16 ran 4 instructions/);
  assert.match(result.text, /OUT: 42 \(0x002A\)/);
  const compile = shell.execute('compile hello.mpl');
  assert.match(compile.text, /assembled 4 instructions/);
});
