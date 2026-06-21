---
name: fo4-armor-swap
description: |
  End-to-end authoring of a Fallout 4 armor variant: clone or swap an armor
  record (ARMO/ARMA), change its material/keywords/stats or model, add a
  craftable recipe (COBJ), and ship it ESL-flagged — all through the Spriggit
  YAML loop, with the mesh/texture/material GUI steps flagged. Use when the user
  wants to "make an armor mod", "retexture this armor", "swap the model",
  "create an armor variant", "add a craftable outfit", or continue the
  fixtures/armor-swap-test flow.
---

# fo4-armor-swap

The first composite authoring workflow (T1). Builds an armor variant by chaining
`fo4-record-edit` (record plumbing) and `fo4-papyrus` (if scripted), and points
at the GUI tools for the art assets it can't drive. The record half is fully
tool-driven and version-controlled; the art half is manual but sequenced.

Worked fixture: `fixtures/armor-swap-test/seed/` (telifsiz `test_armor.esp` +
serialized YAML) is the reproducible example to test the loop against.

## Decide the swap type first

| Type | What changes | Needs new art? | Effort |
|---|---|---|---|
| **Material swap (MSWP)** | textures only, same mesh | new BGSM + textures | low |
| **Stat/keyword variant** | AV, value, keywords, mods | none | lowest |
| **Model swap** | mesh (NIF) | new/edited NIF | medium |
| **New armor** | everything | mesh + textures + material | high |

Pick the lowest type that meets the goal (principle: simplicity first).

## Steps

1. **Pre-flight.** Run `fo4-setup-check`. Confirm MO2 mode + Spriggit live.

2. **Inspect the source.** `fo4_inspect_record(plugin, armor_formid)` on the
   vanilla/base ARMO. Note its `ArmorAddon` (ARMA) link, keywords, material
   (`BOD2`/biped slots), value/weight, and any `Object Template`/OMOD.

3. **Export to staging.** `fo4_spriggit_export(plugin, staging/<name>-yaml/)`.

4. **Author the record (YAML edit, via fo4-record-edit).**
   - **Stat/keyword variant:** edit the ARMO fields directly.
   - **Material swap:** add a `MaterialSwap` (MSWP) record + reference it from
     the ARMO (`Material Swap` field), pointing at your new BGSM paths.
   - **Model swap:** point the ARMA `Model` (and `2nd Model`/world model) at the
     new NIF path.
   - **New armor:** author ARMO + ARMA as new records (Spriggit deserializes
     hand-written YAML — no CK needed), FormIDs ≥ `0x800`.

5. **Craftable recipe (optional).** Author a COBJ: `Created Object` = your ARMO,
   `Workbench Keyword` = `WorkbenchArmor`, components + perk/condition. Lets the
   player build it at the armor workbench.

6. **Distribution (optional).** To inject into leveled lists / vendors without
   editing them directly, generate a SPID-F4 `_DISTR.ini` (keeps the plugin
   conflict-free). SPID config generation is a V2 tool (`docs/V2-backlog.md`);
   for now hand-write the INI and document it.

7. **Diff + import.** `fo4_spriggit_import` WITHOUT confirm → review diff →
   re-call with `confirm_overwrite=True`. Output plugin lands in `staging/`.

8. **Art assets (manual GUI — sequence, don't skip).**
   - **Mesh:** OutfitStudio (`tools/bodyslide/...`) to conform/edit the NIF, build
     BodySlide sliders so it fits body presets.
   - **Material:** Material Editor (`tools/material-editor/Material Editor.exe`) to
     author the BGSM/BGEM pointing at your textures.
   - **Textures:** author, then Cathedral Assets Optimizer (`tools/cao/...`) to
     BC-compress + generate mipmaps + fix the NIF for the AE runtime.

9. **Install + test.** Drop the staged plugin + assets into an MO2 mod folder
   under `tools/mo2/portable-fo4-agentic/mods/<ModName>/` (Data-relative layout),
   activate, launch, verify in-game (console `help "<name>" 4 ARMO`, craft, equip).

## Guards (community best-practice)

- **FormID range — the 0x800–0xFFF window.** SPID-F4 and distributors silently
  drop records below `0x800`; ESL eligibility caps new-record ObjectIDs at
  `0xFFF`. So a distributable, ESL-able armor authors its new records in
  **`0x800`–`0xFFF`**. Stay in that window.
- **Armor is the ESL textbook case.** Armor mods add records (ARMO/ARMA/OMOD/
  MISC/COBJ/keywords) but no new cells → ESL-flag by default (< 2048 new
  records). Saves a precious full load-order slot. Run `fo4-package-release`
  for the eligibility check; never have the END USER compact FormIDs.
- **AWKCR is deprecated (2025+).** Do NOT add an AWKCR (Armor & Weapon Keywords
  Community Resource) dependency to a new armor mod — it's heavy, conflict-prone,
  and stalled. Use vanilla keywords + a minimal custom keyword set; author a new
  INNR (Instance Naming Rule) only when you introduce new keywords.
- **BA2 naming is load-bearing.** If you pack assets, the archives MUST be named
  `<ModName> - Main.ba2` (meshes/scripts) and `<ModName> - Textures.ba2`
  (textures, separate) or the game won't auto-attach them → invisible mesh /
  missing texture. Ship v1 header for max compatibility (see `fo4-package-release`).
- **Biped slots must not collide** with what the player wears alongside it
  (check `BOD2` slot flags); slot conflicts = invisible/clipping armor.
- **Material swap > mesh edit** when only textures change — cheaper, no NIF risk.
- **Keep ARMO↔ARMA wiring intact.** An ARMO with a broken ArmorAddon link shows
  nothing equipped.
- **Precombines N/A for armor** (not worldspace-placed) — but if you ALSO place
  the armor as a static in a cell, see the precombine guard in `fo4-record-edit`.
- **CAO is mandatory for shipped textures** — uncompressed/wrong-format DDS
  tanks VRAM and can CTD on the AE runtime.

## Notes

- Pairs with `fo4-record-edit` (the YAML loop), `fo4-papyrus` (if the armor has a
  script, e.g. an effect on equip), and `fo4-package-release` (ESL + BA2 + FOMOD).
- BA2 packing of the final assets is a V2 gap (`docs/V2-backlog.md` #4); for now
  ship loose files or pack manually with `tools/xedit/BSArch64.exe` (mind the
  v1-vs-v7/v8 header version for AE/NG).
