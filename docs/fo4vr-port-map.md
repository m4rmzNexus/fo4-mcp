# FO4VR → fo4-mcp Port Haritası

> **Durum:** Araştırma + disk-doğrulama tamamlandı (2026-06-21). Kod yazılmadı.
> Kaynak: 103-agent deep-research (çekişmeli-doğrulanmış, 25 iddia → 22 onaylı, 3 elendi)
> + bu makinedeki FO4VR kurulumuna karşı disk çapraz-doğrulama.
> **Kapsam kararı:** "önce araştır + haritalandır" — bu dosya o haritanın kalıcı kaydı.

## TL;DR

Fallout 4 VR (Steam app **611660**) küçük ama aktif, *teknik olarak ayrı* bir modlama
ekosistemi. fo4-mcp'nin **disk-authoring çekirdeği büyük ölçüde portlanabilir**, ama
**üç sert ayrışma** var:

1. **Eski, donmuş runtime + ESL yok** — FO4VR = `1.2.72`, master form versiyonu `0.95`
   (ESL'i getiren AE/1.10.x = form `1.00`'dan önce). ESL-flag base runtime'da güvenli değil.
2. **Native plugin'ler ayrı fork ister** — `alandtse/CommonLibF4` VR target + VR Address
   Library (Nexus 64879). Tier-3 in-game plugin retarget edilebilir; fizibilite YÜKSEK
   (FRIK/Heisenberg/Buffout kanıtı), ama VR struct'ları için el-RE gerekir.
3. **Mutagen'de Fallout4VR GameRelease yok** — record format aynı olduğu için pratik yol:
   düz-FO4 GameRelease'iyle yaz + `Fallout4_VR.esm`'i master ekle.

## Disk-kanıtlı gerçekler (bu makine, 2026-06-21)

| Şey | FO4VR | Düz-ekran | Kanıt |
|---|---|---|---|
| exe / runtime | **1.2.72.0** | 1.11.221.0 | exe ProductVersion |
| `Fallout4.esm` HEDR form ver. | **0.95** (`0x3F733333`) | 1.00 (`0x3F800000`) | TES4/HEDR byte'ları |
| `Fallout4.esm` boyut | 330,553,163 | 330,776,415 | farklı master (eski depot) |
| VR master | ayrı **`Fallout4_VR.esm`** (113,073 B) | yok | Data/ |
| VR arşivleri | `Fallout4_VR - Main/Shaders/Textures.ba2` | yok | Data/ |
| BA2 formatı | OG **v1** (NG v7/v8 değil) | NG v7/v8 | 2017-dönem oyun |
| Config/INI | `Documents\My Games\Fallout4VR\` | `…\Fallout4\` | disk (Saves/ mevcut) |
| Load order | `AppData\Local\Fallout4VR\plugins.txt` | `…\Fallout4\` | rapor (henüz oluşmadı) |
| Kurulum yolu | `…\steamapps\common\Fallout 4 VR\` | `…\Fallout 4\` | disk |
| F4SEVR | kurulu değil | F4SE var | disk |

## Native VR mod ekosistemi (hepsi F4SE DLL — ESP/Mutagen-authorable DEĞİL)

| Mod | Ne | Kaynak |
|---|---|---|
| **FRIK** | full-body IK, weapon reposition, in-VR Pip-Boy | `rollingrock/Fallout-4-VR-Body` · Nexus 53464 |
| **Heisenberg** | HIGGS muadili fiziksel etkileşim (el ile al/at/loot) | Nexus 99105 (HIGGS kodundan) |
| **Buffout 4 NG/VR** | crash logger + engine fix | `alandtse/Buffout4` · Nexus 64880 |
| **VR Address Library** | F4SEVR adres haritası (native plugin'ler için şart) | `alandtse/fallout_vr_address_library` · Nexus 64879 |
| **F4SEVR** | script extender fork, build **0.6.21**, `f4sevr_loader.exe`, `f4sevr_1_2_72.dll` | f4se.silverlock.org · Nexus 42159 |
| **CommonLibF4 VR** | tek codebase'den flat+ng+VR (`ENABLE_FALLOUT_VR`) | `alandtse/CommonLibF4` |
| **FalloutVRESL** | FO4VR'a ESL desteği EKLER (base runtime'da yok) | `rollingrock/FalloutVRESL` |

## fo4-mcp ekseni → port verdikti

| fo4-mcp tool/eksen | Verdikt | Not |
|---|---|---|
| `fo4_spriggit_export/import`, `_inspect_record`, record-edit | 🟢 **Round-trip PASS** | Disk-kanıtlı (§Doğrulama #1): standart `Fallout4` release'i FO4VR master'larını (form 0.95 dahil) round-trip ediyor. Tek dikkat: yeni plugin yazarken `Fallout4_VR.esm` master ekle |
| `fo4_papyrus_build` (Caprica) | 🟢 Port + include swap | Aynı Papyrus; base script'ler VR install'dan, F4SEVR script'leri ayrı |
| `fo4_ba2_version_patch` | 🟢 Port | FO4VR = OG v1; araç zaten v1 hedefliyor |
| `fo4_lint_engine_config`, `fo4_generate_fomod` | 🟢 As-is | Buffout TOML / FOMOD manager-agnostik |
| `fo4_check_esl_eligibility` | 🔴 Anlam değişir | Base runtime ESL yüklemiyor (form 0.95). VR-modu "FalloutVRESL şartı" demeli |
| `fo4_backup_saves`, `fo4_read_load_order`, setup-check, get_environment | 🟡 Path varyantı | `Fallout4VR` ağacına yönlendir |
| `fo4_analyze_crash_log` | 🟡 Doğrula | Buffout 4 NG/VR var; format muhtemelen aynı, yol/format teyit edilmeli |
| `fo4_run_ingame_test` (Tier-3 F4SE DLL) | 🟠 Retarget (C++ iş) | `alandtse/CommonLibF4` VR target + VR Address Library ile rebuild, `f4sevr_loader.exe` ile launch. Fizibilite YÜKSEK, VR struct'lar için el-RE |

## Açık sorular (sonraki adımlarda çözülür)

1. **Spriggit FO4VR round-trip** — `Fallout4_VR.esm` (form 0.95 master üstünde) export/import oluyor mu? → **§Doğrulama** (bu oturumda test edildi)
2. **ESL ampirik** — FalloutVRESL'siz ESL-flag'li plugin FO4VR'da yükleniyor mu? (in-game test, gated)
3. **CK FO4VR** — Creation Kit FO4VR'ı açıyor mu, hangi sürüm? (araştırma çözemedi)
4. **Buffout VR crash-log** — tam yol + format farkı (parser'ı etkiler mi?)
5. **Wabbajack VR / kanonik modlist** — FWDekker `fo4vr-modlist` güncel referans; ötesi netleşmedi

## Doğrulama (§)

### #1 Spriggit/Mutagen FO4VR round-trip → ✅ PASS (2026-06-21, disk-kanıtlı)

**Test:** `Spriggit.CLI.exe serialize` (v0.40.1, `-g Fallout4 -p Spriggit.Yaml.Fallout4`)
girdi = FO4VR `Data/Fallout4_VR.esm` (form-0.95 `Fallout4.esm` master üstünde),
çıktı = `staging/fo4vr-probe/fallout4vr-esm-yaml/` (read-only kaynak).

**Sonuç:**
- `serialize` exit **0**, **181 YAML** dosyası.
- Spriggit'in dahili `deserialize` correctness sanity-check'i (YAML→geçici esm) **hatasız** —
  yani serialize→deserialize round-trip komutun içinde zaten kanıtlandı.
- `Throwing on unknown records: True` aktifti ve **hata fırlatmadı** → temiz parse, bilinmeyen record yok.
- Çıktı **hem** `Fallout4_VR.esm` kayıtlarını (`IMod_VATS_VR_SlowTimeFadeIn`, `WandTeleportEndPointObject`,
  `HelpAimingVR`, cryo furniture default-object'leri) **hem** form-0.95 `Fallout4.esm` master referanslarını
  (`Vault111Cryo - 0016D8_Fallout4.esm`, `SlowTimeImod - 2170E9_Fallout4.esm`) doğru çözdü.

**Çıkarım:** Record-tooling ekseni beklenenden temiz portlanıyor. Mutagen'de ayrı `Fallout4VR`
GameRelease olmaması engel değil — **standart `Fallout4` release'i FO4VR master'larını (eski form 0.95
dahil) okuyup round-trip ediyor.** `fo4_spriggit_export/import`, `_inspect_record`, record-edit eksenleri
FO4VR'da **olduğu gibi çalışıyor**; tek dikkat: YENİ plugin yazarken master listesine `Fallout4_VR.esm`
eklemek (VR-spesifik kayda dayanılıyorsa). Verdikt 🟡 → **🟢 (round-trip PASS)**.

> Geriye kalan record-tooling soru işareti: YENİ bir FO4VR plugin'i `Fallout4_VR.esm` master'ıyla
> *yazıp* FO4VR runtime'ında yüklenmesi (in-game), ve ESL ampirik testi (#2) — ikisi de gated.

### Native stack indirildi + staged (2026-06-21)

`staging/fo4vr-stack/` (+ `INSTALL.md`) — oyun-klasörü düzeninde hazır, Steam'e kopya **user-gated**:
- **F4SEVR 0.6.21** (runtime 1.2.72, silverlock) → GAME-ROOT 3 dosya + Data\Scripts 29 .pex
- **VR Address Library 1.13.1** (Nexus 64879) → `Data\F4SE\Plugins\version-1-2-72-0.csv`
- **Buffout 4 NG/VR 1.35.1** (Nexus 64880) → Data\F4SE\Plugins (universal build, `Fallout4VR.pdb` içeriyor;
  **1.35.1 = VR-güvenli**, 1.37 VR soft-lock bug'ından kaçınıldı)

Kurulduktan sonra açık soru **#4 (Buffout VR crash-log yol/format)** test edilebilir; #2/#3 için zemin hazır.

## Kaynaklar (birincil)

- f4se.silverlock.org — F4SEVR build 0.6.21 / runtime 1.2.72
- `github.com/Mutagen-Modding/Synthesis` discussions/423 — Noggog: "doesn't have Fallout4 VR support"; FO4VR base esm = eski pancake master
- `github.com/alandtse/CommonLibF4`, `/fallout_vr_address_library`, `/Buffout4`, `/vr_address_tools`
- `github.com/rollingrock/Fallout-4-VR-Body` (FRIK), `/FalloutVRESL`
- Nexus: 53464 (FRIK), 99105 (Heisenberg), 64880 (Buffout NG/VR), 64879 (VR Address Lib), 42159 (F4SEVR mirror)
- FWDekker `fo4vr-modlist` (topluluk modlist rehberi)

## Caveat'lar

- F4SEVR/CommonLibF4 VR repo'ları hızlı değişiyor — exact build ID'leri kullanmadan önce
  Silverlock + alandtse repo'larını yeniden kontrol et. Runtime tarafı donmuş (1.2.72 kalıcı).
- FO4VR base-ESM'in "6 Şub 2017 depot" forensik detayı tek forum postuna dayanıyor (exact checksum
  doğrulanmamış) — ama "eski master" mimarisi disk-kanıtlı (form 0.95 vs 1.00).
- Bazı Nexus sayfaları (53464/99105/64880/64879) fetch'e 403 döndü; doğrulama yazarların kendi
  GitHub repo'larına dayandı (eşit/daha güçlü birincil kaynak).
