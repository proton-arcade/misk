(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.MISKOS = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  const STORAGE_KEY = 'miskos.virtual-disk.v1';
  const HOME = '/home/guest';
  const MAX_FILE_BYTES = 256 * 1024;
  const MAX_DISK_BYTES = 1024 * 1024;

  function utf8Size(text) {
    return typeof TextEncoder !== 'undefined' ? new TextEncoder().encode(String(text)).length : String(text).length;
  }
  const COMMANDS = Object.freeze([
    'help', 'man', 'clear', 'pwd', 'ls', 'cd', 'tree', 'cat', 'head', 'tail', 'grep', 'wc',
    'echo', 'touch', 'mkdir', 'rm', 'cp', 'mv', 'nano', 'edit', 'vi', 'compile', 'run',
    'whoami', 'hostname', 'uname', 'lscpu', 'free', 'df', 'ps', 'env', 'history', 'date',
    'uptime', 'neofetch', 'reboot', 'shutdown', 'exit', 'sudo',
  ]);

  const DEFAULT_HELLO = `; A tiny program for the MISK-16 software machine\n; Run it with: run hello.mpl\n        LDI  R0, 40\n        ADDI R0, R0, 2\n        OUT  R0\n        HALT\n`;

  const HELP_TEXT = [
    'MISK Linux shell · commands',
    '  help                   show this command list',
    '  ls [path]              list files and directories',
    '  cd [path]              change directory; cd - returns to the last one',
    '  pwd                    print the current directory',
    '  cat FILE               display a text file',
    '  nano FILE              edit a file in the built-in terminal editor',
    '  echo TEXT > FILE       write text to a virtual file (>> appends)',
    '  touch FILE             create an empty file',
    '  mkdir [-p] DIR         create a directory',
    '  cp SRC DEST            copy a file; mv SRC DEST moves/renames it',
    '  rm [-r] PATH           remove a file or directory in the virtual disk',
    '  tree [path]            show the virtual directory tree',
    '  grep TEXT FILE         find matching lines',
    '  compile FILE.mpl       assemble source into MISK-16 program RAM',
    '  run FILE.mpl           assemble and run MPL on the MISK-16 machine',
    '  lscpu · free · df       inspect simulated CPU and memory',
    '  uname · whoami · env    inspect the simulated system',
    '  history · date · uptime · neofetch',
    '  reboot · shutdown      simulated controls (they do not affect your PC)',
    '',
    'This is an educational Linux-inspired shell, not a Linux kernel. Files stay',
    'in this browser\'s virtual disk; commands cannot access your host computer.',
  ].join('\n');

  const MANUALS = Object.freeze({
    nano: 'nano FILE — open the built-in text editor. Ctrl+S or Ctrl+O saves; Ctrl+X exits.',
    run: 'run FILE.mpl — assemble a virtual-disk MPL source file, then execute it on the MISK-16 emulator. OUT values are printed in decimal and hexadecimal.',
    compile: 'compile FILE.mpl — assemble MPL source and load it into the computer\'s writable program RAM without running it.',
    ls: 'ls [PATH] — list one directory. Directories are marked with a trailing slash.',
    rm: 'rm [-r] PATH — remove a virtual file. Use -r for a non-empty directory. Root and core home/system folders are protected.',
    reboot: 'reboot — clear simulated CPU registers and RAM, then restart this shell. Your virtual files remain saved.',
    'misk-os': 'MISK Linux is a small Linux-inspired text environment running inside the MISK-16 teaching computer. It is not the Linux kernel and does not run host commands.',
  });

  function safeStorage() {
    try {
      return typeof globalThis !== 'undefined' ? globalThis.localStorage || null : null;
    } catch (_error) {
      return null;
    }
  }

  function normalizePath(path, cwd = HOME) {
    let source = String(path == null ? '' : path).trim();
    if (!source) source = cwd;
    if (source === '~') source = HOME;
    else if (source.startsWith('~/')) source = `${HOME}${source.slice(1)}`;
    else if (source.startsWith('~')) source = `${HOME}/${source.slice(1)}`;

    const parts = source.startsWith('/') ? [] : String(cwd || HOME).split('/').filter(Boolean);
    for (const segment of source.split('/')) {
      if (!segment || segment === '.') continue;
      if (segment === '..') parts.pop();
      else parts.push(segment);
    }
    return `/${parts.join('/')}` || '/';
  }

  function parentPath(path) {
    if (path === '/') return '/';
    const slash = path.lastIndexOf('/');
    return slash <= 0 ? '/' : path.slice(0, slash);
  }

  function basename(path) {
    return path === '/' ? '/' : path.slice(path.lastIndexOf('/') + 1);
  }

  function makeDefaultEntries(now) {
    const entries = Object.create(null);
    const timestamp = now();
    for (const path of [
      '/', '/bin', '/dev', '/etc', '/home', HOME, '/proc', '/tmp', '/usr',
      '/usr/share', '/usr/share/doc', '/var', '/var/log',
    ]) entries[path] = { type: 'dir', modified: timestamp };

    const files = {
      '/etc/hostname': 'misk16\n',
      '/etc/motd': 'MISK Linux 0.1 · a small, text-first computer.\nType help to explore the shell.\n',
      '/etc/os-release': 'NAME="MISK Linux"\nID=misk-linux\nPRETTY_NAME="MISK Linux (Linux-inspired MISK-16 shell)"\nVERSION="0.1"\n',
      '/proc/cpuinfo': 'processor : 0\nvendor_id : MISK\nmodel name : MISK-16 teaching CPU\nword size  : 16 bits\nregisters  : 8 general-purpose\n',
      '/proc/meminfo': 'Data RAM: 8192 kB\nProgram RAM: 256 instruction entries\n',
      '/usr/share/doc/misk/README.txt': 'MISK Linux is a simulated command-line environment.\nTry nano notes.txt, then save and use cat notes.txt.\nTry run hello.mpl to execute a small MPL program.\n',
      [`${HOME}/README.txt`]: 'Welcome to your virtual home directory.\n\nTry these commands:\n  help\n  ls -la\n  nano notes.txt\n  run hello.mpl\n\nYour files persist in this browser only.\n',
      [`${HOME}/hello.mpl`]: DEFAULT_HELLO,
      [`${HOME}/notes.txt`]: 'This is your editable MISK Linux notes file.\n',
      '/var/log/boot.log': '[ OK ] Starting MISK-16 virtual console\n[ OK ] Mounting browser-local virtual disk\n[ OK ] Starting misk-shell on tty1\n',
    };
    for (const [path, content] of Object.entries(files)) entries[path] = { type: 'file', content, modified: timestamp };
    return entries;
  }

  function validEntries(value) {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
    return Object.entries(value).every(([path, entry]) => {
      if (normalizePath(path, '/') !== path || !entry || typeof entry !== 'object') return false;
      if (entry.type === 'dir') return true;
      return entry.type === 'file' && typeof entry.content === 'string';
    });
  }

  function createFileSystem(options = {}) {
    const storage = options.storage === undefined ? safeStorage() : options.storage;
    const now = typeof options.now === 'function' ? options.now : () => Date.now();
    let entries = makeDefaultEntries(now);
    let persistenceError = storage ? '' : 'Browser storage is unavailable; virtual files will last for this session only.';
    let loaded = false;

    if (storage && typeof storage.getItem === 'function') {
      try {
        const saved = storage.getItem(STORAGE_KEY);
        if (saved) {
          const parsed = JSON.parse(saved);
          if (validEntries(parsed)) {
            entries = Object.assign(Object.create(null), parsed);
            loaded = true;
            if (!entries['/']) entries['/'] = { type: 'dir', modified: now() };
          }
        }
      } catch (_error) {
        persistenceError = 'Saved virtual disk data could not be read; using a fresh disk.';
      }
    }

    function persist() {
      if (!storage || typeof storage.setItem !== 'function') return true;
      try {
        storage.setItem(STORAGE_KEY, JSON.stringify(entries));
        persistenceError = '';
        return true;
      } catch (_error) {
        persistenceError = 'Browser storage is full or unavailable; recent edits may not survive refresh.';
        return false;
      }
    }

    function resolve(path, cwd = HOME) {
      return normalizePath(path, cwd);
    }

    function requireDirectory(path) {
      const entry = entries[path];
      if (!entry) throw new Error(`ls: cannot access '${path}': No such file or directory`);
      if (entry.type !== 'dir') throw new Error(`ls: '${path}' is not a directory`);
      return entry;
    }

    function ensureWritableParent(path) {
      const parent = parentPath(path);
      if (!entries[parent]) throw new Error(`No such directory: ${parent}`);
      if (entries[parent].type !== 'dir') throw new Error(`Not a directory: ${parent}`);
    }

    function getDestinationPath(destination, sourcePath, cwd) {
      let target = resolve(destination, cwd);
      if (entries[target] && entries[target].type === 'dir') target = resolve(basename(sourcePath), target);
      if (target === sourcePath) throw new Error('Source and destination are the same file.');
      ensureWritableParent(target);
      if (entries[target] && entries[target].type === 'dir') throw new Error(`Is a directory: ${target}`);
      return target;
    }

    const api = {
      storageKey: STORAGE_KEY,
      loadedFromStorage: loaded,
      resolve,
      exists(path, cwd = HOME) {
        return Object.prototype.hasOwnProperty.call(entries, resolve(path, cwd));
      },
      stat(path, cwd = HOME) {
        const absolute = resolve(path, cwd);
        const entry = entries[absolute];
        return entry ? { path: absolute, type: entry.type, size: entry.type === 'file' ? entry.content.length : 0, modified: entry.modified } : null;
      },
      list(path = '.', cwd = HOME) {
        const absolute = resolve(path, cwd);
        requireDirectory(absolute);
        const prefix = absolute === '/' ? '/' : `${absolute}/`;
        const names = new Set();
        for (const candidate of Object.keys(entries)) {
          if (candidate === absolute || !candidate.startsWith(prefix)) continue;
          const remainder = candidate.slice(prefix.length);
          if (!remainder) continue;
          names.add(remainder.split('/')[0]);
        }
        return [...names].map(name => {
          const childPath = resolve(name, absolute);
          const item = entries[childPath];
          return {
            name,
            path: childPath,
            type: item ? item.type : 'dir',
            size: item && item.type === 'file' ? item.content.length : 0,
            modified: item ? item.modified : 0,
          };
        }).sort((a, b) => Number(b.type === 'dir') - Number(a.type === 'dir') || a.name.localeCompare(b.name));
      },
      readFile(path, cwd = HOME) {
        const absolute = resolve(path, cwd);
        const entry = entries[absolute];
        if (!entry) throw new Error(`No such file: ${absolute}`);
        if (entry.type !== 'file') throw new Error(`Is a directory: ${absolute}`);
        return entry.content;
      },
      writeFile(path, content, cwd = HOME) {
        const absolute = resolve(path, cwd);
        const text = String(content);
        if (absolute === '/') throw new Error('Cannot write a file over the root directory.');
        if (utf8Size(text) > MAX_FILE_BYTES) throw new Error(`File is too large (maximum ${MAX_FILE_BYTES} bytes).`);
        if (entries[absolute] && entries[absolute].type === 'dir') throw new Error(`Is a directory: ${absolute}`);
        ensureWritableParent(absolute);
        const previousSize = entries[absolute] && entries[absolute].type === 'file' ? utf8Size(entries[absolute].content) : 0;
        if (api.usedBytes() - previousSize + utf8Size(text) > MAX_DISK_BYTES) {
          throw new Error(`Virtual disk is full (maximum ${MAX_DISK_BYTES} bytes).`);
        }
        entries[absolute] = { type: 'file', content: text, modified: now() };
        persist();
        return absolute;
      },
      appendFile(path, content, cwd = HOME) {
        const absolute = resolve(path, cwd);
        const current = entries[absolute] ? api.readFile(absolute, '/') : '';
        return api.writeFile(absolute, current + String(content), '/');
      },
      touch(path, cwd = HOME) {
        const absolute = resolve(path, cwd);
        if (entries[absolute]) {
          if (entries[absolute].type !== 'file') throw new Error(`Is a directory: ${absolute}`);
          entries[absolute].modified = now();
        } else {
          ensureWritableParent(absolute);
          entries[absolute] = { type: 'file', content: '', modified: now() };
        }
        persist();
        return absolute;
      },
      mkdir(path, options = {}, cwd = HOME) {
        const absolute = resolve(path, cwd);
        const recursive = Boolean(options.recursive);
        if (absolute === '/') return '/';
        const parts = absolute.slice(1).split('/');
        let current = '';
        for (let index = 0; index < parts.length; index++) {
          current += `/${parts[index]}`;
          const existing = entries[current];
          if (existing) {
            if (existing.type !== 'dir') throw new Error(`File exists and is not a directory: ${current}`);
            if (index === parts.length - 1 && !recursive) throw new Error(`Directory exists: ${current}`);
            continue;
          }
          if (!recursive && index !== parts.length - 1) throw new Error(`No such directory: ${parentPath(current)}`);
          entries[current] = { type: 'dir', modified: now() };
        }
        persist();
        return absolute;
      },
      remove(path, options = {}, cwd = HOME) {
        const absolute = resolve(path, cwd);
        const recursive = Boolean(options.recursive);
        const force = Boolean(options.force);
        if (!entries[absolute]) {
          if (force) return false;
          throw new Error(`No such file or directory: ${absolute}`);
        }
        if (['/', '/home', HOME, '/etc', '/bin', '/dev', '/proc', '/usr', '/var'].includes(absolute)) {
          throw new Error(`Refusing to remove protected system path: ${absolute}`);
        }
        if (entries[absolute].type === 'dir') {
          const descendants = Object.keys(entries).filter(candidate => candidate.startsWith(`${absolute}/`));
          if (descendants.length && !recursive) throw new Error(`Directory not empty: ${absolute} (use rm -r)`);
          for (const candidate of descendants) delete entries[candidate];
        }
        delete entries[absolute];
        persist();
        return true;
      },
      copy(source, destination, cwd = HOME) {
        const from = resolve(source, cwd);
        const entry = entries[from];
        if (!entry) throw new Error(`No such file: ${from}`);
        if (entry.type !== 'file') throw new Error('cp currently copies files only.');
        const to = getDestinationPath(destination, from, cwd);
        api.writeFile(to, entry.content, '/');
        return to;
      },
      move(source, destination, cwd = HOME) {
        const from = resolve(source, cwd);
        const entry = entries[from];
        if (!entry) throw new Error(`No such file: ${from}`);
        if (entry.type !== 'file') throw new Error('mv currently moves files only.');
        const to = getDestinationPath(destination, from, cwd);
        entries[to] = { type: 'file', content: entry.content, modified: now() };
        delete entries[from];
        persist();
        return to;
      },
      tree(path = '.', cwd = HOME) {
        const absolute = resolve(path, cwd);
        requireDirectory(absolute);
        const output = [basename(absolute)];
        function walk(directory, prefix) {
          const children = api.list(directory, '/');
          children.forEach((child, index) => {
            const last = index === children.length - 1;
            output.push(`${prefix}${last ? '└── ' : '├── '}${child.name}${child.type === 'dir' ? '/' : ''}`);
            if (child.type === 'dir') walk(child.path, `${prefix}${last ? '    ' : '│   '}`);
          });
        }
        walk(absolute, '');
        return output;
      },
      usedBytes() {
        return Object.values(entries).reduce((total, entry) => total + (entry.type === 'file' ? utf8Size(entry.content) : 0), 0);
      },
      capacityBytes: () => MAX_DISK_BYTES,
      fileCount() {
        return Object.values(entries).filter(entry => entry.type === 'file').length;
      },
      getPersistenceWarning() {
        return persistenceError;
      },
      snapshot() {
        return Object.fromEntries(Object.entries(entries).map(([path, entry]) => [path, { ...entry }]));
      },
      clearAndRestoreDefaults() {
        entries = makeDefaultEntries(now);
        persist();
      },
    };
    return api;
  }

  function tokenize(line) {
    const input = String(line);
    const tokens = [];
    let token = '';
    let quote = null;
    let escaped = false;
    let started = false;

    const flush = () => {
      if (started) tokens.push(token);
      token = '';
      started = false;
    };

    for (let index = 0; index < input.length; index++) {
      const character = input[index];
      if (escaped) {
        token += character;
        started = true;
        escaped = false;
      } else if (character === '\\' && quote !== "'") {
        escaped = true;
        started = true;
      } else if (quote) {
        if (character === quote) quote = null;
        else token += character;
        started = true;
      } else if (character === '"' || character === "'") {
        quote = character;
        started = true;
      } else if (/\s/.test(character)) {
        flush();
      } else if (character === '>') {
        flush();
        if (input[index + 1] === '>') {
          tokens.push('>>');
          index++;
        } else tokens.push('>');
      } else {
        token += character;
        started = true;
      }
    }
    if (escaped) token += '\\';
    if (quote) throw new Error('Unclosed quote.');
    flush();
    return tokens;
  }

  function createShell(options = {}) {
    const fs = options.fileSystem || createFileSystem({ storage: options.storage, now: options.now });
    const computer = options.computer || {};
    const now = typeof options.now === 'function' ? options.now : () => new Date();
    const startedAt = now().getTime ? now().getTime() : Date.now();
    let cwd = HOME;
    let previousCwd = HOME;
    const history = [];

    function promptPath() {
      if (cwd === HOME) return '~';
      return cwd.startsWith(`${HOME}/`) ? `~${cwd.slice(HOME.length)}` : cwd;
    }

    function prompt() {
      return `guest@misk16:${promptPath()}$`;
    }

    function output(text = '') {
      return { type: 'output', text: String(text) };
    }

    function error(text) {
      return { type: 'error', text: String(text) };
    }

    function computerSnapshot() {
      return typeof computer.snapshot === 'function' ? computer.snapshot() : {
        wordBits: 16, registers: Array(8).fill(0), pc: 0, flags: { z: 0, n: 0, c: 0 },
        programCount: 0, programCapacity: 256, dataWords: 4096, dataBytes: 8192,
      };
    }

    function runCommand(command, args) {
      switch (command) {
        case 'help': return output(HELP_TEXT);
        case 'man': {
          const topic = args[0] || 'misk-os';
          return MANUALS[topic] ? output(MANUALS[topic]) : error(`No manual entry for ${topic}.`);
        }
        case 'clear': return { type: 'clear', text: '' };
        case 'pwd': return output(cwd);
        case 'whoami': return output('guest');
        case 'hostname': return output('misk16');
        case 'uname': return output(args.includes('-a')
          ? 'MISK Linux misk16 0.16.0-misk #1 MISK-16 educational-userland'
          : 'MISK Linux');
        case 'date': return output(now().toString());
        case 'uptime': {
          const seconds = Math.max(0, Math.floor(((now().getTime ? now().getTime() : Date.now()) - startedAt) / 1000));
          return output(`up ${Math.floor(seconds / 60)} min, ${seconds % 60} sec · 1 user · load average: 0.00, 0.00, 0.00`);
        }
        case 'env': return output('HOME=/home/guest\nUSER=guest\nHOSTNAME=misk16\nSHELL=/bin/misk-sh\nPATH=/bin:/usr/bin\nMISK_ARCH=misk16');
        case 'ls': {
          const pathArg = args.filter(arg => !arg.startsWith('-'))[0] || '.';
          const entries = fs.list(pathArg, cwd);
          if (!entries.length) return output('');
          if (args.includes('-l') || args.includes('-la') || args.includes('-al')) {
            return output(entries.map(entry => `${entry.type === 'dir' ? 'drwxr-xr-x' : '-rw-r--r--'}  guest guest  ${String(entry.size).padStart(6)}  ${entry.name}${entry.type === 'dir' ? '/' : ''}`).join('\n'));
          }
          return output(entries.map(entry => `${entry.name}${entry.type === 'dir' ? '/' : ''}`).join('    '));
        }
        case 'cd': {
          const destination = args[0] || HOME;
          const target = destination === '-' ? previousCwd : fs.resolve(destination, cwd);
          const stat = fs.stat(target, '/');
          if (!stat) return error(`cd: ${destination}: No such file or directory`);
          if (stat.type !== 'dir') return error(`cd: ${destination}: Not a directory`);
          previousCwd = cwd;
          cwd = target;
          return output('');
        }
        case 'tree': {
          const path = args.find(arg => !arg.startsWith('-')) || '.';
          return output(fs.tree(path, cwd).join('\n'));
        }
        case 'cat': {
          if (!args.length) return error('cat: missing file operand');
          return output(args.map(path => fs.readFile(path, cwd)).join(''));
        }
        case 'head': case 'tail': {
          let count = 10;
          const numberIndex = args.indexOf('-n');
          if (numberIndex >= 0) {
            count = Math.max(0, Math.min(10000, Number(args[numberIndex + 1]) || 0));
            args.splice(numberIndex, 2);
          }
          if (!args.length) return error(`${command}: missing file operand`);
          const lines = fs.readFile(args[0], cwd).split(/\r?\n/);
          return output((command === 'head' ? lines.slice(0, count) : lines.slice(-count)).join('\n'));
        }
        case 'grep': {
          if (args.length < 2) return error('grep: usage: grep PATTERN FILE');
          const pattern = args[0];
          const source = fs.readFile(args[1], cwd).split(/\r?\n/);
          const matches = source.filter(line => line.includes(pattern));
          return matches.length ? output(matches.join('\n')) : { type: 'output', text: '', status: 1 };
        }
        case 'wc': {
          if (!args.length) return error('wc: missing file operand');
          const text = fs.readFile(args[0], cwd);
          return output(`${text.split(/\r?\n/).filter((line, index, array) => line || index < array.length - 1).length} ${text.trim() ? text.trim().split(/\s+/).length : 0} ${text.length} ${args[0]}`);
        }
        case 'echo': {
          const noNewline = args[0] === '-n';
          if (noNewline) args.shift();
          return output(`${args.join(' ')}${noNewline ? '' : '\n'}`);
        }
        case 'touch': {
          if (!args.length) return error('touch: missing file operand');
          args.forEach(path => fs.touch(path, cwd));
          return output('');
        }
        case 'mkdir': {
          const recursive = args.includes('-p') || args.includes('--parents');
          const paths = args.filter(arg => !arg.startsWith('-'));
          if (!paths.length) return error('mkdir: missing operand');
          paths.forEach(path => fs.mkdir(path, { recursive }, cwd));
          return output('');
        }
        case 'rm': {
          const recursive = args.includes('-r') || args.includes('-R') || args.includes('-rf') || args.includes('-fr');
          const force = args.includes('-f') || args.includes('-rf') || args.includes('-fr');
          const paths = args.filter(arg => !arg.startsWith('-'));
          if (!paths.length) return error('rm: missing operand');
          paths.forEach(path => fs.remove(path, { recursive, force }, cwd));
          return output('');
        }
        case 'cp': case 'mv': {
          if (args.length !== 2) return error(`${command}: usage: ${command} SOURCE DEST`);
          const destination = command === 'cp' ? fs.copy(args[0], args[1], cwd) : fs.move(args[0], args[1], cwd);
          return output(`${command === 'cp' ? 'copied' : 'moved'} ${args[0]} → ${destination}`);
        }
        case 'nano': case 'edit': case 'vi': {
          const filename = args[0];
          if (!filename) return error(`${command}: missing file operand`);
          const path = fs.resolve(filename, cwd);
          const existing = fs.stat(path, '/');
          if (existing && existing.type === 'dir') return error(`nano: ${filename}: Is a directory`);
          if (!existing) {
            const slash = path.lastIndexOf('/');
            const parent = slash <= 0 ? '/' : path.slice(0, slash);
            const parentStat = fs.stat(parent, '/');
            if (!parentStat) return error(`nano: ${filename}: No such directory`);
            if (parentStat.type !== 'dir') return error(`nano: ${filename}: Parent is not a directory`);
          }
          return { type: 'editor', path, text: existing ? fs.readFile(path, '/') : '', isNew: !existing };
        }
        case 'compile': {
          if (!args[0]) return error('compile: usage: compile FILE.mpl');
          const sourcePath = fs.resolve(args[0], cwd);
          let result;
          try {
            if (typeof computer.assembleMPL !== 'function') return error('MISK-16 compiler is not connected.');
            result = computer.assembleMPL(fs.readFile(sourcePath, '/'), sourcePath);
          } catch (exception) {
            return error(`compile: ${exception.message}`);
          }
          return result && result.success
            ? output(`assembled ${result.instructionCount} instructions from ${sourcePath} into program RAM`)
            : error(`compile: ${result && result.error ? result.error : 'assembly failed'}`);
        }
        case 'run': {
          if (!args[0]) return error('run: usage: run FILE.mpl');
          let sourcePath = fs.resolve(args[0], cwd);
          if (!fs.exists(sourcePath, '/')) {
            if (!sourcePath.toLowerCase().endsWith('.mpl') && fs.exists(`${sourcePath}.mpl`, '/')) sourcePath += '.mpl';
            else return error(`run: ${args[0]}: No such file or directory`);
          }
          let result;
          try {
            if (typeof computer.runMPL !== 'function') return error('MISK-16 processor is not connected.');
            result = computer.runMPL(fs.readFile(sourcePath, '/'), sourcePath);
          } catch (exception) {
            return error(`run: ${exception.message}`);
          }
          if (!result || !result.success) return error(`run: ${result && result.error ? result.error : 'program failed'}`);
          const lines = [`MISK-16 ran ${result.instructionCount} instructions from ${sourcePath}.`];
          if (result.outputs && result.outputs.length) {
            lines.push(`OUT: ${result.outputs.map(value => `${value} (${`0x${Number(value).toString(16).toUpperCase().padStart(4, '0')}`})`).join(', ')}`);
          } else lines.push('OUT: (no values written)');
          if (!result.halted) lines.push('warning: stopped at the instruction safety limit; the machine may not have halted.');
          return output(lines.join('\n'));
        }
        case 'lscpu': {
          const machine = computerSnapshot();
          return output([
            'Architecture:          misk16',
            'CPU op-mode(s):        16-bit',
            'Word size:             16 bits',
            'General registers:     8 × 16-bit (R0–R7)',
            'Program counter:       8-bit (256 instruction slots)',
            'Instruction set:       MPL-16 teaching ISA',
            `Program loaded:        ${machine.programCount || 0} / ${machine.programCapacity || 256} instructions`,
            'Execution:             software-stepped emulator',
          ].join('\n'));
        }
        case 'free': {
          const machine = computerSnapshot();
          const total = machine.dataBytes || 8192;
          const usedWords = machine.dataUsedWords || 0;
          const used = usedWords * 2;
          return output(`               total        used        free\nData RAM:      ${String(total).padStart(5)} B     ${String(used).padStart(5)} B     ${String(total - used).padStart(5)} B\nProgram RAM:    ${machine.programCapacity || 256} instruction slots (${machine.programCount || 0} loaded)`);
        }
        case 'df': {
          const total = fs.capacityBytes();
          const used = fs.usedBytes();
          const available = Math.max(0, total - used);
          const percent = total ? Math.floor((used / total) * 100) : 0;
          return output(`Filesystem       Size      Used      Avail  Use%  Mounted on\nvirtual-disk     1 MiB  ${String(used).padStart(7)} B  ${String(available).padStart(7)} B  ${String(percent).padStart(3)}%   browser-local /`);
        }
        case 'ps': return output('PID  TTY   TIME     CMD\n  1  tty1  00:00:00 misk-sh\n  2  tty1  00:00:00 misk16-emulator');
        case 'neofetch': return output([
          '        .--.       guest@misk16',
          '       |o_o |      OS: MISK Linux 0.1 (simulation)',
          '       |:_/ |      Host: MISK-16 teaching computer',
          '      //   \\ \\     Kernel: not emulated · shell layer only',
          '     (|     | )    CPU: 16-bit · 8 registers',
          '    /’\\_   _/`\\   Memory: 8 KiB data RAM',
          '    \\___)=(___/    Shell: misk-sh · tty1',
        ].join('\n'));
        case 'reboot': {
          if (typeof computer.reset === 'function') computer.reset();
          cwd = HOME;
          previousCwd = HOME;
          return { type: 'reboot', text: 'Restarting MISK Linux. Virtual disk preserved.' };
        }
        case 'shutdown': case 'poweroff': return { type: 'shutdown', text: 'MISK Linux halted. The simulated computer remains available; press REBOOT OS or switch to WORKBENCH.' };
        case 'exit': return { type: 'exit', text: 'Leaving the shell and returning to the computer workbench.' };
        case 'sudo': return error('sudo: disabled. This educational shell cannot perform privileged host operations.');
        default: return error(`${command}: command not found. Type 'help' to see available commands.`);
      }
    }

    function execute(line) {
      const source = String(line);
      let args;
      try {
        args = tokenize(source);
      } catch (exception) {
        return error(`misk-sh: ${exception.message}`);
      }
      if (!args.length) return output('');
      history.push(source);

      let redirectIndex = args.findIndex(arg => arg === '>' || arg === '>>');
      let redirect = null;
      if (redirectIndex >= 0) {
        if (!args[redirectIndex + 1] || args.length !== redirectIndex + 2 || args.lastIndexOf('>') !== redirectIndex && args.lastIndexOf('>>') !== redirectIndex) {
          return error('misk-sh: invalid output redirection. Use COMMAND > FILE or COMMAND >> FILE.');
        }
        redirect = { append: args[redirectIndex] === '>>', path: args[redirectIndex + 1] };
        args = args.slice(0, redirectIndex);
        if (!args.length) return error('misk-sh: redirection needs a command.');
      }

      const command = args.shift().toLowerCase();
      try {
        const result = runCommand(command, args);
        if (redirect) {
          if (result.type !== 'output') return error('misk-sh: this command cannot be redirected.');
          const existing = redirect.append && fs.exists(redirect.path, cwd) ? fs.readFile(redirect.path, cwd) : '';
          fs.writeFile(redirect.path, existing + result.text, cwd);
          return output('');
        }
        return result;
      } catch (exception) {
        return error(`${command}: ${exception.message}`);
      }
    }

    return {
      fileSystem: fs,
      execute,
      prompt,
      currentDirectory: () => cwd,
      displayDirectory: promptPath,
      history: () => [...history],
      clearHistory: () => { history.length = 0; },
      complete(prefix) {
        const before = String(prefix).split(/\s+/);
        if (before.length <= 1) return COMMANDS.filter(command => command.startsWith(before[0] || ''));
        return fs.list('.', cwd).map(entry => entry.name).filter(name => name.startsWith(before[before.length - 1] || ''));
      },
    };
  }

  return {
    STORAGE_KEY,
    HOME,
    DEFAULT_HELLO,
    HELP_TEXT,
    COMMANDS,
    normalizePath,
    tokenize,
    createFileSystem,
    createShell,
  };
});
