# tools/ MANIFEST

Otomatik indirilen FO4 modlama araç binary'leri. `fo4-mcp` server subprocess çağrılarında bu dosyayı path source-of-truth olarak kullanır.

**Last updated:** 2026-06-21 (34 MCP tools functional, 8 skills, 387 tests; W7-Data + ACTI control-script + W9 voice handoff + **W9 silent-voice baker `fo4_bake_voice_assets`** (e2e-proven) + **W10 FaceGen builder `fo4_build_facegen`** + **W12 `fo4_build_seq`** (CK -GenerateSEQ) + `ck_run` MO2-VFS launcher; **CK LIVE-PROVEN agent-runnable** — previs produced real CombinedObjects.esp+.psg+precombined NIFs via MO2-VFS, FaceGen CLI ran headless [CK merged into main install + CKPE + RTX 3080]; güncel durum → `TASKS.md`)
**Runtime tespit:** Fallout4.exe = 1.11.221.0 (Anniversary Edition / AE)
**Creation Kit:** CreationKit.exe = 1.11.137.0 (Steam app 1946160, ayrı install dir)
**.NET:** 8 SDK 8.0.421 + **9 SDK 9.0.314** (`~/.dotnet`, user-local, side-by-side). Spriggit serialization tool net9.0 hedefliyor — net9 SDK ŞART (Session 5 bulgusu).
**Vanilla Papyrus source:** `tools/papyrus-source/Base/` (Base.zip extract, `TestKevinActivationScript.psc` silindi)

## Konvansiyon

Her giriş şu alanlara sahip:
- `name` — tool adı
- `version` — indirilen sürüm
- `source` — orijinal kaynak (GitHub release URL)
- `asset` — indirilen dosya adı
- `binary_path` — entrypoint executable yolu (repo root'a göre)
- `license` — SPDX kısa kodu
- `downloaded` — ISO tarihi
- `sha256` — asset'in hash'i (provenance için)
- `notes` — özel uyarılar

`binary_path` artık çoğu tool için **resolved** (extract-tools.ps1 çalıştırıldı). Hâlâ TBD olanlar source clone'lar (header library, plugin template — N/A).

---

## Spriggit

```yaml
name: Spriggit
version: 0.40.1
source: https://github.com/Mutagen-Modding/Spriggit/releases/tag/0.40.1
asset: SpriggitCLI.zip
binary_path: tools/spriggit/Spriggit.CLI.exe
license: GPL-3.0
downloaded: 2026-05-10
extracted: 2026-05-10
sha256: 03258E50600CB9BD4DBE2FCA49966D07070A6C8069648D74D4235DC7F332B264
size_mb: 55.8
exe_size_mb: 158.4
notes: |
  ESP <-> YAML/JSON serialization. .NET self-contained single-file
  deployment (158MB exe).
  ESP <-> YAML serialization. fo4_spriggit_export (read-only, free) +
  fo4_spriggit_import (DIFF-GATED: mevcut plugin'i confirm_overwrite
  olmadan ezmiyor, .bak yedeği alıyor). GPL-3.0 -> subprocess-wrap.
  Session 5 (2026-05-28) UNBLOCKED: Session 4'ün "nuget broken" teşhisi
  YANLIŞTI. spriggit.yaml.fallout4 paketi geçerli bir dotnet-tool — ama
  tools/net9.0/ hedefliyor. Lokalde sadece net8 SDK olunca `dotnet tool
  install` net9.0 TFM'i eşleyemeyip "DotnetToolSettings.xml not found"
  veriyordu. FIX: net9 SDK kuruldu. Roundtrip artık LOSSLESS — ModKey
  korununca serialize->deserialize->serialize byte-identical YAML
  (research/p0/spriggit/2026-05-15-roundtrip.md). Binary .esl byte-stable
  DEĞİL (bu yüzden import diff-gate). Çalışma için `~/.dotnet` PATH'te.
```

## Synthesis

```yaml
name: Synthesis
version: 0.35.5
source: https://github.com/Mutagen-Modding/Synthesis/releases/tag/0.35.5
asset: Synthesis.zip
binary_path: tools/synthesis/Synthesis.exe
license: GPL-3.0
downloaded: 2026-05-10
extracted: 2026-05-10
sha256: 74B382ADF48B28EA9E200366993D279F8110DD0C1ECFF82F5CD65AAE8E2678DE
size_mb: 259.5
exe_size_mb: 265.7
notes: |
  Mutagen tabanlı deterministic patcher framework. Synthesis runner
  Mutagen.Bethesda.* runtime'ını bundle ediyor.
  Session 5 (2026-05-28): inspect_record backend olarak DENENDİ ve
  REDDEDİLDİ — CLI'ı GUI/pipeline runner, record-query entry point yok
  (tüm subcommand'ler çıktısız/hang). inspect_record yerine Spriggit
  serialize kullanıyor. Custom Mutagen.Bethesda.Fallout4 console app =
  V2 (docs/V2-backlog.md #2). Detay: research/p0/synthesis/
  2026-05-28-cli-argv.md.
  GPL-3.0 -> subprocess-wrap zorunlu.
```

## Mutagen (NuGet — runtime CLI yok)

```yaml
name: Mutagen.Bethesda
version: 0.53.1
source: https://github.com/Mutagen-Modding/Mutagen/releases/tag/0.53.1
asset: NOT DOWNLOADED (sadece NuGet paketleri var, executable yok)
binary_path: N/A (Synthesis runner üzerinden tüketilir)
license: GPL-3.0
downloaded: N/A
sha256: N/A
notes: |
  Mutagen tek başına bir CLI değil — .NET kütüphanesi olarak tüketilir.
  Release sayfasında sadece NuGet paketleri: Mutagen.Bethesda.{Core,
  Fallout4, Skyrim, ...}.0.53.1.nupkg.
  fo4-mcp için iki seçenek:
  (1) Synthesis runner'ı CLI olarak çağır (subprocess-wrap doğal)
  (2) Mutagen.Bethesda paket'ini referans alan ince custom CLI yaz
  → Seçenek (2) GERÇEKLENDİ: aşağıdaki `mutagen-cli` girdisi
    (record-scoped inspect_record perf path, V2-backlog #2).
```

## VC++ 2012 x86 runtime (vc110-x86 — for CK PapyrusAssembler, validation only)

```yaml
name: vc110-x86
version: 11.00.51106.1 (VS2012 Update 4)
source: https://download.microsoft.com/download/1/6/B/16B06F60-3B20-4FF2-B699-5E9B7962F9AE/VSU_4/vcredist_x86.exe
asset: vcredist_x86.exe (sha256 B924AD8062EAF4E70437C8BE50FA612162795FF0839479546CE907FFA8D6E386)
binary_path: tools/vc110-x86/ (MSVCP110.dll + MSVCR110.dll; no executable)
license: Microsoft redistributable (install/redistribute under MS terms; NOT committed)
downloaded: 2026-06-05
sha256: |
  MSVCP110.dll C8D5572CA8D7624871188F0ACABC3AE60D4C5A4F6782D952B9038DE3BC28B39A
  MSVCR110.dll B30160E759115E24425B9BCDF606EF6EBCE4657487525EDE7F1AC40B90FF7E49
notes: |
  The two 32-bit VC++2012 DLLs that Bethesda's x86 PapyrusAssembler.exe imports
  (absent from SysWOW64 on this machine → 0xC0000135). Obtained WITHOUT admin:
  official MS vcredist_x86.exe → `wix burn extract` (WiX v5 dotnet tool) →
  `expand cab1.cab` → rename F_CENTRAL_msvcp110_x86 / _msvcr110_x86. Both x86
  (PE machine 0x014C). Used ONLY to validate the CK Papyrus toolchain for
  V2-backlog #1 — the bytecode-diff proved CK ≡ Caprica, so backend="ck" is
  NOT wired and this stays an unused, gitignored validation artifact. Karar 4:
  NEVER copy these into the read-only Steam `Papyrus Compiler/` dir; if ever
  needed at runtime, PATH-prepend tools/vc110-x86 in the subprocess env. Do NOT
  commit the DLLs (tools/ gitignored; MS redistributable terms).
```

## JDK (Temurin 21 — for the ReSaver save-clean shim)

```yaml
name: jdk
version: Temurin 21.0.11+10 (LTS)
source: https://api.adoptium.net/v3/binary/latest/21/ga/windows/x64/jdk/hotspot/normal/eclipse
asset: temurin21.zip (Adoptium, no installer, no admin)
binary_path: tools/jdk/jdk-21.0.11+10/bin/ (java.exe, javac.exe, jar.exe)
license: GPLv2+CE (OpenJDK) — runtime/toolchain only, not redistributed
downloaded: 2026-06-05
sha256: N/A (large zip; provenance = official Adoptium over verified TLS)
notes: |
  Headless JDK to build + run the resaver-shim (ReSaver.jar Build-Jdk 19 → needs
  Java >= 19). Zip JDK, extracted under tools/jdk/ (gitignored, ~200 MB). Used by
  fo4_clean_save_papyrus to run the shim; not on PATH, resolved by glob from
  cfg.tools_dir/jdk/*/bin/java.exe.
```

## resaver-shim (headless ReSaver save-clean — custom, Apache-2.0)

```yaml
name: resaver-shim
version: 1.0 (built against ReSaver 6.0.643)
source: custom (tools/resaver-shim/src/fo4mcp/CleanShim.java)
asset: built via javac -cp ReSaver.jar+lib; jar via jdk jar tool
binary_path: tools/resaver-shim/CleanShim.jar
license: Apache-2.0 (links ReSaver, Apache-2.0 — redistribution-safe, no GPL)
downloaded: 2026-06-05 (built)
sha256: 872A12674483857E2EFD291294219CBC151A85E6C8A6D8F7D8AB30D53B6ED8E1
notes: |
  ~90-line headless wrapper over ReSaver's engine (resaver.ess.ESS + Papyrus):
  ESS.readESS -> Papyrus.remove{Undefined,Unattached} -> ESS.writeESS, then
  re-reads its own output as a corruption oracle. argv: --in <fos> --out <fos>
  --op noop|undefined|unattached; stdout = one JSON object {removed_count,
  reread_ok, before, after}. ESS.readESS builds only Swing models (no window) so
  it runs HEADLESS; ModelBuilder uses a non-daemon pool → the shim System.exit()s.
  Validated on a real 5.07 MB AE save: no-op output byte-size-identical + re-read
  by our Python parser; unattached removed 1 instance, reread_ok. Backs
  fo4_clean_save_papyrus (#16-B). Source version-controlled; jar gitignored.
  Rebuild: javac -cp "ReSaver.jar;lib/*" -d build src/fo4mcp/CleanShim.java &&
  jar --create --file CleanShim.jar -C build .
```

## mutagen-cli (record-query + create writer — custom, Mutagen.Bethesda.Fallout4 wrap)

```yaml
name: mutagen-cli
version: 0.53.1
source: custom (tools/mutagen-cli/src/ — Mutagen.Bethesda.Fallout4 0.53.1 NuGet wrap)
asset: built from source via dotnet publish (net9.0, framework-dependent, win-x64)
binary_path: tools/mutagen-cli/mutagen-cli.exe
license: GPL-3.0
downloaded: 2026-06-05 (built; rebuilt 2026-06-06 with `create` subcommand + Faz 1.1 NPC fields + Faz 1.2 rich ARMO fields + Faz 2 Quest skeleton + Faz 2.1a quest dialogue + Faz 2.1b INFO conditions + Faz 2.1c quest aliases + Faz 2.1d Papyrus VMAD binding + Faz 2.1e SCEN scenes + Faz 2.1f quest stage fragments + Faz 2.1g quest alias fragments + Faz 2.2a QUST stage QSDT/RunOnStart fix + Faz 3/W1 condition run-on slots + Faz 3/W1.5 glue records GLOB/MESG/KYWD/FLST + Faz 3/W3.5 Faction FACT + Faz 3/W3a UseTemplateActors RE-probe gate + Faz 3/W3b NPC full-field [voice/combatStyle/defaultOutfit/attackRace/skin + AI enums + keywords/inventory/perks] + Faz 3/W3c NPC template-chain [defaultTemplate + useTemplateActors bitfield] + Faz 3/W3d+W3e leveled lists [LeveledNpc/LeveledItem: entries{reference,level,count} + calc flags] + Faz 3/W3f lint-npc verb [streams NPC template/FaceGen flags for fo4_lint_npc_template] + Faz 3/W2 quest objective QSTA targets [objective flags + targets{aliasId, flags, keyword, conditions}] + Faz 3/A-in-game interior navmesh IN-GAME VALIDATED [AddNavmesh now also authors the flattened cover-grid `[triCount:u32][indices]` + GridMaxDistance + a NAVI override of 000FF1:Fallout4.esm; an NPC pathfinds on it, adversarial-proven 2026-06-21 → interior navmesh reclassified CK-gated → Mutagen-authorable] + navmesh-dump/navi-dump RE ground-truth verbs + Faz 3/W6.7 quest location-alias + event-fill [alias type=location → QuestLocationAlias{specificLocation/referenceAliasLocation/externalAliasLocation}, fromEvent → FindMatchingRefFromEvent on ref+location aliases, externalAliasQuest/externalAliasId → External link; collection alias BLOCKED — Mutagen v0.53.1 can't round-trip multi-member QuestCollectionAlias, writer rejects] + Faz 3/W12 cell-navmesh-list verb [enumerates every cell — interior block hierarchy + worldspace sub-cells — with per-cell {interior, worldspaceParent, navmeshCount, hasNavi} for fo4_navmesh_handoff] + Faz 3/W7-Data package location data-input [`dataLocation` → PackageDataLocation; slot index resolved by NAME against the live template via --masters-dir] + package-dump verb [PACK Data input map ground-truth] + Faz 3/W9 voice-handoff verb [enumerates every DIAL→INFO→line with subtitle + speaker + resolved voice type + canonical .fuz path for fo4_voice_handoff] + W12-RE exterior-navmesh verbs [navmesh-dump --exterior/--record dumps worldspace NAVM geometry + cross-cell edge-links; exterior-navmesh-spike round-trips a NEW isolated WRLD + exterior cell + WorldspaceNavmeshParent NAVM + worldspace-parent 000FF1 NAVI override — disk-proves isolated exterior navmesh is Mutagen-authorable] + Coupon-MVP [Book/Note record type {name→title, text→BookText, value/weight/keywords, Teaches=BookTeachesNothing} + LeveledItemOverride record type {DeepCopy a master LVLI by FormKey, additive entry-add, clearExisting opt-in — loot injection into vanilla leveled lists} + lvli-find verb {reverse-lookup which LVLIs reference a target FormKey} + FIX: removed InvariantGlobalization so 1252 chars ¢—™© no longer corrupt to U+FFFD in authored strings] + Coupon-Visual [Book Model+MaterialSwap {book MODL = world-model nif path + Model.MaterialSwap = MSWP FormLink — the swap rides on the Model, not the Book} + MaterialSwap (MSWP) record type {substitutions[]{original→replacement} .bgsm retexture map} + read-back proof for both {book modelFile/materialSwap, MSWP substitutionCount/pairs}; drives Pre-War Coupons world-model art via the Grognak-comic recipe — DN101Note.nif + per-coupon MSWP → coupon .bgsm → coupon .dds] + MISC record type {pickupable clutter — name/value[Int32]/weight/keywords/Model+MaterialSwap; money/caps analog for a coupon as collectible item, not a readable Book} + MISC ObjectBounds (OBND) {non-zero [x1,y1,z1,x2,y2,z2] — FO4 frames the inventory preview/Inspect camera from OBND; zero box = blank preview} + MISC PreviewTransform (PTRN) {FormLink to a TRNS — the Pip-Boy/Inspect 3D preview is framed by a Transform SEPARATE from the world Model; missing PTRN = a flat item default-frames edge-on → blank preview; e.g. OverdueBook's 1CF028}; read-back proof for objectBounds/objectBoundsZero/previewTransform + Open-structures build-now 2026-06-24 [WEAP weapon {DNAM stats + ammo/keywords/attach-slots/Model+MSWP} + world bases CONT/DOOR/STAT/LIGH/ALCH/INGR {Name/Model+MSWP/Keywords/Flags/Value/Weight; ALCH+INGR effects[]{MGEF, magnitude, area, duration}} + COBJ constructibleobject {createdObject + workbenchKeyword + components/categories/conditions} + OTFT outfit {worn-item list} + NPC actorFlags {Essential/Protected/... bitfield} + MESG menuButtons + FACT Ranks{gendered title}+VendorValues + LVLN/LVLI chanceNone {0-100 loot-tune} + INFO TIF VMAD fragment {per-INFO fragment→VirtualMachineAdapter + FormKey pin} + dialogue-dump verb + RenderParam {GetParameterTypes-bucketed param render — fixes alias-slot rendering as Null}])
sha256(mutagen-cli.exe — static apphost launcher, UNCHANGED across managed-code rebuilds): 81FCBD615DC3ACD2B7D4DDABC734961550BB50FBD0EA59342DF3E5E192A3CC81
sha256(mutagen-cli.dll — the managed assembly that actually carries the code; THIS changes per build): DF444656AF88764B89E3B380E23D34A14E1C7D0B906A4200FDA68303E104C8A3
notes: |
  Three subcommands, one exe:
  (1) record-query backend for fo4_inspect_record (V2-backlog #2).
      argv: --plugin <path> --record <FormID|EditorID>. stdout = one JSON object
      {found, formKey, editorId, recordType}; exit 0 found / 1 not found / 2 error.
      Opens the plugin with a binary OVERLAY (lazy) and streams EnumerateMajorRecords,
      break-on-first-match — no temp-dir, no whole-tree serialize (the Spriggit perf
      problem on Fallout4.esm-scale masters). Overlay reads the plugin's own records
      WITHOUT resolving masters, so no Data-dir/load-order setup is needed.
      Optional: fo4_inspect_record falls back to Spriggit when this exe is absent.
  (2) authoring writer for fo4_create_record (V2-backlog "Record authoring axis"
      Faz 1 / 1.1 / 1.2 / 2 / 2.1a / 2.1b / 2.1c / 2.1d / 2.1e / 2.1f / 2.1g). argv: create --spec <file.json> --out <plugin.esp>.
      spec = {"records":[{"type":"Npc|Armor|Quest|Keyword|FormList|Message|Global|Faction|LeveledNpc|LeveledItem|Cell|CellOverride|Smqn|Activator|Location|LocationRefType|EncounterZone|Package","editorId":...,"name":...,
      NPC: "race":"<6hex>:<master>","class":...,"factions":[{"faction":...,"rank":int}],
        W3b full-field: "voice"/"combatStyle"/"defaultOutfit"/"attackRace"/"skin":"<6hex>:<master>",
        "aggression"/"confidence"/"assistance"/"responsibility"/"mood":<Npc AI enum name>,
        "keywords":["<6hex>:<master>"],"inventory":[{"item":"<6hex>:<master>","count":int>=0}],
        "perks":[{"perk":"<6hex>:<master>","rank":int 0-255}],
        W3c template-chain: "defaultTemplate":"<6hex>:<master>"(NPC_ or LVLN),
        "useTemplateActors":[<Npc.TemplateActorType name: Traits|Stats|Factions|SpellList|AiData|AiPackages|ModelOrAnimation|BaseData|Inventory|Script|DefPackList|AttackData|Keywords>] (OR'd into the bitfield),
      Armor: "keywords":["<6hex>:<master>"],"value":int,"weight":float,
        "armorRating":int(0-65535),"bipedSlots":[<BipedObjectFlag>],
      Quest: "questType":...,"flags":[...],"stages":[{"index":int,"logEntry":...,"runOnStart":bool}],
        (each logEntry auto-gets a QSDT marker — engine-required; runOnStart = INDX 0x02 startup stage)
      "objectives":[{"index":int,"text":...,
        W2: "flags":[<QuestObjective.Flag OrWithPrevious|NoStatsTracking>],
        "targets":[{"aliasId":int(QuestObjectiveTarget.AliasID),"flags":[<Quest.TargetFlag CompassMarkerIgnoresLocks|Hostile|UseStraightLinePathing>],"keyword":"<6hex>:<master>"(LCRT),"conditions":[<same as INFO>]}]}],
      "topics":[{"editorId":...,"name":...,"subtype":...,"category":...,
        "responses":[{"prompt":...,"speaker":"<6hex>:<master>",
          "lines":[{"text":...,"responseNumber":int,"emotion":"<6hex>:<master>"}],
          "conditions":[{"function":<Condition.Function>,"comparison":<CompareOperator>,
            "value":float,"param1":"<6hex>:<master>"|int|str,"param2":...,"runOn":...}]}]}],
      "aliases":[{"id":int?,"name":...,"type":"reference|location"?,"flags":[<AQuestAlias.Flag>],
        "forcedReference":"<6hex>:<master>","uniqueActor":"<6hex>:<master>",  // [reference]
        "specificLocation":"<6hex>:<master>","referenceAliasLocation":int,    // [location]
        "externalAliasQuest":"<6hex>:<master>","externalAliasId":int,         // [location/reference] External link
        "fromEvent":"<4-char sig>",  // FindMatchingRefFromEvent (ref+location); collection alias type BLOCKED (Mutagen no round-trip)
        "conditions":[{...same as INFO conditions...}]}],
      "scripts":[{"name":"<.psc class>","flags":<ScriptEntry.Flag>,
        "properties":[{"name":...,"type":"object|int|float|bool|string",
          "value":<FormKey str|int|float|bool|str>,"alias":int}]}],
      "scenes":[{"editorId":...,"flags":[<Scene.Flag>],"actors":[{"id":int}],
        "phases":[{"name":...,"startConditions":[{...}],"completionConditions":[{...}]}],
        "actions":[{"type":<SceneAction.TypeEnum>,"actor":int,
          "topic":"<topic editorId|6hex:master>","startPhase":int,"endPhase":int,
          "flags":[<SceneAction.Flag>]}]}],
      "fragments":{"scriptName":"<QF_<eid>_<formid> class>","flags":<ScriptEntry.Flag>,
        "properties":[{...same as scripts properties...}],
        "stages":[{"stage":int(0-65535),"stageIndex":int?,"fragmentName":"<Fragment_* fn>"}]},
      "aliasFragments":[{"alias":int(0-32767),"scripts":[{...same shape as scripts...}]}],
      Keyword: (bare KYWD — editorId + optional name),
      Message: "text":<MESG body→Description>,  (title aliases name→Name),
      FormList: "items":["<6hex>:<master>"],  (FLST FormLink entries, any record),
      Global: "globalType":"float|int|short"(default float),"globalValue":number,
      Faction: "flags":[<Faction.FactionFlag>],"interfactionRelations":[{"faction":"<6hex>:<master>","reaction":<CombatReaction Neutral|Enemy|Ally|Friend>}],
      LeveledNpc/LeveledItem: "entries":[{"reference":"<6hex>:<master>"(LVLN INpcSpawn / LVLI IItem),"level":int(1-32767),"count":int(1-32767)}],"flags":[<LeveledNpc.Flag: Calculate{FromAllLevelsLessThanOrEqualPlayer,ForEachItemInCount,All} | LeveledItem.Flag: ...,UseAll>]
      Cell (W4 — interior + placed refs): "lightingTemplate"/"location"/"encounterZone"/"imageSpace"/"acousticSpace"/"music":"<6hex>:<master>","waterHeight":float,"placedObjects":[{"base":"<6hex>:<master>"(REFR,required),"editorId":...,"position":[x,y,z],"rotation":[x,y,z],"scale":float,"persistent":bool}],"placedNpcs":[{...same shape, ACHR base}]  (flagged IsInteriorCell; block=id%10, subblock=(id/10)%10; refs -> Temporary unless persistent)
      CellOverride (W5 — add refs to an EXISTING master cell): "sourcePlugin":"<path>","cell":"<6hex>:<master>","clearExisting":bool(default true),"placedObjects"/"placedNpcs":[...same as Cell]  (DeepCopies the master cell -> data fields carry forward, no editorId needed; clears deep-copied refs so only new refs land in the override -> no ITM dupes). (3) cell-info verb: cell-info --plugin <path> --record <FormID|EditorID> -> {found,formKey,editorId,interior,combinedMeshes,combinedMeshReferences,preCombinedFilesTimestamp,preVisFilesTimestamp,hasPrecombines,hasPrevis,...} precombine/previs signals for fo4_check_previs_safety (W5).
      Smqn (W6 — Story Manager Quest Node, event-driven quest auto-start): "parent":"<6hex>:<master>"(SM event/branch node),"previousSibling":"<6hex>:<master>","flags":[<AStoryManagerNode.Flag Random|WarnIfNoChildQuestStarted>],"maxConcurrentQuests":int,"maxNumQuestsToRun":int,"hoursUntilReset":float,"conditions":[<same as INFO>],"quests":[{"quest":"<6hex>:<master>","hoursUntilReset":float}]  (flat AddNew Fallout4Group; tree linkage via Parent/PreviousSibling FormLinks). (4) sm-tree verb: sm-tree --plugin <path> [--record <node FormID|EditorID>] -> no record: event-node list {editorId,formKey,type,childCount}; with record: node + direct children. For fo4_inspect_sm_tree (W6 — pick the SMQN parent).
      Activator (W6.5): "name","keywords":["<6hex>:<master>"],"scripts":[<same shape as quest scripts — VMAD control-script: compiled .psc class + typed properties>]  (model deferred). Location (W8): "name","parentLocation":"<6hex>:<master>","keywords":[...]. LocationRefType (W8): bare editorId. EncounterZone (W8): "flags":[<EncounterZone.Flag NeverResets|MatchPcBelowMinimumLevel|DisableCombatBoundary|Workshop>],"location"/"owner":"<6hex>:<master>","minLevel"/"maxLevel"/"rank":int(0-255).
      Package (W7 — AI package template-bind): "packageTemplate":"<6hex>:<master>","packageType":"Package|PackageTemplate","flags":[<Package.Flag>],"ownerQuest"/"combatStyle":"<6hex>:<master>","conditions":[<same as INFO>]. W7-Data: "dataLocation":{"target":"<6hex>:<master>","targetType":"reference|cell|keyword"(def reference),"radius":int,"input":str(template input Name, def first location slot)} — one PackageDataLocation; the Data slot index is resolved by NAME against the LIVE template (requires --masters-dir = FO4 Data dir; Travel 002CB0 "Place to Travel", Sandbox 002CB1 "Location"); child Data key + DataInputVersion stay engine-aligned. ProcedureTree / non-location inputs still deferred. NPC also takes "packages":["<6hex>:<master>"] (bind existing PACK). placedObject also takes "teleport":{"door":"<6hex>:<master>","position":[x,y,z],"rotation":[x,y,z]} (W8.5 XTEL door-link). (5) package-dump verb: package-dump --plugin <path> --record <FormID|EditorID|*needle*> -> dumps a PACK's Data input map [{index,name,type,flags}] + packageTemplate + dataInputVersion (or list mode for *needle*) — W7-Data template ground-truth. (6) voice-handoff verb (W9): voice-handoff --plugin <path> [--masters-dir <dir>] -> every dialogue response line {dialog,info,responseNumber,text,speaker,voiceType,fuzPath,voiceTypeResolved}; voiceType = INFO.Speaker→Npc.Voice→VoiceType.EditorID (resolved across the plugin + masters-dir); fuzPath = Sound/Voice/<plugin>/<VoiceType>/<INFO-8hex>_<respNum>.fuz — for fo4_voice_handoff.
      }]} (fields are type-specific). Builds a `new Fallout4Mod` (ModKey from --out
      filename), `AddNew`s each record (armor sets Keywords FormLinks + Value/Weight/
      ArmorRating scalars + BipedBodyTemplate.FirstPersonFlags from BipedObjectFlag names;
      quest dialogue nests DialogTopic/DialogResponses
      under the quest, FormKeys minted from the mod allocator; INFO conditions are
      ConditionFloat + a generic FunctionConditionData so ANY of the 479 function names
      work through one path; quest aliases are QuestReferenceAlias sub-records keyed by a
      quest-local ID — not FormKeys — with ids auto-sequenced by list order when omitted,
      reusing the same condition builder for find-matching-ref conditions; Papyrus VMAD
      binding attaches scripts by .psc class name under the quest's QuestAdapter — a
      nullable optional group, FO4 header Version 6 / ObjectFormat 2 — each with typed
      properties mapped to the per-type ScriptProperty subclass [object→ScriptObjectProperty
      (FormLink or alias index), int/float/bool/string→Script*Property], value-bearing
      props flagged Edited; SCEN scenes nest under the quest as Scene major records
      back-linked to it — actors are SceneActor.ID = the quest alias ID, phases gate
      flow with the same condition builder, and each "typical" action wraps in
      SceneActionTypicalType, resolving its topic by editorId against this spec's topics
      or by FormKey; quest stage script fragments fill the QuestAdapter's single QF
      fragment script [Script] + per-stage Fragments entries [Unknown2=1 per CK output],
      metadata only — the .pex is compiled separately via fo4_papyrus_build; quest ALIAS
      script fragments fill QuestAdapter.Aliases — each QuestFragmentAlias binds one alias
      [Property.Alias = the quest-local alias ID, Property.Object = this quest, Version 6 /
      ObjectFormat 2] to its fragment script(s), reusing the ScriptEntry builder, .pex
      decoupled like stage fragments; glue records mint a bare Keyword, a Message
      [text→Description, title→Name], a FormList [item FormLinks], and an abstract
      Global built as a concrete GlobalFloat/Int/Short subclass via the (mod, editorID)
      ctor + Globals.Add with its value; a Faction sets its FactionFlag flags + interfaction
      Relations [Target FormLink + CombatReaction] — what makes a placed hostile NPC hostile;
      an NPC sets full-field props [W3b] — Voice/CombatStyle/DefaultOutfit/AttackRace/Skin
      FormLinks, AI personality enums [Aggression/Confidence/Assistance/Responsibility/Mood],
      Keywords, Items (ContainerEntry item+count), Perks (PerkPlacement perk+rank), and
      a template-chain [W3c] — DefaultTemplate FormLink (INpcSpawn: NPC_ or LVLN) +
      UseTemplateActors, a non-[Flags] Int32 bitfield OR'd from TemplateActorType names;
      DefaultTemplate + the Traits flag = inherited dark-face-free FaceGen; leveled lists
      [W3d/W3e] mint a LeveledNpc/LeveledItem, each entry wrapping a Leveled*EntryData
      [Level/Count Int16, Reference FormLink — INpcSpawn for LVLN, IItem for LVLI] + calc
      Flags [LVLN bit4=CalculateAll vs LVLI bit4=UseAll]; LVLI is the non-naked-spawn path),
      sets
      fields/FormLinks (which auto-add referenced masters,
      including condition + alias-fill + script-object-property + scene-condition record
      params), and `WriteToBinary`; then re-opens the written file to read fields back.
      stdout = {created, plugin, masters, records:[{type,editorId,formKey, npc: race?/
      class?/factionCount?/voice?/combatStyle?/defaultOutfit?/attackRace?/skin?/
      aggression?/confidence?/assistance?/responsibility?/mood?/keywordCount?/itemCount?/perkCount?/
      defaultTemplate?/useTemplateActors?(raw int — byte-exact bitfield round-trip),
      armor: value?/weight?/armorRating?/keywordCount?/bipedSlotCount?,
      quest: name?/questType?/stageCount?/objectiveCount?/objectiveTargetCount?/objectiveFlaggedCount?/topicCount?/
      infoCount?/lineCount?/conditionCount?/aliasCount?/scriptCount?/scriptPropertyCount?/
      fragmentCount?/fragmentScriptName?/aliasFragmentCount?/sceneCount?/sceneActionCount?,
      leveledNpc/leveledItem: entryCount?/flags?(raw int)/entries?[{reference,level,count}]}]};
      exit 0 / 2 error. Required by fo4_create_record (no Spriggit fallback for write).
  (3) lint-npc data-extractor for fo4_lint_npc_template (Faz 3 / W3f). argv: lint-npc
      --plugin <path>. Streams the plugin's NPCs (binary overlay, read-only) and emits
      {plugin, npcs:[{editorId, formKey, useTemplateActors(int), defaultTemplate(FormKey|null),
      headPartCount, faceMorphCount, faceTintingLayerCount}]}; exit 0 / 2 error. The lint POLICY
      (orphan_template_flags error + facegen_needed warning + severities) lives in tools.py —
      this verb is a thin extractor like (1). Required by fo4_lint_npc_template.
  GPL-3.0 (Mutagen.Bethesda): subprocess-only, gitignored under tools/, never
  distributed (Karar 7 — docs/karar-7-license-strategy.md). Source kept under
  tools/mutagen-cli/src/. Rebuild: dotnet publish src/Mutagen.RecordQuery.csproj
  -c Release -r win-x64 --self-contained false -o tools/mutagen-cli.
```

## Caprica

```yaml
name: Caprica
version: v0.3.0
source: https://github.com/Orvid/Caprica/releases/tag/v0.3.0
asset: Caprica.v0.3.0.7z
binary_path: tools/caprica/Caprica.exe
license: MIT
downloaded: 2026-05-10
extracted: 2026-05-10
sha256: 0037E54CF3A1021E976278D9A637E8AE541AAF9EBEB8D274B6C2CFE32F4EE559
size_mb: 0.4
exe_size_mb: 1.1
notes: |
  Hızlı Papyrus compiler (Bethesda compiler alternatifi). 2023-10 release,
  stale risk var.
  Session 4 (2026-05-15): TBD #2 partial-resolved. Caprica çalışıyor
  (`--game fallout4 --ignorecwd -i Base -i src -f FLG -o OUT`),
  TestScript.pex üretti (550 B). CK PapyrusCompiler `.pas` üretti ama
  `.pex`'e geçemedi (PapyrusAssembler launcher-runtime context bekliyor).
  Karar: fo4_papyrus_build default backend = Caprica.
  Detay: research/p0/papyrus/2026-05-15-bytecode-diff.md.
  Faz 2.2 (2026-06-06): namespaced quest/topicinfo fragment'lar
  ("Fragments:Quests:QF_<eid>_<fid>") artık out-of-the-box derleniyor —
  fo4_papyrus_build kaynağın bildirilen Scriptname'inden namespace root'unu
  türetip import'a ekliyor (yoksa Caprica "namespace does not match ''" fatal
  verir) ve üretilen alt-dizin .pex'ini rglob+posix ile raporluyor. Üretilen
  .pex yolu metadata ScriptName'iyle (`:`→`/`) eşleşir → create_record fragment
  loop'u kapanır (in-game ateşleme user-gated). Bkz quest-roundtrip-proof → Faz 2.2.
```

## Champollion

```yaml
name: Champollion
version: v1.3.2
source: https://github.com/Orvid/Champollion/releases/tag/v1.3.2
asset: Champollion.v1.3.2.zip
binary_path: tools/champollion/Champollion.exe
license: LGPL-3.0
downloaded: 2026-05-10
extracted: 2026-05-10
sha256: EA53054276AC8006CCD3B323286BFBC6E34A454FA419D08DA9BD440CBD31B383
size_mb: 0.6
exe_size_mb: 1.3
notes: |
  Papyrus decompiler (.pex -> .psc). MVP'de zorunlu değil ama reverse
  engineering / Caprica vs Bethesda compiler output karşılaştırması
  için faydalı.
```

## xEdit (FO4Edit) — BSArch DAHIL

```yaml
name: xEdit (FO4Edit)
version: xedit-4.1.5f
source: https://github.com/TES5Edit/TES5Edit/releases/tag/xedit-4.1.5f
asset: xEdit.4.1.5f.7z
binary_path: tools/xedit/xFOEdit64.exe
binary_path_alts: |
  tools/xedit/xFOEdit.exe         (FO4 32-bit)
  tools/xedit/BSArch64.exe        (BA2 pack/unpack 64-bit, BONUS — manuel listeden cikti)
  tools/xedit/BSArch.exe          (BA2 pack/unpack 32-bit)
  tools/xedit/BSArchPro64.exe     (BSArch Pro 64-bit)
  tools/xedit/xDump64.exe         (plugin dump utility)
license: MPL-2.0
downloaded: 2026-05-10
extracted: 2026-05-10
sha256: 54C014DA621F83F06A64FD92DDB8E32ED3082D1C65F543DC1C4E432130DCED08
size_mb: 29.9
notes: |
  Mutagen alternatifi olarak ESP inspect için ground-truth referans.
  fo4-mcp'de doğrudan kullanılmaz (Mutagen tercih), manuel sanity check için.

  ÖNEMLİ KEŞIF: xEdit kurulumu BSArch'ı da getiriyor — manuel listeden
  çıkarıldı. fo4_pack_ba2 BSArch64.exe'yi kullanıyor (ayrı BSArch girdisi aşağıda).
```

## BSArch (console — xEdit bundled)

```yaml
name: BSArch
version: 0.9c
source: xEdit (TES5Edit/github) — bundled
asset: BSArch64.exe (xEdit distribution)
binary_path: tools/xedit/BSArch64.exe
license: MPL-2.0
downloaded: 2026-05-10
extracted: 2026-05-10
sha256: 5A8F1FD36ADB183FCF3EEC04E092F61F2AFA5E9A869AB181F81BD65A55E5B267
notes: |
  Konsol BA2 packer/unpacker (zilav, ElminsterAU, Sheson). fo4_pack_ba2 (#A2)
  bunu wrap'liyor: `pack <folder> <archive.ba2> -fo4` (GNRL) / `-fo4dds` (DX10);
  -z compress (general-only, ses/voice bozar), -mt, -share. Headless, exit 0.
  DİKKAT: ayrı indirilen BSArchPro (Nexus 63243) GUI-only — headless CLI YOK,
  wire EDİLMEDİ. xLODGen (tools/xlodgen/) argv-builder olarak wire EDİLDİ
  (fo4_build_lod; generation adımı GUI-only kalıyor — aşağıda). ReSaver
  (tools/resaver/, Apache-2.0) artık save Papyrus-VM cleaning için WIRE EDİLDİ
  via headless `resaver-shim` (JDK 21 indirildi) → fo4_clean_save_papyrus
  (#16-B). ReSaver'ın kendi CLI'ı hâlâ GUI-only; biz engine sınıflarını
  (ESS/Papyrus) shim'le sürüyoruz. Bkz aşağıdaki jdk + resaver-shim girdileri.
```

## xLODGen (terrain/object LOD — xEdit fork)

```yaml
name: xLODGen
version: beta 132 (sheson)
source: https://stepmodifications.org/forum/topic/13451-xlodgen-terrain-lod-beta-for-fo3-fnv-tes5-sse-enderal-fo4-tes4/
asset: xLODGen.132.7z
binary_path: tools/xlodgen/xLODGen/xLODGenx64.exe
binary_path_alts: |
  tools/xlodgen/xLODGen/xLODGen.exe                 (32-bit fallback; readme: always use x64)
  tools/xlodgen/xLODGen/Edit Scripts/LODGenx64.exe  (object/tree LOD mesh assembler)
  tools/xlodgen/xLODGen/Edit Scripts/Texconvx64.exe (DDS conversion helper)
license: UNVERIFIED — beta-132 arşivi net lisans içermiyor. xEdit fork'u (xEdit MPL-2.0)
  ama xLODGen redistribution şartları doğrulanmadı. Binary/üretilen LOD'u dağıtmadan ÖNCE
  kontrol et. Subprocess-only + dağıtılmaz.
sha256: 738B2AC42AFF3C438AE5706CB33B7E1410E17A3F34DA8AF9A0C14CEF3C270CE4
notes: |
  xEdit'in GUI fork'u — HEADLESS LOD generation YOK. -autoload/-autoexit sadece
  modül-seç dialogunu atlıyor; worldspace seçimi + "Build meshes" interaktif.
  fo4_build_lod argv'yi construct/validate eder + output'u (staging/fixtures)
  gate eder; kullanıcı elle çalıştırır (önerilen: MO2 tool — VFS load order verir).
  Verified argv + reality-check: research/p0/xlodgen/2026-06-05-cli-probe.md
```

## CLASSIC (evildarkarchon v9 fork)

```yaml
name: CLASSIC (evildarkarchon CLI fork)
version: 9.0.0
source: https://github.com/evildarkarchon/CLASSIC-Fallout4/releases/tag/9.0.0
asset: CLASSIC-9.0.0.7z
binary_path: tools/classic/CLASSIC.exe
license: unknown (LICENSE dosyası repo'da yok — Karar 7 license strategy gerekli)
downloaded: 2026-05-10
extracted: 2026-05-10
sha256: 1901D30C5E578ED46F555EBCB432C00D14863F841BF3E9CB4A27CA69926091E4
size_mb: 69.9
exe_size_mb: 12.2
notes: |
  Crash log analyzer. evildarkarchon v9 = C++/Rust rewrite.
  Beklenen `classic-cli.exe` yerine `CLASSIC.exe` (12 MB) — CLI/GUI
  ayrımı argv'ye bağlı olabilir, doğrulama gerek (CLASSIC.exe --help).
  vc_redist.x64.exe da içeride (kullanıcı kurmamış olabilir).
  Output markdown — JSON desteği yok, parser yazılması gerekir.
  fo4_analyze_crash_log default backend.
```

## LOOT

```yaml
name: LOOT
version: 0.29.1
source: https://github.com/loot/loot/releases/tag/0.29.1
asset: loot_0.29.1-win64.7z
binary_path: tools/loot/loot_0.29.1-0-g77f3ba9_0.29.1/LOOT.exe
license: GPL-3.0
downloaded: 2026-05-10
extracted: 2026-05-10
sha256: 699DBB1157E26CBD8B8758632B8370BBB372759C9A00FFD9A4300A05F3409837
size_mb: 16.8
exe_size_mb: 4.3
notes: |
  Load order sort + masterlist. CLI: loot --game=Fallout4 --auto-sort.
  fo4-mcp tarafından load order normalization için subprocess hedefi
  olabilir (V2). GPL-3.0 -> subprocess-wrap zorunlu.
  Versioned subdir (loot_0.29.1-0-g77f3ba9_0.29.1/) — versiyon yenilemede
  binary_path otomatik refresh edilmeli.
```

## NifSkope (FO4 NG fork)

```yaml
name: NifSkope (fo76utils fork)
version: v2.0.dev11-20251230
source: https://github.com/fo76utils/nifskope/releases/tag/v2.0.dev11-20251230
asset: NifSkope_2_0_2025-12-30-win64qt6_clang.7z
binary_path: tools/nifskope/NifSkope/NifSkope.exe
binary_path_alts: |
  tools/nifskope/NifSkope/NifSkope_noavx.exe   # AVX yok CPU'lar
  tools/nifskope/NifSkope/NifSkope_noavx2.exe  # AVX2 yok CPU'lar
  tools/nifskope/NifSkope/NifMopp.exe          # collision shape utility
license: BSD-3-Clause
downloaded: 2026-05-10
extracted: 2026-05-10
sha256: 561E4F7C1A74762134C3AEB3883143DDEAACFFC6F60697EC7B2022987BA8FB50
size_mb: 23.9
exe_size_mb: 5.8
notes: |
  Original niftools/nifskope FO4 NG'yi destekliyor ama 2017'de donmuş.
  fo76utils fork aktif (2025-12-30 build), FO4 NG + Starfield + glTF
  export/import destekli. GUI tool — fo4-mcp doğrudan subprocess
  çağırmaz, kullanıcı manuel kullanır. Mesh inspect ground-truth.
```

## Wrye Bash

```yaml
name: Wrye Bash
version: v314
source: https://github.com/wrye-bash/wrye-bash/releases/tag/v314
asset: Wrye.Bash.314.-.Standalone.Executable.7z
binary_path: tools/wrye-bash/Mopy/Wrye Bash.exe
license: GPL-3.0
downloaded: 2026-05-10
extracted: 2026-05-10
sha256: 221DC3BCAFEB00FA69C8AA1E98A81C1EFF8B8A7709FF2B00317485143C7D8E57
size_mb: 45.1
exe_size_mb: 41.4
notes: |
  Bashed Patch + plugin merge. GUI primary, CLI argument'ları var
  (auto-merge, auto-export). fo4-mcp Phase 2+ değerlendirmesi.
  BONUS: Mopy/bash/compiled/7z.exe var — gelecekte 7-Zip subprocess
  bağımlılığı için kullanılabilir.
```

## CommonLibF4 (source clone)

```yaml
name: CommonLibF4
version: master (shallow clone @ 2026-05-10)
source: https://github.com/Ryan-rsm-McKenzie/CommonLibF4
asset: git clone --depth 1
binary_path: N/A (header library — CMake target, vcpkg dep)
license: MIT
downloaded: 2026-05-10
sha256: N/A (source tree)
notes: |
  Ryan-rsm-McKenzie original. F4SE plugin yazımı için reverse-engineered
  C++23 type-safe wrapper. **MIT lisansı** — static link OK, kullanıcı
  kendi plugin'ini istediği lisansta dağıtabilir (GPL contagion yok).
  V3 hedefi (kendi DLL'ini yazma) için temel. Build: CMake + vcpkg.
  fo4-mcp tarafından doğrudan tüketilmez.
```

## commonlibf4-template (source clone)

```yaml
name: commonlibf4-template (libxse)
version: main (shallow clone @ 2026-05-10)
source: https://github.com/libxse/commonlibf4-template
asset: git clone --depth 1
binary_path: N/A (template scaffold — xmake build)
license: GPL-3.0
downloaded: 2026-05-10
sha256: N/A (source tree)
notes: |
  libxse'nin plugin template'i. **DİKKAT: GPL-3.0** — bu template'ten
  türeyen pluginler GPL-3.0 olmak zorunda. Permissive lisans için
  Ryan'ın CommonLibF4'ünü doğrudan referans al + kendi CMake setup'ı.
  Build: xmake (alternatif). Modern, libxse aktif maintain ediyor.
```

---

## Session 3 — Nexus Premium API toplu indirme (2026-05-13)

Aşağıdaki 14 mod `tools/fetch-nexus.py` ile Nexus Premium API üzerinden indirildi (Nexus Premium hesabı, key `secrets/nexus.env` içinde). Tümü AE (1.11.191) runtime'a uyumlu. `tools/extract-nexus.py` ile arşivler açıldı, binary_path'ler tespit edildi.

## Fallout 4 Script Extender (F4SE)

```yaml
name: F4SE
version: 0.7.7
source: https://www.nexusmods.com/fallout4/mods/42147
asset: Fallout 4 Script Extender-42147-0-7-7-1765908597.7z
binary_path: tools/f4se/f4se_0_07_07/f4se_loader.exe
binary_path_alts: |
  tools/f4se/f4se_0_07_07/f4se_*.dll          # F4SE runtime DLLs (deploy to game root)
  tools/f4se/f4se_0_07_07/Data/F4SE/Scripts/  # F4SE Papyrus script sources
license: silverlock (binary distribution OK; source on GitHub ianpatt/f4se)
downloaded: 2026-05-13
extracted: 2026-05-13
sha256: D1747DFEFA28E2DE37468D0DE4B2458EB7C5224E30FCA24ED328CFC1B40D8A08
size_bytes: 916047
notes: |
  Nexus mirror (silverlock.org canonical). v0.7.7 AE-uyumlu.
  Deploy: f4se_loader.exe + f4se_*.dll game folder kökü.
  Data/F4SE/Scripts/ Papyrus include path olarak Caprica'ya geçer.
```

## Addictol (Buffout 4 NG/AE successor)

```yaml
name: Addictol
version: 1.2
source: https://www.nexusmods.com/fallout4/mods/84214
asset: Addictol 1.2-84214-1-2-1775139822.zip
binary_path: tools/addictol/f4se/plugins/Addictol.dll
license: GPL-3.0 (subprocess-wrap zorunlu)
downloaded: 2026-05-13
extracted: 2026-05-13
sha256: 829E8DD79CF6BBDB450E706E91E354AC912405D213E9570E41EA575974BAB7FB
size_bytes: 9909265
notes: |
  2026 NG/AE standard crash logger + engine fixes bundle (Buffout 4 NG +
  X-Cell + Mentats + Escape Freeze + Baka MaxPapyrusOps).
  AddictolCrashLogger ayrı binary — bu pakette dahil mi kontrol edilmeli.
  Crash log path: %USERPROFILE%/Documents/My Games/Fallout4/F4SE/crash-*.log.
  MiniBuff DEPRECATED 2026 → Addictol primary hedef.
```

## Address Library for F4SE Plugins (All-In-One)

```yaml
name: Address Library
version: 1.11.191 (All-In-One bundle, OG + NG + AE)
source: https://www.nexusmods.com/fallout4/mods/47327
asset: Address Library - All In One-47327-1-11-191-1765967714.zip
binary_path: tools/address-library/F4SE/Plugins/version-1-11-191-0.bin  # AE
binary_path_alts: |
  tools/address-library/F4SE/Plugins/version-1-10-163-0.bin   # OG
  tools/address-library/F4SE/Plugins/version-1-10-984-0.bin   # NG
  # 13 runtime variantı toplam mevcut (1.10.130 → 1.11.191)
license: MIT-style (Fudgyduff; standard F4SE plugin license pattern)
downloaded: 2026-05-13
extracted: 2026-05-13
sha256: FFAC5F9E8CACE8E7FEFF6B5089AB7FDC89A7FCC81F806EA676717999ADC3F6AB
size_bytes: 52712149
notes: |
  Veri dosyaları (.bin offset tables), executable değil. F4SE plugin'lerinin
  %95'i buna bağlı (Buffout/Addictol, RobCo, SPID-F4, BOS-F4, Lighthouse).
  AE deployment: tools/address-library/F4SE/Plugins/version-1-11-191-0.bin
  → game folder Data/F4SE/Plugins/ altına kopyalanır.
```

## xSE PluginPreloader F4

```yaml
name: xSE PluginPreloader F4
version: 0.3
source: https://www.nexusmods.com/fallout4/mods/33946
asset: xSE PluginPreloader F4 0.3-33946-0-3-1718686029.zip
binary_path: tools/xse-preloader/WinHTTP.dll
binary_path_alts: |
  tools/xse-preloader/xSE PluginPreloader.xml   # config
license: unknown (LICENSE dosyası yok)
downloaded: 2026-05-13
extracted: 2026-05-13
sha256: 5DF039EFD0A523245BC6914EC6E8595522B0063BDE996582116EC746499929C9
size_bytes: 2497829
notes: |
  DLL hijack pattern (WinHTTP.dll → game folder kökü). Buffout/Addictol
  için erken yükleme şart, bunsuz crash logger çakışabilir. Anti-virüs
  alarm üretebilir (DLL hijack tekniği yüzünden).
```

## RobCo Patcher (AE branch)

```yaml
name: RobCo Patcher
version: 4.4.5-AE
source: https://www.nexusmods.com/fallout4/mods/69798
asset: RobCo Patcher - AE-69798-4-4-5-1772466014.zip
binary_path: tools/robco-patcher/F4SE/Plugins/RobCoPatcherAE.dll
license: unknown (LICENSE dosyası repo'da yok → Nexus permissions tek hukuki kaynak)
downloaded: 2026-05-13
extracted: 2026-05-13
sha256: 7959F923E89AAE07D2D8738B752C6405FBECF9FDD8DA95CC85587846E437D967
size_bytes: 5692752
notes: |
  Mod meta v4.4.6 ama AE primary file v4.4.5 (Zzyxzz publish window).
  V2 tool hedefi (fo4_validate_robco_config, fo4_generate_robco_config).
  Silent-ignore failure: bad config = no log no crash → MCP validator değer üretir.
  AE branch'i ayrı dosya (NG/OG için ayrı dist).
```

## Spell Perk Item Distributor F4 (AE branch)

```yaml
name: SPID-F4
version: 3.1.1-AE
source: https://www.nexusmods.com/fallout4/mods/48365
asset: Spell Perk Item Distributor F4  - AE-48365-3-1-1-1764509621.7z
binary_path: tools/spid-f4/Data/F4SE/Plugins/po3_SpellPerkItemDistributorF4.dll
license: unknown (LICENSE dosyası repo'da yok)
downloaded: 2026-05-13
extracted: 2026-05-13
sha256: 3BAD83A4CE02643B3F43D4AA28ECDE61E7675CB16B9677DB4740EB4C4E3187AC
size_bytes: 5447319
notes: |
  powerof3 master "AE update" 2025-11-30; v3.1.1 AE-uyumlu.
  V2 tool: fo4_generate_spid_config. FormID < 0x800 silent-drop bug (issue #3).
  Skyrim SPID ile codebase ayrı — repo: powerof3/SPID-F4.
```

## Base Object Swapper F4 (AE branch)

```yaml
name: BOS-F4
version: 2.2.1-AE
source: https://www.nexusmods.com/fallout4/mods/67528
asset: Base Object Swapper AE-67528-2-2-1-1764509259.7z
binary_path: tools/bos-f4/Data/F4SE/Plugins/po3_BaseObjectSwapperF4.dll
license: unknown (LICENSE dosyası repo'da yok)
downloaded: 2026-05-13
extracted: 2026-05-13
sha256: 63562FE85FDD5B5938FA581752E22241D05D62B6E4B705312E3BDF387398AF48
size_bytes: 3970803
notes: |
  powerof3 master "AE update" 2025-11-20; v2.2.1 AE-uyumlu.
  V2 tool: fo4_generate_bos_config. Precombine breakage riski STAT swap'larda.
  PRP ile birlikte kullanılmalı (worldspace edits).
  Repo: powerof3/BaseObjectSwapperF4 (Skyrim'in MIT BOS'undan ayrı codebase).
```

## Previsibines Repair Pack (Stable Branch, AE Full)

```yaml
name: PRP
version: 81.8 (1.11.191 Full)
source: https://www.nexusmods.com/fallout4/mods/46403
asset: Previsibines Repair Pack - Full (1.11.191)-46403-81-8-1777900797.7z
binary_path: N/A (data mod — ESM + BA2 + .csg/.cdx geometry cache)
binary_path_alts: |
  tools/prp/ppf.esm                    # base previs replacement master
  tools/prp/prp.esp                    # PRP patch plugin
  tools/prp/ppf - main.ba2
  tools/prp/ppf - textures.ba2
  tools/prp/prp - main.ba2
  tools/prp/prp - geometry.csg         # CK Platform Extended geometry
  tools/prp/prp.cdx                    # combined cell data index
  tools/prp/CellOffsetCache/           # cell offset overrides
license: BenRierimanu Nexus permissions (LICENSE doc Nexus'ta)
downloaded: 2026-05-13
extracted: 2026-05-13
sha256: D59D7F310F7FE4BCD8F186C47890AB77D6ED39D3AEC21B0D05AD92E1B1F58FC9
size_bytes: 2263993175
notes: |
  2.26 GB — en büyük asset paketi. BOS-F4 ve diğer mesh swap modlarında
  precombine breakage'i kapatır. AE-specific build (1.11.191 only).
  Deploy: mod olarak yüklenir (MO2 mod folder olarak), ESM master loaded.
  fo4-mcp subprocess hedefi değil; environment check'te dependency olarak izlenir.
```

## Lighthouse Papyrus Extender

```yaml
name: Lighthouse Papyrus Extender
version: 1.13.0
source: https://www.nexusmods.com/fallout4/mods/71420
asset: Lighthouse Papyrus Extender-71420-1-13-0-1732846550.7z
binary_path: tools/lighthouse-papyrus/F4SE/Plugins/LighthousePapyrusExtender.dll
license: doğrulanamadı (GELUXRUM author, Nexus permissions kontrol)
downloaded: 2026-05-13
extracted: 2026-05-13
sha256: 300DAE5E053F2A93FAF8F7F6FDA97341B8817D851459426474CBDA55C468A92D
size_bytes: 3576591
notes: |
  PapyrusUtil F4 mevcut değil — FO4 ekosistemi LPE'yi kullanıyor.
  Vanilla Papyrus'a string format / math / array / file I/O API'leri ekler.
  Quest scripting common dependency. Caprica include path'inde Papyrus
  script source'ları (Lighthouse*.psc) olabilir — paket içeriği kontrol.
```

## HUDFramework

```yaml
name: HUDFramework
version: 1.0f
source: https://www.nexusmods.com/fallout4/mods/20309
asset: HUDFramework 1.0f-20309-1-0f.zip
binary_path: N/A (data mod — ESM + BA2 + SWF)
binary_path_alts: |
  tools/hudframework/HUDFramework.esm
  tools/hudframework/HUDFramework - Main.ba2
  tools/hudframework/Interface/HUDMenu.swf
license: doğrulanamadı (registrator2000)
downloaded: 2026-05-13
extracted: 2026-05-13
sha256: 82F8D7E3CE21DE434DC892898C77CED9911213288156F91B336BF44F8EDBD627
size_bytes: 287655
notes: |
  Pure Papyrus + SWF — F4SE DLL yok. UI framework for HUD widgets.
  V2 quest mod'da custom HUD element için zorunlu, MVP'de değil.
```

## Mod Configuration Menu (MCM)

```yaml
name: MCM
version: 1.43
source: https://www.nexusmods.com/fallout4/mods/21497
asset: Mod Configuration Menu 1.43-21497-1-43-1765911344.zip
binary_path: tools/mcm/Data/F4SE/Plugins/mcm.dll
binary_path_alts: |
  tools/mcm/Data/MCM/
  tools/mcm/Data/Interface/MCM/
license: doğrulanamadı (registrator2000)
downloaded: 2026-05-13
extracted: 2026-05-13
sha256: 621D2CB36A2494553F372E8B5DBAB7DF5FE732C4D6CA04979BDDEA209528802F
size_bytes: 361517
notes: |
  In-game config UI. Mod publish ederken standart kullanıcı arayüzü.
  Quest mod'lar genelde MCM dependency'sini bildirir.
```

## BodySlide and Outfit Studio

```yaml
name: BodySlide
version: 5.7.1
source: https://www.nexusmods.com/fallout4/mods/25
asset: BodySlide and Outfit Studio - v5.7.1-25-5-7-1-1753637014.7z
binary_path: tools/bodyslide/Tools/BodySlide/BodySlide x64.exe
binary_path_alts: |
  tools/bodyslide/Tools/BodySlide/OutfitStudio x64.exe   # outfit conversion
  tools/bodyslide/Tools/BodySlide/BodySlide.exe          # 32-bit fallback
  tools/bodyslide/Tools/BodySlide/OutfitStudio.exe       # 32-bit fallback
license: GPL-3.0 (subprocess-wrap zorunlu)
downloaded: 2026-05-13
extracted: 2026-05-13
sha256: E15E7849005EA92A11B1FBE02635D1149A0D0A0BFA6894563CF45594A4543360
size_bytes: 16820030
notes: |
  Custom armor authoring core tool (Karar 2 persona: armor end-to-end).
  GUI primary; CLI argümanları sınırlı. fo4-mcp doğrudan subprocess hedefi
  değil — kullanıcı manuel çalıştırır, fo4-mcp output BSA/NIF paketleri okur.
```

## Material Editor (BGSM/BGEM)

```yaml
name: Material Editor
version: 1.9.0
source: https://www.nexusmods.com/fallout4/mods/3635
asset: Material Editor-3635-1-9-0-1721769261.zip
binary_path: tools/material-editor/Material Editor.exe
license: unknown
downloaded: 2026-05-13
extracted: 2026-05-13
sha256: 713AF2E5B746A3AB5F60470BAF70C734DB8AD065149F2797C45B6158CC985AB3
size_bytes: 82478542
notes: |
  Mod meta v1.9.1, en yeni primary file v1.9.0 — bug fix güncellemeleri
  Update kategorisinde gelebilir, kontrol et. Custom armor authoring V2.
  BGSM/BGEM material files editor. GUI tool.
```

## Cathedral Assets Optimizer

```yaml
name: CAO
version: 5.3.7
source: https://www.nexusmods.com/skyrimspecialedition/mods/23316 (cross-game, FO4 destekli)
asset: Cathedral Assets Optimizer 64-23316-5-3-7-1638099043.7z
binary_path: tools/cao/Cathedral_Assets_Optimizer.exe
license: doğrulanamadı (Guekka author, GitHub repo private/deleted)
downloaded: 2026-05-13
extracted: 2026-05-13
sha256: 4A9DBD61E91FE1C1C810816DED0A8A5A265A971CEB0C231CBF564F5DE844EA6E
size_bytes: 9468857
notes: |
  Cross-game SSE Nexus sayfası — FO4 desteği config profile'ı seçilerek.
  Texture compression + NIF optimization + BSA/BA2 batch. Mod release
  pipeline'ında zorunlu. Mod meta v5.3.15 ama primary file v5.3.7 —
  ayrı download'lar olabilir, FO4 profile kontrol.
```

## Mod Organizer 2

```yaml
name: MO2
version: v2.5.2
source: https://github.com/ModOrganizer2/modorganizer/releases/tag/v2.5.2
asset_installer: Mod.Organizer-2.5.2.exe        (147.5 MB, sistem-wide installer)
asset_portable: Mod.Organizer-2.5.2.7z          (149.7 MB, portable archive)
binary_path: tools/mo2/portable/ModOrganizer.exe   # ← PORTABLE seçildi (Session 3)
binary_path_alt: tools/mo2/Mod.Organizer-2.5.2.exe # installer kalıyor; istenirse sistem-wide kurulur
license: GPL-3.0 (subprocess-wrap zorunlu)
downloaded: 2026-05-13
extracted: 2026-05-13 (portable .7z → tools/mo2/portable/, 154 dir / 1626 file / 390 MB)
sha256_installer: D3F699D4042FF209F596D98DACD7EBAA99D27E01C3A17CD5D4E19C2BAB6ED006
sha256_portable: E6376EFD87FD5DDD95AEE959405E8F067AFA526EA6C2C0C5AA03C5108BF4A815
size_bytes_installer: 147500664
size_bytes_portable: 149660212
notes: |
  Karar 2 persona: MO2 user (solo mod author + dev). PORTABLE seçildi —
  sistem-wide install yok, instance tools/mo2/portable/. Avantajları:
    • Tek root altında; repo dışı yan etki yok
    • fo4-mcp MO2_INSTANCE_DIR deterministic (tools/mo2/portable/)
    • Reset/yeniden kurulum trivial (klasör silip yeniden extract)
  fo4-mcp `fo4_get_environment` MO2 instance detection bu path'i kullanır.
  İlk launch'ta MO2 profile + Fallout 4 binary path soracak (manuel adım).
```

---

## Creation Kit (Steam — read-only, Steam-managed)

```yaml
name: Fallout 4 Creation Kit
version: 1.11.137.0
source: https://store.steampowered.com/app/1946160/
app_id: 1946160
asset: (Steam-managed, no standalone archive)
install_dir: C:/Program Files (x86)/Steam/steamapps/common/Fallout 4 1946160/
binary_path: C:/Program Files (x86)/Steam/steamapps/common/Fallout 4 1946160/CreationKit.exe
binary_path_papyrus_compiler: C:/Program Files (x86)/Steam/steamapps/common/Fallout 4 1946160/Papyrus Compiler/PapyrusCompiler.exe
binary_path_papyrus_assembler: C:/Program Files (x86)/Steam/steamapps/common/Fallout 4 1946160/Papyrus Compiler/PapyrusAssembler.exe
binary_path_profile_analyzer:  C:/Program Files (x86)/Steam/steamapps/common/Fallout 4 1946160/Tools/PapyrusProfileAnalyzer.exe
binary_path_stack_dump_analyzer: C:/Program Files (x86)/Steam/steamapps/common/Fallout 4 1946160/Tools/PapyrusStackDumpAnalyzer.exe
license: Bethesda EULA (proprietary, ücretsiz kullanım — redistribute yasak)
installed: 2026-05-14 (Steam app 1946160 üzerinden, kullanıcı tarafından)
sha256_creationkit_exe: 222FD0AAD949E76721D85C922AE508ADA6816BA2F3E1FC11647C7239C24C2E13
size_bytes_creationkit_exe: 69017440
size_bytes_total_install: 212141970   # 202.3 MB
papyrus_compiler_version: 2.8.0.4
notes: |
  Steam tarafından Fallout 4 ana install'ından AYRI bir dizine kurulur:
    Fallout 4/          → oyun (1.11.191.0, runtime)
    Fallout 4 1946160/  → Creation Kit (1.11.137.0, editor)
  Bu önemli: CK Data/ kendi klasörünün altında — oyunun Data/'sıyla aynı
  değil. CK'yı modlu setup'la çalıştırmak için ya Data/'yı symlink/junction'la
  oyunun Data/'sına bağla, ya da MO2 üzerinden CK'yı launch et (önerilen).
  CK 1.11.137 → game 1.11.191 sürüm farkı var; CK 1.10/1.11 generation
  hâlâ AE oyununu açar (form record yapısı uyumlu, esm save yaparken çakışma yok).
  Papyrus Compiler dahil — Caprica (custom) ve Champollion (decompiler)
  reverse direction; bu official forward compiler. Path:
    Papyrus Compiler/PapyrusCompiler.exe  v2.8.0.4
  Lisans: Bethesda EULA proprietary, üretilen mod kullanıcının; CK'nın kendisi
  redistribute edilemez. fo4-mcp subprocess çağrısı OK (tool olarak çağrı serbest).
```

---

## Manuel indirilecekler

`MANUAL-DOWNLOADS.txt` dosyasına bak. Auth-required tool'lar:
- F4SE (silverlock.org) [#1]
- Buffout 4 / Addictol (Nexus) [#2]
- RobCo Patcher (Nexus) [#3]
- SPID-F4 (Nexus) [#4]
- BaseObjectSwapperF4 (Nexus) [#5]
- ~~Creation Kit~~ → **Steam app 1946160 üzerinden kurulu** (2026-05-14), see CK entry above [#6 ✅]
- ~~Bethesda Papyrus Compiler~~ → **CK ile geldi**, see CK entry above [#7 ✅]
- Address Library for F4SE (Nexus) [#8]
- xSE PluginPreloader F4 (Nexus) [#9]
- PRP - Previs Repair Pack (Nexus) [#10]
- ~~BSArch~~ → **xEdit ile geldi**, manuel'e gerek yok
- BodySlide and Outfit Studio (Nexus) [#12]
- Material Editor (Nexus) [#13]
- Cathedral Assets Optimizer (Nexus) [#14]
- PapyrusUtil F4 (Nexus) [#15]
- HUDFramework (Nexus) [#16]
- MCM (Nexus) [#17]
- Mod Organizer 2 (Nexus tercih veya GitHub installer) [#18]
