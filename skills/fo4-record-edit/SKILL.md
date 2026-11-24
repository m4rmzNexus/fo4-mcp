---
name: fo4-record-edit
description: |
  Inspect a Fallout 4 plugin record by FormID or EditorID, change existing
  record fields, author supported new records, or round-trip a plugin through
  Spriggit YAML with a mandatory diff gate before any binary overwrite. Use when
  the user says "look at FormID ...", "edit this record", "change the armor
  value", "serialize this plugin" or "swap this field", without opening the
  Creation Kit.
---

# fo4-record-edit

The core authoring primitive. Existing records are edited through Spriggit's
ESP <-> YAML serialization so every change is a reviewable text diff and the
original is never silently clobbered. New plugins with supported record types
can be written directly by the Mutagen writer (`fo4_create_record`).

The safe loop: **inspect -> export -> edit YAML -> diff -> import (gated) -> re-export**.

## When to run

- Reading a record: identity, type, compact field summary.
- Editing an existing record's fields (armor rating, keywords, value, weight ...).
- Authoring new records: `fo4_create_record` for supported types, hand-written
  YAML through Spriggit for anything else.
- Putting a plugin under version control (the exported YAML is git-trackable).

## The loop

1. **Inspect first.** `fo4_inspect_record(plugin, record_id)`. `record_id`
   accepts an EditorID, `0x...`, bare hex or an 8-digit load-order FormID (the
   tool normalizes to the plugin-relative 6-digit id). Pass an absolute plugin
   path; a bare `Fallout4.esm` is resolved against the repo root. Check the
   reported backend: the mutagen-cli fast path returns identity plus a compact
   summary; use a Spriggit export when the task needs fields the summary omits.
   If nothing matches, check the plugin and whether the id is load-order or
   plugin-relative. Do not guess a FormID.

2. **Export to staging.** `fo4_spriggit_export(plugin_path, output_dir)` with
   `output_dir` under `staging/` (e.g. `staging/<plugin>-yaml/`). Never export
   into the game `Data/` or the live MO2 mods directory.

3. **Edit the YAML.** Change the record's `.yaml` as a normal text edit and show
   the edit. Keep the `ModKey` line, reference targets and existing FormIDs
   untouched; preserving them is what keeps the round trip lossless.

4. **Diff gate (mandatory).** `fo4_spriggit_import(source_dir, output_plugin)`
   WITHOUT `confirm_overwrite`. For a first round trip, import to a separate
   staged output. If `output_plugin` exists the tool returns
   `diff_required: true, wrote: false` plus the diff. Present it and get an
   explicit yes.

5. **Write.** Only after approval call again with `confirm_overwrite=True`. The
   tool keeps a `.bak` of the existing plugin.

6. **Verify.** Re-export the written plugin and compare the changed fields and
   references. Spriggit compares serialized data; binary byte identity is a
   separate check.

### New records with the Mutagen writer

`fo4_create_record(spec, output_plugin)` writes supported types (NPC, ARMO,
WEAP, QUST + dialogue, FLST, MESG, GLOB, FACT, LVLN/LVLI, CELL, ACTI, LCTN,
PACK, BOOK, MISC, MSWP, OTFT, STAT, DOOR, LIGH, CONT, ALCH, INGR, COBJ ...;
the tool error lists the exact set). It reads its output back from disk. If a
field the source supports is missing from the readback, check the writer build:
`fo4_get_environment(check_tools=["mutagen-cli"])` and compare
`managed_dll.sha256_matches` (see `fo4-setup-check`).

## Guards (community best-practice)

- **Never hand-edit the binary ESP.** Binary edits are not diffable and corrupt
  subrecord offsets.
- **Output lands in `staging/`.** The path policy denies writes to the game
  `Data/`; the user installs staged output through MO2.
- **Diff before every overwrite.** The binary is not byte-stable even when the
  YAML is. No silent overwrite.
- **`.bak` is the safety net.** Restore from `<plugin>.bak` if a write looks wrong.
- **FormID >= 0x800 for new records.** SPID-F4 and distributors drop lower ids.
- **Preserve `ModKey` and published FormIDs.** Changing them breaks masters,
  saves and dependents.
- **Precombine awareness.** Editing a CELL or a placed reference can invalidate
  precombines/previs (stutter, holes). Run `fo4_check_previs_safety(cell)` on
  the specific cell and warn the user.

## Notes

- A full `Fallout4.esm` export is slow (Spriggit serializes the whole file);
  prefer `fo4_inspect_record` for lookups on master-scale plugins.
- For player-visible changes, name which behavior still needs an in-game test
  (`fo4-ingame-test`).
- Pairs with `fo4-setup-check` (run first) and `fo4-papyrus` (when the change
  needs a script).
