---
name: fo4-papyrus
description: |
  Compile Fallout 4 Papyrus scripts (.psc → .pex) with Caprica, resolving the
  standard include paths (vanilla Base, F4SE, Lighthouse Papyrus Extender) and
  reporting compile diagnostics. Use when the user wants to write, compile, or
  debug a Papyrus script — quest scripts, alias scripts, magic-effect scripts,
  fragments — or says "compile this script", "build my papyrus", "fix this .psc
  error", or "why won't this compile". Output .pex lands in staging/.
---

# fo4-papyrus

Compiles Papyrus through Caprica (MIT, fast, no Creation Kit launcher needed).
Caprica is the supported MVP backend; the Bethesda `PapyrusCompiler.exe` is
deferred to V2 because it won't run headless (`docs/V2-backlog.md` #1).

## When to run

- Writing a new script and compiling it.
- Fixing compile errors in an existing `.psc`.
- Rebuilding scripts after a record/quest change from `fo4-record-edit`.

## Steps

1. **Stage the source.** Put the `.psc` under `staging/` (or a fixtures source
   dir). Never compile into or write `.pex` to the Steam `Data/` folder.

2. **Resolve includes.** Papyrus needs its import paths. The standard set:
   - **vanilla Base** — `tools/papyrus-source/Base/` (Form, Quest, ObjectReference…).
   - **F4SE** — `tools/f4se/f4se_0_07_07/Data/Scripts/Source/` (F4SE.psc and the
     extended script headers).
   - **Lighthouse Papyrus Extender** — if the script uses LPE functions, add its
     source path (`tools/lighthouse-papyrus/...`). PapyrusUtil F4 does not
     exist; LPE is its replacement (see `tools/MANIFEST.md`).

3. **Compile.** Call `fo4_papyrus_build(source_paths, output_dir)` with
   `output_dir` under `staging/`. The tool drives Caprica
   (`--game fallout4 --ignorecwd -i <include> ... -f FLG -o <out>`) and returns
   exit code + produced `.pex` paths + any compiler diagnostics.

4. **Read diagnostics.** On failure, surface the exact Caprica error line. The
   usual causes are below.

5. **Deploy note.** The `.pex` is in `staging/`. To run it in-game, the user
   installs it as a mod via MO2 (Data/Scripts/<name>.pex) — don't copy into the
   Steam folder.

## Guards (community best-practice)

- **Missing include = the #1 error.** `unknown type Quest` / `unknown type
  ObjectReference` means the Base import path is missing; an F4SE function not
  found means the F4SE source path is missing. Add the path and recompile
  before assuming the script is wrong.
- **Compile clean — no warnings ignored.** Treat Caprica warnings as real;
  shipped scripts should compile without them.
- **Source AND .pex ship together.** Distribute the `.psc` alongside the `.pex`
  so others (and future-you) can recompile. Authoring repos keep both.
- **Caprica vs Bethesda bytecode.** Caprica output is functionally equivalent;
  no in-practice `.pex` difference has been observed
  (`research/p0/papyrus/2026-05-15-bytecode-diff.md`). If a script ever behaves
  differently at runtime than expected, that's the one case to consider the CK
  compiler (V2).
- **Script names match.** The `.psc` filename, the `ScriptName` header, and the
  record's attached-script name must all agree, or the engine won't bind it.

## Notes

- Pairs with `fo4-record-edit`: edit the record to attach a script, then compile
  the script here.
- Decompilation (`.pex → .psc`) is available via Champollion
  (`tools/champollion`) for reverse-engineering vanilla scripts — not wired as a
  tool, run manually.
