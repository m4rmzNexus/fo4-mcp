---
name: fo4-setup-check
description: |
  Pre-authoring readiness check for Fallout 4 modding. Verifies the toolchain
  (FO4 install, Creation Kit, .NET 8+9, Spriggit), reads the active load order
  (MO2 instance vs vanilla), and walks community best-practice guards before you
  start authoring: masters-first ordering, ESL budget headroom, FormID hygiene.
  Use at the START of any modding session, or when the user asks "is my setup
  ready", "check my environment", "what's my load order", or before running any
  other fo4-* authoring skill.
---

# fo4-setup-check

Pre-flight for FO4 mod authoring. Confirms the environment is sane and the load
order is safe to build on. Pure read-only: calls `fo4_get_environment` and
`fo4_read_load_order`, interprets them against the guards below, and emits a
**go / no-go** readiness report. It never writes.

## When to run

- First thing in a modding session.
- Before `fo4-record-edit`, `fo4-papyrus`, or any authoring flow.
- After the user changes their MO2 setup, installs F4SE, or updates the game.

## Steps

1. **Environment.** Call `fo4_get_environment`. Read off:
   - FO4 install dir + runtime version (expect 1.11.191 / AE).
   - Creation Kit present? (separate `Fallout 4 1946160/` dir.)
   - .NET: both 8 AND 9 SDK on PATH? (Spriggit needs net9 — see
     `docs/karar-7-license-strategy.md` and the dotnet9 requirement.)
   - Spriggit binary resolvable (`tools/spriggit/Spriggit.CLI.exe`)?
   - Caprica present (`tools/caprica/Caprica.exe`)?

2. **Load order.** Call `fo4_read_load_order`. Note `source` (`mo2` vs
   `vanilla`), `active_profile`, plugin `count`, and any `warnings`.

3. **Walk the guards** (checklist below). For each, state PASS / WARN / FAIL
   with the specific value that triggered it.

4. **Verdict.** Emit a short report:
   - `READY` — all guards PASS, environment complete.
   - `READY_WITH_NOTES` — authoring can proceed; list each WARN.
   - `BLOCKED` — a FAIL that stops authoring (e.g. no FO4 install, net9
     missing so Spriggit is dead). State exactly what to fix.

## Guards (community best-practice)

- **Toolchain complete.** FO4 install + .NET 9 are hard requirements; Spriggit
  is dead without net9 (FAIL). CK / Caprica missing = WARN (record + Papyrus
  work degrade but env-check and crash-triage still work).
- **Load-order source.** `source=mo2` is preferred for authoring — it isolates
  your work in a profile and keeps the vanilla `Data/` clean. `source=vanilla`
  = WARN: edits land in the shared plugins.txt with no profile isolation.
- **Masters-first.** ESM/ESL masters must sort before ESP plugins. If a plugin
  references a master that loads after it, flag FAIL (the engine won't resolve
  the dependency). Suggest a LOOT sort (`tools/loot`).
- **ESL budget.** Count `.esl` + ESL-flagged plugins. The light-master space is
  finite (FE slot). If the user is near the cap, WARN and suggest reserving
  ESL flags for genuinely small plugins (<2048 new records).
- **FormID hygiene (reminder, not a failure).** When new records get authored
  this session, they must use FormIDs ≥ `0x800`. Records below `0x800` are
  silently dropped by SPID-F4 and several distributors. State this up front so
  the YAML the user writes later starts in the safe range.
- **No duplicate / missing masters.** If `warnings` from `fo4_read_load_order`
  mention a missing or duplicated master, surface it as FAIL.

## Output shape

Keep it scannable. Example:

```
FO4 setup readiness: READY_WITH_NOTES

Environment
  FO4 install ........ PASS  1.11.191 (AE)
  Creation Kit ....... PASS  1.11.137
  .NET 8 + 9 ......... PASS  spriggit live
  Spriggit / Caprica . PASS

Load order (source=mo2, profile=default-ae, 7 plugins)
  Masters-first ...... PASS
  ESL budget ......... PASS  0 light plugins, full headroom
  Source isolation ... PASS  MO2 profile active

Notes
  - FormID reminder: author new records at ≥ 0x800 (SPID drops below).

Verdict: clear to author. Run /fo4-record-edit or /fo4-papyrus next.
```

## Notes

- This skill is read-only and safe to run anytime.
- If `fo4_read_load_order` reports `source=vanilla` but the user expected MO2,
  the MO2 instance probably isn't onboarded (no `ModOrganizer.ini`, or its
  `base_directory` profiles are empty). MO2 onboarding is done as of Session 6
  (instance data root `tools/mo2/portable-fo4-agentic/`); first-launch steps are
  in `docs/archive/handoff-from-session-5.md`.
