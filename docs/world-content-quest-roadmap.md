<!-- Üretim: 2026-06-06, çok-ajanlı planlama workflow'u (run wf_5ec027a8-368; 17 ajan / 5 faz: Baseline→Research→Sequence→Adversarial→Lock; 1.66M token, 427 tool-use). Adversarial 3 lens (completeness/feasibility/risk) critical+major bulguları içselleştirildi. Workflow script: .claude/.../world-content-quest-roadmap-wf_5ec027a8-368.js -->

# Faz 3 — New-World-Content Quest Roadmap (LOCKED)

> **DURUM (2026-06-20): Mutagen-authorable eksen TAMAMLANDI.** DONE = W0, W1, W1.5, W2, W3(a-f),
> W3.5, **W4** (interior cell + placed refs), **W5** (cell-override + previs-safety), **W6** (Story
> Manager SMQN + sm-tree), **W6.5** (ACTI), **W7** (PACK template-bind MVP), **W8** (LCTN/LCRT/ECZN),
> **W8.5** (XTEL door-link), **W11a** (integration assembly — tek plugin multi-system). 28 MCP tool,
> 352 test. Probe doc'lar: `research/p0/world-content/2026-06-20-w{4,5,6,65-w8,7-w85}-*.md`.
> **DEFER (refinement, concrete-demand bekler):** W6.7 (location/collection alias + event-fill —
> base QuestReferenceAlias yeterli), W7 Package.Data input-map (semantik index-map research gate),
> ACTI control-script VMAD, LCTN ref-list'leri.
> **CK/İNSAN-GATED terminal fazlar (kilitli Mutagen-vs-CK sınırı — ASLA otomatik değil):** W9 voice
> (.fuz/.lip + FonixData), W10 FaceGen (.nif/.dds CKPE), W12 navmesh+previs+precombine batch + FormID-
> lock + ship-preflight, W11b in-game smoke (POST-CK; `fo4_run_ingame_test` runner mevcut ama canlı
> oyun + Steam login + W12-CK-finalize gerektirir). Bu fazlar handoff-doc + destek-tool üretir
> (`fo4_build_previs`/`fo4_compact_formids` SHIPPED; navmesh_handoff/voice-bake/facegen/preflight =
> sonraki destek-tooling katmanı), çekirdek EXECUTION insan/CK/GPU.

> **SSOT durumu:** Bu dosya, "yeni dünya içeriği üreten bir quest" yazma işinin **kilitli** faz planıdır. Canonical live board = `TASKS.md`; bu dosya onun anlatısal companion'ı (faz tablosu + gerekçe + doğrulama). Faz sınırlarında güncellenir. Oluşturma: Session 6 sonu (2026-06-06).
>
> **Kilit ilkesi (değişmez):** Steam game folder **read-only**. Tüm output → `staging/` veya `fixtures/`. GPL/3rd-party araçlar (LipGen, CKPE, FaceFX, BSArch, ReSaver) subprocess-isolated, **asla dağıtılmaz**. "Bükebileceğimiz kurallar" = Bethesda/CK konvansiyonları ve RE kısayolları — **güvenlik/boundary kuralları değil.**

## 1. Amaç + kapsam

Şimdiye kadarki authoring ekseni quest'in **mantık + diyalog omurgasını** çözdü (QUST iskeleti, DIAL/INFO/replik, koşullar, Papyrus VMAD + fragment `.pex` loop). **Faz 3'ün hedefi**: bu omurganın ötesine geçip **dünyada yeni içerik yaratan** bir quest'i uçtan uca yazmak — yeni NPC/obje/marker yerleştirme, yeni iç mekân CELL veya override-injection, NPC AI davranışı, Story-Manager-driven event başlangıç, opsiyonel seslendirilmiş + lip-sync diyalog ve custom FaceGen.

### Mutagen-vs-CK sınırı (en başta, kilitli)

| Katman | İçerik | Sınır |
|---|---|---|
| **A — Saf record authoring** | QUST/DIAL/INFO/SCEN, REFR/ACHR, iç-mekân CELL, NPC/LVLN/LVLI, FACT, GLOB/MESG/KYWD/FLST, ACTI, PACK, LCTN/LCRT/ECZN, SMQN | **Mutagen ile tam authorable**, byte-vs-Remnants doğrulanabilir, agent-otomatik |
| **B — Mutagen-feasible ama elle-pointless** | Exterior WRLD terrain (LAND) | Authorable ama anlamsız → mevcut cell'leri override et, terrain generator YAZMA |
| **C — CK/harici-exclusive, insan-gated** | NAVM/NAVI **generation + finalize**, precombine/previs regen, FaceGen `.nif`/`.dds`, AI-TTS audio | Byte round-trippable AMA **üretim** CK/GPU-bound → **insan-gated bottleneck** |

> **Dürüst kabul:** navmesh generation, precombine/previs regen, FaceGen üretimi ve gerçek TTS audio = bu roadmap'in **insan-gated darboğazlarıdır.** Disk-provable şimdi; runtime-provable **sadece oyun-içi.** Roadmap bunları geciktirir, batch'ler ve tek bir CK oturumuna toplar.

## 2. Mevcut durum (omurga = DONE)

- `fo4_create_record` (C# Mutagen writer): QUST type/flags/stages(+QSDT+RunOnStart)/objectives; quest-nested DIAL→INFO→replik; INFO/alias/scene koşulları; QuestReferenceAlias + koşullar; Papyrus VMAD + typed property; quest stage/alias fragment; SCEN sahneleri. **Desteklenen tipler: `npc`/`armor`/`quest`** (dünya-içeriği tipleri YOK).
- `fo4_papyrus_build`: fragment `.pex` Caprica ile, CK ile byte-aynı. 21 MCP tool, 253 test. Doktrin: in-tool read-back + Spriggit YAML 2. motor + byte-vs-CK.

## 3. Faz faz roadmap

> **Kilit terminoloji düzeltmesi (R&S critic):** "parallel-agentic" bu projede plugin/FormID-space paylaşımı yüzünden ikili-yazma anlamına GELMEZ. Tek `create_record` çağrısı tek `Fallout4Mod` + tek FormID allocator ile tek `.esp` yazar. **Karar kilitli:** paralellik SPEC/research authoring seviyesindedir; binary yazma her zaman tek plugin'e serileşir. Çok-plugin merge code-path'i V2'ye ertelendi (Remnants tek `.esp`, gerek yok).

### W0 — Plugin-format + conflict-safety fork'u kilitle (Track A vs Track B)
> **✅ DONE (2026-06-06, Track A seçildi).** `fo4_plan_plugin_format` + `fo4_set_master_flag` kuruldu (`plugin_format.py`, esl_flag helper'larını reuse), 23 tool / 270 test. **Düzeltme:** aşağıdaki "Track A → ESL-eligible" KABA idi — mevcut `_esl_verdict` yasası HER yeni cell/worldspace'i (iç-mekân DAHİL) ESM-zorlayıcı sayar → **yeni iç-mekân cell = ESM-flagged ESP** (tek ESL-uygun dünya-içeriği yolu = mevcut cell'e ref enjekte = W5). **Bonus fix:** W0 implementasyonu `fo4_check_esl_eligibility`'nin foundational bug'ını açtı — güncel Spriggit karmaşık record'u folder-per-record (`<Type>/<rec>/RecordData.yaml`) yazıyor, eski scan onları `RecordData.yaml`-name-skip ile düşürüyordu (her quest mod "no-new-records"); `_scan_serialized_records` ile düzeltildi (path-skip + type-klasör record_type). Bu olmadan advisor + tüm W-fazları yanlış format öğüdü verirdi.
- **Hedef:** Her sonraki fazın miras aldığı tek ikili tasarım kararını kilitle: yeni cell/worldspace mı (Track B → ESM-flagged-ESP, previs yükümlülüğü, light-flag YOK) yoksa mevcut cell'lere / yeni iç mekâna mı (Track A → ESL-eligible). **Bu taze bir karar DEĞİL** — `TASKS.md` satır 140 yasayı zaten kaydetmiş; W0 onu CITE EDEREK açar, tek açık soruyu sorar: yeni İÇ MEKÂN cell (Track A) mı yoksa yeni WORLDSPACE/exterior cell (Track B) mi? (30-sn onayı).
- **Deliverables:** `fo4_plan_plugin_format` (read-only verdict advisor, mevcut yasayı ZORLAR); `fo4_set_master_flag` (saf-Python TES4 0x01 ESM byte-flip, **yeni CELL/WRLD varsa 0x0200 light/ESL'i REDDEDEN guard ile EŞLEŞTİRİLMİŞ**, gated + .bak); bu dosya SSOT; TASKS.md W0..W12 ağacı. **DEFAULT = Track A** (Remnants `Small`/ESL flag disk-doğrulandı).
- **Yeni tool'lar:** `fo4_plan_plugin_format` (S), `fo4_set_master_flag` (S) · **Bağımlılık:** yok
- **Execution mode:** **kullanıcı-gated** — Track yaratıcı-kapsam çağrısı; advisor read-only paralel-build.
- **Risk:** 0x01-vs-0x0200 silent footgun (yeni-cell light-flag = load error yok ama previs kırılır). Guard sert reddetmeli.
- **Doğrulama:** verdict vs `fo4_check_esl_eligibility` Remnants dump'ında (✅ disk-doğrulandı); master-flag byte-diff + reopen.

### W1 — Condition-builder cerrahi genişletme: QuestAlias run-on (Unknown3) + Reference slot
- **Hedef:** Alias üzerinde çalışan GetDead/IsDead/GetItemCount paternini aç — `FunctionConditionData.Unknown3` (aliasID) + `Reference` (FormLink) slotları. QSTA/alias/SM/scene için keystone mikro-dep.
- **Deliverables:** `ConditionSpec` `aliasRunOn`/`reference` (~10 satır Program.cs:220-240); `_norm_conditions` erken-reject (`aliasRunOn` `runOn=QuestAlias` ister); **SetParam shape-heuristik testi** (Reference FormLink'in `ParameterOneRecord`'a yanlış düşmediği + `aliasRunOn=0` explicit-reddedildiği); round-trip byte-vs-Remnants.
- **Yeni tool:** condition-builder genişlemesi (S) · **Bağımlılık:** W0
- **Execution mode:** **dikkatli-sıralı (kaynak)** — tek hot BuildCondition; W2/W6/scene tüketir.
- **Risk:** Unknown3 yanlış default → her alias run-on sessizce alias-0. · **Doğrulama:** write→reopen + Spriggit vs Remnants GetDead+QuestAlias+Unknown3.
- **✅ DONE (2026-06-06):** `ConditionSpec.AliasRunOn` (int?, QuestAlias→`Unknown3`; alias-0 geçerli → explicit ŞART) + `Reference` (string?, Reference-runon FormLink slotu, param'lardan ayrı). `_norm_conditions` 3-kurallı erken-reject (QuestAlias→explicit aliasRunOn / aliasRunOn→QuestAlias / reference→Reference). Reflection-probe DONDURDU (`Unknown3`=Int32, `QuestAlias`=5, `Reference`=FormLink). Round-trip: write→disk→Spriggit `Unknown3: 2`/`RunOnType: QuestAlias`/`RunOnType: Reference`/`Reference: 000014:Fallout4.esm`. +6 test.

### W1.5 — Quest-support glue records: GLOB / MESG / KYWD / FLST *(CRITIC-EKLENDI, critical)*
- **Hedef:** Condition/script/objective'in bağlı olduğu glue record'ları mintle (yoksa dangling FormLink). Disk-doğrulandı: **16 GLOB, 8 MESG, KYWD, FLST.**
- **Deliverables:** `type=global` (GlobalFloat/Int/Short); `type=message` (MESG); `type=keyword` (KYWD); `type=formList` (FLST). Her tip Spriggit-diff proof.
- **Yeni tool'lar:** {global, message, keyword, formList} (her biri S) · **Bağımlılık:** W0
- **Execution mode:** **paralel-agentic (spec)** — bağımsız record; binary write tek plugin'e serileşir.
- **Risk:** Tüketiciler freeze ÖNCE land etmeli. · **Doğrulama:** vs `Globals/`, `Messages/`, `Keywords/`, `FormLists/`.
- **✅ DONE (2026-06-06):** `type=global` (abstract Global→concrete GlobalFloat/Int/Short, `(IFallout4Mod,string)` ctor + `Globals.Add`; `globalType`/`globalValue` double?, armor `Value` int?'den ayrı→fraction korunur), `type=message` (MESG text→Description/title→Name), `type=keyword` (bare KYWD), `type=formList` (FLST `items` FormLink listesi, element=`IFallout4MajorRecordGetter` NOT IKeywordGetter). Paralel-agentic spec workflow (`wf_511e86b4-c9c`, 4 spec + 1 synthesis) → binary write tek plugin'e serileşti (concurrency kuralı). abstractGlobalVerdict empirik DONDU (build-gate + read-back overlay interface-switch + Spriggit: int/float read-back + GlobalShort `MutagenObjectType`). +6 test → 282 suite.

### W2 — QSTA objective targets + objective-level flags — ✅ DONE (2026-06-07)
- **Hedef:** Quest arrow / compass marker datası — objective'i bir alias'a işaret ettir, per-target koşul/flag.
- **Deliverables:** `targets:[{aliasId, flags:[CompassMarkerIgnoresLocks|Hostile|UseStraightLinePathing], keyword?(LCRT), conditions?}]`; objective `flags:[OrWithPrevious|NoStatsTracking]`; aliasId validation; ~30-50 satır + ObjectiveTargetSpec.
  - **✅ DONE (2026-06-07):** `objectives[]` genişledi — `flags` (`QuestObjective.Flag` nullable [Flags]) + `targets[{aliasId, flags, keyword?, conditions?}]`. **Probe dondurdu:** `QuestObjectiveTarget.AliasID` = **Int32** (FormLink değil — SceneActor.ID deseni), `.Flags` = `Quest.TargetFlag` (non-null), `.Keyword` = `IFormLink<IKeywordGetter>` (LCRT), `.Conditions` = `ExtendedList<Condition>`. **Build-gate CS8852 yakaladı:** `Targets`/`Conditions` **init-only** (ctor-initialized) → `??= new()` yasak, doğrudan `.Add`. Conditions = 2.1b `BuildCondition` reuse (sıfır yeni infra); `ObjectiveTargetSpec` yeni. Round-trip: objective flags [OrWithPrevious+NoStatsTracking] + target [aliasId=1, CompassMarkerIgnoresLocks+Hostile, LCRT keyword, GetIsID condition] write→reopen (objectiveTargetCount=1/objectiveFlaggedCount=1) + Spriggit teyit. +4 test → 307. **Quest-yazma tarafı bununla pratikte tamamlandı** (skeleton+stages+dialogue+conditions+aliases+VMAD+scenes+fragments+objective markers).
- **Yeni tool:** objective `targets` (S) · **Bağımlılık:** W1, W1.5
- **Execution mode:** **paralel DISTINCT quest / sıralı tek quest içi** — target aynı quest objective listesine append.
- **Risk:** Görünür marker downstream'de W4 placed-ref'e bağlı. · **Doğrulama:** vs Remnants Objectives bloğu.

### W3 — Deep NPC + template chain + LVLN/LVLI (FaceGen'siz actor yolu) — ✅ TAM (W3a–W3f, 2026-06-07)
- **Hedef:** NPC'yi tam alan setine + template-chain'e (`DefaultTemplate` + `UseTemplateActors`) genişlet — pişmiş FaceGen miras = dark-face-free agent-authorable NPC.
- **W3-precondition gate (critical):** `UseTemplateActors` raw bitfield reflection-probe ile çözülMEDEN signature DONDURULAMAZ. Enum dök + tüm raw decode + arketip byte-verify. Probe pass etmeden npc-template `_CREATE_SUPPORTED_TYPES`'a girmez.
  - **✅ W3a ÇÖZÜLDÜ (2026-06-07):** enum = `Npc.TemplateActorType` (Int32, bit `Traits=1`…`Keywords=4096`, `[Flags]`'siz); property = `Npc.UseTemplateActors` (CanWrite); `Npc.DefaultTemplate` = `IFormLinkNullable<INpcSpawnGetter>`. Draft yanlıştı: **3360 = WorkshopTurret subset** (FaceGen-siz), gerçek LvlTurret = **8127**; `0x40` = `ModelOrAnimation` (boş bit değil). **6/6 byte-verify, 87 NPC, tüm raw'lar tam decode.** Spriggit YAML adları Mutagen üye adlarına `Template` suffix'i ekler. Tam tablo + W3c imzası → `research/p0/world-content/2026-06-07-w3a-usetemplateactors-probe.md`.
- **Deliverables:** aiData/flags/voice/combatStyle/combatOverridePackageList(FLST→W1.5)/defaultOutfit/keywords/attackRace/items(CNTO)/packages(W7)/perks; template-chain (probe-verified); `type=leveledNpc` (LVLN); **`type=leveledItem` (LVLI, CRITIC-EKLENDI** — yoksa NPC çıplak spawn); `fo4_lint_npc_template` (FaceGen-gerek tahmini, **W3-probe doğruysa güvenilir**).
  - **✅ W3b DONE (2026-06-07):** NPC full-field (probe-bağımsız) — scalar FormLink (`Voice`/`CombatStyle`/`DefaultOutfit`/`AttackRace`/`Skin`, hepsi `IFormLinkNullable`) + AI personality enum (`Aggression`/`Confidence`/`Assistance`/`Responsibility`/`Mood`, non-null `Npc.*Type`) + `Keywords` (`??= new()` guard) + `inventory` (CNTO `ContainerEntry{ContainerItem{Item,Count}}`, `Items ??= new()`) + `perks` (`PerkPlacement{Perk,Rank:Byte}`, `Perks ??= new()`). Mevcut Race/Class/Factions/ARMO-keywords/faction-flag desenlerini kompoze etti; sıfır yeni infra. Defer: spells(ActorEffect)/packages(W7)/package-list FLST/properties(ActorValue)/level/weight/shortName/flags. read-back tüm alanları geri okur. +5 test → 291. **combatStyle/defaultOutfit/skin = appearance-link'i besler; W3c template-chain üstüne oturur.**
  - **✅ W3c DONE (2026-06-07):** template-chain (W3a'ya dayanır) — `DefaultTemplate.SetTo(FormKey)` + `UseTemplateActors` (non-[Flags] Int32 → named flag'leri OR'la, cast). Race/Class/quest-flag desenlerini kompoze etti; sıfır yeni infra. **Byte-exact round-trip:** trooper (11 flag) → `7999`, turret (11+BaseData) → `8127` — ikisi de gerçek disk arketibini (EncEnclaveSoldier / LvlTurret) üretti; DefaultTemplate = `113341:Fallout4.esm` (LCharWorkshopNPC, gerçek LeveledNpc, reality-checked). **2 W3a-notu düzeltmesi:** (a) `8127 = 7999 + BaseData yalnız` (ModelOrAnimation ikisinde de KAPALI — satır-67'deki hex doğru, prose'taki "+ModelOrAnimation" değil); (b) Spriggit 0.40.1 `UseTemplateActors`'i **bare int** serileştiriyor (`Template` suffix iddiası per-flag `TemplateActors` alt-objesi içindi, bu bitfield için değil). +3 test → 294. Defer: per-flag `TemplateActors` + `LegendaryTemplate` (V2). Detay → W3a notunun "W3c DONE" eklentisi.
  - **✅ W3d+W3e DONE (2026-06-07):** LVLN + LVLI leveled lists (birlikte — aynı `Leveled*Entry`→`Leveled*EntryData{Level:Int16,Count:Int16,Reference:FormLink}` iskelesi). `type=leveledNpc`/`leveledItem`: `entries[{reference,level,count}]` + `flags` (mevcut `Flags` alanı reuse). **Flag bit-4 ADI FARKLI:** LVLN=`CalculateAll`, LVLI=`UseAll` (probe; writer her tip için kendi enum'unu parse eder). Faction-flag + Factions-list desenlerini kompoze etti; `LeveledEntrySpec` yeni; sıfır yeni infra. Build-gate `Entries ??= new()` guard'ı yakaladı (nullable-ref, W3b/Keywords dersi). **Round-trip:** LVLN 2-entry (Codsworth lvl1×1 + LCharWorkshopNPC lvl5×2, flags=2) + LVLI 1-entry (Caps lvl1×100, flags=4) — entry reference/level/count + flags byte-byte geri okundu; Spriggit `Entries:-Data:{Level,Reference,Count}` + flag adları teyit. Defer (§2): chanceNone(`Percent`-scaling belirsiz)/Global/MaxCount/FilterKeywordChances/LVLI EpicLootChance/OverrideName. +5 test → 299. Detay → `research/p0/world-content/2026-06-07-w3de-leveled-list-probe.md`. **LVLI = non-naked-spawn yolu (critic-CRITICAL).** Kalan W3 kalemi = W3f lint.
  - **✅ W3f DONE (2026-06-07):** `fo4_lint_npc_template` (yeni read-only tool, 23→24) + mutagen-cli `lint-npc` verb (3. subcommand, thin extractor; policy Python'da). 2 kural: `orphan_template_flags` (ERROR — UTA flag set ama DefaultTemplate yok = inert bug) + `facegen_needed` (WARNING — kendi face-data var [HeadParts/FaceMorphs/FaceTintingLayers>0] → baked FaceGen/W10 gerek, dark-face riski; `inheritsTraits` annotasyonu). **W3a FaceGen-hipotezi gerçek Remnants verisinde KISMEN ÇÜRÜTÜLDÜ:** Traits-ON troopers (7999) de FaceMorphs=28 taşıyor → "Traits set = miras alır, kendi FaceGen'i yok" YANLIŞ; **dark-face riski plugin'den tek başına belirlenemez** (asset'ler external) → lint verdict iddia etmez, coverage+bug-check verir. e2e: orphan (writer footgun → error/bug) + clean + gerçek Remnants 87-NPC coverage (error=0, facegen>0, review). +4 test → 303. Detay → `research/p0/world-content/2026-06-07-w3f-npc-template-lint.md`. **→ W3 TAM TAMAMLANDI.**
- **Yeni tool'lar:** npc full-field (M), template-chain (M), LVLN (S), LVLI (S), lint (S) · **Bağımlılık:** W0, W3.5
- **Execution mode (DÜZELTILDI — critic wrong-tag):** **karma** — npc-switch in-place edit = dikkatli-sıralı (kaynak); LVLN/LVLI/FACT bağımsız record = paralel (spec).
- **Risk:** Yanlış decode → AI yok VEYA dark-face geri döner. · **Doğrulama:** vs Remnants Enclave template/child/unique; LVLN vs LChar; LVLI vs LLI_EnclaveTrooper_Weapons.

### W3.5 — Faction (FACT) + interfaction relations *(CRITIC-EKLENDI, critical)*
- **Hedef:** Placed hostile NPC'yi gerçekten düşman yap. Disk-doğrulandı: `ccOTMFO4001_EnclaveFaction` (000008) main quest VMAD property. Draft FACT'ı sadece NPC ALANI olarak listeliyordu — yeni faction AUTHOR etmiyordu.
- **Deliverables:** `type=faction` (flags + interfactionRelations [{faction, combat reaction}] + ranks/crimeGold); byte-vs `Factions/ccOTMFO4001_EnclaveFaction`.
- **Yeni tool:** faction (S) · **Bağımlılık:** W0 (W3'ün bağımlılığı)
- **Execution mode:** **paralel-agentic (spec)** · **Doğrulama:** vs `Factions/ccOTMFO4001_EnclaveFaction`.
- **✅ DONE (2026-06-06):** `type=faction` — `name` + `flags` (RecordSpec.Flags reuse; `Faction.FactionFlag` non-nullable enum) + `interfactionRelations` [{faction, reaction}] → `Relations` list (`Relation.Target` FormLink + `Reaction` `CombatReaction`). Ranks/CrimeValues/VendorValues defer (hostility Hedef'i Relations+flags ile karşılanır). **Reality-check = Remnants ground-truth + compile-driven discovery** (AMSI dersi: inline-PS reflection yok; build=gate). W0/Faz2.2a deseni: cerrahi → main-loop, workflow değil. E2e write→reopen (flagCount=1/relationCount=1 + master auto-add) + Spriggit (`Reaction: Enemy`/`Target: 068043:Fallout4.esm`/`TrackCrime`). +4 test → 286 suite. Bkz `research/p0/world-content/2026-06-06-w3.5-faction.md`.

### W4 — Placed refs (REFR/ACHR) + yeni iç-mekân CELL — keystone gap-closer ✅ DONE (2026-06-20)
- **SONUÇ (2026-06-20):** `type=cell` SHIPPED — interior cell (IsInteriorCell + LightingTemplate/location/encounterZone/imageSpace/acousticSpace/music + waterHeight) + nested `placedObjects`[REFR] / `placedNpcs`[ACHR] (base/position/rotation/scale → Temporary veya Persistent). Probe doc: `research/p0/world-content/2026-06-20-w4-probe.md`. **3-motor doğrulama** (Mutagen round-trip + mutagen-cli query record_type=Cell + Spriggit `Cells/block/subblock/` nesting), +6 test → 334 pass. **Probe-düzeltmeleri:** (1) block/subblock formülü = **block=id%10, subblock=(id/10)%10** (önce ters sanılmıştı; vanilla SanctuaryRosaHouse 01F398→blk6/sub9 düzeltti); (2) lit interior = LightingTemplate (LTMP) ŞART; (3) Position/Rotation düz P3Float (Placement wrapper YOK); (4) verify-target = **SanctuaryRosaHouse "Rosa Residence"** (NavMeshGenCell DEĞİL — aşağıdaki düzeltme uygulandı). **Scope kararı (§2 basitlik):** placed refs cell'e NEST edilir (tek `type=cell`); standalone `type=placedObject`/`placedNpc` ayrı-tip + ref-into-vanilla-cell W5'e DEFER. DEFER: XCLL inline lighting (LTMP yeterli), enableParent XESP 0x7F0000, MajorFlag 0x400, patrol XPRD, primitive, exterior cell.
- **Hedef (orijinal):** PlacedObject/PlacedNpc AddNew (Base/Position/Rotation/Scale/EnableParent/LinkedRefs/Primitive/MajorFlags/VMAD/Patrol) + yeni iç-mekân CELL. Quest-alias forcedReference, map marker, scene staging, placed actor burada açılır.
- **W4 verify-target DÜZELTMESI (critical, üç lens hemfikir):** Remnants dump'ta **TEK cell `NavMeshGenCell` (000025, OVERRIDE)** — siyah lighting, navmesh-gen yardımcı, oynanabilir DEĞİL (disk-doğrulandı). Freeze template OLAMAZ. Düzeltme: (a) Fallout4.esm'den gerçek furnished vanilla iç-mekân dump et template yap; VEYA (b) box-room scope + ertelenen alanları (Room/Portal XCRI, AcousticSpace, ImageSpace, LightingTemplate, EncounterZone, Music) bilinen-gap dokümante.
- **Deliverables:** `type=cell` (interior: Flags/Lighting/WaterHeight/Location/EncounterZone); `type=placedObject`/`placedNpc` (base/position/rotation/scale/enableParent 0x7F0000/linkedRefs/primitive/collisionLayer/locationRef/MajorFlags 0x400/VMAD + **patrol {idleTime, topics} → XPRD** [FEASIBILITY critic, linked-ref chain 00003F→000040→000041]); **reflection reality-check ÖNCE** (child-group AddNew, XESP 0x7F0000, MajorFlag 0x400, XPRD); `_CREATE_SUPPORTED_TYPES` += cell/placedObject/placedNpc.
- **Yeni tool'lar:** cell (M), placedObject (M), placedNpc (S) · **Bağımlılık:** W0, W3, W3.5
- **Execution mode:** **dikkatli-sıralı (OUTPUT)** — aynı CELL child listesine append; enable-marker temporary'lerden ÖNCE.
- **Risk:** Persistent-vs-Temporary silent footgun; koordinat görsel-doğrulanamaz. · **Doğrulama:** vs Remnants Commonwealth Temporary PlacedObjects; iç-mekân = düzeltilmiş vanilla-interior template (NavMeshGenCell DEĞİL).

### W5 — Cell-override resolution: mevcut vanilla cell'lere ref enjekte ✅ DONE (2026-06-20)
- **SONUÇ (2026-06-20):** `fo4_place_into_cell` + `fo4_check_previs_safety` SHIPPED. Probe doc: `research/p0/world-content/2026-06-20-w5-probe.md`. **Feasibility-gate GEÇİLDİ.** Kritik bulgu: `mod.Cells.GetOrAddAsOverride` YOK (Cells = blok-list group, flat group değil) → **`srcCell.DeepCopy()` + manuel blok yerleşimi** kullanıldı; **LinkCache/LoadOrder GEREKMEZ** (roadmap'in "writer sıfır LinkCache" endişesi çözüldü — DeepCopy yolu master context'i gerektirmiyor, sadece source plugin overlay). Temiz add-ref deseni: DeepCopy (master data/lighting carry-forward → black-cell yok) → `Temporary/Persistent.Clear()` (master ref'leri master'da kalır → **ITM yok**) → yeni ref ekle → blok-yerleştir. **previs-safety BLOCKING gerçeklendi:** precombined/previs'li cell'e ref eklemek görselleri bozar → `acknowledge_previs=false` ise REDDET (yazma yok). Doğrulama: SanctuaryRosaHouse override → FormKey 01F398:Fallout4.esm korundu + name/lighting carry-forward + temp=2 sadece yeni ref. +7 test → 341 pass. **DEFER:** exterior/worldspace-persistent child-group hedefleme + GetOrAddAsOverride-with-linkcache (ITM-full deep override) yolu.
- **Hedef (orijinal):** Writer'a link-cache context ver, GetOrAddAsOverride. Disk-doğrulandı: writer `new Fallout4Mod(modKey)+AddNew`, sıfır LinkCache/LoadOrder. **Writer'ın en büyük lift'i.**
- **FEASIBILITY downgrade (critical):** "feasibility HIGH for RECORD bytes, **UNPROVEN for override code-path**, previs Mutagen-problemi DEĞİL." **Sert gate:** genişlemeden ÖNCE gerçek Commonwealth cell'inde elle-test GetOrAddAsOverride round-trip + byte-diff (CLAUDE.md §4).
- **Deliverables:** `fo4_place_into_cell`; worldspace-persistent child-group hedefleme; `fo4_check_previs_safety` (**BLOCKING precondition — "warning" değil "hard gate"**, critic critical).
- **Yeni tool'lar:** `fo4_place_into_cell` (L), `fo4_check_previs_safety` (S) · **Bağımlılık:** W4
- **Execution mode:** **dikkatli-sıralı (OUTPUT)** — aynı vanilla cell override = merge conflict.
- **Risk:** Precombined cell'e ref = sessiz previs kırılması (disk-doktrini KÖR). Safety scan gate'ler ama düzeltmez (W12). **MVP yeni-iç-mekâna SERT bias.** · **Doğrulama:** vs Remnants override paterni (EnableMarker 000088 flag 0x400).

### W6 — Story Manager quest-start (SMQN) + SM-tree reader ✅ DONE (2026-06-20)
- **SONUÇ (2026-06-20):** `type=smqn` + `fo4_inspect_sm_tree` SHIPPED. Probe doc: `research/p0/world-content/2026-06-20-w6-probe.md`. SMQN = **flat `Fallout4Group`** (AddNew, cell-blok değil); tree = `Parent` (SNAM, event/branch node) + `PreviousSibling` (sibling sıra). MVP: parent/previousSibling/flags(Random|WarnIfNoChildQuestStarted)/maxConcurrentQuests/maxNumQuestsToRun/hoursUntilReset/conditions(W1 builder)/quests[{quest,hoursUntilReset}]. `fo4_inspect_sm_tree` (mutagen-cli `sm-tree` verb): event-node listele (17 vanilla anchor + type + childCount) / node children — author doğru Parent'ı seçsin (silent-fail önlemi). Ground-truth = DmndSchoolhouseEvents (1BC007/parent 029152). Doğrulama: round-trip + inspect record_type=StoryManagerQuestNode + Spriggit (`StoryManagerQuestNodes/` + quest FormLink + Random). +5 test → 346 pass. **Disk-valid; oyun-içi auto-start = user-gated runtime smoke** (`fo4_run_ingame_test`). **DEFER:** FNAM per-quest flag + node QuestFlags + SMEN/SMBN authoring (yeni event/branch node — MVP mevcut vanilla event node'a parent'lar).
- **Hedef (orijinal):** Event-driven auto-start; SMQN + vanilla event node child (Parent + PreviousSibling). **KRİTİK YOLA EKLENDI (critic major):** auto-start = shippable; en silent-failure-prone faz (yanlış sibling temiz load + Spriggit geçer ama oyun-içi ASLA fire etmez — Faz 2.2 dersinin tekrarı). Smoke İLK item.
- **Deliverables:** `type=smqn` (parent/previousSibling/flags/questFlags/maxConcurrentQuests/quests + W1-run-on koşulları); `fo4_inspect_sm_tree` (Fallout4.esm SM tree yürür — **repo'da DEĞİL**); Event-fill bağımlılığı → W6.7.
- **Yeni tool'lar:** smqn (S), inspect_sm_tree (M) · **Bağımlılık:** W1, W6.5
- **Execution mode:** **dikkatli-sıralı (OUTPUT)** — vanilla node child zinciri sıra-duyarlı.
- **Doğrulama:** vs Remnants `ccOTMFO4001_EncEncounterQuests` (PreviousSibling 1BC007 — disk-doğrulandı, dump'ta `DmndSchoolhouseEvents 1BC007` mevcut).

### W6.5 — Activator (ACTI) + quest control-script *(CRITIC-EKLENDI, critical+major)* ✅ ACTI DONE (2026-06-20)
- **SONUÇ (2026-06-20):** `type=activator` SHIPPED (ACTI base record: name + keywords; flat AddNew). Round-trip + Spriggit (`Activators/` folder) doğrulandı. **GAP (DEFER, roadmap'te zaten işaretli):** ACTI model mesh + VMAD control-script binding (`.psc` + typed-property wiring) — control-script `.pex` Caprica/CK ile derlenir, sonra VMAD bind edilir; quest control-logic (QuestScript/CheckQuestInProgress/QuestCounter/StartAfterCharGenScript) doc-only kaldı.
- **Hedef (orijinal):** (1) SM-start eksik keystone base record: script-bound ACTI trigger (`EncEncounterTrigger` 0004D9 disk-doğrulandı). (2) Main quest 4 control script bind eder (QuestScript + CheckQuestInProgress + QuestCounter + StartAfterCharGenScript) = gerçek quest LOGIC, QF_ fragment'tan ayrı.
- **Deliverables:** `type=activator` (Name/ObjectBounds/model/VMAD/keywords); control-script binding (VMAD var, GAP = `.psc` + typed-property wiring); StartAfterCharGenScript doc (MQ102 1851A0).
- **Yeni tool'lar:** activator (S); control-script (M) · **Bağımlılık:** W4, W6, W1.5
- **Execution mode:** **karma** — ACTI paralel (critic wrong-tag fix: W6'ya absorbe DEĞİL); control-script dikkatli-sıralı.
- **Doğrulama:** vs `Activators/ccOTMFO4001_EncEncounterTrigger` + `Quests/...Quest` VMAD.

### W6.7 — Quest-alias extension: location/collection alias + event-fill *(CRITIC-EKLENDI, major)*
- **Hedef:** W6/W8'in tüketip hiçbir fazın SAHİPLENMEDİĞİ orphan alias-fill işini sahiplen. 3 alias tipi (QuestReferenceAlias/QuestLocationAlias/QuestCollectionAlias) + fill (ForcedReference/External/CreateReferenceToObject/find-in-location/Reserves).
- **Deliverables:** QuestLocationAlias + QuestCollectionAlias; External + CreateReferenceToObject + FindMatchingRefFromEvent event-fill (W6 tüketir); find-in-location (W8 tüketir). V2 "kalan Faz 2.1 surface" buraya promote.
- **Yeni tool:** alias-type + fill (M) · **Bağımlılık:** W1
- **Execution mode:** **dikkatli-sıralı (kaynak)** — alias listesi ordered, ID auto-seq.
- **Doğrulama:** vs Remnants `...Quest` Aliases (her fill mekanizması).

### W7 — AI Packages (PACK) template-override authoring ✅ MVP DONE (2026-06-20)
- **SONUÇ (2026-06-20):** `type=package` template-bind MVP (PackageTemplate + Type[Package/PackageTemplate] + Flags[OffersServices/MustComplete/...] + Conditions[W1 builder] + OwnerQuest + CombatStyle) + **NPC `packages` binding** (npc.Packages — mevcut PACK'i placed NPC'ye bağla = pratik davranış). Round-trip + inspect(record_type=Package). +1 test. **GAP (DEFER — roadmap sert-gate'i korundu):** `Package.Data` input-map (sbyte index → template Public input — yanlış index = sessiz bozuk AI; per-template index-map'in canlı Fallout4.esm template'lerine karşı doğrulanması gerek) + `fo4_inspect_package_template` tool + ProcedureTree/IdleAnimations. Pratik yol şu an = mevcut vanilla package'ı bind et (Data gerektirmez).
- **Hedef (orijinal):** Placed NPC'leri davranır yap; 16 Remnants paketi hepsi template-based. Zor kısım SEMANTIK: Package.Data key = sbyte index template Public input'larına.
- **Deliverables:** `fo4_inspect_package_template` (index→(name,type) map, curated fallback Travel/Sandbox/Guard/UseItemAt/Patrol); `type=package` (template + Data spec validated); package-binding (Npc.Packages + QuestReferenceAlias.PackageData); **DEFERRED:** ProcedureTree/PackageAdapter/IdleAnims.
- **Yeni tool'lar:** inspect_package_template (M), package (M), binding (S) · **Bağımlılık:** W3, W6
- **Execution mode (DÜZELTILDI — iki critic wrong-tag):** **dikkatli-sıralı** — alias.PackageData + Npc.Packages ordered list (sıra=öncelik); index-map zaten sıralı gate.
- **Risk:** Yanlış index = sessiz bozuk AI. **Sert freeze gate:** index map Fallout4.esm canlı template'e karşı doğrulanmadan donmaz. · **Doğrulama:** vs Remnants `Packages/` (Patrol01 ~27-key, SoldiersAmbushPlayer).

### W8 — Locations (LCTN) + LocationReferenceTypes (LCRT) + EncounterZone (ECZN) ✅ DONE (2026-06-20)
- **SONUÇ (2026-06-20):** `type=location` (name/parentLocation/keywords) + `type=locationRefType` (bare) + `type=encounterZone` (flags[NeverResets/MatchPcBelowMinimumLevel/DisableCombatBoundary/Workshop] + location/owner FormLink + minLevel/maxLevel/rank byte) SHIPPED. Hepsi flat AddNew; round-trip + inspect (record_type=Location/LocationReferenceType/EncounterZone) + Spriggit (folder + ECZN flags) doğrulandı. +2 test. **DEFER:** LCTN ref-list alanları (LocationRefTypeReferences*/persistent-unique actor refs/worldspace cells — quest/cell context'inden dolar) + LCRT Color/TNAM.
- **Hedef (orijinal):** Keyword-tagged Location yapısı (find-in-location fill, encounter zone, enable-parent encampment toggle).
- **Deliverables:** `type=location` (EnableParentReferencesStatic → master enable marker, CK-cache boş bırak); `type=locationRefType`; **`type=encounterZone` (ECZN, CRITIC-EKLENDI** — leveled spawn scaling; MVP = vanilla reuse); Cell/PlacedObject Location FormLink kabul eder.
- **Yeni tool'lar:** location (S), locationRefType (S), encounterZone (S) · **Bağımlılık:** W4, W3.5
- **Execution mode:** **paralel-agentic (spec)** — static cache CK-owned. · **Doğrulama:** vs Remnants `EnclaveEncampment01Location` (EnableParent → 000088).

### W8.5 — Door-link (XTEL) + iç-mekân navmesh feasibility spike *(CRITIC-EKLENDI, major)* ✅ XTEL DONE (2026-06-20)
- **SONUÇ (2026-06-20):** placedObject `teleport` alanı (XTEL — `TeleportDestination`: Door FormLink + Position + Rotation) SHIPPED; bir door REFR'i hedef kapıya + spawn noktasına bağlar (yeni interior'ı ULAŞILABILIR yapar). Round-trip (teleportDoor) doğrulandı. +2 test. **Navmesh-spike SONUCU (research gate):** navmesh generation **%100 CK-gated** — NAVI 23-mesh stitch + komşu-mesh corruption + crash riski; Mutagen'de ASLA author edilmez (kilitli kural). Writer `navmesh_handoff` checklist üretir (W12 batch). "Trivial düz-oda navmesh stub" reddedildi (güvenli değil). XTEL = authorable parça; navmesh = CK-gated.
- **Hedef (orijinal):** (1) Yeni iç-mekân door REFR çifti (XTEL) olmadan ULAŞILMAZ — interior↔exterior + NAVI LinkedDoors. (2) Track A DEFAULT'u yeni-iç-mekân ama placed actor navmesh ister → "düz oda navmesh'i CK'sız mı" DEFAULT kritik yolda.
- **Deliverables:** placedObject XTEL {destinationDoor, position, rotation}; **navmesh spike pass/fail gate** (NAVI 000FF1 disk-doğrulandı 23-mesh stitch; **default %100 CK-gated**, trivial-room stub güvenliyse revize).
- **Yeni tool:** XTEL door-link (S); navmesh-spike = research · **Bağımlılık:** W4
- **Execution mode:** **dikkatli-sıralı (OUTPUT door pair) + research-spike.** · **Doğrulama:** vs vanilla door-link çifti + spike notu.

### W9 — Voice + lip pipeline (.fuz/.lip) — silent-subtitled MVP, headless CLI
- **Hedef:** INFO-FormID dosya-adı konvansiyonuyla harici voice/lip bake; tam-oynanabilir SUBTITLED quest silent placeholder ile; gerçek AI-TTS opsiyonel insan/GPU.
- **FEASIBILITY düzeltmeleri (major):** LipGenerator **FonixData.cdf** (6.3MB, disk-doğrulandı) + transcript ister; **silent = KAPALI ağız** (açıkça söyle, "silent'tan gerçek lipsync" İMA ETME); "live proven" → **bu environment'ta tarihli e2e koşusu** ZORUNLU; verify_voice_coverage ayrıca subtitle-duration kontrol eder.
- **Deliverables:** `fo4_bake_voice_assets` (FormID-geri-oku → silent/sourceWav → ffmpeg → LipGen.lip → xWMAEncode.xwm → FUZE pack → `staging/.../Sound/Voice/...`, ASLA game folder); pure-Python FUZE packer; `fo4_verify_voice_coverage`; `fo4_tts_generate` (OPSİYONEL, AGPL isolated).
- **Yeni tool'lar:** bake (M), FUZE packer (S), verify (S), tts (M, opsiyonel) · **Bağımlılık:** W2 + FormID-lock invariant
- **Execution mode:** **dikkatli-sıralı** — .fuz adı FormID gömer, FormID-lock SONRASI çalışmalı.
- **Doğrulama:** tarihli e2e koşusu (FUZE magic ver=1) ZORUNLU; pytest byte-level; coverage subtitle loop.

### W10 — FaceGen export (CK-gated, bounded, opsiyonel)
- **Hedef:** SADECE custom-face bounded NPC seti için baked FaceGen .nif/.dds. Trait-templated NPC (W3) SIFIR ister → en küçük insan-gated vergi.
- **Deliverables:** `fo4_build_facegen` (CKPE batch, dry_run=True default); **default GUI/CK-bound + insan-gated** (FEASIBILITY critic — CKPE full CK process spawn eder, headless DEĞİL); **MVP checklist-only**; lint FormID listesi besler (**W3-probe doğruysa güvenilir**).
- **Yeni tool:** build_facegen (M) · **Bağımlılık:** W3
- **Execution mode:** **kullanıcı-gated** — **W12 CK oturumuna batch'lenir.** · **Doğrulama:** dry_run argv; output staging/; oyun-içi face-render insan.

### W11a — Integration assembly + disk-doğrulama (agent-otomatik, PRE-CK) *(W11 split)* ✅ DONE (2026-06-20)
- **SONUÇ (2026-06-20):** Yeni tool gerekmedi — `fo4_create_record` çoktan multi-record spec'i tek plugin'e kompoze ediyor. **Integration test kanıtladı:** Quest + NPC + interior Cell (NPC içine yerleştirilmiş) + SMQN (quest'i auto-start) TEK spec → TEK plugin; FormID'ler sıralı (0x800+); **intra-spec cross-ref'ler self-mod ref olarak çözülüyor** (cell.placedNpc→NPC, smqn→quest), plugin kendi master'ı olarak EKLENMİYOR (sadece Fallout4.esm). Kilitli kural ("spec paralel, binary serileşir, tek allocator, çok-plugin merge YOK") gösterildi. İki-motor disk verify (mutagen-cli query + Spriggit) zaten her fazda CK-ÖNCESİ çalışıyor. +1 test → suite 352.
- **Hedef (R&S critic critical):** Tüm output'u tek staging plugin'e topla, disk-bug'ları **CK ÖNCE** yakala.
- **Deliverables:** Tek plugin (QUST + dialogue/scene + W2 QSTA + W3 NPC/LVLN/LVLI + W3.5 FACT + W4/W5 ref/cell + W6/W6.5 SMQN/ACTI/script + W6.7 alias-fill + W7 package + W8 location/ECZN + W8.5 door + W9 voice + W10 FaceGen). **Concurrency KİLİTLİ:** spec fan-out paralel, binary-write serileşir (tek FormID allocator), çok-plugin merge YOK (V2). Multi-quest reality: create_record tek spec'te N quest + cross-quest ref (Remnants 15-quest disk-doğrulandı).
- **Yeni tool:** yok · **Bağımlılık:** W2, W3, W3.5, W4, W5, W6, W6.5, W6.7, W7, W8, W8.5, W9
- **Execution mode:** **dikkatli-sıralı (OUTPUT)** — paylaşılan plugin; agent-otomatik.
- **Risk:** FormID-space yarışı → **spec paralel, binary serileşir.** · **Doğrulama:** iki-motor disk verify CK ÖNCE.

### W12 — CK-exclusive batch (navmesh + FaceGen + previs) + FormID-lock *(BATCH'LENDI)*
- **Hedef (R&S critic critical — tek CK oturumu):** Batched CK hesaplamaları + ship-gate. Tüm CK işi tek touchpoint (4→2 oturum).
- **CK sırası (kilitli):** navmesh gen+finalize → **FaceGen (W10 buraya)** → precombine/previs regen.
- **FormID-lock invariant (KİLİTLİ — artık open-question DEĞİL):** `fo4_compact_formids` final voice bake ÖNCE çalışır VE bake her koşuda post-compaction'dan re-derive eder. Sıra: **assemble → compact_formids → bake_voice → verify_voice_coverage → ship.** verify_voice_coverage MANDATORY gate (FormID eşleşmiyorsa build fail).
- **Deliverables:** `fo4_navmesh_handoff` (per-cell CK checklist; writer'da **ASLA NAVM/NAVI author** — NAVI 000FF1 disk-doğrulandı 23-mesh stitch, elle-edit komşu bozar+crash); `fo4_build_previs` (SHIPPED, dry_run); FaceGen (W10); `fo4_release_preflight` (format/previs-impact/ESL/hygiene/BA2/FOMOD verdict compose).
- **Yeni tool'lar:** navmesh_handoff (S), release_preflight (M) · **Bağımlılık:** W11a (NOT W11b)
- **Execution mode:** **kullanıcı-gated** — navmesh/previs/FaceGen CK-exclusive, junction/MO2.
- **Risk:** ORDERING TRAP voice/compaction → invariant KİLİTLİ; BA2 pack-before-finish tavanı. · **Doğrulama:** dry_run → gated run; finalize CK (purple); preflight read-only.

### W11b — Oyun-içi smoke test (insan-gated, POST-CK) *(W11 split, ordering inverted-fix)*
- **Hedef (R&S critic critical — W12 ÖNCE):** Draft `W12 dependsOn W11` ters idi; smoke navmesh/previs/FaceGen olmadan = bug-olmayan "fail" + ikinci smoke. Düzeltildi: assemble (W11a) → CK batch (W12) → tek smoke (W11b).
- **Deliverables:** Smoke checklist, **W6 SM-fire İLK item** (en ucuz sinyal): event-start → NPC path/door → arrow → line (subtitled) → marker → no dark-face → no flicker; bug log → faz geri-besleme; `fo4_validate_navmesh_coverage` (**opsiyonel POST-CK audit** — FEASIBILITY critic: pre-CK navmesh YOK, W11'den kesilip buraya taşındı).
- **Yeni tool:** validate_navmesh_coverage (S, opsiyonel, post-CK) · **Bağımlılık:** W12
- **Execution mode:** **kullanıcı-gated** — **W12 ile aynı sit-down'a batch'lenir** → 2 touchpoint. · **Doğrulama:** oyun-içi smoke (insan).

## 4. Kritik yol + paralel track'ler

**Kritik yol (seri, terminal CK gate'inde biter):**
```
W0 → W1 → W3 → W3.5 → W4 → W5 → W6 → W11a → W12 → W11b
[Track]  [cond] [NPC] [FACT] [KEYSTONE] [override] [SM-start*] [disk] [CK batch] [smoke]
*W6 CRITIC-EKLENDI kritik yola: auto-start = shippable
```

| Track | Fazlar | Doğa |
|---|---|---|
| Quest-logic glue | W1, W1.5, W2, W6, W6.7 | Front-loaded, düşük CK coupling |
| Support data | W1.5 | Saf data, bağımsız record |
| Actors + davranış | W3, W3.5, W7, W8 | NPC base, faction, paket, location |
| World placement | W4, W5, W8.5 | Keystone, **dikkatli-sıralı — kendi içinde paralel DEĞİL** |
| Triggers + control logic | W6.5 | ACTI (paralel) + control-script (sıralı) |
| Assets | W9, W10 | FormID-ordering-coupled |
| CK-gated batch | W12, W11b | Kullanıcı-gated, **tek oturuma batch'lenir** |

## 5. Paralel-agentic vs ekstra-dikkat ayrımı (kullanıcının istediği tablo)

> **Temel kural (KİLİTLİ):** "paralel" = SPEC/research paralel; binary yazma her zaman tek plugin'e serileşir.

| Faz | Mod | Eşzamanlı-yazma tehlikesi |
|---|---|---|
| W0 | kullanıcı-gated | — |
| W1 | dikkatli-sıralı (kaynak) | git merge (binary değil) |
| W1.5 | paralel (spec) | FormID-space (write serileşir) |
| W2 | paralel DISTINCT quest / sıralı tek quest | Tek-quest objective yarışı |
| W3 | karma (in-place=kaynak; LVLN/LVLI=spec) | Source vs FormID-space |
| W3.5 | paralel (spec) | FormID-space |
| W4 | dikkatli-sıralı (OUTPUT) | **Same-CELL child group corruption** |
| W5 | dikkatli-sıralı (OUTPUT) | **Same-CELL Temporary clobber** |
| W6 | dikkatli-sıralı (OUTPUT) | Sibling-chain order corruption |
| W6.5 | karma (ACTI=paralel; script=sıralı) | ACTI FormID-space; script semantic |
| W6.7 | dikkatli-sıralı (kaynak) | Tek-quest alias collection |
| W7 | dikkatli-sıralı (critic-fix) | **Shared ordered parent → nondeterministik precedence** |
| W8 | paralel (spec) | FormID-space |
| W8.5 | dikkatli-sıralı (OUTPUT) + research | Door REFR pair contention |
| W9 | dikkatli-sıralı | FormID-drift → sessiz mute |
| W10 | kullanıcı-gated (CK) | CK requirement |
| W11a | dikkatli-sıralı (OUTPUT) | FormID-space → binary serileşir |
| W12 | kullanıcı-gated (CK) | CK requirement |
| W11b | kullanıcı-gated (oyun) | Oyun-içi gözlem |

**Üç tehlike kategorisi:** (1) **FormID-space sharing** — tek allocator; "paralel" fazlar spec-fan-out + serileşmiş binary-write ile çözer. (2) **Same-CELL contention** — W4/W5/W8.5 child group corruption (error yüzeyi YOK). (3) **CK requirement** — W10/W12/W11b genuinely CK/GPU/oyun-bound.

## 6. Dokümantasyon + ilerleme takip planı

1. **`docs/world-content-quest-roadmap.md`** (bu dosya) = Faz 3 SSOT, faz sınırlarında güncellenir.
2. **`TASKS.md`** `§Aktif` W0..W12 ağacı; CK işi **tek `[!]` entry'de sıralı checklist** (dört değil); `§Best-practice log` (ESL/Track yasası, precombine footgun, FaceGen-avoidance, FormID-vs-voice ordering, FormID-space concurrency); `§Retrospektif` W4/W11a/W12 backward-check.
3. **`research/p0/world-content/<phase>/`** per-faz probe + Spriggit-diff proof signature-freeze ÖNCE (CLAUDE.md §4). **Eksik-tip takibi kapatıldı:** FACT/GLOB/MESG/KYWD/FLST/ACTI/LVLI/ECZN/TERM/NOTE aynı proof zorunluluğuna tabi.
4. **`docs/V2-backlog.md`** `fo4_build_previs` (#13) W12 consumer; tarihli tracked-not-forgotten: ProcedureTree/PackageAdapter/terrain-generator/AI-TTS/SMEN node/**çok-plugin merge**/**TERM+NOTE exposition** (14 TERM + 6 NOTE disk-doğrulandı)/workshop STAT-COBJ.
5. **`tools/MANIFEST.md`** her tool (license: subprocess-isolated, asla dağıtılmaz).
6. **`docs/phase-0-decisions.md`** W0 Track pointer.

**Disiplin:** her tip `_CREATE_SUPPORTED_TYPES` ÖNCE write→reopen + Spriggit-diff vs Remnants; hiçbir signature elle-test komutu olmadan donmaz.

## 7. Açık sorular / kullanıcı kararları (bekleme-noktaları)
1. **TRACK KARARI (W0):** yeni İÇ MEKÂN cell (Track A, ESL) vs yeni WORLDSPACE/exterior (Track B, ESM)? **DEFAULT Track A.**
2. **`fo4_place_into_cell` (W5)** ayrı verb mi create_record'a mı katlanır (boş-Fallout4Mod path regress riski)?
3. **Çok-quest authoring:** create_record tek spec'te N quest + cross-quest ref mi (Remnants 15-quest) yoksa tek-quest MVP + V2 clone-pattern mi?
4. **Coordinate 3D-view'sız (W4/W11b):** ground-truth coord kopyala / düz iç-mekân + insan-gate görsel mi, daha hafif heuristik mi?
5. **Headless CK FaceGen (W10):** reprodüklenebilir mi yoksa GUI+insan mı? **Default: GUI/CK-bound, checklist-only.**
6. **Navmesh stub (W8.5 spike):** güvenli minimal NAVM stub var mı? **Default: %100 CK-gated.**
7. **TERM/NOTE exposition (minor):** roadmap'e tip mi yoksa V2 mi?

> **Artık açık-soru DEĞİL, KİLİTLENDİ:** UseTemplateActors RE (W3-gate), TNAM enum (W4 probe), package index map (W7 gate), FormID-lock vs voice (W12 invariant).

## 8. Incorporated-critique note

**COMPLETENESS:** FACT→W3.5 · ACTI→W6.5 · GLOB/MESG/KYWD/FLST→W1.5 · LVLI→W3 · control-script→W6.5 · alias-domain orphan→W6.7 · W4 NavMeshGenCell verify-target DÜZELTİLDİ · ECZN→W8 · multi-quest→W11a+§7 · TERM/NOTE→V2+§7.

**FEASIBILITY:** navmesh tool çelişkisi → validate_navmesh_coverage W11'den W11b POST-CK'ye · W5 "full" → DOWNGRADE + elle-test gate · precombine kör → check_previs_safety BLOCKING · W3 UseTemplateActors → precondition gate · W9 FonixData+transcript+tarihli-e2e · W4/W7 Patrol/XPRD eklendi · W7 parallel→dikkatli-sıralı · W10 headless→checklist-only · FormID-vs-voice → W12 invariant KİLİTLİ.

**RISK & SEQUENCING:** cross-faz FormID-space yarışı → concurrency KİLİTLİ (spec paralel, binary serileşir) · CK fragmentasyonu → W10→W12 batch (4→2 touchpoint) · W11↔W12 ters → W11a (PRE-CK) / W11b (POST-CK) split · W6 kritik yola eklendi · W9↔W12 ordering → invariant + verify gate · W0 re-litigation → mevcut TASKS.md yasası CITE · W3 careful-tag → kaynak-vs-output contention ayrımı tüm tabloda.

---

**Dosya:** `C:\Modding\docs\world-content-quest-roadmap.md` (committed-ready). Tüm üç adversarial lens'in critical/major/wrong-tag bulguları çözüldü; her feasibility iddiası disk ground-truth (Remnants Cells=tek NavMeshGenCell-override, Factions/Globals×16/Activators/Messages×8/Terminals×14/LVLI/Holotapes mevcut, `Small`/ESL flag, SMQN PreviousSibling 1BC007, NAVI 23-mesh stitch) veya CLAUDE.md §4 reality-check disiplinine zeminlendi.
