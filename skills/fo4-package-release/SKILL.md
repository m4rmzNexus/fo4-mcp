---
name: fo4-package-release
description: |
  Pre-release packaging + hygiene for a Fallout 4 mod: check ESL-flag
  eligibility, verify precombine/previs safety, pack assets into a BA2 with the
  correct header version for the runtime, and scaffold a FOMOD installer. Use
  when the user wants to "release this mod", "package my mod", "can this be
  ESL-flagged", "make a FOMOD", "pack a BA2", or do a final pre-upload check.
  Surfaces what's tool-driven vs what's a V2 gap / manual step.
---

# fo4-package-release

The release-hygiene workflow (T2). Runs the pre-upload checklist a careful FO4
author runs by hand, grounded in the actual plugin + load order. Some steps are
tool-driven today; BA2 packing is a V2 gap and flagged as manual.

## Steps

1. **Inspect the plugin.** Export it (`fo4_spriggit_export`) and read the record
   set: count new records, note FormID range, note any CELL/STAT/worldspace
   edits, masters required.

2. **ESL vs ESM vs plain ESP.** Decide the flag by what the plugin contains:
   - **Adds new cells / worldspaces / interiors → ESM-flagged `.esp`, NOT ESL.**
     Previs/precombine cannot be built for FE-space (ESL) cells, so a
     cell-creating mod must stay full-master (ESM flag) for stable load + previs.
   - **No new cells, < 2048 new records, new-record ObjectIDs within
     `0x001–0xFFF` → ESL-flag** (saves a full load-order slot). If the mod is
     also SPID-distributed, keep new records in `0x800–0xFFF` (SPID drops below
     0x800).
   - Otherwise → plain ESP.
   Call **`fo4_check_esl_eligibility(plugin)`** — it serializes the plugin and
   returns new-record count, max ObjectID, new-cell count, and the advisory
   verdict (esm-flag / esl-eligible / esl-needs-compaction / plain-esp). Report
   it with the counts; the tool is read-only and never writes flags.
   - **Compaction is gated + irreversible.** If records exceed `0xFFF`, ESL needs
     FormID compaction (xEdit → "Compact FormIDs for ESL"). This is
     **save-breaking and one-way** — do it on YOUR plugin only, before any save
     uses it, never on a released/in-use plugin, and the END USER must never
     compact. Treat as a user-gated step (`fo4_compact_formids`, V2 #14).

3. **Precombine / previs safety.** If the plugin edits worldspace CELLs or moves
   /disables placed references, it likely breaks precombines → stutter + visual
   holes. Verdict:
   - No worldspace edits → SAFE.
   - Worldspace edits → WARN: rebuild previs in the CK, OR ship a PRP patch, OR
     mark the mod "previs-breaking" in the description. See
     `research/p0/bos/2026-05-28-precombine-safety.md` and `tools/prp`.

4. **Load-order / master check.** Run `fo4_read_load_order`. Confirm every master
   the plugin needs is present; flag missing/disabled masters. Suggest a LOOT
   sort (`tools/loot`) for the release's recommended order.

5. **BA2 packing (V2 gap — manual for now).** Loose files work but BA2 loads
   faster and is tidier. Two load-bearing rules:
   - **Naming:** `<ModName> - Main.ba2` (meshes/scripts/misc) and
     `<ModName> - Textures.ba2` (textures, separate archive). Wrong names → the
     game won't auto-attach the archive → invisible meshes / missing textures.
   - **Header version:** this AE/NG install mixes v1 (OG) and v7/v8 (NG) headers
     (`research/p0/spriggit/2026-05-28-ng-ba2.md`); a wrong version byte = the
     runtime won't load it. **Ship v1 for maximum compatibility** (OG / downgraded
     games / older tools / BASS users can read it).
   Prefer **BSArchPro** (Nexus mods/63243 — actively maintained, outputs both OG
   and NG) over Archive2; `tools/xedit/BSArch64.exe` also works (`fo4_pack_ba2`
   wrapper is download-blocked, V2 #8). To downgrade an NG archive to v1, call
   **`fo4_ba2_version_patch(ba2_path, output_path, target_version=1)`** — a
   pure-Python header rewrite (gated output + .bak; warns on DX10 textures).
   Document the version chosen.

6. **FOMOD installer scaffold.** For a multi-option release, call
   **`fo4_generate_fomod(spec, output_dir)`** — it emits `fomod/info.xml` +
   `fomod/ModuleConfig.xml` from a spec (name/author/version + `required_files`
   + `install_steps` → groups → plugins with files + type). Output is gated to
   `staging/`. It validates the group/plugin type enums and warns on
   non-standard values. Build the spec from the user's option layout.

7. **Final manifest.** Emit a release checklist report: ESL verdict, previs
   verdict, masters OK, BA2 version (if packed), FOMOD present, and the exact
   `staging/` paths of the artifacts.

## Guards (community best-practice)

- **Don't ESL-flag a plugin that needs > 2048 records or full-master status** —
  it'll drop records or break dependents. The check is non-negotiable.
- **Previs-breaking mods MUST say so** or ship a patch. Silent previs breakage is
  the most-reported "your mod causes stutter" bug.
- **BA2 version must match the runtime.** Default to the AE/NG version on this
  install; never guess. Wrong version = silent load failure.
- **Ship source with scripts** — `.psc` alongside `.pex` (see `fo4-papyrus`).
- **Clean masters list** — no accidental dependency on a mod the user had
  enabled while authoring (xEdit "clean masters" / check the masters block).
- **Test the FOMOD** install path in MO2 before upload (a broken ModuleConfig.xml
  installs nothing).

## Notes

- BA2 packing and ESL-flag *writing* are the two V2 gaps here; everything else is
  doable today. Both are tracked in `docs/V2-backlog.md` (#3, #4) and should
  become MCP tools (`fo4_pack_ba2`, ESL-flag write) — propose the task in
  `TASKS.md` before building.
- Pairs with `fo4-armor-swap` / `fo4-quest-author` (the things being packaged).
