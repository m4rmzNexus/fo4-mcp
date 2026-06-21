---
name: fo4-record-edit
description: |
  Safely view and edit a Fallout 4 plugin record through the Spriggit
  serialize → edit → diff → deserialize loop, with version-controllable YAML
  and a mandatory diff gate before any binary write. Use when the user wants to
  inspect, tweak, or author an ESP/ESM/ESL record (armor stats, keywords,
  globals, leveled lists, constructible objects, quest data) without opening
  the Creation Kit. Use when they say "edit this record", "change the armor
  value", "look at FormID ...", "serialize this plugin", or "swap this field".
---

# fo4-record-edit

The core authoring primitive. Edits records through Spriggit's lossless
ESP↔YAML serialization instead of touching the binary plugin directly, so every
change is a reviewable text diff and the original is never silently clobbered.

This is the safe loop: **inspect → export → edit YAML → diff → import (gated)**.

## When to run

- Editing an existing record's fields (armor AV, keywords, value, weight…).
- Authoring a NEW record by writing its YAML (Spriggit deserializes it into the
  plugin — no CK needed for record plumbing).
- Putting a plugin under version control (the exported YAML is git-trackable).

## The loop

1. **Inspect first.** Call `fo4_inspect_record(plugin, record_id)` to confirm
   the record exists and see its current EditorID / FormKey / type / fields.
   `record_id` accepts `0x...`, bare hex, or an 8-digit load-order FormID (the
   tool normalizes to the in-mod 6-digit id). If it's not found, stop and
   report — don't guess the FormID.

2. **Export to staging.** Call `fo4_spriggit_export(plugin_path, output_dir)`
   with `output_dir` under `staging/` (e.g. `staging/<plugin>-yaml/`). This
   writes the whole plugin as YAML. Never export into the Steam `Data/` folder
   or the live MO2 mods dir.

3. **Edit the YAML.** Open the record's `.yaml` file in the export tree and make
   the change as a normal text edit. Show the user the edit. Keep the `ModKey`
   line untouched — preserving it is what makes the roundtrip byte-identical
   (see `research/p0/spriggit/2026-05-15-roundtrip.md`).

4. **Diff gate (mandatory).** Call `fo4_spriggit_import(source_dir,
   output_plugin)` WITHOUT `confirm_overwrite`. When `output_plugin` already
   exists, the tool returns `diff_required: true, wrote: false` plus the YAML
   diff. Present that diff to the user and get explicit approval.

5. **Commit the write.** Only after approval, call again with
   `confirm_overwrite=True`. The tool backs up the existing plugin to `.bak`
   and deserializes the YAML into the binary plugin.

6. **Verify roundtrip.** Re-export the written plugin and confirm the record now
   shows the intended values. For a sanity check, the YAML should be stable on a
   second serialize.

## Guards (community best-practice)

- **Never hand-edit the binary ESP.** Always go through serialize/deserialize.
  Binary edits aren't diffable and corrupt subrecord offsets.
- **Output lands in `staging/` only.** The path policy denies writes to the
  Steam `Data/` folder; keep YAML exports and rebuilt plugins in `staging/`,
  then the user installs them via MO2.
- **Diff before every overwrite.** No silent overwrite — the `confirm_overwrite`
  gate exists precisely because the binary `.esl/.esp` is NOT byte-stable even
  when the YAML is. Show the diff, get a yes.
- **`.bak` is your safety net.** The import keeps one. If a write looks wrong,
  restore from `<plugin>.bak` before re-trying.
- **FormID ≥ 0x800 for new records.** Records below `0x800` are silently dropped
  by SPID-F4 and other distributors. When authoring new YAML records, start the
  FormID in the safe range.
- **Preserve `ModKey`.** Changing it breaks the master/dependency wiring and
  makes the roundtrip lossy.
- **Precombine awareness.** If you edit a CELL or a placed reference (STAT/MSTT
  in a worldspace cell), you may invalidate precombines/previs → stutter and
  occlusion bugs. Warn the user and point at PRP (`tools/prp`) + the
  `research/p0/bos/2026-05-28-precombine-safety.md` notes.

## Notes

- For master-scale plugins (`Fallout4.esm`), the full export is slow (Spriggit
  serializes the whole file). That's a known perf cost; a record-scoped path is
  V2 (`docs/V2-backlog.md` #2). For mod-sized plugins it's fine.
- Pairs with `fo4-setup-check` (run that first) and `fo4-papyrus` (when the
  record change needs a script).
