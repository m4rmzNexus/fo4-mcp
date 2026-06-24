# fo4-mcp — Açık Yapı Envanteri & Geliştirme Yol Haritası (2026-06-24)

## 1. Yönetici özeti

fo4-mcp, tek-kişilik bir mod yazarı + geliştirici personası (m4rmz) için kurulmuş, ajan-sürümlü bir FO4 modlama sistemidir: çekirdeği Mutagen + Spriggit + Papyrus authoring üzerine oturur, RobCo değil. Bugünkü durum olgun: 34 MCP aracı / 402 test, kayıt-yazımı ekseni (Faz 0–2.2 + Faz 3 W0–W12) büyük ölçüde tamamlanmış, imza yeteneği olan "diyalog → quest-stage" sistemi P0 (SNAM/script-free SetParentQuestStage) seviyesinde canlıda kanıtlanmış ("Yolcu Kerem" reward-chain), ve sürpriz bir kazanım olarak interior navmesh tersine mühendislikle Mutagen-yazılabilir hale getirilip oyun-içi pathable olarak adversarial-kanıtlanmış. Release/hygiene katmanı da sanılandan olgun: BA2 paketleme, ESL/master flag, save inspect/clean tamamen otonom çalışıyor.

Tamamlananın ötesinde, açık yapıların büyük bölümü **eklemeli (additive), düşük-riskli ve kanıtlanmış bir deseni izleyen** kalemlerdir. En büyük persona boşluğu kayıt-türü kapsamasıdır: WEAP (silah), yaygın dünya temel kayıtları (CONT/DOOR/STAT/LIGH/ALCH), ve COBJ crafting tamamen yok — bu üçü "quest+armor+weapon uçtan uca" hedefini doğrudan bloke ediyor ve hepsi armor/book deseninin birebir aynası. İkinci tema diyalog-omurgasının tamamlanması: INFO Papyrus fragment (TIF VMAD) yazımı, GetIsAliasRef render düzeltmesi + fragment readback, NPC Essential/Protected flag'leri ve quest scaffolder. Üçüncü tema headless kanalların güven-sertleştirmesi: oyun-içi runner ve CK otomasyonu yanlış işi çalıştırırken veya bir crash'ten sonra "başarı" raporlayabiliyor — job-provenance sentinel'leri, crash-log tespiti, ck_run unit testleri ve writer-gerekli test flag'i her diğer iddiayı korur.

Dördüncü tema art/asset pipeline'ının ürünleştirilmesi: BGSM/NIF/collision bugün buggy tek-seferlik staging scriptleri olarak yaşıyor; nif_tri_decode.py kanıtlanmış şekilde bozuk (golden vanilla donor'da çöp veriyor ama "renderable" diyor), make_bgsm.py throw atıyor, ve hiçbiri MCP aracı olarak sarılmamış. Bu sınıf, oyun-başlatmadan, tamamen disk-doğrulanabilir biçimde kapatılabilir — "sessiz görünmeme" (silent no-show) hatalarını yakalayan tam katman budur. Beşinci tema release hygiene kompozisyonu: BA2 doğrulama+adlandırma+sürüm, gerçek TES4 flag okuyan preflight, manifest sha256, ve save-clean copy-back — hepsi zaten gönderilmiş yardımcıların küçük kompozisyonları.

Doğrulama (koda-karşı) sonuçları bu temaları somutlaştırıyor: 12 kalem tek tek koda karşı kanıtlandı. 10'u "confirmed-open" (gerçekten açık, başlamaya hazır), 2'si "partially-done" (yazar yolu var ama test/alan eksik), ve önemli iki düzeltme yapıldı: OS-03 (kupon OBND/AlphaTest) zaten-tamamlandı olarak çürütüldü (disk-kanıtlı), ve birkaç sentez iddiası düzeltildi (LVLI UseAll zaten gönderilmiş, asıl eksik ChanceNone; NPC Aggression/Relations zaten gönderilmiş, asıl eksik npc.Flags + OTFT; COBJ kategorileri FLST değil keyword FormLink'leri).

Son olarak ertelenmiş/araştırma sınırı dürüst tutuluyor: exterior worldspace authoring, PACK procedure trees, headless LOD/FormID-compaction, multi-plugin merge, Ghidra native-RE ve FO4VR gerçek ama somut talep, upstream düzeltme veya aktif native-DLL çalışmasına bağlı — mevcut düz-FO4 quest+armor personası için doğru biçimde kapsam-dışı. Bu oturumun stratejisi: kayıt-türü boşluklarını ve güven-sertleştirmelerini otonom kapatmak; CK/oyun-içi/credential gerektiren her şeyi tek bir minimal kullanıcı dokunuş noktasında toplamak.

## 2. Alt-sistem durum tablosu

| Alt-sistem | Durum | Açık yapı sayısı | En kritik boşluk |
|---|---|---|---|
| Record-authoring core | Büyük ölçüde DONE (22 tür) | ~9 (OS-01,02,06,08,11,15,24,38,43,44) | WEAP + yaygın dünya temelleri (CONT/DOOR/STAT/LIGH/ALCH) + COBJ tamamen yok → uçtan-uca hedefi bloke |
| Quest + Dialogue | P0 SHIPPED, canlı PASS | ~8 (OS-04,05,13,14,16,23,30,37) | INFO TIF fragment yazımı yok (reward-on-line bloke); GetIsAliasRef render bug |
| In-game testing / CK automation | 3 kanal canlı/wired | ~7 (OS-09,10,12,25,29,34,35) | False-positive: yanlış job veya crash sonrası "başarı" raporlanabiliyor |
| Navmesh | Interior DONE + in-game PROVEN | ~3 (OS-26,31,32) | Exterior worldspace navmesh ürünleştirilmemiş (sadece spike) + in-game kanıt yok |
| Coupon pipeline / NIF | P0 DONE (disk-kanıtlı) | ~4 (OS-07,19,28,42) | Art pipeline ad-hoc scriptler; in-game eyeball + display-board showcase açık |
| Art/asset (BGSM/NIF/collision) | Tek-seferlik scriptler | OS-07 (çekirdek) | nif_tri_decode bozuk (yanıltıcı verdict); MCP araç yok |
| Release / hygiene | Daha olgun (otonom yazıcılar) | ~5 (OS-17,18,20,33,40) | BA2 başarı = sadece dosya varlığı; preflight gerçek TES4 flag okumuyor |
| Save-edit | Otonom (read+clean) | OS-33 | apply_cleaned_save copy-back yok (otonom döngü kırık) |
| FO4VR port | Araştırma-tamamlandı, 0 kod | ~2 (OS-22,36) | config.py path-variant farkındalığı yok; ESL verdict yanlış |
| Native-RE (Ghidra) | UNSTARTED (research-only) | OS-41 | Hiç plumbing yok; persona aktif değil |
| Server infra | Temiz, ince FastMCP çekirdeği | ~3 (OS-21,24,45) | tools.py 3949-satır monolith; in-flight feature commit bekliyor |

## 3. Önemli denemeler & başarısızlıklar (kör tekrar etmeyin)

Bu bölüm, hangi yolların denenip neden kapandığını kaydeder — gelecekteki bir ajanın körlemesine geri-regress etmemesi için.

- **Multi-member QuestCollectionAlias round-trip (OS-37)** — Mutagen v0.53.1'de write→reopen son üyeyi phantom 2. alias'a duplike eder (asimetrik ALCS read/write, ID/Name index yok). Writer bunu **bilinçli olarak hard-reject ediyor** (Program.cs:1832, tools.py:1564). Bu audit'te STILL BLOCKED doğrulandı. v0.53.1'de un-reject ETMEYİN; tek aksiyon yeni Mutagen sürümünde re-probe. Workaround (location alias + event-fill) mevcut ihtiyacı karşılıyor.

- **CK Papyrus backend (V2 #1)** — CK bytecode'unun Caprica ile identik olduğu kanıtlandı (sadece kozmetik --asm farkı), backend='ck' tasarımca raise ediyor. "Won't-wire" olarak KAPATILDI. Yeniden bağlamayın.

- **PyNifly collision regenerate** — PyNifly FO4 bhkPhysicsSystem'i yeniden üretirken bozuyor (1572→1684B, bhkNPCollisionObject::CreateInstance'da crash). Çözüm = donor'un collision bloklarını **binary-splice** etmek (splice_collision.py), offline byte-identik kanıtlı. PyNifly'ye collision yeniden-üretmesi için güvenmeyin.

- **nif_tri_decode.py (OS-07)** — Empirik olarak kanıtlandı: golden vanilla donor Money_Prewar.nif'te numTriangles=65535, vertexSize=0xFFFFFFFF (underflow) çıkarıyor ama "VERDICT: geometry renderable" basıyor. Offset walk'u BSVersion 130 için yanlış hizalanmış. Bu decoder'ın HER "invisible" verdict'i güvenilmez; düzeltme golden-file'a karşı RE işidir, doc'un "canonical layout"undan VARSAYILAMAZ.

- **make_bgsm.py (OS-07)** — Template path'i (DN101Note.BGSM) diskte yok, FileNotFoundError atıyor. Deploy edilen BGSM'ler aslında Note.BGSM'den geldi (byte-exact, sadece AlphaTest@0x2a flip'li). Reproducible authoring aracı yok; make_bgsm output'u sanmayın.

- **Tier-3 IsPath* predicates (OS-39)** — 1.11.221'de vfunc'lar CTD atıyor, devre dışı bırakıldı; navtest verdict şu an sadece ham displacement>32'ye dayanıyor. Re-enable, Address Library'den offset pin + C++ rebuild + canlı doğrulama gerektirir.

- **Direct-Steam launch (OS-28)** — FormID index'i 0x0A→0x09 kaydırır. Oyun-içi test her zaman MO2→F4SE üzerinden başlatılmalı, direct Steam değil.

- **publish ≠ build / apphost-vs-dll** — mutagen-cli'de yeni case ekledikten sonra `dotnet build` yetmez; `dotnet publish` gerekir, yoksa MCP eski apphost'u resolve eder ve yeni case **runtime'da sessizce yok** olur. WEAP/COBJ/CONT vb. her yazıcı genişletmesinde bu kritik.

- **Stale paths / repo move** — Repo bir kez C:\Modding'e taşındı; Tier-3 plugin job/diag path'lerini hardcode ediyor (OS-09), bu yüzden bir taşıma sessizce DefaultJob'a düşer ve test "geçer". Provenance sentinel'i bunun panzehiri.

## 4. Açık yapı envanteri (önceliklendirilmiş)

| id | başlık | alan | eksik | yaklaşım | effort | risk | track | öncelik |
|---|---|---|---|---|---|---|---|---|
| OS-01 | WEAP base record authoring | record-core | WEAP case yok (DNAM/model/ammo) | armor branch'ini aynala | M | low | autonomous | 10 |
| OS-02 | CONT/DOOR/STAT/LIGH/ALCH(+INGR) | record-core | Yaygın dünya temelleri yok | book/misc desenini batch'le | L | low | autonomous | 10 |
| OS-03 | Kupon P0 (OBND+AlphaTest) | coupon/core | (zaten-yapıldı) | — | M | low | autonomous | 9 |
| OS-04 | INFO TIF VMAD fragment writer | quest+dialogue | INFO Papyrus çalıştıramıyor | QUST fragment plumbing'i aynala | M | med | autonomous | 9 |
| OS-05 | INFO SNAM round-trip test + conftest | quest/test | SNAM testi yok; conftest yok | dialogue-dump ile assert | S | low | autonomous | 9 |
| OS-06 | Writer yoksa testler gürültülü düşsün | core/test | ~60 test sessiz skip | FO4MCP_REQUIRE_WRITER flag | S | low | autonomous | 8 |
| OS-07 | BGSM writer + offline NIF/collision validators | art pipeline | Buggy decoder, MCP araç yok | golden-file decoder fix → 3 araç | L | med | autonomous | 8 |
| OS-08 | COBJ + workshop recipe | record-core/craft | COBJ/OMOD yok | COBJ (BuildCondition reuse); OMOD gate | L | med | autonomous | 8 |
| OS-09 | Job-provenance + path-desync guard | in-game infra | Yanlış job sessizce "geçer" | uuid sentinel + cmd-count assert | M | med | autonomous | 8 |
| OS-10 | Crash-log tespiti + CK output validation | in-game/CK | CTD = "başarı" raporlanabilir | mtime check + expected_outputs | M | low | autonomous | 7 |
| OS-11 | Glue field genişletme (buttons/ranks/chanceNone) | record-core | MESG/FACT/LVLI minimal | additive field blokları | M | low | autonomous | 7 |
| OS-12 | ck_run unit testleri + CSV parser | in-game/CK infra | ck_run sıfır doğrudan test | synthetic ini fixtures | M | low | autonomous | 7 |
| OS-13 | GetIsAliasRef render fix + fragment readback | quest+dialogue | Spurious FormKey gösterimi | GetParameterTypes ile slot seç | S | low | autonomous | 7 |
| OS-14 | NPC Essential/Protected + OTFT outfit | quest/NPC | npc.Flags hiç set edilmiyor | bitfield + outfit case | S | low | autonomous | 6 |
| OS-15 | TERM/NOTE/holotape + SMEN/SMBN | record-core/world | Exposition + event-node yok | probe→author deseni | M | med | autonomous | 6 |
| OS-16 | INFO chaining (linkTopic/StartScene) | quest+dialogue | Dallanan diyalog yok | SCEN probe önce | M | med | research | 6 |
| OS-17 | BA2 hardening (validate+naming+version) | release | Başarı = dosya varlığı | header-read + name-pattern | M | low | autonomous | 6 |
| OS-18 | preflight gerçek TES4 flag + BA2 | release | Yanlış-flag plugin geçiyor | plan_plugin_format compose | S | low | autonomous | 6 |
| OS-19 | Stale RESUME.md (v2 BOOK design) | docs/coupon | Eski tasarımı anlatıyor | v3 MISC state'e re-author | S | low | autonomous | 5 |
| OS-20 | Manifest existence + sha256 verify | release/infra | "resolved" ≠ var/doğru | resolver'da hash-check | S | low | autonomous | 5 |
| OS-21 | lvli-find MCP surface + timeout audit | server infra | CLI verb sarılmamış | read-only wrapper | S | low | autonomous | 5 |
| OS-22 | FO4VR path-variant + ESL verdict fix | FO4VR | config flat-only | game-variant resolver | M | low | autonomous | 5 |
| OS-23 | fo4_author_quest scaffolder | quest/DX | 3-beat blueprint her sefer | spec scaffolder | L | med | autonomous | 4 |
| OS-24 | tools.py monolith böl (3949 satır) | server infra | Tek dosya regression riski | create_record.py çıkar | L | med | autonomous | 4 |
| OS-25 | MO2/CK concurrency lock + atomic ini | in-game infra | Çakışan run'lar birbirini öldürür | lockfile + os.replace | M | med | autonomous | 4 |
| OS-26 | validate_navmesh_coverage post-CK | navmesh/release | CK sonrası audit yok | handoff wrapper | S | low | autonomous | 4 |
| OS-27 | Real-audio/TTS voice-bake | voice/world | Silent-only | FUZE packer + audio_source | M | med | user-gated | 4 |
| OS-28 | Kupon + collision in-game eyeball | coupon/NIF | P0 sonrası launch yok | tek session additem+placeatme | S | low | user-gated | 4 |
| OS-29 | MO2 CK/F4SE env-check + provisioner | in-game infra | Entries assume ediliyor | ini parse + idempotent append | M | low | user-gated | 3 |
| OS-30 | Kerem uçtan-uca playthrough | quest+dialogue | In-wheel pass kanıtsız | ingame_test + manuel eyeball | M | med | user-gated | 3 |
| OS-31 | Exterior navmesh in-game validation | navmesh | Pathable kanıtı yok | displacement harness | M | med | user-gated | 3 |
| OS-32 | Exterior navmesh ürünleştir + guardrail | navmesh/core | Sadece spike verb'i | AddExteriorNavmesh + master-reject | L | med | user-gated | 3 |
| OS-33 | apply_cleaned_save copy-back | save-edit/release | Saves'e geri-kopya yok | allowlisted carve-out + confirm | M | med | user-gated | 3 |
| OS-34 | build_previs dry_run=False smoke | world/CK | Gerçek run hiç olmadı | minimal plugin + CK | S | low | user-gated | 3 |
| OS-45 | In-flight kupon/loot feature commit | infra/release | 402 iddia, HEAD 393 | green pytest → tek commit | S | low | user-gated | 3 |
| OS-35 | W12 CK-exclusive batch | world/CK | Live CK exec gerekli | tek CK sit-down | L | high | user-gated | 2 |
| OS-36 | FO4VR empirical gates + VR DLL | FO4VR | 4 soru çözülmemiş | staging deploy + C++ retarget | L | high | user-gated | 2 |
| OS-37 | QuestCollectionAlias re-probe | quest (blocked) | Upstream bug | yeni Mutagen'de re-probe | M | med | research | 2 |
| OS-38 | PACK Data multi-input + ProcedureTree | record-core (defer) | Tek input çözülebilir | per-template index map | L | high | research | 2 |
| OS-39 | Tier-3 IsPath* + generic STATE query | in-game (research) | Displacement-only verdict | offset RE + query verb | L | high | research | 2 |
| OS-40 | Headless LOD + FormID-compaction | release (research) | GUI/backend-blocked | CK-headless / native remap | XL | high | research | 1 |
| OS-41 | Ghidra native-RE axis | native RE (research) | Hiç plumbing yok | tools/ghidra + analyzeHeadless | XL | high | research | 1 |
| OS-42 | Display-board auto-fill showcase | coupon/Papyrus (gated) | Tamamen unbuilt | COBJ + pre-placed refs + controller | XL | high | user-gated | 1 |
| OS-43 | Multi-plugin merge / FormID-remap | record-core (defer) | Tek allocator | OS-40 remap engine'iyle birlikte | L | high | research | 1 |
| OS-44 | Exterior worldspace LAND/terrain | record-core (non-goal) | Bilinçli non-goal | ertelenmiş kalsın | XL | high | research | 1 |

## 5. Koda-karşı doğrulama sonuçları

12 kalem koda karşı tek tek doğrulandı. Her biri için: verdict, kanıt, somut plan, dokunulacak dosyalar, test stratejisi.

### OS-01 — WEAP base record authoring · **confirmed-open · ŞİMDİ İNŞA ET**
- **Kanıt:** Create-switch (Program.cs:1350-2645) 25 case içeriyor, hiçbiri `weapon` değil; "Weapon|WEAP" grep'i 0 sonuç. Self-verify round-trip'te `check.Weapons` bloğu yok. Python `_CREATE_SUPPORTED_TYPES` (tools.py:553-554) 22 türde weapon'ı reddediyor (tools.py:971). Mutagen API compiled reflection probe ile doğrulandı: `mod.Weapons.AddNew` armor ile identik; DNAM stats record üzerinde DOĞRUDAN (xEdit'teki nested WeaponData değil): BaseDamage(UInt16), Speed, Reach, MinRange, MaxRange, Capacity(UInt16); FormLink'ler Ammo→IAmmunitionGetter, AttackSound→ISoundDescriptorGetter; enum Weapon.AnimationTypes (Gun/Bow/...). **Solo author bugün silah yapamıyor.**
- **Plan:** RecordSpec'e nullable weapon alanları ekle (BaseDamage/Speed/Reach/Min-MaxRange/AmmoCapacity/Ammo/AttackSound/AnimationType/AttachParentSlots); armor+book aynası `case "weapon"`; self-verify read-back bloğu; `dotnet publish`; tools.py'de tür allowlist + normalizer + `_WEAPON_ANIM_TYPES` frozenset. OMOD/attach-mod authoring kapsam-dışı (TASKS.md backlog).
- **Dosyalar:** Program.cs, tools.py, test_tools_create_record.py
- **Test:** 3-4 unit reject (negatif baseDamage, bad animationType, range ammoCapacity, non-list attachParentSlots) + 1 integration round-trip (vanilla 10mm 0001F279 ammo) `_skip_if_no_writer` gate'li, staging_out'a. Blocker yok.

### OS-02 — Yaygın dünya temelleri (CONT/DOOR/STAT/LIGH/ALCH+INGR) · **confirmed-open · ŞİMDİ İNŞA ET**
- **Kanıt:** Allowlist'te hiçbiri yok; switch'te container/door/static/light/ingestible/ingredient case yok (default Fail 2708). Reflection v0.53.1: tüm türler mevcut; alan shape'leri doğrulandı. Container contents için ContainerEntry/ContainerItem idiom'u zaten NPC inventory'de var (Program.cs:1451). Tek genuinely-yeni alt-builder: ALCH/INGR için EffectSpec.
- **Plan:** STAT/DOOR/LIGH/CONT case'leri (model+keywords+OBND+flags reuse); yeni EffectSpec + BuildEffect helper; CONT için Inventory reuse; LIGH Color erteleneb (System.Drawing surface, MVP-defer); read-back blokları; tools.py allowlist+normalizer; `dotnet publish` + MANIFEST sha256.
- **Dosyalar:** Program.cs, tools.py, test_tools_create_record.py, MANIFEST.md, world-content-quest-roadmap.md
- **Test:** İki-katman: validation reject (CONT item'sız, ALCH baseEffect'siz, LIGH radius range) + real-writer round-trip (her tür, vanilla master FormKey'ler) + fo4_inspect_record cross-check. Blocker yok; tek karar LIGH Color defer (blocker değil).

### OS-03 — Kupon P0 (OBND+AlphaTest) · **already-done · İNŞA ETME**
- **Kanıt:** REFUTED. Fix diskte tam: Program.cs:3304 `short[]? ObjectBounds`, case "misc" 2205-2214 default {-7,-3,0,7,3,4}; tools.py:1939-1955 passthrough; spec value:8 + objectBounds. mutagen-cli.dll mtime > Program.cs; authored esp xxd'sinde 6 MISC OBND non-zero + DATA value 8; BGSM byte 0x2a==0x00. Test `test_create_misc_obnd_nonzero` PASS (skip değil). docs/coupon-pipeline-diagnosis.md SSOT, P0 1-6 diskle eşleşiyor.
- **Plan:** Build işi kalmadı. Opsiyonel: TASKS.md "Son guncelleme"yi 2026-06-23 OBND fix'iyle güncelle; P1 follow-up'ları (fo4_validate_nif) ayrı yapılar (OS-07). Kalan tek item in-game eyeball = OS-28 (user-gated).

### OS-04 — INFO TIF VMAD fragment writer · **confirmed-open · ŞİMDİ İNŞA ET**
- **Kanıt:** INFO build loop (1726-1776) VirtualMachineAdapter'ı HİÇ atamıyor; ResponseSpec'te Fragment alanı yok (3617-3624); dump sadece bool hasFragment (537). QUST/ACTI fragment plumbing'i ÇALIŞIYOR (1934-1955) — birebir aynalanabilir. Reflection: DialogResponses.VirtualMachineAdapter settable; ScriptFragments.Script tipi == BuildScriptEntry'nin döndürdüğü ScriptEntry (doğrudan oturur). FormID-pin endişesi gerçek (TIF adı 8-hex INFO FormID içerir).
- **Plan:** InfoFragmentSpec + ResponseSpec.Fragment; build loop'a adapter set (Version=6/ObjectFormat=2); opsiyonel FormKey pin (new DialogResponses(formKey, release)); QUST summary'ye infoFragmentCount; opsiyonel TIF_<eid>_<8hex>.psc stub (compile decoupled). ExtraBindDataVersion'ı vanilla TIF'e karşı doğrula.
- **Dosyalar:** Program.cs, test_tools_create_record.py, fo4-quest-dialogue-system.md
- **Test:** Negatif (scriptName-eksik, onBegin/onEnd ikisi-de-yok) + round-trip (infoFragmentCount==1) + FormID-pin determinism. In-game reward-on-line kanıtı OS-04 kapsam-dışı (papyrus_build + ingame harness). Risk: med (VMAD binary detayı).

### OS-05 — INFO SNAM round-trip test + conftest · **partially-done · ŞİMDİ İNŞA ET**
- **Kanıt:** SNAM writer tam (tools.py:1438-1465, Program.cs:1766-1772), dialogue-dump readback VAR (535-536), ama SIFIR round-trip test (grep boş). conftest.py yok. **Düzeltme:** "37 redefinition / 21 file" YANLIŞ — gerçekte real_env 6 dosyada, staging_out 4 dosyada, toplam 6 dosya. Binary built (test çalışır, skip değil).
- **Plan:** ÖNCE yüksek-değer yarı: `test_create_quest_info_set_parent_quest_stage` — setParentQuestStage{onEnd:20} + no-SNAM kontrol topic; dialogue-dump subprocess ile setStageOnEnd==20 assert; kontrol için `None` (info.SetParentQuestStage null olur, -1 DEĞİL). SONRA ayrı commit: conftest.py + 6 dosyadan dedup.
- **Dosyalar:** test_tools_create_record.py, conftest.py(yeni), + 5 test dosyası (dedup)
- **Test:** Integration `_skip_if_no_writer` gate'li, bağımsız read-path (dialogue-dump) ile round-trip kanıtı. Effort S, risk low, blocker yok. Dikkat: kontrol assert'i None olmalı.

### OS-06 — Writer yoksa testler gürültülü düşsün · **confirmed-open · ŞİMDİ İNŞA ET**
- **Kanıt:** 61 `_skip_if_no_writer` call-site 3 dosyada + 12 inline skip; FO4MCP_REQUIRE_WRITER grep 0 hit; CI bare `pytest -q` binary kasıtlı yokken yeşil. Binary şu an built (yerel çalışıyor), ama hiçbir enforcement yok → Program.cs serialization regression sessizce iner.
- **Plan:** conftest.py'de `require_or_skip_writer` — env truthy ise `pytest.fail(pytrace=False)`, değilse skip. 3 duplicate `_skip_if_no_writer` body'sini delegate et + inspect/bake guard'larını da. Dev-loop'a `FO4MCP_REQUIRE_WRITER=1 pytest -q` dokümante et. Meta-test (monkeypatch None → flag davranışı). Binary'yi commit ETME (GPL-3.0, gitignored).
- **Dosyalar:** conftest.py(yeni), 5 test dosyası, test_writer_enforcement.py(yeni), CONTRIBUTING.md, TASKS.md, ci.yml(opsiyonel)
- **Test:** Pure-Python meta-test (Skipped vs Failed). Blocker yok; opsiyonel CI job (GPL build dep) policy kararı — dev-loop dokümantasyonunu varsayılan al.

### OS-07 — BGSM writer + offline NIF/collision validators · **confirmed-open · ŞİMDİ İNŞA ET**
- **Kanıt:** Dört alt-iddia empirik doğrulandı: (1) nif_tri_decode golden donor'da çöp (65535/0xFFFFFFFF) ama "renderable" basıyor; (2) make_bgsm template path yok, throw; (3) deploy BGSM'ler Note.BGSM'den byte-exact (sadece 0x2a flip); (4) hiçbir MCP araç yok. Ön-koşullar mevcut: golden donor, 6616-dosya vanilla BGSM kütüphanesi (NoteLowPoly.BGSM dahil), splice_collision.py çalışıyor (CLI, sarılmamış).
- **Plan:** Dependency-ordered: (P1-1) decoder'ı golden Money_Prewar fixture'ına karşı DÜZELT (gerçek RE, doc'tan varsayma); (P1-2) fo4_validate_nif (renderable geo + bound + material chain + AlphaTest-vs-alpha cross-check); (P1-7) fo4_create_bgsm NoteLowPoly preset'inden round-trip; (P1-5) fo4_splice_collision structured diff + byte-equality. **BGEM kapsam-dışı** (farklı tail, golden yok). 3 araç server.py'ye register.
- **Dosyalar:** nif_inspect.py, bgsm.py, collision_splice.py (yeni), server.py, 3 test dosyası, 2 fixture, MANIFEST.md, make_bgsm.py(sil)
- **Test:** Pure-Python (skip-yok). Golden decoder regression (load-bearing), validate verdict'leri, BGSM round-trip + flag-override + staging-gate (PathForbiddenError), splice byte-equality. Risk med (decoder RE). Blocker yok; tüm output staging/fixtures.

### OS-08 — COBJ + workshop recipe · **confirmed-open · ŞİMDİ İNŞA ET**
- **Kanıt:** Switch'te cobj case yok (default Fail 2708); allowlist'te yok. Reuse iddiası doğru: BuildCondition (927) 8 türde paylaşılıyor, COBJ Conditions'a doğrudan oturur. Reflection: mod.ConstructibleObjects.AddNew; CreatedObject/CreatedObjectCounts/Components/Conditions/WorkbenchKeyword/Categories/MenuArtObject. **Düzeltmeler:** menu prop `MenuArtObject` (`MenuArt` değil); created-count bir LİSTE (scalar değil); kategoriler **KEYWORD FormLink'leri** (FLST/CategoryKeyword DEĞİL — bunlar API'de yok).
- **Plan:** `case "constructibleobject"/"cobj"`: CreatedObject+WorkbenchKeyword (REQUIRED), Components loop, Categories keyword loop, Conditions BuildCondition reuse, read-back blok; RecordSpec alanları + CobjComponentSpec; tools.py allowlist+validation. **OMOD ertele** (binary property-modifier value-union, research gate, V2-backlog'a).
- **Dosyalar:** Program.cs, tools.py, test_tools_create_record.py, V2-backlog.md
- **Test:** Python reject'ler (createdObject/workbenchKeyword/components) + real-writer round-trip (vanilla WorkshopWorkbenchKeyword + steel component) + opsiyonel Spriggit 2nd-engine. Risk low. COBJ yarısı tam otonom; OMOD ayrı research kalmalı.

### OS-09 — Job-provenance + path-desync guard · **confirmed-open · ŞİMDİ İNŞA ET**
- **Kanıt:** Plugin path'leri hardcode (main.cpp:54-55); Python cfg.tools_dir'den türetir (264-266); open-fail'de sessizce DefaultJob (123-129), o da qqq atar → false-positive (370). Diag `[job] loaded: N resolves, M cmds` (187-189) basıyor ama Python parse ETMİYOR; jobid/job_confirmed grep 0 hit.
- **Plan:** Plugin: `jobid <token>` verb parse + diag'a echo (additive, eski DLL uyumlu). Python: per-run uuid, ilk data satırı; post-run `[job] loaded:` parse + jobid echo match + cmd-count assert; `job_confirmed` success'e fold; `[job] no job file` → loud fail. **Uyumluluk shim'i:** eski DLL (no `[job] loaded:`) → legacy rule + `job_confirmed:null` + warning; ama `no job file` varsa her zaman fail.
- **Dosyalar:** main.cpp, ingame_test.py, test_tools_ingame_test.py
- **Test:** Pure-Python monkeypatched (no launch): happy-path, no-file false-positive guard (çekirdek), stale-jobid mismatch, count-mismatch. DLL rebuild yerel xmake (MO2 mod folder, Steam Data değil). Python guard önce shim'le iner, sonra DLL redeploy, sonra echo zorunlu kıl.

### OS-10 — Crash-log tespiti + CK output validation · **confirmed-open · ŞİMDİ İNŞA ET**
- **Kanıt:** ingame_test.py sıfır crash handling; Fallout4.exe vanish = exited=True (CTD ≡ clean exit). CK consumer'ları "hang yok" = başarı (previs.py:152, facegen.py:91, seq.py:70); overwrite_new/ckpe_log_tail döndürülüyor ama assert edilmiyor. fo4_analyze_crash_log + parse_crash_log ZATEN var, danışılmıyor.
- **Plan:** In-game: `_newest_crash_after(crash_dir, run_start)` (mtime vs run-başlangıç); fresh crash → success=False + crash_summary (parse_crash_log reuse). CK: run_ck_via_mo2'ye expected_outputs + failure_markers; missing/log_errors → artifacts_ok; consumer'lar fold etsin. Yeni MCP surface yok.
- **Dosyalar:** ingame_test.py, ck_run.py, previs.py, facegen.py, seq.py, 2 test dosyası
- **Test:** Unit (no launch): crash-forces-failure, stale-crash-ignored (mtime gating load-bearing), CK missing-output + ckpe-error. Risk low (mevcut araç reuse, rebuild yok). Canlı CTD kanıtı user-gated ama mtime logic offline coverable.

### OS-11 — Glue field genişletme · **partially-done · ŞİMDİ İNŞA ET**
- **Kanıt:** MESG sadece Description+Name (2106-2117, "MenuButtons deferred"); FACT Name+Flags+Relations (Ranks/VendorValues deferred); LVLI/LVLN chanceNone deferred. Reflection: hepsi writable. **Düzeltme:** UseAll + CalculateForEachItemInCount ZATEN var ve test ediliyor (2364, test:1179) — "UseAll coupon loot'u bloke" iddiası YANLIŞ; gerçek lever **ChanceNone**. MESG'in read-back back-dict'i HİÇ yok (yeni foreach gerekli).
- **Plan:** MVP scope: MESG MenuButtons(+Conditions+MessageBox flag), FACT Ranks(gendered Title)+VendorValues, LVLI/LVLN ChanceNone (0-100 spec → Percent). CrimeValues/EpicLootChance/MaxCount ertele. RecordSpec spec sınıfları + read-back (MESG yeni, FACT/LVLI extend).
- **Dosyalar:** Program.cs, tools.py, test_tools_create_record.py, TASKS.md
- **Test:** Gating (chanceNone range, button-no-text, rank-range) + round-trip (buttonCount==2, rankCount==2, chanceNone==25) + Spriggit cross-check. Mevcut leveled/faction testleri UNCHANGED kalmalı (additive). Risk low.

### OS-12 — ck_run unit testleri + CSV parser · **confirmed-open · ŞİMDİ İNŞA ET**
- **Kanıt:** test_tools_ck_run.py yok; ck_run sadece previs testinde fake'leniyor (gerçek logic test edilmiyor). _read_base_directory/@ByteArray-unwrap/_ck_entry_index/ini-restore-finally sıfır test. _proc_running `name.lower() in out.lower()` FRAGILE substring (ingame_test.py:193-212 exact-field CSV kullanıyor). Modül test-friendly (module-level funcs, lazy imports).
- **Plan:** Shared `parse_tasklist_csv`/`_proc_present` (ingame_test'ten çıkar, _tasklist_ws_mb delegate); ck_run._proc_running'i exact-CSV (/FO CSV /NH) yap. test_tools_ck_run.py: ini fixtures (plain/@ByteArray/missing-CK/missing-base_dir), monkeypatch ShellExecute/tasklist/kill/time → seen→gone/never/hung; ini-restore-on-exception (çekirdek), overwrite-diff, exact-match regression.
- **Dosyalar:** test_tools_ck_run.py(yeni), ck_run.py, ingame_test.py
- **Test:** Pure pytest, no CK launch (b'MZ' stub'lar), sadece tmp_path. run_ck_via_mo2 polling semantics değişmez (sadece predicate). Refactor sonrası tam suite yeşil. Risk low.

### OS-13 — GetIsAliasRef render fix + fragment readback · **confirmed-open · ŞİMDİ İNŞA ET**
- **Kanıt:** Program.cs:543 param1'i koşulsuz Form slot'tan (ParameterOneRecord.FormKeyNullable) okuyor; ama GetIsAliasRef param1 bir Alias = NUMBER slot (Condition.GetParameterTypes ile doğrulandı, probe: ParameterOneNumber=4 iken Record 'Null' render ediyor). Part 2: dump sadece bool hasFragment (537); link/scene (PreviousDialog/StartScene/Topic) okunmuyor. İkisi de doc'ta planned (P3/P4).
- **Plan:** `RenderParam(d, which)` helper — GetParameterTypes ile slot kategorisi (Number/String/Form/None) seç. Program.cs:543'ü değiştir + param2/aliasRunOn/paramType1-2 ekle. INFO projection'a fragment{onBegin/onEnd scriptName/fragmentName} + link/scene (null emit, P4'te aktive). Thin `_dialogue_dump` Python wrapper (_cell_navmesh_list aynası).
- **Dosyalar:** Program.cs, tools.py, test_tools_create_record.py, fo4-quest-dialogue-system.md
- **Test:** PARAM RENDER (GetIsAliasRef param1=='4'/paramType1=='Alias', NOT Null; GetIsID FormKey regression guard), aliasRunOn, link/scene null shape. Part 1 bağımsız+shippable şimdi; fragment-populated assert OS-04'e gated. Risk low.

### OS-14 — NPC Essential/Protected + OTFT outfit · **partially-done · ŞİMDİ İNŞA ET**
- **Kanıt:** npc.Flags HİÇ set edilmiyor (case 1352-1497); reflection: npc.Flags type Npc.Flag (Essential/Protected/Invulnerable/Unique...). `outfit` allowlist'te yok, case yok; mod.Outfits + Outfit.Items doğrulandı. **Düzeltme:** Aggression/Confidence/Assistance/Mood (1403-1427) + Sandbox package binding (1493-1495) + faction Relations (test PASS 917) ZATEN var — iddia 3 REFUTED. Sadece (a) npc flags (b) OTFT eksik.
- **Plan:** RecordSpec.NpcFlags (yeni alan — mevcut Flags Quest/Faction'a ait, collision için ayrı); case npc'ye Enum.TryParse<Npc.Flag> accumulator + read-back `(int)g.Flags`; `case "outfit"` (mevcut Items reuse); tools.py `flags`→`npcFlags` passthrough + outfit branch. Kerem spec'ine `flags:["Essential"]` (showcase wiring, ayrı adım).
- **Dosyalar:** Program.cs, tools.py, test_tools_create_record.py
- **Test:** npc flags (Essential|Protected = 258 bit), bad-flag reject, outfit round-trip (itemCount==1), non-list items reject. Effort S, risk low, blocker yok. İddia 3'ü RE-ADD ETME.

## 6. "Şimdi inşa et" kısa listesi

Bu oturumda otonom, düşük-risk, yüksek-kaldıraçlı kalemler — inşa sırasıyla, her biri 1-paragraf execution sketch ile. Hepsi disk-doğrulanabilir, oyun-başlatmasız, sadece staging/ yazıyor.

**1. OS-05 (INFO SNAM test + conftest) — S/low.** En ucuz, en yüksek-güven kalem; gönderilmiş-ama-test-edilmemiş kritik P0 yolunu kilitler. Önce `test_create_quest_info_set_parent_quest_stage`'i yaz (setParentQuestStage{onEnd:20} + no-SNAM kontrol → dialogue-dump subprocess ile assert; kontrol için `None`). Sonra ayrı commit olarak conftest.py oluştur ve 6 dosyadan real_env/staging_out dedup et. Tam suite yeşil kalmalı. Sonraki tüm yazıcı işlerinin önkoşulu değil ama regression coverage'ı hemen sağlar.

**2. OS-06 (writer-gerekli test flag) — S/low.** İkinci olarak çünkü bundan sonraki her yazıcı genişletmesini (OS-01/02/04/08/11/13/14) sessiz serialization regression'larından korur. conftest.py'de `require_or_skip_writer` helper'ı ekle: `FO4MCP_REQUIRE_WRITER=1` ise skip'i `pytest.fail`'e çevir. 3 duplicate `_skip_if_no_writer` body'sini delegate et. Dev-loop'a `FO4MCP_REQUIRE_WRITER=1 pytest -q` dokümante et. Bir meta-test ekle. Binary commit etme (GPL). Bu, dormant test katmanını gerçek bir guard'a çevirir.

**3. OS-13 Part 1 (GetIsAliasRef render fix) — S/low.** Standalone correctness bug, yazarları bugün yanıltıyor. `RenderParam(d, which)` helper'ı ekle (GetParameterTypes ile slot kategorisi seç), Program.cs:543'ü değiştir, GetIsID FormKey regression guard'ı koy. Part 2'nin read-side projection'ını (fragment/link/scene null-emit) aynı anda ekle — pure additive. Fragment-populated assert OS-04'e gated. Bu, OS-04/OS-16'nın doğrulama yüzeyini de hazırlar.

**4. OS-14 (NPC flags + OTFT) — S/low.** Ucuz bitfield + küçük case; gerçek bir quest soft-lock footgun'unu (Kerem turn-in öncesi ölebilir) kaldırır. RecordSpec.NpcFlags (Flags collision'ı için ayrı alan) + Enum.TryParse<Npc.Flag> accumulator + read-back; `case "outfit"` mevcut Items reuse. İddia 3'ü (Aggression/Relations zaten var) RE-ADD ETME. `dotnet publish` unutma.

**5. OS-01 (WEAP authoring) — M/low.** En yüksek persona değeri: armor bitti, silahlar (uçtan-uca hedefin diğer yarısı) tamamen yok. armor branch'ini birebir aynala (DNAM stats record üzerinde DOĞRUDAN — nested WeaponData değil), tools.py normalizer + `_WEAPON_ANIM_TYPES`, `dotnet publish` + apphost-resolve doğrula. OMOD/attach-mod kapsam-dışı (backlog). 3-4 unit reject + 1 integration round-trip (vanilla 10mm ammo).

**6. OS-11 (glue field genişletme) — M/low.** Merchant/choice-dialog/loot-tuning'i birçok içerik türünde açar. MVP scope: MESG MenuButtons, FACT Ranks+VendorValues, LVLI/LVLN **ChanceNone** (UseAll DEĞİL — o zaten var). MESG için yeni read-back foreach gerekli. Mevcut leveled/faction testleri UNCHANGED.

**7. OS-04 (INFO TIF VMAD fragment) — M/med.** Diyalog-omurgasını tamamlar (projenin imza yeteneği). QUST fragment plumbing'ini (1934-1955) aynala: InfoFragmentSpec + adapter set + opsiyonel FormID-pin + QUST summary'ye infoFragmentCount. ExtraBindDataVersion'ı vanilla TIF'e karşı doğrula. Metadata + round-trip şimdi gönder; in-game reward-on-line kanıtını ingame harness'a ertele. Med risk (VMAD binary).

**8. OS-02 (CONT/DOOR/STAT/LIGH/ALCH+INGR) — L/low.** Batch'lenebilir, kısmi teslim değerli. book/misc desenini her tür için aynala; yeni EffectSpec (ALCH/INGR için tek genuinely-yeni builder); CONT için Inventory reuse; LIGH Color MVP-defer. `dotnet publish` + MANIFEST sha256.

**9. OS-08 (COBJ) — L/med.** Settlement crafting'i açar, display-board showcase'in gating bağımlılığı. `case "constructibleobject"/"cobj"` BuildCondition reuse'la; **MenuArtObject** (MenuArt değil), CreatedObjectCounts liste, Categories **keyword FormLink'leri** (FLST DEĞİL). OMOD ayrı research gate.

**10. OS-09 + OS-10 (in-game/CK güven-sertleştirme) — M/low-med.** Beraber yapılır. OS-09: uuid sentinel + cmd-count assert (Python guard shim'le önce, sonra DLL echo); OS-10: crash-log mtime check + CK expected_outputs. İkisi de headless kanalların false-positive sınıfını kapatır — her diğer in-game iddiasını korur. fo4_analyze_crash_log reuse.

OS-07 (BGSM/NIF/collision validators, L/med) ve OS-12 (ck_run testleri, M/low) bu listeden sonra gelir — ikisi de otonom-güvenli ama decoder-RE (OS-07) ve daha geniş test-yazımı (OS-12) effort'u yukarıda. OS-17/18/19/20/21 (release/docs hygiene, S-M/low) ara dolgu olarak herhangi bir noktada eklenebilir.

## 7. Kullanıcı-gated & araştırma kalemleri

Bu kalemler m4rmz'in kararını, GUI'sini, credential'ını veya daha fazla araştırma gerektiriyor — otonom shortlist'e GİRMEZ.

**Tek CK/oyun-içi oturumda toplanacak doğrulamalar (kullanıcı dokunuş noktaları minimize):**
- **OS-28** (S/low) — Kupon in-game eyeball + collision-splice in-engine. MO2→F4SE launch (direct Steam DEĞİL, FormID 0x0A→0x09 kayar), `player.additem 0A000800` + `player.placeatme 0A000800`. OS-03 indikten sonra. İki eyeball tek session.
- **OS-30** (M/med) — Kerem uçtan-uca: in-wheel accept/turn-in stage hareketi, clean-new-game SEQ auto-start, 3 human-eyeball (wheel topics, FaceGen, armor render). W11b post-CK smoke ile batch.
- **OS-31** (M/med) — Exterior/isolated-worldspace navmesh in-game pathable kanıtı (~10 launch). OS-32'yi greenlight eder.
- **OS-34** (S/low) — build_previs dry_run=False ilk gerçek smoke. W12 sit-down'a batch.
- **OS-35** (L/high) — W12 CK-exclusive batch: exterior navmesh + previs + SEQ + FaceGen + FormID-lock. Tüm support araçlar gönderilmiş; kalan iş genuine CK-GUI-bound + GPU FaceGen. W10/W11b/OS-34'ü tek sit-down'a konsolide et. Live game-Data write (high risk).

**Config/credential/deploy kararı gerektiren:**
- **OS-29** (M/low) — MO2 CK/F4SE env-check + provisioner. ini-write confirmation gerektirir; read-only env-check yarısı daha erken gönderilebilir.
- **OS-33** (M/med) — apply_cleaned_save copy-back. safety.py'de user-save space'e bilinçli carve-out (destructive, confirm-gated).
- **OS-45** (S/low) — In-flight kupon/loot commit. Mekanik basit ama commit explicit user-gated (policy: sadece istenince). OS-03/05/06 indikten sonra green state'i yakalar.
- **OS-27** (M/med) — Real-audio/TTS voice-bake. FUZE packer + coverage gate otonom; gerçek .lip generation human/GPU/TTS-gated.
- **OS-36** (L/high) — FO4VR empirical gates + Tier-3 VR DLL rebuild. Live VR launch (Steam opt-in deploy) + high-risk C++ retarget + VR struct hand-RE. OS-22'ye bağlı.

**Araştırma frontier'ı (somut talep/upstream-fix/aktif native-DLL çalışması bekliyor):**
- **OS-16** (M/med) — INFO chaining; SCEN probe önce (medium-confidence). OS-04/OS-13 sonrası.
- **OS-37** (M/med) — QuestCollectionAlias re-probe; sadece yeni Mutagen sürümünde watch-item, build değil. v0.53.1'de un-reject ETME.
- **OS-38** (L/high) — PACK Data multi-input/ProcedureTree; silent-AI footgun, template-bind pratik ihtiyacı karşılıyor; ROI somut talebe gated.
- **OS-39** (L/high) — Tier-3 IsPath* re-enable + generic STATE query channel; runner'ı gerçek assertion engine'e yükseltir ama C++ rebuild + offset RE + live validation.
- **OS-40** (XL/high) — Headless LOD + FormID-compaction; backend/GUI limitleri, native Mutagen-remap stratejik long-term bahis (license/correctness riski). Mevcut safe-gating fallback çalışıyor.
- **OS-41** (XL/high) — Ghidra native-RE; persona düz quest+armor yaparken idle, sadece aktif native-DLL/own-RE goal'üyle değerli. crash-decompile en düşük-risk giriş.
- **OS-42** (XL/high) — Display-board auto-fill showcase; capstone, OS-03/07/28 hardening + OS-08 COBJ'a bağlı, in-game/CK validation.
- **OS-43** (L/high) — Multi-plugin merge; somut talep yok, core remap engine OS-40 ile örtüşür, beraber inşa edilmeli.
- **OS-44** (XL/high) — Exterior LAND/terrain; bilinçli non-goal ("override existing cells"). Tamlık için listelendi.
- **OS-22** (M/low) — FO4VR path-variant + ESL verdict fix; düşük-risk pozitif-keşif + yanlış-verdict düzeltmesi, OS-36'yı unblock eder ama düz-FO4 personasına ikincil.

## 8. Önerilen sıralama

**Bu oturum (otonom, disk-doğrulanabilir, oyun-başlatmasız):**

Sıra, güven-sertleştirme önce → yazıcı genişletme sonra mantığını izler, çünkü OS-06 sonrasındaki her yazıcı işi regression-korumalı olur:

1. **OS-05** (SNAM test + conftest) — kritik P0 yolunu kilitle, fixture dedup
2. **OS-06** (writer-gerekli flag) — bundan sonraki tüm yazıcıları koru
3. **OS-13 Part 1** (GetIsAliasRef render) + Part 2 read-side projection — standalone bug fix + OS-04 doğrulama yüzeyi
4. **OS-14** (NPC flags + OTFT) — soft-lock footgun kaldır
5. **OS-01** (WEAP) — en yüksek persona değeri, uçtan-uca hedefin diğer yarısı
6. **OS-11** (glue field genişletme, ChanceNone dahil) — merchant/dialog/loot tuning
7. **OS-04** (INFO TIF fragment) — diyalog-omurgasını tamamla
8. **OS-09 + OS-10** (in-game/CK güven-sertleştirme) — false-positive sınıfını kapat
9. **OS-02** (CONT/DOOR/STAT/LIGH/ALCH) — batch'lenebilir dünya temelleri
10. **OS-08** (COBJ) — settlement crafting + display-board gating

Ara dolgu olarak herhangi bir noktada: **OS-19** (stale RESUME.md re-author), **OS-20** (manifest sha256), **OS-21** (lvli-find wrapper + timeout audit), **OS-17/18** (BA2 hardening + preflight TES4 flag). **OS-07** (BGSM/NIF validators) ve **OS-12** (ck_run testleri) bu oturumda yer varsa; decoder-RE ve geniş test-yazımı effort'u nedeniyle yazıcı genişletmelerinden sonra.

**Sonraki oturum / kullanıcı sit-down'ları:**

- **Tek CK/oyun-içi oturum (W12 batch):** OS-28 + OS-30 + OS-31 + OS-34 + OS-35'i konsolide et. m4rmz'in tek makine-locked sit-down'ı; navmesh→FaceGen→previs locked order. Bu oturum exterior navmesh ürünleştirmeyi (OS-32) greenlight eder ve Kerem demosunu kapatır.
- **Commit penceresi:** OS-05/06 (+ inen yazıcılar) yeşil ve tutarlı olunca **OS-45** (in-flight feature commit) kullanıcı talebiyle.
- **Sırada bekleyen ürünleştirme:** OS-32 (exterior navmesh, OS-31 PASS sonrası), OS-29 (MO2 env-check, ini-write onayıyla), OS-33 (apply_cleaned_save carve-out).

**Aktif çalışmaya bağlı (somut talep gelene kadar register'da bekler):** OS-16, OS-22/OS-36 (FO4VR), OS-23 (scaffolder — alttaki yazıcılar OS-04/13/14/16 indikten sonra), OS-24 (monolith split — OS-06 round-trip'leri non-skippable yaptıktan sonra en güvenli), OS-25 (concurrency lock), OS-27 (TTS), OS-42 (display-board).

**Pür research / non-goal (inşa etme, watch/dokümante et):** OS-37 (re-probe watch-item), OS-38/39/40/41/43/44.

Net yön: bu oturumda 10 otonom kayıt-türü + güven-sertleştirme kalemini sırayla inşa et (hepsi armor/book deseninin aynası, düşük-risk, staging-only); tüm CK/oyun-içi/credential işini tek bir W12 sit-down'da topla; FO4VR ve native-RE'yi somut talep gelene kadar dürüstçe register'da beklet.