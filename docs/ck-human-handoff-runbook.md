# CK + insan execution runbook (W9/W10/W12/W11b)

**Amaç.** Faz 3 roadmap'inin (W0–W12) terminal kalemleri için adım-adım çalıştırma prosedürü.

> **GÜNCELLEME (2026-06-21) — bunların çoğu artık AGENT-OTOMATİK.** Bu makinede CK ana-install'a
> merge + CKPE + RTX 3080 olduğu için "imkânsız" diye sınıfladığım işler aslında çalıştırılabilir:
> - **Silent-voice (W9):** `fo4_bake_voice_assets` tam-otomatik (mikrofon gerekmez), e2e-kanıtlı. Adım 4'ün yerine geçer.
> - **FaceGen (W10):** `fo4_build_facegen` (CK `-ExportFaceGenData`). **Previs (W12):** `fo4_build_previs`. İkisi de agent-runnable; ama canlı koşu **oyun Data tree'sine yazdığı için** safe-write sınırı gereği `dry_run=False` = **kullanıcının açık tetiği** (yetenek değil, izin).
> - **GERÇEKTEN GUI-interaktif tek kalan:** exterior navmesh finalize/stitch + combat-cover (Adım 1) — CLI flag yok. Track-A iç-mekân quest bunu gerektirmez (iç-mekân navmesh zaten Mutagen-authored).
>
> Aşağıdaki adımlar hem otomatik tool çağrısını hem de (istersen) elle CK prosedürünü verir.

> **Durum sınıflandırması.** Roadmap'te bu kalemler `[~]` (agent-payı DONE, çekirdek-execution
> insan-gated). Bu runbook'u izleyip her adımı tamamladıktan sonra ilgili TASKS.md kalemini
> `[x]`'e çevir — onları "tamamlandı" yapacak olan **bu insan oturumu**, agent değil.

## Sert güvenlik sınırları (her adımda geçerli)

- **Steam game folder'a ASLA yazma:** `C:/Program Files (x86)/Steam/steamapps/common/Fallout 4/`
  ve CK dizini `...Fallout 4 1946160/` salt-okunur. Tüm output → `staging/` veya MO2 mod klasörü.
- CK'yı **MO2'den launch et** (`tools/mo2/portable-fo4-agentic/`) ki mod-context'inde çalışsın.
- Üretilen `.fuz`/`.lip`/`.nif`/`.dds`/previs → `staging/.../` veya yazılabilir MO2 mod dizini;
  `Data/*` yasak. Generated dosya = diff + onay (Karar 4 PreToolUse hook).

## Kilitli sıra (roadmap W12 — sapma = bozuk build)

```
assemble (W11a, DONE)
  → fo4_compact_formids            # FormID-lock — voice .fuz adı FormID gömer
  → CK: navmesh gen + finalize     # exterior; interior zaten Mutagen-authored
  → CK: FaceGen bake (W10)
  → CK: precombine + previs regen  # en son (ref değişikliklerinden sonra)
  → fo4_bake_voice / kayıt (W9)    # post-compaction FormID'lerden re-derive
  → fo4_release_preflight          # MANDATORY ship-gate
  → oyun-içi smoke (W11b)
```
**Neden bu sıra:** `.fuz` dosya-adı INFO FormID'sini gömer → voice **FormID-lock'tan SONRA**.
FaceGen ref değiştirmez ama previs precombine'a bağlı → previs **en son**. `release_preflight`
hepsini tek verdict'te toplar; "ship-blocked" varsa oyuna girme.

---

## Adım 0 — FormID-lock (agent-doable, önce çalıştır)

```
fo4_compact_formids(plugin)        # ESL tavanı + stabil FormID'ler
fo4_release_preflight(plugin)      # başlangıç durumu: ne CK gerektiriyor?
```
`release_preflight` çıktısındaki `sections` her alt-ekseni gösterir; `ck_checklist` +
`recording_checklist` bu oturumun iş listesidir.

---

## Adım 1 — Exterior navmesh + finalize (W12, CK GUI)

> İç-mekân navmesh **artık gerekmez** — Mutagen-authored + in-game-pathable (A-in-game PASS
> 2026-06-21). `fo4_navmesh_handoff` sadece **exterior/worldspace** hücreleri CK'ya yönlendirir.

1. Checklist'i üret:
   ```
   fo4_navmesh_handoff(plugin)     # error-level = exterior_navmesh_ck_gated -> CK işi
   ```
2. CK'yı MO2'den aç, plugin'i **active file** yap (modlu yükle).
3. Her `ck_checklist` hücresi için: cell'i Render Window'da aç → **Navmesh** toolbar →
   alanı düz-üçgenle (veya auto-gen) → komşu hücrelerle **Finalize Navmesh** (yeşil→stitch).
4. NPC combat-cover gerekiyorsa: navmesh seçili → cover-edge işaretle (CK Navmesh menüsü).
5. **File → Save** (plugin'e yazar — MO2 overwrite/mod dizinine; Steam'e değil).
6. Doğrula: `fo4_navmesh_handoff(plugin)` → exterior error'lar 0 olmalı.

## Adım 2 — FaceGen bake (W10, CK GUI / GPU)

> Trait-template'li NPC'ler (W3) **sıfır FaceGen** ister; sadece **kendi yüz verisi taşıyanlar**.

1. Coverage listesini üret (destek-tool zaten mevcut, ayrı tool yazılmadı):
   ```
   fo4_lint_npc_template(plugin)
   # facegen_needed = bake gereken NPC'ler; inheritsTraits=true -> düşük risk
   ```
2. CK'da: `facegen_needed` NPC'lerini Object Window → Actors'tan çoklu-seç.
3. **Ctrl+F4** → "Export FaceGen for selected" (CKPE ile batch).
4. Üretilen `.nif` (`Meshes/Actors/Character/FaceGenData/FaceGeom/<plugin>/`) +
   `.dds` (`Textures/Actors/Character/FaceCustomization/<plugin>/`) → MO2 mod dizini.
5. Doğrula (oyun-içi, Adım 5): yüz dark-face değil, doğru morph.

## Adım 3 — Precombine + previs regen (W12, CK GUI / GPU — EN SON)

> Yeni loose cell precombine taşımaz (sorun yok); **mevcut precombined cell'e ref eklediysen**
> (W5 override) previs **bozulur** → regen şart, yoksa görünmez ref + görsel delik.

1. Etkilenen hücreleri bul:
   ```
   fo4_check_previs_safety(cell, source_plugin=plugin)   # safe=False -> regen gerek
   fo4_release_preflight(plugin)                          # section "previs" -> cells_with_previs
   ```
2. CK: **World → Generate Precombined** (seçili/tüm cell) → tamamla.
3. CK: **World → Generate Previs (Visibility)** → tamamla.
4. Alternatif/CLI yardımcısı (dry-run önce):
   ```
   fo4_build_previs(... dry_run=True)   # argv'yi gör, sonra gated gerçek koşu
   ```
5. Çıktı previs `.uvd`/`.cdx` → MO2 mod dizini; `Fallout4 - Geometry` BA2'ye `fo4_pack_ba2`.

## Adım 4 — Voice kaydı + FUZE-pack (W9, insan/audio)

1. Satır-satır kayıt checklist'ini üret:
   ```
   fo4_voice_handoff(plugin)
   # her satır: text (subtitle) + speaker + voiceType + kanonik fuzPath
   # recording_checklist = .fuz'u eksik satırlar
   ```
2. Her satır için sesi üret (insan/audio adımı — agent yapamaz):
   - **Silent-subtitled MVP:** sessiz/çok-kısa WAV (ağız kapalı; "lipsync" İMA ETME).
   - **Gerçek ses:** kaydet veya TTS → WAV.
3. Pipeline (her satır): `WAV → ffmpeg → LipGenerator (.lip, FonixData.cdf + transcript)
   → xWMAEncode (.xwm) → FUZE pack (.lip + .xwm → tek .fuz)`.
4. `.fuz`'u **tam olarak** `fo4_voice_handoff`'un verdiği yola koy:
   ```
   staging/<mod>/Sound/Voice/<plugin>/<VoiceTypeEditorID>/<INFO-FormID-8hex>_<respNum>.fuz
   ```
   (`.lip` ayrı shipping yok — `.fuz` içinde FUZE-packed.)
5. Doğrula:
   ```
   fo4_voice_handoff(plugin, audio_root="staging/<mod>")
   # her satır voice_line_present (OK) olmalı; verdict = voice-complete
   ```

## Adım 5 — Ship-gate + oyun-içi smoke (W11b, canlı oyun + insan)

1. **MANDATORY ship-gate** (oyuna girmeden önce):
   ```
   fo4_release_preflight(plugin)
   # verdict ship-ready olmalı; ship-blocked varsa geri dön (eksik CK/voice/compaction)
   ```
2. Mod'u MO2'de enable et (`modlist.txt` `+`, `plugins.txt` `*`); Steam `ActiveUser≠0`
   (yoksa 25MB DRM stub launch olur).
3. Smoke checklist (en ucuz sinyal **önce** — W6 SM-fire):
   - [ ] Story Manager event tetikleniyor → quest auto-start (en ucuz sinyal)
   - [ ] NPC navmesh'te path'liyor + door geçiyor (interior zaten kanıtlı; exterior = Adım 1)
   - [ ] Objective arrow + compass marker doğru
   - [ ] Dialogue satırı oynuyor (subtitled; .fuz varsa sesli)
   - [ ] Yüz dark-face değil (FaceGen, Adım 2)
   - [ ] Görsel flicker/delik yok (previs, Adım 3)
4. Headless yardımcı (SM-fire + Papyrus iz, otomatik-quit):
   ```
   fo4_run_ingame_test(... save="coc:<interiorEditorId>", dry_run=False)
   ```
   (Tier 3 F4SE runner; canlı game state + Steam login bir-kerelik insan adımı.)
5. Bug bulursan → ilgili faz'a geri-besle (yeniden author → bu runbook'u tekrar koş).

---

## Hangi tool hangi adımı besler (özet)

| Adım | Tool | Otomasyon durumu |
|---|---|---|
| 0 FormID-lock | `fo4_compact_formids`, `fo4_release_preflight` | agent-otomatik |
| 1 exterior navmesh | `fo4_navmesh_handoff` (checklist) | **GUI-interaktif** (CK Render Window; agent yapamaz) — Track-A iç-mekân quest gerektirmez |
| 2 FaceGen | `fo4_lint_npc_template` (kapsam) + `fo4_build_facegen` (CK CLI) | agent-runnable; `dry_run=False` = kullanıcı tetiği (oyun Data'ya yazar) |
| 3 previs | `fo4_check_previs_safety` + `fo4_build_previs` (CK CLI) | agent-runnable; `dry_run=False` = kullanıcı tetiği (oyun Data'ya yazar) |
| 4 voice (silent MVP) | `fo4_voice_handoff` + `fo4_bake_voice_assets` | **agent-otomatik, e2e-kanıtlı** (staging'e yazar); gerçek ses opsiyonel insan |
| 5 smoke | `fo4_release_preflight` + `fo4_run_ingame_test` | runner otomatik; final görsel onay insan |

Tüm destek-tool'lar **read-only** (author etmez) ve çıktıyı `staging/`'e yönlendirir; bu
runbook'taki tek yazma işlemleri CK Save + üretilen asset'lerin MO2 mod dizinine kopyası —
hiçbiri Steam game folder'a dokunmaz.
