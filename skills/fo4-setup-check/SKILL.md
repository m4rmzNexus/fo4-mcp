---
name: fo4-setup-check
description: |
  Pre-authoring readiness check for Fallout 4 modding. Reads the game and F4SE
  loader file versions, verifies only the backends the next operation needs
  (mutagen-cli, Spriggit, Caprica, BSArch, texconv ...), reads the MO2 profile and
  load order, and walks the community guards (masters-first, ESL budget, FormID
  hygiene). Use at the start of a modding session, when a tool reports a missing
  binary, when a supported field disappears on readback, or when the user asks
  "is my setup ready", "check my environment", "what's my load order".
---

# fo4-setup-check

Read-only pre-flight. Calls `fo4_get_environment` and `fo4_read_load_order`,
interprets them against the guards below and emits a **go / no-go** report
scoped to what the user wants to do next. It never writes.

## When to run

- First thing in a modding session, before `fo4-record-edit`, `fo4-papyrus` or
  any authoring flow.
- After the game, F4SE, the MO2 setup or a tool binary changes.
- When a field the writer supports is missing from the readback.

## Steps

1. **Environment.** Call `fo4_get_environment(check_tools=[...])` with only the
   backends the next operation needs:

   | Next operation | `check_tools` |
   |---|---|
   | `fo4_create_record`, fast `fo4_inspect_record` | `mutagen-cli` |
   | `fo4_spriggit_export` / `_import` | `spriggit` |
   | `fo4_papyrus_build` | `caprica` |
   | `fo4_pack_ba2` | `bsarch` |
   | `fo4_encode_texture` | `texconv` |
   | `fo4_nif_build` | `nifsharp-cli` |

   Read off:
   - `fo4.runtime_version` and `f4se.version`: numeric file versions read
     without starting the executables (e.g. `1.11.240.0`, `0.7.9`). Compare
     them with what the profile's F4SE plugins and Address Library expect; a
     mismatch is the usual cause of "plugin failed to load".
   - `f4se.data_dir_present` and the `mo2` block. `mo2` null means no MO2
     instance was detected: set `MO2_INSTANCE_DIR` in `mcp-server/.env`.
   - `tool_status.<name>`: `listed`, `present`, `sha256_matches`. For
     mutagen-cli also read `managed_dll.sha256_matches`: the `.exe` apphost is
     the same across rebuilds, only the managed `.dll` identifies the build.
     `null` means no hash is recorded, so the identity is **unverified**, not OK.
   - Creation Kit: the CK tools expect `CreationKit.exe` next to `Fallout4.exe`
     in the detected install dir.

2. **Load order.** Call `fo4_read_load_order`. Note `source` (`mo2` vs
   `vanilla`), `active_profile`, plugin `count` and `warnings`. A vanilla
   fallback cannot establish the state of a requested MO2 profile.

3. **Walk the guards** (below). For each, state PASS / WARN / FAIL with the
   value that triggered it.

4. **Verdict**, scoped to the requested operation:
   - `READY`: every guard the operation depends on passes.
   - `READY_WITH_NOTES`: it can proceed; list each WARN.
   - `BLOCKED`: name the exact dependency and the fix.

   Checking a finished ZIP or querying an existing catalog can proceed while the
   game, compiler or CK is unavailable. Report only the checks that actually ran.

## Guards (community best-practice)

- **Backend per operation.** A missing backend blocks only the tools that use
  it: no Caprica blocks `fo4_papyrus_build`, not record work. Spriggit needs a
  .NET 9 runtime; without it Spriggit fails with a misleading
  "DotnetToolSettings.xml not found".
- **Writer identity.** A stale mutagen-cli build silently drops fields that the
  source supports. If `managed_dll.sha256_matches` is false, rebuild from
  `tools/mutagen-cli/src/` with
  `dotnet publish src/Mutagen.RecordQuery.csproj -c Release -r win-x64 --self-contained false -o tools/mutagen-cli`
  and record the new `managed_dll_sha256` in `tools/MANIFEST.md`.
- **Load-order source.** `source=mo2` is preferred for authoring: work stays in
  a profile and the game `Data/` stays clean. `source=vanilla` = WARN.
- **Masters-first.** ESM/ESL masters sort before ESP plugins. A plugin that
  references a master loading after it = FAIL (the engine won't resolve it).
  Suggest a LOOT sort.
- **ESL budget.** Count `.esl` and ESL-flagged plugins; the light-master space
  is finite. Near the cap = WARN; reserve ESL for small plugins (< 2048 new
  records). For the plugin itself use `fo4_plan_plugin_format` and
  `fo4_check_esl_eligibility`.
- **FormID hygiene (reminder).** New records start at ObjectID `0x800`; SPID-F4
  and several distributors silently drop records below it.
- **Missing or duplicate masters.** A missing master is FAIL for the plugins
  that depend on it, and only for those.

## Output shape

```
FO4 setup readiness (for: record authoring): READY_WITH_NOTES

Environment
  FO4 runtime ........ PASS  1.11.240.0
  F4SE loader ........ PASS  0.7.9, Data/F4SE present
  mutagen-cli ........ PASS  exe + managed DLL hash match MANIFEST
  Spriggit ........... PASS  present, hash match

Load order (source=mo2, profile=<profile>, 12 plugins)
  Masters-first ...... PASS
  ESL budget ......... PASS  2 light plugins
  Source isolation ... PASS  MO2 profile active

Notes
  - Caprica not installed: Papyrus compile blocked (not needed for this task).
  - FormID reminder: author new records at >= 0x800.
```

## Notes

- Read-only and safe to run any time.
- `source=vanilla` while MO2 was expected: `MO2_INSTANCE_DIR` is unset or the
  instance has no `ModOrganizer.ini` / `profiles/`. Auto-detect only checks
  `tools/mo2/portable` and `%LOCALAPPDATA%/ModOrganizer/Fallout4`.
- Pairs with every other `fo4-*` skill; run it first.
