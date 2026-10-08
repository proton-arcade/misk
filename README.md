# MISK-16 · MPL Workbench

A compact 16-bit computer teaching project: write MPL assembly, load instructions into writable program RAM, directly edit CPU registers, and execute one instruction per deliberate button press. The design avoids shared buses, ROMs, free-running clocks, pulse generators, and tri-state buffers. A DLS-oriented project structure, circuit formulas, constraints, and test vectors are in [DIGITAL-LOGIC-SIM.md](DIGITAL-LOGIC-SIM.md); the full MPL reference is [MPL.md](MPL.md).

## Run the workbench

Open `index.html` in a modern browser, or serve the repository with a static server:

```sh
python3 -m http.server 8000
```

Then visit `http://localhost:8000`. There is no build step, package install, or backend. The included example sums 1 through 5; assemble it and step through the loop until OUTPUT shows `15 / 15`.

## What's included

- `index.html`, `style.css`, `app.js`: the interactive assembler and computer workbench.
- `MPL.md`: complete language and ISA summary with examples.
- `DIGITAL-LOGIC-SIM.md`: DLS project format notes, sorted chip collections, gate equations, hierarchy, and validation vectors.

**Native DLS note:** The web workbench is a behavioral implementation and the circuit notes are a build specification, not an imported `.dls` file. Build and save the physical gate project from within the linked Digital Logic Sim application; its project schema is versioned and DLS generates the required identifiers on save. DLS's stock stateful components generally use a clock, so the no-clock constraint is preserved by treating register editing/manual state as the teaching interface and restricting the DLS circuit recipes to combinational logic unless the target DLS version offers a suitable manual state component.
