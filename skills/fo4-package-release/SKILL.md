---
name: fo4-package-release
description: |
  Prepare or review a Fallout 4 release: decide plugin flags (ESL / ESM-flagged
  ESP / plain ESP), check previs and masters, pack BA2 assets with the right
  name and header, generate a FOMOD, and check the final ZIP for missing or
  externally supplied files. Use when the user wants to "release this mod",
  "package my mod", "can this be ESL-flagged", "make a FOMOD", "pack a BA2",
  review a downloaded ZIP, or chase missing textures / purple meshes in a release.
---

# fo4-package-release

Release-hygiene workflow. Runs the pre-upload checklist a careful FO4 author
runs by hand, grounded in the actual plugin, load order and archive. Start from
the artifact the user wants checked: a ZIP-only review can begin at step 6.

## Steps

1. **Preflight the plugin.** `fo4_release_preflight(plugin)` on the actual
   release plugin. It composes plugin format, navmesh, previs and voice
   findings into one verdict (ship-blocked > review > ship-ready). Follow up
   on each finding that affects this mod; a sub-check that could not run is a
   warning, not a pass.

2. **Plugin flags.** `fo4_plan_plugin_format(plugin)` returns the current TES4
   flags and the content-derived recommendation; `fo4_check_esl_eligibility`
   gives new-record count, max ObjectID and new-cell count. Decide:
   - **Adds new cells / worldspaces / interiors -> ESM-flagged `.esp`, not ESL.**
     Previs/precombines cannot be built for FE-space (ESL) cells.
   - **No new cells, < 2048 new records, new ObjectIDs within `0x001-0xFFF`
     -> ESL-flag** (saves a full load-order slot). SPID-distributed records stay
     in `0x800-0xFFF`.
   - Otherwise plain ESP.
   Write flags with `fo4_set_esl_flag` / `fo4_set_master_flag` to a staged copy.
   **Compaction is a separate, irreversible decision**: it changes FormIDs used
   by saves, voice assets and dependent mods. Only on an unreleased plugin no
   save uses yet; never on a published one; the end user never compacts.

3. **Previs / precombine safety.** For every worldspace CELL the plugin edits,
   `fo4_check_previs_safety(cell, source_plugin)`. No worldspace edits = SAFE.
   Otherwise: rebuild previs (`fo4_build_previs`, CK-gated), ship a PRP patch, or
   state "previs-breaking" in the description.

4. **Masters.** Compare the plugin's masters with `fo4_read_load_order` for the
   target profile. Missing or disabled masters = FAIL. Clean accidental
   dependencies on mods that were only enabled while authoring.

5. **BA2 packing (when the release ships archives).**
   `fo4_pack_ba2(source_dir, output_ba2, archive_type)` on staged files:
   - **Naming is load-bearing:** `<Plugin> - Main.ba2` (meshes, scripts, misc)
     and `<Plugin> - Textures.ba2` (`archive_type="textures"`, packs DX10; separate
     archive). Wrong names = the game never attaches them = invisible meshes /
     missing textures.
   - **Header version** must match the target runtime. Check the returned
     header, file count and warnings. For maximum compatibility downgrade an NG
     archive with `fo4_ba2_version_patch(ba2_path, output_path, target_version=1)`
     (gated output + `.bak`; warns on DX10 textures). Record the version chosen.
   - If the BSArch backend is missing, report it and finish the independent checks.

6. **FOMOD installer (when options are requested).**
   `fo4_generate_fomod(spec, output_dir)` emits `fomod/info.xml` +
   `fomod/ModuleConfig.xml` from name/author/version, `required_files` and
   `install_steps` -> groups -> plugins. Output is gated to `staging/`.

7. **Check the final ZIP.** `fo4_check_release_zip(archive, expected_members, catalog, verify_crc)`:
   - `expected_members`: exact archive-root paths of every required deliverable
     (the plugin, BA2s, any custom loose assets).
   - It reports missing members, case-insensitive collisions, FOMOD source
     paths across all options, and loose NIF shader / material references.
   - `verify_crc=true` reads every member payload; use it for the release check.
   - Pass the catalog for the intended profile to see which external provider
     (base game, DLC, another mod) supplies a referenced file.

8. **Missing textures or purple meshes.** For a plain ZIP, inspect the reported
   NIF shader and material references. If a dependency should come from the
   base game or another mod, trace it with `fo4_trace_catalog_asset` (see
   `fo4-asset-trace`) and check that the provider is a declared requirement.
   Assets inside a BA2 are not covered by the ZIP check; inspect the archive
   separately. A developer's loose fallback in their own Data can hide an
   omission in the release.

9. **Release report.** Plugin flag verdict, previs verdict, masters, BA2 names
   and version, FOMOD present, the exact archive checked, missing or externally
   supplied paths, and the `staging/` paths of the artifacts.

## Guards (community best-practice)

- **Never ESL-flag a plugin with > 2048 new records, new cells, or full-master
  dependents.** It drops records or breaks dependents.
- **Previs-breaking mods must say so** or ship a patch.
- **Published FormIDs stay stable** across updates.
- **Ship script source** (`.psc` alongside `.pex`, see `fo4-papyrus`).
- **Keep three results separate:** package inspection, a clean-profile install,
  and an observed in-game result. To claim a FOMOD option installs correctly,
  exercise that selection in a test profile.

## Notes

- Pairs with `fo4-armor-swap` / `fo4-quest-author` (what is being packaged)
  and `fo4-asset-trace` (where an external file comes from).
