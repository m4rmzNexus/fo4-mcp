---
name: fo4-quest-author
description: |
  Scaffold a Fallout 4 quest end-to-end: author the QUST record (stages,
  objectives, aliases) as Spriggit YAML, attach and compile a Papyrus quest
  script, and sequence the dialogue/scene/navmesh work that must happen in the
  Creation Kit. Use when the user wants to "make a quest", "add a quest mod",
  "write a quest script", "set up quest stages/aliases", or build a mission.
  This is the most complex authoring flow — it leans on fo4-record-edit and
  fo4-papyrus and is explicit about what only the CK can do.
---

# fo4-quest-author

The deepest composite workflow (T1). Quests span record data (QUST + refs),
scripts (Papyrus), and inherently-GUI content (dialogue audio, scenes, navmesh).
This skill drives the record + script halves through the MCP tools and sequences
the CK-only steps so nothing is forgotten.

Be honest about the split: roughly the *structure* is tool-driven; the
*content* (voiced dialogue, lip files, scenes, new cells/navmesh) is CK + manual.

## Plan the quest first (principle: think before coding)

State, before authoring:
- Trigger: start-game-enabled, dialogue-triggered, item-triggered, or script-started?
- Aliases needed (actors, locations, items the quest references).
- Stages + objectives (the player-visible progression).
- Does it need new dialogue? new location/cell? → flags CK work.

## Steps

1. **Pre-flight.** Run `fo4-setup-check`.

2. **Author the QUST (YAML, via fo4-record-edit).** New plugin or export an
   existing one, then author the quest record:
   - **Stages** (`INDX` entries) with log entries.
   - **Objectives** (`QOBJ`) tied to stages, with target aliases.
   - **Aliases** (`ALST`/`ALLS`) — reference aliases (specific ref), create-ref
     aliases, location aliases. Each alias that a script touches needs a stable
     name.
   - **Quest data flags:** start-game-enabled? run-once? Set deliberately.
   - FormIDs ≥ `0x800`.

3. **Quest script (via fo4-papyrus).** Write the quest script (extends `Quest`)
   and any alias scripts (extend `ReferenceAlias`). Compile with
   `fo4_papyrus_build` — include paths must cover Base + F4SE (+ LPE if used,
   since PapyrusUtil F4 doesn't exist). The `ScriptName` must match the name
   attached to the QUST record exactly, or the engine won't bind it.

4. **Fragments (if used).** Stage/dialogue fragments are usually authored in the
   CK (it generates the fragment script skeletons). You can hand-author them as
   Papyrus, but the CK wiring is easier — flag it.

5. **Dialogue (CK + manual).** DIAL/INFO topics, voice files (.fuz/.wav/.xwm),
   and lip sync (.lip) are CK/recording work. Tool side can stub the topic
   records, but voiced delivery is manual. Sequence it; don't pretend it's
   tool-driven.

6. **Scenes / packages / new cells (CK).** Scenes, AI packages, new
   worldspace/interior cells, and **navmesh** are CK-only. If the quest adds a
   location, navmesh generation + finalize happens in the CK.

7. **Diff + import** the record work (`fo4_spriggit_import`, gated). Compile
   scripts to `staging/`. Assemble into an MO2 mod folder for testing.

8. **Test loop.** Use console (`sqt`, `setstage <questID> <stage>`,
   `getstage`, `caqs` for completion check). Iterate.

## Guards (community best-practice)

- **ESM-flag, not ESL, if the quest adds cells/worldspaces.** A quest that
  creates new cells/interiors/worldspaces must NOT be ESL-flagged — precombine/
  previs cannot be built for FE-space cells (engine limit). The 2025 standard for
  a cell-creating quest is an **ESM-flagged `.esp`** (stable load position, full
  previs support). ESL is only for script/dialogue/logic-only quest addons with
  no new cells.
- **Never generate previs for FE-space (ESL) cells** — it's engine-broken.
  "Leave it alone" is the rule there.
- **FormID 0x800–0xFFF** for new records distributed via SPID and kept ESL-able
  (SPID drops < 0x800; ESL caps at 0xFFF). And do NOT renumber/compact after
  dialogue/aliases/fragments reference FormIDs — it breaks the bindings.
- **Script name ↔ attachment match** (QUST attached-script name == `.psc`
  `ScriptName` == `.pex` filename) — the #1 silent quest-script failure.
- **Alias fill conditions matter.** An alias that fails to fill leaves its
  script unbound; the quest silently stalls. Verify fill logic.
- **start-game-enabled quests run on EVERY save load** — keep their `OnInit`
  cheap and guard re-entry, or you bloat save files.
- **Stage/objective ordering** must be monotonic and reachable; an unreachable
  stage = a stuck quest with no error.
- **New cells → navmesh is mandatory** (CK). No navmesh = NPCs can't path =
  broken quest. Editing/placing in a vanilla cell breaks its precombines/previs
  (the #1 quest-mod failure → stutter + object pop); build on PRP and rebuild
  previs for touched cells. Previs/precombine generation IS CLI-scriptable
  headless (`CreationKit.exe -GeneratePrecombined:<esp> clean all` /
  `-GeneratePreVisData:<esp> clean all` + xEdit `-script:` merges) but needs
  CKPE installed — tracked as a gated tool (`fo4_build_previs`, TASKS #U1).
- **Compile clean** — a quest script with warnings often misbehaves at runtime.

## Notes

- This skill orchestrates; it does not replace the CK for dialogue/scene/navmesh.
  Be explicit with the user about which parts are manual.
- Lighthouse Papyrus Extender (`tools/lighthouse-papyrus`) adds string/array/math
  /file APIs vanilla Papyrus lacks — commonly needed in quest scripts. Add its
  source to the include paths when used. Papyrus Common Library (Nexus mods/86222,
  ~1000 helper fns) is the other modern go-to.
- Heavy script load: Baka MaxPapyrusOps (op-limit raise) is now BUILT INTO
  Buffout 4 NG (`MaxPapyrusOpsPerFrame`) — document the dependency, don't tell
  users to also install the standalone. Keep `OnInit` cheap on start-game-enabled
  quests (they run every save load).
- Pairs with `fo4-record-edit`, `fo4-papyrus`, and `fo4-package-release`.
