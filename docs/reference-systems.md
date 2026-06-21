# Fallout 4 Modding + MCP / Agentic Tooling Reference Inventory

**Araştırma tarihi:** 2026-05-09
**Plan C wave fix-up:** 2026-05-10 — 9 P0 sistem (Mutagen, Spriggit, Synthesis, Papyrus stack, RobCo, SPID-F4, BOS-F4, Buffout/Addictol, CLASSIC) `research/p0/<system>/index.md` altında derinlemesine doğrulandı. Bu belge o dalganın bulgularıyla yamalandı (kritik repo URL düzeltmeleri, 8-eksenli scoring, license alanı, Last verified damgası).
**Session 3 cross-check:** 2026-05-14 — `tools/MANIFEST.md` Nexus Premium API + Steam CK bulk download ile genişledi (14 Nexus mod + MO2 portable + CreationKit 1.11.137 + Papyrus Compiler 2.8.0.4). **Binary path + sha256 için kanonik kaynak artık `tools/MANIFEST.md`'dir**; bu belge yalnız tool kapsam/karar/scoring referansı. Yeni tools (MO2 v2.5.2, CK, Lighthouse Papyrus Extender, Addictol, HUDFramework, MCM, Material Editor, CAO) için ayrı bölüm açılmadı — MANIFEST'te tam YAML var.
**Amaç:** Fallout 4 için MCP tabanlı, skill-driven, agentic mod geliştirme sistemi tasarlarken referans alacağımız resmi/community araçları, SDK/library'leri, build/validation pipeline'larını, runtime patcher'ları, asset araçlarını ve agentic entegrasyon sistemlerini tek dosyada toplamak.

## Plan C dalgası scoring legend

Aşağıdaki 9 P0 sistem girdisinde **Scoring** alanı eklendi. Her eksen 1-5 (yüksek = iyi), istisnalar `risk_level` (low/medium/high) ve `mvp_priority` (5 = MVP must-have).

| Eksen | Anlam |
|---|---|
| automation_friendliness | CLI / deterministic I/O / headless çalıştırılabilirlik |
| documentation_quality | Resmi spec, API ref, örnek kapsamı |
| source_availability | Açık kaynak + erişilebilir + LICENSE netliği |
| maintenance_status | 2026 commit/release aktivitesi |
| fallout4_relevance | FO4'e özgü olgunluk (Skyrim portu vs first-class) |
| mcp_suitability | Subprocess-wrap edilebilirlik, structured output |
| risk_level | low / medium / high — license, NG drift, silent-fail |
| mvp_priority | 1-5; MVP-1 (5), V2 (3), V3+ (1-2) |

## License notu

GPL-3.0 araçlar (**Mutagen, Spriggit, Synthesis, Buffout/Addictol/MiniBuff, RD-SAKR-RCP-Gen**) için MCP entegrasyonu **subprocess-wrap zorunlu** — `fo4-mcp` server'ı bunlarla in-process link kurarsa kendisi de GPL-3.0 olmak zorunda kalır. Caprica = MIT, Champollion = LGPL-3.0 (LGPL ile daha esnek). **RobCo, SPID-F4, BOS-F4, CLASSIC** repo'larında LICENSE dosyası **yok** — Nexus permissions sayfası tek hukuki kaynak; repo fork/redistribute hâlâ "all rights reserved" varsayılır. Generated config `.ini`'lerin bu plugin'leri yeniden dağıtmadığı sürece üretimi güvenli; binary bundling yapma.

---

## Tarih ve güven notu

Bu envanterdeki tarihler üç farklı kaynaktan derlendi:

1. **GitHub repo / release / issue metadata**: GitHub arama ve release sayfalarında görünen en güncel activity veya release tarihleri.
2. **Nexus Mods / Steam / Bethesda Creations metadata**: `Original upload`, `Last updated`, `Created On`, `Last Update` gibi alanlar.
3. **Dokümantasyon veya forum/wiki tarihi**: Resmi release tarihi bulunamadığında, doküman veya public duyuru tarihi.

Her tool için exact `created_at` / `updated_at` API metadata'sı yakalanamadı. Bu yüzden aşağıdaki tabloda **“Oluşturma / ilk yayın”** alanı bazen “repo creation”, bazen “Nexus original upload”, bazen de “ilk public release / doküman tarihi” anlamına gelir. Emin olmadığım yerlerde açıkça **Doğrulanamadı** yazdım.

---

## Öncelik etiketi

| Etiket | Anlam |
|---|---|
| **P0** | MCP MVP için doğrudan gerekli. Text/diff/validate edilebilir ve agentic otomasyona uygun. |
| **P1** | İkinci faz entegrasyonları. Build, packaging, UI, mod manager, asset validation gibi alanlar. |
| **P2** | Güçlü ama riskli/uzmanlık isteyen alanlar: native hooks, animation, previs/precombine, voice synthesis. |
| **REF** | Doğrudan tool olmayabilir ama referans/dokümantasyon olarak gerekli. |

---

# 1. Resmi ve temel Fallout 4 toolchain

| Öncelik | Sistem | Rol | Repo / Link | Developer documentation | Oluşturma / ilk yayın | Son güncelleme | MCP / agentic kullanım notu |
|---|---|---|---|---|---:|---:|---|
| P1 | Fallout 4 Creation Kit | Resmi FO4 mod editor; quest, dialogue, worldspace, NPC, forms, weapons, settlement object authoring | https://store.steampowered.com/app/1946160/Fallout_4_Creation_Kit/ | Official CK site currently unstable; archived/maintained resources: https://fallout.wiki/wiki/Resource:Creation_Kit | Steam release: 2022-04-25 | Steam page current; CK versions vary by FO4 runtime | İlk MCP hedefi olmamalı. CK input/output hazırlama, form/template generation ve validation daha güvenli. |
| P1 | Creation Kit Platform Extended / CKPE | CK için fixes/improvements, stability ve UI/editor patches | https://github.com/Perchik71/Creation-Kit-Platform-Extended ; Nexus FO4: https://www.nexusmods.com/fallout4/mods/51165 | README + Nexus description | Nexus original upload: 2021-04-03 | Nexus last updated: 2026-03-11 | CK kullanan workflow'larda environment check ve version compatibility için takip edilmeli. |
| P0 | Fallout 4 Script Extender / F4SE | FO4 scripting/runtime extension; native plugin ecosystem temeli | https://f4se.silverlock.org/ ; GitHub: https://github.com/ianpatt/f4se ; Nexus mirror: https://www.nexusmods.com/fallout4/mods/42147 | Official site + source headers | Nexus original upload: 2019-11-18 | Latest observed Nexus file activity: 2025-12-16 | MCP environment detector mutlaka FO4 runtime + F4SE version + Steam/GOG ayrımını tespit etmeli. |
| P0 | F4SE Fallout 4 Tools | `ba2extract.exe`, `scriptdump.exe` gibi yardımcı command-line araçlar | https://f4se.silverlock.org/ | Official F4SE tools section | Doğrulanamadı | Current build observed: 0003 | BA2 extraction ve PEX disassembly pipeline'ı için scriptable helper. |
| P0 | Address Library for F4SE Plugins | Runtime address/offset relocation için version-independent ID resource | https://www.nexusmods.com/fallout4/mods/47327 | Nexus description; CommonLibF4 docs/readme | Nexus original upload: 2020-09-10 | Nexus last updated: 2025-12-17 | Native plugin compatibility checker için kritik. DLL mod üretiminden önce dependency check yapılmalı. |

---

# 2. Plugin database, ESP/ESM/ESL, conflict graph ve patch generation

| Öncelik | Sistem | Rol | Repo / Link | Developer documentation | Oluşturma / ilk yayın | Son güncelleme | MCP / agentic kullanım notu |
|---|---|---|---|---|---:|---:|---|
| P0 | xEdit / FO4Edit | Bethesda plugin editor, conflict detector, cleaning, scripting, record inspection | https://github.com/TES5Edit/TES5Edit ; FO4 Nexus: https://www.nexusmods.com/fallout4/mods/2737 | https://tes5edit.github.io/docs/ ; https://tes5edit.github.io/ | FO4 Nexus original upload: 2015 era; exact not reconfirmed | xEdit 4.1.5f released 2024-04-27; repo activity observed 2025-12 | MCP tool: load order read, conflict scan, xEdit script run, cleaning/patch validation. |
| P0 | xEdit Scripts | xEdit automation scripts; Pascal-like scripting workflow | https://github.com/TES5Edit/xEditScripts | xEdit scripting docs: https://tes5edit.github.io/docs/13-Scripting-Functions.html | Doğrulanamadı | Repo activity observed 2025 | Agent can generate/review scripts, but execution must be sandboxed and diff-gated. |
| P0 | Mutagen | Strongly typed C# library for analyzing, modifying and creating Bethesda plugins | https://github.com/Mutagen-Modding/Mutagen | https://mutagen-modding.github.io/Mutagen/ ; Big Cheat Sheet: https://mutagen-modding.github.io/Mutagen/Big-Cheat-Sheet/ | Doğrulanamadı | **Stable 0.53.1 on 2026-02-04; alpha 0.54.0-alpha.87 on 2026-05-01** (verified 2026-05-10) | Ana programatik plugin API adayı. **License: GPL-3.0-only — subprocess-wrap zorunlu.** Scoring: automation 5 / docs 3 (FO4 örnekleri ince) / source 5 / maintenance 5 / fo4 5 / mcp 5 / risk low (GPL + NG schema drift) / mvp 5. |
| P0 | Mutagen.Bethesda.Fallout4 NuGet | Fallout 4-specific Mutagen package | https://www.nuget.org/packages/Mutagen.Bethesda.Fallout4/ | Mutagen docs | NuGet package lineage not fully checked | Stable 0.53.1 / alpha 0.54.0-alpha.87 (verified 2026-05-10) | Plugin schema/type generation ve record-level validation için kullanılabilir. TFM: net8/net9/net10. |
| P0 | Synthesis | Mutagen üstünde code-based patcher framework + GUI | https://github.com/Mutagen-Modding/Synthesis | https://mutagen-modding.github.io/Synthesis/ ; dev docs: https://mutagen-modding.github.io/Synthesis/devs/Configuring-a-Patcher-at-Startup/ ; CLI: https://mutagen-modding.github.io/Synthesis/Synthesis-CLI/ | Doğrulanamadı | **0.35.5 on 2026-02-04; pre-release 0.36.0-pr001 with .NET 10** (verified 2026-05-10) | AI-generated deterministic patcher framework. **License: GPL-3.0 — subprocess-wrap zorunlu.** MO2 USVFS exec olarak çalıştırılmalı. Scoring: automation 5 / docs 4 / source 5 / maintenance 5 / fo4 3 (Skyrim primary) / mcp 5 / risk low / mvp 2 (V2). |
| P0 | Spriggit | Bethesda pluginlerini YAML/JSON text formatına çevirip Git/diff workflow'una sokar | https://github.com/Mutagen-Modding/Spriggit | https://mutagen-modding.github.io/Spriggit/ ; CLI: https://mutagen-modding.github.io/Spriggit/cli/ | Doğrulanamadı | **0.40.1 on 2024-04-24** (verified 2026-05-10; reference doc'taki "0.40.0 / 2025-10-19" GitHub releases page ile tutarsız — GitHub canonical) | Agentic workflow için kritik: text diff, review, rollback, PR. **License: GPL-3.0 — CLI subprocess-wrap zorunlu.** Roundtrip byte-identical garantisi YOK; semantic-identical ve hands-on test gerekli. Scoring: automation 5 / docs 3 / source 5 / maintenance 3 (~13 ay sessiz, issue aktif) / fo4 5 / mcp 5 / risk medium (roundtrip + GPL) / mvp 5. |
| P1 | Wrye Bash | Mod conflict manager, plugin load order manager, Bashed Patch / compatibility workflow | https://github.com/wrye-bash/wrye-bash | https://wrye-bash.github.io/docs/Wrye%20Bash%20General%20Readme.html ; version history: https://wrye-bash.github.io/docs/Wrye%20Bash%20Version%20History.html | Long-running project; exact repo creation not checked | Latest release observed: v314 on 2025-04-05 | Load-order/merge/patch reference. MCP MVP'de doğrudan değil, compatibility knowledge için useful. |

---

# 3. Papyrus scripting, build, compile, decompile ve semantic analysis

| Öncelik | Sistem | Rol | Repo / Link | Developer documentation | Oluşturma / ilk yayın | Son güncelleme | MCP / agentic kullanım notu |
|---|---|---|---|---|---:|---:|---|
| P0 | Pyro | Parallel incremental build system; Papyrus compile, BSA/BA2 packaging, release prep | https://github.com/fireundubh/pyro | https://wiki.fireundubh.com/pyro | Doğrulanamadı | **Last release 2022-07-03; no 2024-2026 release** (stale-but-not-archived; verified 2026-05-10) | MCP build tool için iyi şekil. **License: MPL-2.0.** AE/NG BA2 v7/v8 desteği fixture testi gerektirir. Scoring: automation 4 / docs 3 / source 5 / maintenance 2 / fo4 5 / mcp 4 / risk medium (BA2 NG) / mvp 5. |
| P0 | Papyrus Language Tools / VSCode | Papyrus language server/editor tooling; completion, definition, diagnostics, PPJ tasks | https://github.com/joelday/papyrus-lang ; Marketplace: https://marketplace.visualstudio.com/items?itemName=joelday.papyrus-lang-vscode | Repo docs + marketplace manual | Doğrulanamadı | **v3.2.0 stable 2023-03-15; v3.3.0-prerelease.1 2024-10-04** (verified 2026-05-10) | Agent skill Papyrus source analizinde diagnostics. **`papyrus-debug-server` ARCHIVED 2023-01** — AE/NG runtime debug riskli. License: doğrulanamadı. Scoring: automation 2 (VSCode-bound) / docs 3 / source 5 / maintenance 2 / fo4 5 / mcp 2 / risk medium / mvp 2. |
| P1 | Caprica | Open-source Papyrus compiler; PSC -> PEX | https://github.com/Orvid/Caprica ; Nexus FO4: https://www.nexusmods.com/fallout4/mods/7380 | README + Nexus | Nexus original upload: 2016-04-30 | **v0.3.0 on 2024-10-02 (Starfield support added)** (verified 2026-05-10) | **License: MIT.** Bethesda compiler'dan stricter (`None` coercion yok); ekstra: `Switch`/`For`/`ForEach`/`Break`/`Continue`/Auto-typed locals. Vanilla 7.8k script ~5s. Scoring: automation 5 / docs 3 / source 5 / maintenance 4 / fo4 5 / mcp 4 / risk low / mvp 5. |
| P1 | Champollion | PEX -> PSC decompiler/disassembler | https://github.com/Orvid/Champollion ; Nexus FO4: https://www.nexusmods.com/fallout4/mods/3742 | README + Nexus | Nexus original upload: 2016-04-26 | **v1.3.2 on 2023-10-03; no 2024-2026 release activity** (verified 2026-05-10) | **License: LGPL-3.0** (LGPL → in-process linkleme GPL-3'ten daha esnek). Output structurally equivalent, stylistically lossy (gotos, synthetic vars). Vanilla decompile Bethesda EULA → local-only, gitignore. Scoring: automation 5 / docs 3 / source 5 / maintenance 3 / fo4 5 / mcp 5 / risk low / mvp 5. |
| REF | Open Papyrus resources | Papyrus compiler/decompiler/parser/language tooling kaynak indeksi | https://open-papyrus.github.io/docs/Additional_Resources.html | Same docs site | Doğrulanamadı | Doğrulanamadı | Papyrus AST/lint/refactor toolchain araştırmasında başlangıç indeksi. |
| P1 | Lighthouse Papyrus Extender | Fallout 4 Papyrus extender; additional Papyrus APIs | https://github.com/GELUXRUM/LighthousePapyrusExtender | https://fallout.wiki/wiki/Mod:Lighthouse_Papyrus_Extender | Doğrulanamadı | Doğrulanamadı | Papyrus API symbol index'e dahil edilmeli; runtime dependency checker gerekli. |
| REF | Fallout Wiki Papyrus / CK resources | Papyrus compiler ve CK reference pages | https://fallout.wiki/wiki/Resource:Creation_Kit ; example: https://fallout.wiki/wiki/Resource:Creation_Kit/Papyrus_Compiler | Fallout Wiki | Wiki pages vary | Papyrus compiler page observed updated 2025 | Resmi wiki yerine pratik reference source. Agent retrieval corpus'a eklenebilir. |

---

# 4. Native runtime, C++ plugin SDK'ları ve reverse-engineered API katmanı

| Öncelik | Sistem | Rol | Repo / Link | Developer documentation | Oluşturma / ilk yayın | Son güncelleme | MCP / agentic kullanım notu |
|---|---|---|---|---|---:|---:|---|
| P1 | CommonLibF4 | Reverse-engineered C++ library/resource for F4SE plugin development | https://github.com/Ryan-rsm-McKenzie/CommonLibF4 | README/source headers; formal docs limited | Doğrulanamadı | Doğrulanamadı | Native mod scaffolding ve API search için önemli; otomatik hook generation riskli. |
| P1 | libxse/commonlibf4 | Collaborative modern CommonLibF4 fork | https://github.com/libxse/commonlibf4 | README/source | Doğrulanamadı | Doğrulanamadı | Modern C++ SDK referansı. MCP native tools için daha güncel fork olarak izlenmeli. |
| P1 | commonlibf4-template | CommonLibF4 plugin template; C++23, XMake, spdlog/fmt pattern | https://github.com/libxse/commonlibf4-template | README | Doğrulanamadı | Doğrulanamadı | Agent için native plugin scaffold template. İlk fazda sadece scaffold/build diagnostics önerilir. |
| P2 | X-Cell FO4 | F4SE-based engine optimization/fix layer | https://github.com/Perchik71/X-Cell-FO4 | README/source | Project copyright observed 2024-2025 | GitHub update observed 2026-02-23 | Crash/performance compatibility knowledge için izlenmeli; direct automation riskli. |
| P2 | Mentats - F4SE | Engine-level fixes/patches/warnings; Buffout/X-Cell-compatible ecosystem reference | https://www.nexusmods.com/fallout4/mods/91565 | Nexus description | Nexus observed: 2025-03-08 | 2025-03-08 observed | Crash/debug knowledge base'e eklenebilir. |
| P2 | Addictol | New/experimental bundle combining engine fixes/crash logger style tooling | https://github.com/Dear-Modding-FO4/Addictol | README/source | Nexus observed publish: 2026-04-02 | GitHub org activity observed 2026-05-06 | Experimental; knowledge base'e ekle ama core dependency yapma. |

---

# 5. Runtime / declarative patcher ecosystem

| Öncelik | Sistem | Rol | Repo / Link | Developer documentation | Oluşturma / ilk yayın | Son güncelleme | MCP / agentic kullanım notu |
|---|---|---|---|---|---:|---:|---|
| P0 | RobCo Patcher | F4SE/CommonLibF4 based runtime patcher; plugin oluşturmadan game data değiştirir | https://www.nexusmods.com/fallout4/mods/69798 ; source: https://github.com/Zzyxz/RobCo-Patcher | Nexus description + `object_*.h` headers (header struct ↔ INI key 1:1) + community "RobCo Patcher Repository" cookbook (Nexus 70509) | Nexus original upload: 2023-03-18 | **4.3.5 on 2026-01-29 (NG track); AE alpha through Jan 2026** (verified 2026-05-10) | **License: LICENSE dosyası YOK — Nexus permissions tek hukuki kaynak.** Silent-ignore failure mode (bad config = no log, no crash). No first-party validator → MCP value-add. Scoring: automation 5 / docs 2 / source 4 / maintenance 4 / fo4 5 / mcp 5 / risk low (license medium) / mvp 2 (V2). |
| P0 | RobCo Patcher Repository | RobCo config collection; DLC/CC/AE support, non-invasive/no scripts/no record edits approach | https://www.nexusmods.com/fallout4/mods/70509 | Nexus examples/configs | Nexus original upload: 2023-04-14 | Activity varies | Agent için style/examples corpus. RobCo config lint/generator skill geliştirilebilir. |
| P0 | Spell Perk Item Distributor F4 / SPID-F4 | Startup'ta NPC actorbase'lerine spell/perk/item/keyword/outfit/faction/package distribution | **https://github.com/powerof3/SPID-F4** (DÜZELTME: önceki entry Skyrim repo'su `Spell-Perk-Item-Distributor`'a yönlendiriyordu — Skyrim ve FO4 **ayrı codebase, ayrı binary, syntax 1:1 değil**) ; Nexus FO4: https://www.nexusmods.com/fallout4/mods/48365 ; SPID Complete Reference (community): https://www.nexusmods.com/fallout4/articles/5166 ; active fork: https://github.com/ohois/SPID-F4 | Nexus + community article (README boş) | GitHub repo: 2022-06-04; Nexus original upload: 2020-11-11 | **`powerof3/SPID-F4` master last commit 2025-11-30 ("AE update"); project version 3.1.1; GitHub Releases tab boş** (verified 2026-05-10). **Reference-doc'taki "7.2.1 / 2026-04-03" Skyrim sürümüne aitti — DÜZELTİLDİ.** | Declarative NPC distribution. **License: LICENSE dosyası YOK — Nexus permissions tek hukuki kaynak.** No native validator; FormID < 0x800 silent-drop bug (issue #3). Scoring: automation 5 / docs 2 / source 4 / maintenance 4 / fo4 5 / mcp 5 / risk low (license medium) / mvp 3 (V2). |
| P0 | Base Object Swapper F4 / BOS-F4 | Config-driven base object swap; runtime hook on `TESObjectREFR::InitItem` | **https://github.com/powerof3/BaseObjectSwapperF4** (DÜZELTME: önceki entry Skyrim `BaseObjectSwapper` repo'sunu gösteriyordu — Skyrim **MIT/CommonLibSSE**, FO4 **lisanssız/CommonLibF4**, ayrı codebase) ; FO4 Nexus: https://www.nexusmods.com/fallout4/mods/67528 ; STEP wiki: https://stepmodifications.org/wiki/Fallout4:Base_Object_Swapper | Nexus + STEP wiki (README boş) | GitHub repo: 2023-01-05; Nexus original upload: 2023-01-05 | **`BaseObjectSwapperF4` master last commit 2025-11-20 ("AE update"); CMake 2.2.0; Nexus dist 2.2.1** (verified 2026-05-10) | Object swap via `*_SWAP.ini`. **License: LICENSE dosyası YOK — Skyrim'in MIT'si FO4 portuna devrolmuyor; Nexus permissions tek hukuki kaynak.** Precombine breakage riski (STAT swap'larda); `chanceR/L/S` random pool. Scoring: automation 5 / docs 2 / source 4 / maintenance 4 / fo4 5 / mcp 4 / risk medium (precombine + license) / mvp 2 (V2). |

---

# 6. Asset, mesh, material, body/outfit, archive pipeline

| Öncelik | Sistem | Rol | Repo / Link | Developer documentation | Oluşturma / ilk yayın | Son güncelleme | MCP / agentic kullanım notu |
|---|---|---|---|---|---:|---:|---|
| P1 | NifSkope | NIF mesh viewer/editor | https://github.com/niftools/nifskope ; FO4 resource: https://fallout.wiki/wiki/Resource:NifSkope | https://github.com/niftools/nifskope/wiki | Long-running NIF project; exact not checked | Fallout Wiki page observed updated 2025-06-14 | Asset validator: NIF metadata read, missing shader/material/path checks. |
| P1 | NifSkope Experimental / FO4-focused fork | FO4 material edit/save improvements, experimental NIF workflow | https://www.nexusmods.com/fallout4/mods/91780 | Nexus description | Doğrulanamadı | Doğrulanamadı | Optional reference for FO4-specific NIF handling. |
| P1 | Material Editor | BGSM/BGEM material file editor | https://www.nexusmods.com/fallout4/mods/3635 | Fallout Wiki material reference: https://fallout.wiki/wiki/Resource:Creative_Family_Wiki/Materials_Files | Nexus original upload: 2015-11-29 | Nexus last updated: 2025-01-11 | MCP asset validator: material path/texture flags/shader sanity checks. |
| P1 | BodySlide and Outfit Studio | Body/outfit customization, conversion, creation | https://github.com/ousnius/BodySlide-and-Outfit-Studio ; Nexus FO4: https://www.nexusmods.com/fallout4/mods/25 | README/wiki/community docs | Nexus original upload: 2015-12-24 | Nexus last updated: 2025-07-27 | Outfit pipeline manifest, conversion checklist, generated patch/release validations. |
| P1 | PyNifly | Blender import/export bridge for NIF; FO4 support, Nifly-based | https://github.com/BadDogSkyrim/PyNifly | https://github.com/BadDogSkyrim/PyNifly/blob/main/DEVELOPERS.md | Doğrulanamadı | Release V25.6 observed; exact date not captured | Blender-based asset workflow. MCP skill can produce import/export checklist and validate output paths. |
| P1 | Archive2 | Official Bethesda BA2 archive packer in CK tools | CK tool; guides: https://stepmodifications.org/wiki/Guide:Archive2 ; Nexus article: https://www.nexusmods.com/fallout4/articles/5844 | STEP guide + Nexus article | Official tool age not verified; STEP guide 2021-12-05 | Nexus BA2/Archive2 article observed 2025-05-26 | Release packaging. Must account for post-2024 BA2 format differences. |
| P1 | BSArch / BSArchPro | xEdit archive pack/unpack tooling for Bethesda archive formats | xEdit source: https://github.com/TES5Edit/TES5Edit/blob/dev-4.1.6/BSArch.dpr | xEdit docs/source | Doğrulanamadı | xEdit 4.1.5f observed 2024-04-27 with FO4 NG BA2 v7/v8 support | Scriptable archive extraction/packaging alternative to Archive2. |
| P1 | BSA Browser | Archive browser/extractor for BSA/BA2 | https://github.com/AlexxEG/BSA_Browser ; Nexus FO4: https://www.nexusmods.com/fallout4/mods/17061 | README + Nexus | Nexus original upload: 2016-08-02 | Nexus last updated: 2023-02-06 | Asset discovery and extraction helper. Lower priority than Archive2/BSArch. |

---

# 7. Animation / HKX / behavior ecosystem

| Öncelik | Sistem | Rol | Repo / Link | Developer documentation | Oluşturma / ilk yayın | Son güncelleme | MCP / agentic kullanım notu |
|---|---|---|---|---|---:|---:|---|
| P2 | Fallout 4 Animation Kit / F4AK | FO4 custom animation authoring kit; guide/tools | Nexus: https://www.nexusmods.com/fallout4/mods/16694 ; GitHub: https://github.com/ShadeAnimator/ShadeAnimator_Fallout4_AnimationKit | PDF guide inside kit + README | Nexus original upload: 2016-07-21 | Nexus last updated: 2016-08-27 | Project abandoned/kinda works. Use as historical workflow reference, not core dependency. |
| P2 | HKXAnim | FBX animation -> HKX converter for Fallout 4 | https://github.com/Dexesttp/hkxanim | README | Doğrulanamadı | Doğrulanamadı | Animation conversion reference. Automation risky; start with diagnostics only. |
| P2 | HKXPack | HKX pack/unpack / binary-XML converter optimized for FO4 | https://github.com/dexesttp/hkxpack ; docs/site: https://dexesttp.github.io/hkxpack/ | Site + README | Doğrulanamadı | Release observed: 0.1.6-beta | HKX inspection/conversion reference. Useful for validators before generators. |
| P2 | Animated World Framework | F4SE-based framework for world object interaction animations | https://www.nexusmods.com/fallout4/mods/100946 | Nexus description/posts | Nexus original upload: 2026-02-01 | Nexus last updated: 2026-03-28 | Modern animation framework. Add to knowledge corpus; avoid first-wave automation. |

---

# 8. UI, MCM, HUD, interface framework

| Öncelik | Sistem | Rol | Repo / Link | Developer documentation | Oluşturma / ilk yayın | Son güncelleme | MCP / agentic kullanım notu |
|---|---|---|---|---|---:|---:|---|
| P1 | Mod Configuration Menu / MCM | In-game mod configuration page via pause menu; requires F4SE | https://github.com/reg2k/f4mcm ; Nexus: https://www.nexusmods.com/fallout4/mods/21497 | README + Nexus examples | Nexus original upload: 2017-09-08 | Nexus last updated: 2025-12-16 | Agent can generate MCM config skeleton and check MCM dependency. |
| P1 | HUDFramework | Conflict-free HUD element framework | https://github.com/reg2k/hudframework ; Nexus: https://www.nexusmods.com/fallout4/mods/20309 | README + Nexus | Nexus original upload: 2016-12-14 | Nexus last updated: 2017-03-17 | UI/HUD mod reference. Use for manifest/dependency validation. |
| P1 | F4CF Interface | Unofficial FO4 UI source/interface development kit | https://github.com/F4CF/Interface | README/source | Doğrulanamadı | Doğrulanamadı | AS3/SWF UI workflow reference. Good for UI skill corpus. |
| P1 | F4CF Creation Framework | FO4 UI/Papyrus interface framework | https://github.com/F4CF/Creation-Framework | README/source | Doğrulanamadı | Doğrulanamadı | UI modding framework reference. |
| P1 | LooksMenu | Character creation/morph UI and runtime extensions | https://www.nexusmods.com/fallout4/mods/12631 | Nexus description | Nexus upload observed: 2016-04-30 | Last update observed: 2026-01-17 | Character/morph mods dependency checker and compatibility reference. |

---

# 9. Crash, logs, stability, diagnostics

| Öncelik | Sistem | Rol | Repo / Link | Developer documentation | Oluşturma / ilk yayın | Son güncelleme | MCP / agentic kullanım notu |
|---|---|---|---|---|---:|---:|---|
| P0 | Buffout 4 (OG, Fudgyduff/alandtse) | Engine fixes + crash logger; OG/NG odaklı baseline | Nexus: https://www.nexusmods.com/fallout4/mods/47359 ; alandtse fork: https://github.com/alandtse/Buffout4 | Nexus + Step Modifications wiki: https://stepmodifications.org/wiki/Fallout4:Buffout_4 | Nexus original upload: 2020-09-12 | **alandtse fork v1.37.0 on 2025-03-13** (verified 2026-05-10); OG Nexus page no 2024+ files | Crash log foundation. **License: MIT.** OG 1.10.163 + partial NG 1.10.984. Scoring: automation 4 / docs 3 / source 5 / maintenance 3 / fo4 5 / mcp 5 / risk low / mvp 5. |
| P0 | Buffout 4 NG with PDB support | NG single-DLL with PDB symbol decoding | Nexus: https://www.nexusmods.com/fallout4/mods/64880 (alandtse) | Nexus | — | Active 2024-2026 | **License: MIT.** PDB-aware crash log function names. |
| DEPRECATED | Buffout 4 AE / MiniBuff | AE-only port of Buffout 4 NG | Nexus: https://www.nexusmods.com/fallout4/mods/99911 ; source: https://github.com/TheGamerX20/MiniBuffAE | Nexus | Observed upload: 2026-02-07 | **DEPRECATED 2026: Nexus description "Buffout 4 AE no longer in development; future updates and fixes in Addictol"** (verified 2026-05-10). MiniBuff fork ekosistem tarafından bırakıldı. License: GPL-3.0. MCP parser opportunistic destek; primary değil. |
| P0 | Addictol + AddictolCrashLogger (2026 NG/AE standard) | Buffout 4 NG + X-Cell + Mentats + Escape Freeze + Baka MaxPapyrusOps **birleştirme**; crash logger ayrı binary | Addictol Nexus: https://www.nexusmods.com/fallout4/mods/84214 ; AddictolCrashLogger source: https://github.com/Dear-Modding-FO4/AddictolCrashLogger ; org: https://github.com/Dear-Modding-FO4/Addictol | Nexus + The Midnight Ride (https://themidnightride.moddinglinked.com/bugfix.html) | Nexus observed: 2026-04-02 | **Active 2026 (commits ongoing); recommended 2026 NG/AE standard** (verified 2026-05-10) | **License: GPL-3.0** — subprocess-wrap zorunlu. Multi-runtime FOMOD (OG 1.10.163 + NG 1.10.984 + AE 1.11.191). Buffout 4/NG/AE, Disk Cache Enabler, Escape Freeze ile çakışıyor → kaldırma gerekli. Scoring: automation 4 / docs 2 / source 5 / maintenance 4 / fo4 5 / mcp 4 / risk medium (format drift) / mvp 5. **m4rmz NG kullanıyorsa primary hedef.** |
| P0 | CLASSIC Fallout 4 | Crash Log Auto Scanner and Setup Integrity Checker; scans Buffout logs and files | Upstream (Python/PySide6): https://github.com/GuidanceOfGrace/CLASSIC-Fallout4 ; v9 fork (Rust/C++ native, AI-coding optimised): https://github.com/evildarkarchon/CLASSIC-Fallout4 ; Nexus: https://www.nexusmods.com/fallout4/mods/56255 | PDF readme + dictionary in repo; pattern data: `CLASSIC Data/databases/CLASSIC FO4.yaml` | Nexus original upload: 2021-12-04 | **Upstream Nexus 2026-04-02; fork v9.0.0 on 2026-03-31; previous stable v8.1.0 on 2026-01-07** (verified 2026-05-10) | **License: LICENSE dosyası YOK — repo root 404 — Nexus permissions tek hukuki kaynak.** Output **markdown only** (no JSON), v9 fork `classic-cli.exe` headless binary önerilen subprocess hedef. Scoring: automation 3 / docs 4 / source 5 / maintenance 5 / fo4 5 / mcp 4 / risk low (license medium) / mvp 5. |

---

# 10. LOD, previs, precombine ve world performance

| Öncelik | Sistem | Rol | Repo / Link | Developer documentation | Oluşturma / ilk yayın | Son güncelleme | MCP / agentic kullanım notu |
|---|---|---|---|---|---:|---:|---|
| P2 | PRP / Previsibines Repair Pack | Rebuilt precombined meshes + occlusion/previs data; FO4 performance/visual fixes | https://www.nexusmods.com/fallout4/mods/46403 | Nexus documentation | Nexus original upload: 2020-07-23 | Nexus last updated: 2026-05-04 | Worldspace edits compatibility reference. MCP can warn about precombine/previs risk. |
| P2 | ModernPrecombines | Modern docs/workflow for command-line precombine/previs generation | https://github.com/Diskmaster/ModernPrecombines ; docs: https://diskmaster.github.io/ModernPrecombines/ | https://diskmaster.github.io/ModernPrecombines/Creating_PRP_patches_for_other_mods.html | Doğrulanamadı | Doğrulanamadı | Expert workflow. Do not automate blindly; use guided checklist/diagnostics. |
| P2 | xLODGen / FO4LODGen | xEdit-based object/tree/terrain LOD generator | https://github.com/sheson/xLODGen | https://dyndolod.info/Help/xLODGen ; https://tes5edit.github.io/docs/16-xLODGen.html | FO4LODGen forum history observed 2017 | Doğrulanamadı | LOD generation helper; later-stage build pipeline. |
| P2 | FOLIP / Far Object LOD Improvement Project | Adds missing LODs + xEdit scripts for FO4 LOD generation | https://www.nexusmods.com/fallout4/mods/61884 ; article: https://www.nexusmods.com/fallout4/articles/4162 | Nexus article/instructions | Nexus original upload: 2022-07-04 | Activity observed 2026-02-16 | LOD asset reference and xEdit script workflow. |

---

# 11. Mod managers, load order, deployment, packaging metadata

| Öncelik | Sistem | Rol | Repo / Link | Developer documentation | Oluşturma / ilk yayın | Son güncelleme | MCP / agentic kullanım notu |
|---|---|---|---|---|---:|---:|---|
| P0 | Mod Organizer 2 / MO2 | Virtualized mod manager; profiles, load order, mod isolation | https://github.com/ModOrganizer2/modorganizer ; site: https://www.modorganizer.org/ | Python plugin docs: https://www.modorganizer.org/python-plugins-doc/ ; writing plugins: https://www.modorganizer.org/python-plugins-doc/writing-plugins.html | Long-running project; exact not checked | Latest release observed: 2024-08-04; docs/guides active through 2025 | MCP environment detector should read MO2 profiles, loadorder/plugins and virtualized paths. |
| P1 | MO2 Python Plugin | Python plugin layer for MO2 integration | https://github.com/ModOrganizer2/modorganizer-plugin_python | MO2 Python docs | Doğrulanamadı | Doğrulanamadı | Potential direct integration path if building UI-side helper/plugin. |
| P0 | Vortex | Nexus Mods mod manager; profiles/rules/extensions | https://github.com/Nexus-Mods/Vortex ; Nexus page: https://www.nexusmods.com/site/mods/1 | Wiki: https://github.com/Nexus-Mods/Vortex/wiki ; API package: https://github.com/Nexus-Mods/vortex-api | Long-running project; exact not checked | Vortex 2.0 activity/release notes observed 2026 | MCP environment detector should support Vortex too; extension API if deeper integration needed. |
| P0 | LOOT | Automated load-order sorter for Bethesda games | https://github.com/loot/loot | https://loot.github.io/docs/ ; https://loot.readthedocs.io/ | Long-running project; exact not checked | LOOT 0.29.1 observed 2026-04-18 | Load-order sort / warnings / metadata. P0 for diagnosis. |
| P0 | libloot | Library exposing LOOT metadata/sorting logic | https://github.com/loot/libloot | LOOT/libloot docs | Doğrulanamadı | Latest libloot observed: v0.29.x | MCP backend can call libloot rather than shelling LOOT. |
| P0 | LOOT Fallout 4 Masterlist | Fallout 4 load order metadata | https://github.com/loot/fallout4 | Masterlist schema via LOOT docs | Doğrulanamadı | Observed update activity 2026 | Knowledge base for mod compatibility and sorting metadata. |
| P1 | Bethini Pie | INI editor and performance/settings tool | https://github.com/DoubleYouC/Bethini-Pie-Performance-INI-Editor ; Nexus: https://www.nexusmods.com/site/mods/631 | README + Nexus | Nexus original upload: 2023-09-02 | Nexus last updated: 2026-01-31 | MCP INI sanity checker: archive invalidation, paths, performance settings. |
| P1 | FOMOD docs | FOMOD installer XML documentation/schema reference | https://github.com/GandaG/fomod-docs ; docs: https://fomod-docs.readthedocs.io/ | Same docs | Doğrulanamadı | Doğrulanamadı | Agent can generate/review installer metadata. |
| P1 | Nexus fomod-installer | Nexus implementation/reference for FOMOD installer | https://github.com/Nexus-Mods/fomod-installer | README/source | Doğrulanamadı | Activity observed 2026-03-26 | For packaging/install workflow compatibility. |
| P1 | Mod Installer schema | Community schema work for mod installers | https://github.com/mod-installer/schema | README/schema | Doğrulanamadı | Doğrulanamadı | Optional future packaging abstraction. |
| P1 | Nexus Mods API | Nexus public API for mods/files/games/users metadata | Release note: https://www.nexusmods.com/fallout4/news/13921 | API docs linked from Nexus; SwaggerHub public API docs | Released: 2019-02-11 | API docs currentness not fully checked | Dependency/update checks; avoid scraping when official API can be used. |
| REF | Nexus Mods App | Next-gen Nexus app, but not primary path currently | https://github.com/Nexus-Mods/NexusMods.App | README | Doğrulanamadı | Release activity observed 2026; product direction changed | Treat as non-primary/deprecated relative to Vortex unless requirements change. |

---

# 12. Dialogue, voice, LIP, localization helpers

| Öncelik | Sistem | Rol | Repo / Link | Developer documentation | Oluşturma / ilk yayın | Son güncelleme | MCP / agentic kullanım notu |
|---|---|---|---|---|---:|---:|---|
| P1 | Lazy Voice Finder | Search/play/edit/extract voice assets by dialogue text/voice type; supports FO4 BA2/FUZ | https://www.nexusmods.com/fallout4/mods/24309 | Nexus description | Doğrulanamadı | Posts/activity observed 2024 | Dialogue/voice asset discovery. MCP can build manifest and missing audio checks. |
| P1 | FaceFXWrapper | Generate native LIP files without installing/using CK | https://github.com/Nukem9/FaceFXWrapper | README | Doğrulanamadı | Doğrulanamadı | Dialogue release pipeline. License/CK-code constraints should be reviewed before bundling. |
| P2 | xVASynth / F4VA Synth | AI voice line generation app for game voices | GitHub: https://github.com/DanRuta/xVA-Synth ; Nexus FO4: https://www.nexusmods.com/fallout4/mods/49340 | README + Nexus | Nexus original upload: 2021-01-10 | Nexus last updated: 2023-08-31 | Strong ethical/legal risk. Use only with permission/appropriate voice assets; do not make it default. |

---

# 13. Settlement / Workshop systems

| Öncelik | Sistem | Rol | Repo / Link | Developer documentation | Oluşturma / ilk yayın | Son güncelleme | MCP / agentic kullanım notu |
|---|---|---|---|---|---:|---:|---|
| P1 | Place Everywhere | Workshop placement F4SE plugin; settlement-building utility | https://www.nexusmods.com/fallout4/mods/9424 | Nexus description / hotkey docs | Nexus original upload: 2016-02-02 | Nexus last updated: 2025-12-17 | Dependency/reference for settlement workflow, not direct mod authoring API. |
| P1 | Settlement Menu Manager / SMM | Safe custom workshop menu/category management | https://github.com/cadpnq/fo4-smm ; Nexus: https://www.nexusmods.com/fallout4/mods/24204 | GitHub README + Nexus | Nexus original upload: 2017-05-14 | Nexus last updated: 2020-06-27 | MCP can validate menu injection, categories, uninstall-safety patterns. |
| P1 | SMM Patches | Modern SMM patch collection | https://www.nexusmods.com/fallout4/mods/72254 | Nexus | Nexus original upload: 2023-06-18 | Nexus last updated: 2026-02-13 | Compatibility corpus for workshop menu conflicts. |
| P1 | Workshop Framework | Opens settlement system to mod authors; dynamic settlement/resource/settings changes | Nexus: https://www.nexusmods.com/fallout4/mods/35004 ; Bethesda PC: https://creations.bethesda.net/en/fallout4/details/c4288787-6bd6-4c36-b280-0ec326e9cdfc/Workshop_Framework__PC_ | Nexus + Sim Settlements forum/docs | Created On: 2018-09-28 | Bethesda Creations Last Update: 2026-04-22 | Settlement modding core framework. Agent can validate dependency and add-on patterns. |
| P1 | Sim Settlements 2 Wiki / Addon Toolkit | Settlement add-on creation docs and helper files | Wiki: https://wiki.simsettlements2.com/ ; Addon guide: https://wiki.simsettlements2.com/CreateAddons/GettingStarted ; Toolkit Nexus: https://www.nexusmods.com/fallout4/mods/48521 | Wiki/toolkit PDFs | Toolkit observed: 2020-11-25 | Wiki currentness varies | Rich docs corpus for settlement/quest/building-plan add-ons. |

---

# 14. MCP, skills, agentic clients and integration layer

| Öncelik | Sistem | Rol | Repo / Link | Developer documentation | Oluşturma / ilk yayın | Son güncelleme | MCP / agentic kullanım notu |
|---|---|---|---|---|---:|---:|---|
| P0 | Model Context Protocol / MCP spec | Standard protocol for exposing tools/resources/prompts to AI clients | https://github.com/modelcontextprotocol/modelcontextprotocol | https://modelcontextprotocol.io/specification/2025-11-25 ; SDKs: https://modelcontextprotocol.io/docs/sdk | Public launch observed: 2024-11-25 | Spec versions observed: 2025-06-18 and 2025-11-25 | Core protocol for FO4 MCP server. |
| P0 | MCP Python SDK | Official Python SDK for MCP clients/servers | https://github.com/modelcontextprotocol/python-sdk | README + https://modelcontextprotocol.io/docs/sdk | Doğrulanamadı | Release activity observed 2026-03-24; issues active 2026-05 | Best if FO4 tools are mostly subprocess/file-system wrappers. |
| P0 | MCP TypeScript SDK | Official TS SDK for MCP clients/servers | https://github.com/modelcontextprotocol/typescript-sdk | README + docs | Doğrulanamadı | Release activity observed 2026-04-01; npm observed 2026-03 | Best for Codex/Node tool packaging and cross-platform glue. |
| P0 | MCP C# SDK | Official .NET/C# SDK for MCP | https://github.com/modelcontextprotocol/csharp-sdk | API docs linked in repo; .NET blog: https://devblogs.microsoft.com/dotnet/release-v10-of-the-official-mcp-csharp-sdk/ | v1.0 milestone observed 2026-03-05 | v1.3.0 activity observed 2026 | Interesting because Mutagen/Synthesis are .NET/C#. Could build FO4 MCP directly in C#. |
| P0 | Claude Code Skills | Skill format and `/skill-name` invocation in Claude Code | https://docs.anthropic.com/en/docs/claude-code/skills | Same page | Doğrulanamadı | Docs current as observed 2026 | Create FO4 skills: `/fo4-audit`, `/fo4-robco`, `/fo4-crash-debug`, `/fo4-release`. |
| P0 | Claude Code MCP integration | Claude Code connects to external tools/data via MCP | https://docs.anthropic.com/en/docs/claude-code/mcp | Same page | Doğrulanamadı | Docs current as observed 2026 | FO4 MCP server can be consumed directly by Claude Code. |
| P0 | Claude Code Hooks | Deterministic hooks before/after file edits/tool calls/session events | https://docs.anthropic.com/en/docs/claude-code/hooks ; guide: https://docs.anthropic.com/en/docs/claude-code/hooks-guide | Same pages | Doğrulanamadı | Docs current as observed 2026 | Enforce safety: no Data overwrite, run validation after edits, block unsafe commands. |
| P0 | Claude Code Subagents | Isolated subagents with custom prompts/tool restrictions | https://docs.anthropic.com/en/docs/claude-code/sub-agents | Same page | Doğrulanamadı | Docs current as observed 2026 | Separate agents: plugin analyst, Papyrus compiler, crash triage, release packager. |
| P0 | Claude Code SDK | Programmatic agent SDK with tools/hooks/subagents/MCP/permissions/sessions | https://docs.anthropic.com/en/docs/claude-code/sdk | Same page | Doğrulanamadı | Docs current as observed 2026 | If building higher-level FO4 agent runner, useful. |
| P0 | OpenAI Codex CLI | Local terminal coding agent; reads/edits/runs code in selected directory | https://developers.openai.com/codex/cli | CLI features/reference: https://developers.openai.com/codex/cli/features ; https://developers.openai.com/codex/cli/reference | Doğrulanamadı | Docs current as observed 2026 | Alternative agentic client for FO4 repo workflows. |
| P0 | Codex Agent Skills | Codex reusable workflow skills | https://developers.openai.com/codex/skills | Same page | Doğrulanamadı | Docs current as observed 2026 | Same FO4 skill pack can be adapted to Codex. |
| P0 | Codex Plugins | Bundle skills, app integrations and MCP servers into reusable workflows | https://developers.openai.com/codex/plugins | Same page | Doğrulanamadı | Plugins in Codex observed release note 2026-03-25 | Package FO4 skills + MCP server config as installable plugin. |
| P0 | Codex MCP | Codex MCP server support in CLI and IDE extension | https://developers.openai.com/codex/mcp | Same page | Doğrulanamadı | Docs current as observed 2026 | FO4 MCP server should be compatible with Codex CLI/IDE. |
| P0 | Codex customization | Project guidance + skills + MCP + subagents configuration | https://developers.openai.com/codex/concepts/customization | Same page | Doğrulanamadı | Docs current as observed 2026 | Declare skill dependencies on MCP via Codex config. |

---

# 15. Modding guides / knowledge corpus candidates

These are not necessarily tools, but they are useful retrieval corpora for an agentic system.

| Öncelik | Sistem | Rol | Link | Oluşturma / ilk yayın | Son güncelleme | MCP / agentic kullanım notu |
|---|---|---|---|---:|---:|---|
| REF | The Midnight Ride | Modern Fallout 4 setup/modding guide | https://themidnightride.moddinglinked.com/ | Doğrulanamadı | GitHub topic activity observed 2026-04 | Good baseline for install hygiene, LOOT/MO2, stability setup. |
| REF | Fallout Wiki Resource pages | CK, Papyrus, Material, tool references | https://fallout.wiki/wiki/Category:Resources | Varies | Varies | Good fallback docs corpus because official CK wiki availability fluctuates. |
| REF | Nexus Mods articles/posts | Tool-specific practical workflows | Nexus per-tool articles/posts | Varies | Varies | Use carefully; mark source and age. |
| REF | Sim Settlements wiki/forums | Settlement-specific workflow knowledge | https://wiki.simsettlements2.com/ ; https://simsettlements.com/site/ | Varies | Varies | Specialized settlement/workshop knowledge. |

---

# 16. Recommended MCP server shape for Fallout 4

## Resources

```text
fo4://environment
fo4://runtime/version
fo4://f4se/version
fo4://mod-manager/profiles
fo4://load-order/plugins
fo4://load-order/masters
fo4://plugins/{plugin}/records
fo4://plugins/{plugin}/spriggit-yaml
fo4://papyrus/source-index
fo4://papyrus/compiled-index
fo4://assets/manifest
fo4://assets/missing-paths
fo4://robco/configs
fo4://spid/configs
fo4://crash-logs/latest
fo4://loot/report
fo4://ini/settings
```

## Tools

```text
fo4.detect_environment
fo4.read_load_order
fo4.check_missing_masters
fo4.run_loot_dry
fo4.index_plugin_records
fo4.inspect_conflicts
fo4.spriggit_serialize
fo4.spriggit_deserialize_dry
fo4.synthesis_run_patcher
fo4.xedit_run_script_sandboxed
fo4.papyrus_compile
fo4.papyrus_dependency_graph
fo4.robco_validate_config
fo4.robco_generate_config
fo4.spid_validate_config
fo4.bos_validate_config
fo4.ba2_extract
fo4.ba2_pack_dry
fo4.asset_validate_paths
fo4.material_validate
fo4.crash_scan_classic
fo4.release_package_validate
```

## Prompts / Skills

```text
/fo4-environment-audit
/fo4-plugin-audit
/fo4-conflict-review
/fo4-spriggit-diff-review
/fo4-synthesis-patcher
/fo4-runtime-config-mod
/fo4-papyrus-build
/fo4-crash-debug
/fo4-asset-validate
/fo4-release-package
/fo4-workshop-addon
/fo4-dialogue-release-check
```

---

# 17. Suggested repo layout for our own system

```text
fallout4-agentic-modding/
  README.md
  docs/
    reference-systems.md
    compatibility-matrix.md
    safety-policy.md
    tool-contracts.md
  mcp-server/
    src/
      resources/
      tools/
      validators/
      integrations/
        mutagen/
        synthesis/
        xedit/
        loot/
        papyrus/
        robco/
        spid/
        ba2/
        classic/
    tests/
    fixtures/
  skills/
    fo4-environment-audit/SKILL.md
    fo4-plugin-audit/SKILL.md
    fo4-runtime-config-mod/SKILL.md
    fo4-papyrus-build/SKILL.md
    fo4-crash-debug/SKILL.md
    fo4-release-package/SKILL.md
  codex-plugin/
    agents/openai.yaml
    skills/
    mcp.json
  claude/
    .claude/settings.json
    .claude/skills/
    .claude/hooks/
  examples/
    robco-configs/
    spid-configs/
    synthesis-patchers/
    spriggit-yaml/
```

---

# 18. First-wave implementation recommendation

## MVP 1: Read-only intelligence

- Detect FO4 install path, runtime version, F4SE version.
- Detect MO2/Vortex profile and load order.
- Read plugin list, masters and missing masters.
- Run/read LOOT metadata if available.
- Index Papyrus source files.
- Index RobCo/SPID/BOS config files.
- Parse Buffout/CLASSIC logs.

## MVP 2: Safe generated outputs

- Generate RobCo/SPID/Base Object Swapper config files.
- Generate Papyrus source but compile in dry/isolated output path.
- Generate Synthesis patcher project skeleton.
- Serialize plugin with Spriggit and review text diff.
- Package release into staging directory, never direct overwrite of game Data.

## MVP 3: Controlled execution

- Run xEdit scripts only from allowlisted script directory.
- Run Synthesis patchers in isolated worktree/staging profile.
- Compile Papyrus with explicit source/include/output paths.
- Create BA2 archives only from staging manifest.
- Use hooks to block unsafe shell commands and direct game-folder overwrites.

---

# 19. Risk boundaries for automation

## Do not make default in early versions

- Direct Creation Kit GUI automation.
- Native C++ hook generation without human review.
- Direct writes into Fallout 4 `Data/` without staging and backup.
- Previs/precombine generation without explicit expert workflow.
- Animation/HKX generation as an automatic feature.
- AI voice generation for existing character voices without rights/permission review.

## Always require review/diff

- ESP/ESM/ESL edits.
- Generated Papyrus scripts.
- Generated F4SE/native plugin files.
- RobCo/SPID configs that affect large NPC/race/leveled-list sets.
- BA2 archive generation.
- INI changes.

---

# 20. Data refresh checklist for future passes

For a more exact version of this inventory, run a scripted metadata refresh against:

- GitHub REST/GraphQL: `created_at`, `pushed_at`, latest release, latest tag.
- Nexus Mods API: `created_time`, `updated_time`, current version, files.
- Steam Web/API where available: app release metadata.
- Bethesda Creations page/API if accessible.
- NuGet/npm/PyPI: package latest versions and publish dates.

Candidate refresh outputs:

```text
reference-systems.generated.json
reference-systems.generated.md
compatibility-matrix.fo4-runtime.json
mcp-tool-dependency-lock.json
```

---

# 21. Shortlist: likely core stack for our own FO4 MCP system

| Layer | Preferred first choice | Why |
|---|---|---|
| MCP server language | C# or TypeScript/Python hybrid | C# pairs with Mutagen/Synthesis; TS/Python easier for subprocess glue. |
| Plugin data | Mutagen + Spriggit + xEdit fallback | Strong typing + text diff + existing conflict tooling. |
| Patch generation | Synthesis + generated patcher projects | Deterministic, reviewable, reproducible. |
| Safe runtime mod generation | RobCo Patcher + SPID + Base Object Swapper | Text configs, low binary risk, easy diff/review. |
| Papyrus | Pyro + Papyrus Language Tools + Caprica/Champollion fallback | Compile/build + language semantics + decompile fallback. |
| Load order | LOOT/libloot + MO2/Vortex profile readers | Diagnosis and environment fidelity. |
| Crash/debug | Buffout 4 (OG) + Addictol/AddictolCrashLogger (NG/AE) + CLASSIC | MiniBuff deprecated 2026; Addictol+AddictolCrashLogger NG/AE standardı. Fast user value and practical troubleshooting. |
| Packaging | Archive2/BSArch + FOMOD docs | Releasable mod artifacts. |
| Agentic client | Claude Code skills/hooks/MCP + Codex skills/plugins/MCP | Both support reusable skills and MCP-backed tools. |

