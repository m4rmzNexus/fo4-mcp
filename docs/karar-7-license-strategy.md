# Karar 7 — License Strategy (Formalize: 2026-05-14)

**Status:** ÇÖZÜLDÜ (Session 3 sonu)
**Önceki status (Session 2):** AÇIK
**Yer aldığı tablo:** `docs/phase-0-decisions.md` Karar 1-7 listesinde Karar 7 satırı

---

## Soru

Fo4-mcp ve onun bağımlılık ekosistemi (Mutagen, Spriggit, Synthesis, BodySlide, MO2, Caprica, vs) içinde **GPL-3.0 contagion riski** nasıl yönetilir? fo4-mcp'nin kendi lisansı ne olmalı? Tool binary'leri redistribute edilebilir mi?

## Karar

### Fo4-mcp kendisi: **MIT veya Apache 2.0**

Permissive lisans seçilir. Gerekçe:
- Modlama ekosistemi (F4SE, CommonLibF4) zaten permissive (MIT)
- Geniş adoption hedefli (Claude Code, Codex CLI, başka MCP client'lar)
- GPL contagion riskinden kaçınmak için subprocess-only boundary tutulur

**Tercih:** MIT (basitlik) > Apache 2.0 (patent grant gerekirse). Final seçim Phase 2 release öncesi.

### GPL-3.0 bağımlılıklara asla `import` yok — yalnız subprocess

**Kural:** Fo4-mcp source kodunda GPL-3.0 lisanslı kütüphane import edilmez. Mutagen/Spriggit/Synthesis/BodySlide/MO2/Caprica/Champollion/LOOT/NifSkope-NG/Wrye Bash gibi araçlar **sadece subprocess çağrısıyla** kullanılır (`fo4_mcp/subprocess_wrap.py` → `run_tool()`).

**Hukuki gerekçe:**
- GPL-3.0 derivative-work tanımı (FSF GPL FAQ "Mere Aggregation") subprocess çağıranı kapsamaz
- Subprocess process boundary, contagion firewall
- Case law: GPL'li CLI tool'ları (örn: gcc) proprietary kod tarafından subprocess olarak çağrılır, contagion oluşmaz
- Kütüphane import etmek (in-process linking) vs subprocess invocation farkı GPL FAQ'da net

**Kontrol mekanizması:** CI'da basic grep — `mcp-server/` altında `import mutagen`, `import spriggit`, vb. olmayacak (Mutagen + Spriggit zaten .NET, Python'dan import edilemez ama prensip aynı). pythonnet import'u da yasak (Mutagen DLL'yi `Add-Type` ile çağırma yolu).

### Tool binary'leri bundle edilmez

**Kural:** `tools/` git'te tracked değil (`.gitignore`: `tools/*` allowlist ile yalnızca `MANIFEST.md`, `MANUAL-DOWNLOADS.txt`, `fetch-nexus.py`, `extract-nexus.py` izinli).

Kullanıcı `tools/fetch-nexus.py` çalıştırır, binary'leri kendisi indirir. Provenance + lisans yükümlülüğü kullanıcıda. Fo4-mcp release'i sadece source + MANIFEST + fetch script şeklinde — tool binary'lerini içermez.

**Hukuki gerekçe:**
- GPL-3.0 redistribute izni var ama source/copyright notice include zorunluluğu (GPL §4-5)
- Bunu yapmamak için en güvenli yol: redistribute etmemek. Kullanıcı kendi binary'sini indirir.
- Bethesda EULA (CK için) redistribute YASAK — başka seçenek yok
- No-LICENSE tools (RobCo, SPID-F4, BOS-F4, CLASSIC, Addictol): "all rights reserved" varsayılır, redistribute güvenli değil

### Üretilen mod çıktısı (`staging/`, `fixtures/`)

**Kural:** Kullanıcı tarafından fo4-mcp aracılığıyla üretilen ESP/.psc/.pex/.ba2/.yaml dosyaları kullanıcının copyright'ında. Fo4-mcp proje claim etmez.

**Hukuki gerekçe:**
- Tool kullanmak (örn: bir compiler) çıktının lisansını belirlemez; çıktının yaratıcısı kullanıcıdır
- GCC ile compile edilen kod GCC'nin GPL'sini miras almaz (compiler exception)
- Aynı mantık: Caprica/Spriggit/Mutagen ile üretilen mod kullanıcının
- **Ancak:** Üretilen mod vanilla Bethesda asset (mesh, dialogue, voice) referansı içeriyorsa, Bethesda EULA o asset'ler için uygulanır. Bu kullanıcının sorumluluğudur, fo4-mcp scope dışı.

---

## Per-tool license inventory

| Tool | License | fo4-mcp etkileşimi | Notlar |
|---|---|---|---|
| F4SE | F4SE custom (modding-friendly) | subprocess yok (game-side, runtime) | fo4-mcp sadece existence check + plugin enum |
| CommonLibF4 | MIT | header library, link OK (eğer C++ plugin yazılırsa) | Phase 3+ DLL authoring planı için |
| Mutagen | GPL-3.0 | subprocess only (Synthesis runner üzerinden) | NuGet-only, .NET; pythonnet ile import yasak |
| Synthesis | GPL-3.0 | subprocess only | `Synthesis.Bethesda.CLI.exe` ile patcher invocation |
| Spriggit | GPL-3.0 | subprocess only | `spriggit.exe serialize/deserialize` CLI |
| BodySlide & Outfit Studio | GPL-3.0 | subprocess only | `BodySlide x64.exe` batch build CLI |
| MO2 | GPL-3.0 | subprocess only | Genelde launch için; profile/plugin list read filesystem üzerinden |
| Caprica | MIT (! permissive) | subprocess only (yine de — uniform pattern) | Future native binding option (MIT alır) |
| Champollion | LGPL-3.0 | subprocess only | LGPL link OK ama subprocess yine de tercih |
| xEdit (FO4Edit) | MPL-2.0 | subprocess only | Script-based usage (.pas), yedek tool |
| LOOT | GPL-3.0 | subprocess only | Load order sort |
| NifSkope-NG | GPL-3.0 | subprocess only | Mesh inspection (Phase 3+) |
| Wrye Bash | GPL-3.0 | subprocess only | BSA archive, bashed patch (V2+) |
| Creation Kit | Bethesda EULA (proprietary) | subprocess only | Redistribute YASAK; invoke serbest |
| PapyrusCompiler (CK ile) | Bethesda EULA (proprietary) | subprocess only | CK ile bundled |
| PapyrusAssembler/ProfileAnalyzer/StackDumpAnalyzer | Bethesda EULA | subprocess only | CK ile bundled |
| Buffout 4 / Addictol | No LICENSE file | **subprocess yok** (game-side DLL) | fo4-mcp sadece path resolve + crash log path |
| RobCo Patcher | No LICENSE file | **subprocess yok** (game-side DLL, MO2 runtime alanı) | INI generation fo4-mcp tarafı; DLL invocation runtime |
| SPID-F4 | No LICENSE file | **subprocess yok** (game-side DLL) | _DISTR.ini generation fo4-mcp; DLL invocation runtime |
| BOS-F4 | No LICENSE file | **subprocess yok** (game-side DLL) | _SWAP.ini generation fo4-mcp; DLL invocation runtime |
| CLASSIC | No LICENSE file | subprocess only (crash log parse) | Markdown output parse; binary invoke OK |
| Material Editor | No LICENSE file (?) | subprocess yok (GUI tool) | Materyal yapımı için kullanıcı manuel; fo4-mcp scope dışı şimdilik |
| Cathedral Assets Optimizer (CAO) | GPL-3.0 (license var) | subprocess only | Asset optimization batch (V2+) |
| HUDFramework, MCM, Lighthouse Papyrus Extender, Address Library, xSE Preloader | (data mod / framework) | **subprocess yok** (game-side) | fo4-mcp sadece presence + version check |
| PRP (Previsibines Repair Pack) | (data mod) | **subprocess yok** | fo4-mcp sadece presence check |

### Özet kategoriler

1. **Permissive (MIT/MPL/Apache):** F4SE, CommonLibF4, Caprica, xEdit — subprocess yine de tutarlılık için
2. **GPL-3.0:** Mutagen, Spriggit, Synthesis, BodySlide, MO2, Champollion (LGPL), LOOT, NifSkope-NG, Wrye Bash, CAO — **subprocess zorunlu**
3. **No LICENSE file:** RobCo, SPID-F4, BOS-F4, CLASSIC, Addictol/Buffout — Nexus terms-of-service governs; **bundle yasak**, kullanıcı kendi indirir; fo4-mcp çoğunlukla path resolve (subprocess çağırma ihtiyacı yok)
4. **Bethesda EULA (proprietary):** Creation Kit + bundled Papyrus tools — **redistribute YASAK**, subprocess invoke serbest
5. **Data mods (no executable):** HUDFramework, MCM, LPE, Address Library, xSE Preloader, PRP — fo4-mcp sadece presence check

---

## Çıkan 4 kural (CI / linting / release checklist)

### Kural 1: GPL-3.0 import yasak

`mcp-server/` source kodunda:
- `import mutagen`, `import spriggit`, `from synthesis import ...` → CI fail
- pythonnet ile GPL-3.0 DLL load (`clr.AddReference("Mutagen.Bethesda")`) → CI fail
- Subprocess çağrısı her zaman `subprocess_wrap.run_tool()` üzerinden

### Kural 2: tools/ git'te tracked değil

`.gitignore`:
```
tools/*
!tools/README.md
!tools/MANIFEST.md
!tools/MANUAL-DOWNLOADS.txt
!tools/.gitkeep
!tools/fetch-tools.ps1
!tools/extract-tools.ps1
!tools/fetch-nexus.py
!tools/extract-nexus.py
```

Yeni script eklenirse allowlist'e yaz. Binary asla commit edilmez.

### Kural 3: Üretilen mod kullanıcının

`staging/` ve `fixtures/` altındaki üretilen dosyalar (ESP, YAML, PSC, PEX, BA2) kullanıcının copyright'ında. README'de açık ifadeyle:

> User-generated mod outputs in `staging/` and `fixtures/` are the user's intellectual property. fo4-mcp claims no copyright over outputs produced via its tools.

### Kural 4: README license section

Release öncesi `README.md` license bölümü:

```markdown
## License

- **fo4-mcp (this repo):** MIT (or Apache 2.0) — see `LICENSE` file.
- **Tool binaries:** Each tool ships under its own license; downloaded via `tools/fetch-nexus.py`. fo4-mcp does not bundle or redistribute. See `docs/karar-7-license-strategy.md` for the full per-tool inventory.
- **GPL-3.0 contagion firewall:** GPL-licensed tools (Mutagen, Spriggit, Synthesis, BodySlide, MO2, etc.) are invoked only via subprocess (`subprocess_wrap.run_tool()`). No in-process linking or import. This preserves fo4-mcp's permissive license.
- **User-generated outputs (`staging/`, `fixtures/`):** User's copyright. fo4-mcp claims no rights.
- **Bethesda assets:** Vanilla mesh/dialogue/voice references in generated mods remain under Bethesda EULA. User responsibility.
```

---

## phase-0-decisions.md güncellemesi

Karar 7 satırı tabloya eklenir (status: ÇÖZÜLDÜ). Bu doküman pointer olarak referans verilir. `phase-0-decisions.md`'nin tablosu güncellenmedi henüz — Phase E commit ile eş zamanlı yazılabilir veya CLAUDE.md'deki tablo zaten Karar 7 AÇIK göstermez (Session 3'te ÇÖZÜLDÜ olarak güncellendi).

---

## Açık kalan hukuki sorular (V2+ değerlendirme)

- **No-LICENSE tool'ları Nexus terms-of-service'in yorumu:** Nexus permissions tab'ı her mod için ayrı izinler tanımlıyor (modification permitted, redistribution permitted, vs). Fo4-mcp bu izinleri programmatic olarak read etmeli mi? Nexus API'da var (`/v1/games/.../mods/{id}.json` permissions field).
- **Patent risk:** Apache 2.0 patent grant'ı versek mi? Modlama ekosisteminde patent litigation precedent yok, ama 2026'da AI tooling alanında genel risk var. Risk düşük; MIT yeterli.
- **Mutagen native binding (pythonnet) tartışması:** Eğer Mutagen'in performansı kritik blocker olursa (büyük load order'da subprocess overhead 10x slow), pythonnet import GPL-3.0'a kapı açar. fo4-mcp'nin de GPL-3.0 olması gerekir. V3 reconsider.
