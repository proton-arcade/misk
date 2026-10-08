# MISK16 raw-gate text pad for Digital Logic Sim 2.1.6

This separate DLS project is a small gate-level hardware text-entry demonstration. Open the **MISK16_GATE_TEXT_PAD** chip, start the DLS simulator, then press the letter keys A–Z. Press **1** to write a blank cell and **0** to clear the four-character buffer. The 16×16 dot display shows four 3×5 uppercase glyphs in a one-line scratchpad; new letters wrap and overwrite from the first cell.

## Circuit policy

- All logic, character storage, cursor state, key-edge detection, font decoding, and screen scanning is made from individual primitive DLS NAND gates.
- The only other DLS components are one **CLOCK**, alphanumeric **KEY** components, the permitted **DOT DISPLAY**, and one **1-8BIT** signal-width adapter used solely to join the eight address wires required by the display.
- There are no DLS custom CPU/ALU/register/RAM/ROM chips, no prebuilt DLS logic blocks, no PULSE, BUS, or tri-state wiring. The only stored display pixels are inside the explicitly permitted DOT DISPLAY; the four text cells are raw NAND-gate clocked latches.
- The DLS screen is a four-character hardware text-pad demo, not a Linux kernel, full operating system, or hardware version of the browser shell. The browser's MISK Linux remains an educational software simulation. DLS is used here for the hand-built digital input, state, font and screen-IO logic.

The DLS built-in NAND is the primitive logic gate; DLS's CLOCK, KEY and DOT DISPLAY are the expressly permitted interface devices. Character cells and control state use hand-wired master/slave NAND latches clocked by the DLS CLOCK. Hold one key through a clock edge so the press is sampled, then release it before the next key. The simulator starts paused; resume it to scan the screen.

Generated contents: 1766 subchips total, including 1735 individual NAND gates, 28 KEY chips, one CLOCK, one DOT DISPLAY, and one 1-8BIT address adapter. `tools/build_dls_text_terminal.py` rebuilds this project. DLS's own GUI import/save remains the final compatibility check.
