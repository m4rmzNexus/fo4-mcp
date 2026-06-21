---
name: fo4-crash-debug
description: |
  Triage a Fallout 4 crash by parsing a Buffout 4 / Addictol crash log and
  cross-referencing the culprit against the active load order. Use when the user
  has a crash log, says "the game crashed", "why did FO4 crash", "read this
  crash log", "what's causing this CTD", or points at a file under
  Documents/My Games/Fallout4/F4SE/crash-*.log. Produces a triage report with a
  probable culprit and a concrete fix, not a guess.
---

# fo4-crash-debug

Turns a raw crash log into an actionable triage. Parses the log natively
(`fo4_analyze_crash_log`) and checks the named culprit against the user's real
load order (`fo4_read_load_order`) so the fix is grounded in what's actually
installed.

## When to run

- The user has a `crash-YYYY-MM-DD-*.log` from Buffout 4 / Addictol.
- A repeatable CTD they want diagnosed.
- After an authoring change, to confirm a new plugin isn't the culprit.

## Steps

1. **Locate the log.** Crash logs live in
   `%USERPROFILE%/Documents/My Games/Fallout4/F4SE/crash-*.log`. If the user
   didn't give a path, the most recent file there is the one to read.

2. **Parse.** Call `fo4_analyze_crash_log(crash_log_path)`. It returns the
   exception, the crash generator (Buffout vs Addictol) + version, the top call
   stack frames (module + offset), loaded XSE plugins, and the plugin list.
   `analyzer` is `native` (CLASSIC is not invoked — see `docs/V2-backlog.md` #5).

3. **Cross-reference.** Call `fo4_read_load_order`. Match the top non-engine
   stack frames and any named plugin against the active load order:
   - Which loaded plugin/DLL owns the faulting module?
   - Where does it sit in load order — is something overriding it?
   - Is a referenced master missing or disabled?

4. **Triage report.** Emit:
   - **Exception + faulting module** (one line).
   - **Probable culprit** — the plugin/DLL, with why (which frame, which load
     order interaction).
   - **Fix** — concrete: disable X, reorder Y after Z, update plugin to AE
     build, install the missing master, or "engine-level / Address Library
     mismatch" if no mod owns the frame.
   - **Confidence** — high / medium / low, and what would raise it.

## Guards (community best-practice)

- **Engine frames ≠ culprit.** A top frame in `Fallout4.exe` or a core DLL
  usually means the *real* cause is data/load-order, not that module. Keep
  reading down the stack to the first mod-owned frame.
- **Address Library mismatch is the classic AE crash.** If XSE plugins fail to
  load or the runtime version (1.11.191) doesn't match a plugin's expected
  build, flag it first — it's the most common false "random crash".
- **Load-order position matters.** A culprit that's fine alone can crash when
  overridden. Always state the culprit's index and what loads around it.
- **Missing master = hard fail.** If the plugin list references a master not in
  the active load order, that's almost certainly the crash — surface it.
- **Don't over-claim.** If no mod-owned frame and no load-order anomaly, say so
  and mark confidence low rather than blaming a random plugin.

## Notes

- The parser handles both Buffout 4 and Addictol formats (Addictol is the 2026
  NG/AE standard; see `research/p0/addictol/2026-05-28-vs-buffout.md`).
- **Config neighbor:** if the crash smells engine-level (memory, scaleform,
  Papyrus op limit) or you suspect double-patching, run
  **`fo4_lint_engine_config(config_path, plugins_dir=...)`** — it flags no-op
  settings, bad scaleform values, and Addictol coexisting with standalone
  Buffout4/X-Cell/Baka (a common stutter/CTD cause). Addictol bundles all three,
  so running the standalones too double-patches the engine.
- Enriching with CLASSIC's known-bad-mod database (FormID → mod) is V2
  (`docs/V2-backlog.md` #5). For now the triage is stack + load-order based.
