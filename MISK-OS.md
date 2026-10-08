# MISK Linux: the MISK-16 text environment

MISK Linux is a small, original, Linux-inspired command-line environment running inside the MISK-16 computer workbench. It is an educational **userland simulation**, not the Linux kernel or a Linux distribution. It cannot execute commands on the user's PC, access the host filesystem, or install host software.

The app starts on the text-mode virtual console. Use the **WORKBENCH** tab to inspect the CPU and RAM directly, or return to **MISK OS** for the terminal.

## Quick start

```text
help
ls -la
cat README.txt
nano notes.txt
run hello.mpl
```

The built-in `hello.mpl` writes `42` to the machine's OUT port. The shell prints OUT values as decimal and hexadecimal. To write a short text file without opening the editor:

```text
echo "A note from MISK Linux" > note.txt
cat note.txt
```

## Shell input

- **Enter** runs the typed command.
- **Up / Down** recalls command history.
- **Tab** completes command names or files in the current directory.
- **Ctrl+L** clears the terminal screen.
- **Ctrl+C** cancels the current input line.
- The quick-start command buttons put a command at the prompt; press Enter to run it.

## Built-in commands

| Command | What it does |
| --- | --- |
| `help`, `man COMMAND` | Show shell help or a short manual page. |
| `pwd`, `ls [-la] [PATH]`, `cd [PATH]`, `cd -` | Navigate the simulated directory tree. `~` means `/home/guest`. |
| `tree [PATH]`, `cat FILE`, `head FILE`, `tail FILE`, `grep TEXT FILE`, `wc FILE` | Inspect virtual files. |
| `touch FILE`, `mkdir [-p] DIR`, `rm [-r] PATH`, `cp SRC DEST`, `mv SRC DEST` | Create and manage files/directories in the virtual disk. Core system directories are protected from removal. |
| `echo TEXT > FILE`, `echo TEXT >> FILE` | Write or append text using shell redirection. Quotes preserve spaces. |
| `nano FILE`, `edit FILE`, `vi FILE` | Open the built-in editor. |
| `compile FILE.mpl` | Assemble MPL source from the virtual disk into writable program RAM. |
| `run FILE.mpl` | Assemble and execute MPL on the MISK-16 emulator. OUT results appear in the terminal. |
| `lscpu`, `free`, `df`, `ps`, `env`, `uname`, `whoami`, `hostname` | Inspect the simulated system. |
| `history`, `date`, `uptime`, `neofetch` | Shell/session information. |
| `clear`, `reboot`, `shutdown`, `exit` | Screen and simulated system controls. |

`sudo` is deliberately disabled. The shell has a fixed command allowlist; unknown commands are not passed to the browser, operating system, or server.

## Terminal text editor

Run `nano FILE` to edit any file in the virtual filesystem. The editor is embedded in the console and supports plain text, multi-line editing, and two-space Tab indentation.

- **Ctrl+S** or **Ctrl+O** saves the file.
- **Ctrl+X** exits when there are no unsaved changes. If there are edits, save them or choose **DISCARD & EXIT**.
- **SAVE & EXIT** writes the current text and returns to the shell.

Create an MPL file, then build and run it from the same virtual shell. For example, copy or edit `hello.mpl`:

```mpl
LDI  R0, 40
ADDI R0, R0, 2
OUT  R0
HALT
```

```text
compile hello.mpl
run hello.mpl
```

The terminal compiler shares the MISK-16 machine with the Workbench. A program run updates the machine's registers, PC, flags, program RAM, data RAM, and output display; inspect those values by switching to **WORKBENCH**.

## Virtual disk and system boundaries

The simulated filesystem begins with `/bin`, `/dev`, `/etc`, `/home/guest`, `/proc`, `/tmp`, `/usr`, and `/var`. It has a **1 MiB virtual-disk quota** and is saved in the current browser's `localStorage` under `miskos.virtual-disk.v1`. Clearing browser site data may remove it. `reboot` clears emulated registers/flags/data RAM and keeps the virtual files. `shutdown` only halts the simulated shell; it does not power off the user's computer.

The visible Linux-inspired terminal is browser UI using keyboard input, and the computer's MPL CPU is still the MISK-16 software machine. The user-provided [PC.zip DLS project](https://github.com/proton-arcade/misk/raw/refs/heads/main/PC.zip) was used as hardware context for its custom gates, latches, registers, and adders. A separate [raw-gate DLS text pad](MISK16-GATE-LEVEL-DLS/README.md) uses individual NAND gates, a clock, DLS key chips, its built-in dot screen, and a wiring-only address adapter to enter four uppercase characters; it is a small hardware demonstration, not a Linux shell or persistent operating system.
