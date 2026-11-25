---
name: fo4-quest-author
description: |
  Author or repair a Fallout 4 quest end to end: QUST record (stages,
  objectives, aliases), player dialogue choices that advance stages, scenes,
  Papyrus quest/alias scripts and fragments, new locations with navmesh, voice
  handoff and reward progression. Use when the user wants to "make a quest",
  "add a quest mod", "wire this dialogue choice to a stage", "write a quest
  script", "set up quest stages/aliases", or fix a quest that stalls or rewards
  too early. Leans on fo4-record-edit and fo4-papyrus and names what still
  needs the Creation Kit.
---

# fo4-quest-author

The deepest composite workflow. Quests span record data (QUST + DIAL/INFO +
SCEN + refs), scripts (Papyrus) and content that may still need the CK or a
recording session. Drive the record and script halves through the MCP tools
and sequence the rest so nothing is forgotten.

## Plan the quest first

State before authoring:
- **Trigger:** start-game-enabled, dialogue, item, location or script-started?
- **The player's path:** the action the player takes, the state required before
  it, and the observable change it causes (stage, objective, reward).
- **Aliases** (actors, locations, items) and how each fills.
- **Stages + objectives**, monotonic and reachable.
- New dialogue? New location/cell? -> plan navmesh, voice and flag (ESM vs ESL).

For an existing quest inspect the QUST and its child records first
(`fo4_inspect_record`, `fo4_inspect_sm_tree` for Story Manager placement).
Preserve published FormIDs, alias IDs and fragment bindings.

## Steps

1. **Pre-flight.** Run `fo4-setup-check` (`mutagen-cli`, and `caprica` if scripted).

2. **Author the records.**
   - **New quest:** `fo4_create_record(spec, output_plugin)`. The Mutagen writer
     supports stages (with log entries + stage fragments), objectives with QSTA
     targets, reference / location / create-ref aliases (with fill conditions
     and event fill), VMAD script bindings, alias fragments, dialogue topics +
     INFO responses + conditions, player dialogue branches, SCEN scenes with
     supported actions, and SMQN Story Manager nodes. FormLinks auto-add masters.
   - **Existing plugin:** `fo4-record-edit` (Spriggit loop) and review the diff
     before importing into staging.
   - FormIDs >= `0x800`.

3. **Dialogue choice -> stage.** Wire the starting topic to a player branch and
   the response to the intended stage. `setParentQuestStage.onEnd` on the
   response gives a script-free transition. Check the INFO conditions and that
   the speaker alias fills. A topic existing on disk does not establish that a
   player can select it. Diagnosing a stalled or premature reward:
   [quest and dialogue engineering notes](../../docs/fo4-quest-dialogue-system.md)
   (its historical gap lists describe the writer at the time they were written).

4. **Scripts (via fo4-papyrus).** Quest script (`extends Quest`), alias scripts
   (`extends ReferenceAlias`), fragments. Compile with
   `fo4_papyrus_build(source_paths, output_dir)`; fragment namespaces
   (`Fragments:Quests:QF_<eid>_<fid>`) are derived automatically. Verify the
   attached name == `.psc` `ScriptName` == `.pex` filename, and the fragment and
   alias bindings.

5. **Locations.** The writer supports interior cells, placed references and an
   isolated interior navmesh (in-game pathable). `fo4_navmesh_handoff(plugin)`
   lists which cells still need CK navmesh work. Placing into a vanilla cell
   (`fo4_place_into_cell`): run `fo4_check_previs_safety` first.

6. **Voice.** `fo4_voice_handoff(plugin)` lists every response line with
   subtitle, speaker, resolved voice type and canonical `.fuz` path. With the
   LipGen toolchain present, `fo4_bake_voice_assets(plugin, dry_run=False)`
   bakes silent placeholder `.fuz` files; real recordings replace them.

7. **Stage the output** in `staging/`, then a test MO2 profile.

## Verify the player's path

Read back the branch, starting topic, response and stage transition from the
written plugin. In game (`fo4-ingame-test` or by hand) use the intended profile
and starting state. `setstage` / `sqt` / `getstage` isolate a fragment but
bypass the dialogue choice. To claim "the choice awards the item": observe an
eligible player selecting it and the reward arriving at that transition; check
the reward is absent beforehand and that an unavailable or repeated choice
cannot grant it again when the design requires that. Report the strongest step
actually observed.

## Guards (community best-practice)

- **ESM-flagged `.esp`, not ESL, if the quest adds cells/worldspaces** (no
  previs for FE-space cells). ESL only for logic/dialogue-only add-ons.
- **Never generate previs for ESL cells.**
- **Do not renumber or compact** after dialogue, aliases or fragments reference
  FormIDs; it breaks the bindings.
- **Script name <-> attachment match**, the most common silent quest-script failure.
- **Alias fill conditions matter.** An unfilled alias leaves its script unbound
  and the quest silently stalls.
- **Start-game-enabled quests run on every save load**: keep `OnInit` cheap and
  guard re-entry.
- **New cells need navmesh.** Editing a vanilla cell breaks its precombines;
  rebuild previs for touched cells (`fo4_build_previs`, CK-gated).
- **Compile clean.** A quest script with warnings often misbehaves at runtime.

## Notes

- Lighthouse Papyrus Extender adds string/array/math/file APIs vanilla Papyrus
  lacks; add its source to the include paths when used.
- MaxPapyrusOps is built into Buffout 4 NG; document the dependency instead of
  the standalone mod.
- Pairs with `fo4-record-edit`, `fo4-papyrus`, `fo4-ingame-test` and
  `fo4-package-release`.
