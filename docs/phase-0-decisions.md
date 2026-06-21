# Phase 0 Decisions — Fallout 4 Agentic Modding

**Tarih:** 2026-05-10 (Karar 1-6), genişletme 2026-05-14 (Karar 7)
**Session:** 1 (handoff prep, repo seed, Phase 0 close); Session 3'te Karar 7 formalize edildi
**Durum:** TÜM KARARLAR ÇÖZÜLDÜ (Karar 1-6: 2026-05-10; Karar 7: 2026-05-14). Phase 0 tamamen kapalı.

Phase 0, research'in geri kalanını şekillendiren foundational kararlar içerir. Bu dosya hangi kararın çözüldüğünü, hangisinin açık olduğunu ve önerilen default'ları kayıt altına alır.

---

## Karar 1 — Artifact repo'sunun konumu

**Durum:** ÇÖZÜLDÜ
**Cevap:** `C:\Modding\`

**Rasyonel:**
Steam doğrulamalı oyun klasörü (`C:/Program Files (x86)/Steam/steamapps/common/Fallout 4/`) artifact repo'su olamaz çünkü:
- Steam "Verify integrity of game files" çalıştırıldığında buraya eklenen her şey silinir
- Game folder izinleri Program Files altında — bazı işlemler UAC gerektirir
- Git repo'su game folder'da yaşamamalı (binary asset bloat, accidental commit risk)

`C:\Modding\` bağımsız, yazılabilir, Steam'den izole. Reference dökümanlar bu klasöre kopyalanır (Steam folder'a bağımlılık kalmaz).

**Kullanım kuralı:**
- `C:\Modding\` = ALL writes, repo, generated outputs, staging
- Steam game folder = READ-ONLY (Mutagen/Spriggit data source, INI lookup, plugin enumeration)
- Kullanıcı `Documents/My Games/Fallout4/` = READ-ONLY (load order, prefs, kullanıcı INI'leri)
- `%LOCALAPPDATA%/Fallout4/` = READ-ONLY (plugins.txt, loadorder.txt, crash logs)

---

## Karar 2 — Hedef kullanıcı persona

**Durum:** ÇÖZÜLDÜ
**Cevap:** **A (Mod author) — solo developer, MO2 user, end-to-end authoring (quest + armor), kendi DLL'lerini yazmaya açık**

**Kullanıcı sözü (2026-05-10):** "Mod Organizer 2 kullanıyorum - solo developer'im farklı modlar yapmak istiyorum agentic workflow'lar ile çalışmak için var olan tüm tool'ları toplayıp gerekirse kendi dll'lerimi alacağım. Amaç a'dan z'e senle beraber questler - armor'lar vb yapmak."

**Net özellikler:**
- Mod manager: **MO2** (Vortex değil) — şu an henüz kurulu değil, ileride eklenecek; tool MO2-aware ama vanilla `%LOCALAPPDATA%/Fallout4/plugins.txt` fallback şart
- Single user, kendi modları için
- Hedef: end-to-end authoring — sadece config patcher değil, ESP + Papyrus + asset pipeline tam
- Native plugin (CommonLibF4 / F4SE DLL) yolda — V2/V3 hedefinde, riski kullanıcı üstleniyor

**Etki:**
- C (Developer SDK) yönünden A (Mod author) yönüne pivot — RobCo/SPID/BOS declarative patcher çekirdekten kenara, Mutagen + Spriggit + Papyrus authoring çekirdeğe
- CK GUI automation hâlâ P2 risk listesinde — ama gerekirse kapı açık
- UI insan-için (kullanıcının kendisi), AI-değil-için

---

## Karar 3 — MVP tool listesi

**Durum:** ÇÖZÜLDÜ
**Cevap:** Karar 2 = A (mod author) sonrası revize edilen 6 tool'lu set onaylandı.

**MVP 6 tool (quest + armor authoring odaklı):**

1. **`fo4_get_environment`** — FO4 install path, runtime version, F4SE varsa version, **MO2 detection** (portable mı, instance dir nerede), MO2 yoksa vanilla fallback
2. **`fo4_read_load_order`** — MO2 active profile + `%LOCALAPPDATA%/Fallout4/plugins.txt` birleşik okuma; CC ESM ↔ ESP ayrımı; LOOT/libloot ileride
3. **`fo4_inspect_record`** — Mutagen ile record query; **ARMO / QUST / DIAL+INFO / LVLI** öncelikli (armor + quest authoring için); diğer record type'lar V2'ye
4. **`fo4_spriggit_export` + `fo4_spriggit_import`** — ESP ↔ YAML/JSON roundtrip; **versiyon kontrolü için kritik** (binary ESP git'lenemez, YAML git'lenir)
5. **`fo4_papyrus_build`** — Pyro ile script compile + lint; hata raporu structured
6. **`fo4_analyze_crash_log`** — Buffout/MiniBuff log parse; FormID → plugin mapping (CLASSIC tarzı); iterasyon sırasında kritik

**V2'ye itilen (Phase 0'da çekirdek değil):**
- `fo4_generate_robco_config`, `fo4_generate_spid_config`, `fo4_generate_bos_config` — declarative runtime patcher'lar; quest/armor authoring'in çekirdeğinde değil, ama tool kutusunda kalır
- `fo4_check_missing_masters`, `fo4_validate_load_order` — load order doğrulama
- `fo4_pack_ba2` — BA2 paketleme
- `fo4_render_nif_thumbnail` — asset preview

**V3'e itilen:**
- CommonLibF4 / F4SE plugin scaffolding (kullanıcı kendi DLL'lerini yazma yolunda; tool sonra)
- CK automation (P2 risk listesi)

---

## Karar 4 — Safe-write boundary

**Durum:** ÇÖZÜLDÜ (kural set; hook enforcement sonraki session'da)

| Kategori | Path | İzin |
|---|---|---|
| READ-ONLY | `C:/Program Files (x86)/Steam/steamapps/common/Fallout 4/` | Read |
| READ-ONLY | `%USERPROFILE%/Documents/My Games/Fallout4/` | Read |
| READ-ONLY | `%LOCALAPPDATA%/Fallout4/` | Read |
| READ-ONLY referans (MO2 ileride kurulduğunda) | MO2 instance `mods/`, `profiles/`, `overwrite/` | Read; deployment ise diff-gated |
| WRITE OK (no diff gate) | `C:\Modding\staging\` | Write generated outputs |
| WRITE OK (no diff gate) | `C:\Modding\research\` | Write research outputs |
| WRITE only with diff+approval | `C:\Modding\fixtures\*.yaml` (Spriggit) | Write |
| WRITE only with diff+approval | `C:\Modding\staging\*.psc` (Papyrus) | Write |
| WRITE only with diff+approval | `C:\Modding\staging\*.ini` (RobCo/SPID/BOS configs) | Write |
| YASAK | `Data/*.esp`, `Data/*.esl`, `Data/*.esm`, `Data/*.ba2` overwrite | Forbidden |
| YASAK | `Fallout4_Default.ini` overwrite | Forbidden |
| YASAK | `Fallout4.ccc`, `Fallout4IDs.ccc` modify | Forbidden |
| YASAK | Steam game folder içinde herhangi bir dosya yaratma/silme | Forbidden |

**Mevcut kurulum durumu (Session 1 sonu):** Kullanıcının Steam üzerinden FO4 install'ı var, MO2 henüz kurulu değil. `fo4_get_environment` MO2'yi detect edemezse vanilla fallback'e düşer (Documents + LOCALAPPDATA okur).

**Uygulama:** Claude Code hooks (PreToolUse) ile path check. Sonraki session'da `.claude/settings.json` içinde tanımlanmalı.

---

## Karar 5 — Tek server vs modüler server ailesi

**Durum:** ÇÖZÜLDÜ
**Cevap:** Tek server ile başla (`fo4-mcp`). MVP sonrası split tetikleyiciler aşağıda.

**Rasyonel:**
- 5 tool'lu MVP tek server için fazlasıyla uygun
- MCP client (Claude Code/Codex) namespacing'i ile gruplama yeterli (tool isimleri `fo4_*` ile prefix'li)
- Modüler aile (`fo4-context-mcp`, `fo4-plugin-mcp`, ...) overhead'e değecek complexity threshold'una MVP'de ulaşmaz

**Split tetikleyicileri (MVP sonrası):**
- Tool sayısı 12+ olunca
- Farklı runtime gereksinimi doğunca (örn. Mutagen .NET ayrı process; Pyro Python; CLASSIC Python)
- Bir kategori başkasının çakmasına engel olunca (örn. asset scanner uzun sürerse plugin reader bloklanmasın)

---

## Karar 6 — Phase 1 kapsamı

**Durum:** BELİRLENDİ
**Cevap:** Phase 1 = `reference-systems.md` üzerine fix-up + scoring + freshness check (tam yeniden yazma değil).

**Yapılacaklar:**
- Reference doc'taki "Doğrulanamadı" alanları GitHub/Nexus API ile teyit et
- License alanı ekle (research plan formatında var, reference doc'ta yok)
- 8 eksenli puanlama uygula: automation_friendliness, documentation_quality, source_availability, maintenance_status, fallout4_relevance, mcp_suitability, risk_level, mvp_priority
- "Last updated" alanları 2026-05-10 itibariyle freshness check
- CLI/library boolean'larını netleştir

**Maliyet tasarrufu:** ~%40 daha hızlı, çünkü envanter zaten var.

---

## Karar 7 — License strategy

**Durum:** ÇÖZÜLDÜ (2026-05-14 formalize; **2026-05-29 kesinleşti: MIT**)
**Cevap:** Fo4-mcp **MIT** (kullanıcı kararı 2026-05-29: "herkese tamamen açık, tek şart credit"). MIT'in attribution şartı = copyright + lisans bildirimini koruma zorunluluğu, tam olarak istenen "kullanan credit versin" davranışı. `LICENSE` dosyası repo kökünde (Copyright 2026 m4rmz). GPL-3.0 bağımlılıklar yalnız subprocess; tool binary'leri redistribute edilmez (tools/ gitignored); üretilen mod kullanıcının copyright'ında.

**Detay:** `docs/karar-7-license-strategy.md` — subprocess-wrap firewall rationale, per-tool license inventory (24+ tool tablosu), CI/release 4 kuralı, no-LICENSE tool'lar için Nexus terms-of-service yaklaşımı. MIT'in temiz kalması: GPL tool'lar sadece out-of-process çağrılıyor + dağıtılmıyor → contagion yok.

**Etki:**
- `mcp-server/` source'ta GPL-3.0 import yasak (CI check)
- `tools/` git'te tracked değil (`.gitignore` allowlist mevcut)
- README license bölümü Phase 2 release öncesi yazılır
- Native binding (Mutagen pythonnet) V3'e ertelendi

---

# Phase 0 kapanışı (2026-05-10)

Tüm kararlar çözüldü. Tetikleme komutu **Plan C** (FO4 plugin/Papyrus/runtime patcher dalgası) onaylandı.

## Sonraki session'ın ilk işi: Plan C dalgası

1. **Mutagen** elle test — küçük bir test ESP'sini Mutagen ile aç, ARMO/QUST/DIAL/INFO/LVLI record'larını listele, override chain çıkar
2. **Spriggit** roundtrip — aynı ESP'yi Spriggit ile YAML'a serialize et, geri convert et, semantik-identity teyit et
3. **Synthesis** scaffolding — minimal bir patcher project oluştur, dummy bir leveled list edit
4. **Papyrus** build pipeline — Pyro + Caprica ile minimal script compile
5. **RobCo / SPID / BOS** — config gen taraması (V2'ye işaretli ama envanter çıkarılır)
6. **Buffout / CLASSIC** — crash log parse pipeline

Her sistem için `research/p0/<system>/` altında 8-eksenli scoring + format dolduruldu (research-plan.md "Araştırma çıktısı formatı" bölümü).

## İlk fixture stratejisi

Karar 2 (mod author, quest+armor authoring) ışığında ilk fixture'lar:
- `fixtures/armor-swap-test/` — vanilla armor record'unu kopyalayıp keyword/leveled list değişikliği (Mutagen + Spriggit roundtrip için ideal başlangıç)
- `fixtures/mini-quest-test/` — bir NPC + bir DIAL+INFO + bir QUST stage + bir Papyrus tetik (Plan C dalgası sonunda)
- Custom armor (yeni mesh + NIF/BGSM/slot) ve settlement object → V2'ye

İlk somut mod hedefi Session 1'de explicit seçilmedi — fixture stratejisi "armor swap → mini quest" sırasını izleyecek (artan karmaşıklık).
