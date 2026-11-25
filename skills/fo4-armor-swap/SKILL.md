---
name: fo4-armor-swap
description: |
  Create or repair a Fallout 4 armor variant end to end: stats or keyword
  variant, material swap, model swap or new armor (ARMO/ARMA), craftable recipe
  (COBJ), materials and textures, and release flags. Use when the user wants to
  "make an armor mod", "retexture this armor", "swap the model", "create an
  armor variant", "add a craftable outfit", fix a worn appearance, or continue
  the fixtures/armor-swap-test flow.
---

# fo4-armor-swap

Composite authoring workflow. Chains `fo4-record-edit` (record plumbing),
`fo4-papyrus` (if scripted) and `fo4-package-release`, and sequences the art
steps the tools cannot drive. Worked fixture: `fixtures/armor-swap-test/seed/`
(a small copyright-free plugin plus serialized YAML) for testing the loop.

## Decide the swap type first

| Type | What changes | New art? | Effort |
|---|---|---|---|
| **Stat/keyword variant** | AV, value, keywords, mods | none | lowest |
| **Material swap (MSWP)** | materials/textures, same mesh | BGSM + DDS | low |
| **Model swap** | worn mesh (ARMA model) | edited NIF | medium |
| **New armor** | everything | mesh + material + textures | high |

Pick the lowest type that meets the goal. What the player sees **equipped**
comes from the ARMA models for the body and perspective; the ARMO world model
only covers the dropped item. Changing the inventory or world model alone does
not change the worn appearance.

## Steps

1. **Pre-flight.** Run `fo4-setup-check` for `mutagen-cli` / `spriggit`.

2. **Inspect the source.** `fo4_inspect_record(plugin, armor_id)` on the base
   ARMO. Note its ArmorAddon (ARMA) links, biped slots (`BOD2`), keywords,
   value/weight and any object template / OMOD. Inspect each ARMA for the race,
   sex and first/third-person models that matter.

3. **Author the record.**
   - **Stat/keyword variant:** edit the ARMO fields through the Spriggit loop
     (`fo4-record-edit`). Keep the existing ARMA links.
   - **Material swap:** read the original material paths on the actual mesh.
     Write the replacement with `fo4_create_bgsm(output, fields, template=<original .bgsm>)`
     and the textures with `fo4_encode_texture` (diffuse `BC7_UNORM_SRGB`,
     normal `BC5_UNORM`, spec/mask `BC7_UNORM`). Author an MSWP (substitutions
     original -> replacement) and hang it on the model that is actually worn.
     A matching filename on a different model does not exercise the swap.
   - **Model swap:** point the ARMA model(s) at the new NIF.
   - **New armor:** author ARMO + ARMA as new records (`fo4_create_record` for
     ARMO, Spriggit YAML for anything it does not cover), FormIDs >= `0x800`.

4. **Craftable recipe (optional).** `fo4_create_record` with a
   `constructibleobject`: `createdObject` = the ARMO, `workbenchKeyword` =
   `WorkbenchArmor`, components and conditions. Read back target, workbench,
   conditions and requirements.

5. **Distribution (optional).** Inject into leveled lists without editing them
   via `leveleditemoverride` (additive) or a hand-written SPID `_DISTR.ini`.
   Keep IDs referenced by external configs stable.

6. **Diff + import.** `fo4_spriggit_import` without confirm -> review the diff ->
   re-call with `confirm_overwrite=True`. Output lands in `staging/`.

7. **Worn geometry (manual GUI, do not skip).** For new or edited worn meshes:
   OutfitStudio/BodySlide for skinning, weighting, slot fit and body-preset
   sliders. The MCP geometry writer (`fo4_nif_build`) only handles plain static
   shapes; it refuses skinned meshes.

8. **Install + test.** The user installs the staged plugin and assets as an MO2
   mod in the target test profile. Verify in game: `help "<name>" 4 ARMO`,
   craft at the armor workbench, equip, check every requested body and
   perspective. Record inspection, crafting availability and fit are separate
   results; report which ones were observed.

## Guards (community best-practice)

- **FormID window 0x800-0xFFF.** SPID drops records below `0x800`; ESL caps new
  ObjectIDs at `0xFFF`. A distributable, ESL-able armor stays in that window.
- **Armor is the ESL textbook case.** Records only, no new cells -> ESL-flag by
  default (< 2048 new records). Confirm with `fo4_plan_plugin_format`; the end
  user never compacts FormIDs.
- **No AWKCR dependency.** Deprecated and conflict-prone; use vanilla keywords
  plus a minimal custom set, and a new INNR only for new keywords.
- **BA2 naming is load-bearing.** `<Plugin> - Main.ba2` and
  `<Plugin> - Textures.ba2` (separate) or the game won't attach them
  (`fo4-package-release`).
- **Biped slots must not collide** with what is worn alongside (`BOD2`);
  collisions = invisible or clipping armor.
- **Material swap before mesh edit** when only the look changes.
- **Keep ARMO <-> ARMA wiring intact.** A broken ArmorAddon link shows nothing
  equipped.
- **Shipped textures must be BC-compressed with mips.** Uncompressed or wrong
  DDS formats waste VRAM and can crash the AE runtime.

## Notes

- Pairs with `fo4-record-edit`, `fo4-papyrus` (equip effects) and
  `fo4-package-release` (flags, BA2, FOMOD, ZIP check).
