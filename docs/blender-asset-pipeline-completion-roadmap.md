# Blender→Oyun Asset Pipeline — Tam-Çözüm Roadmap'i

**Tarih:** 2026-06-24
**Kaynak:** 25-agent asset-pipeline audit (Task `wep2ekpn5`) + 3-agent community-tooling araştırması.
**Hedef (tek cümle):** Bugün yalnızca *tek dar sınıf* (donör-türevi düz MISC kartı) için diskte çalışan Blender→oyun pipeline'ını, **keyfi geometri + materyal + collision üreten, kendi kendini oyun-içi doğrulayan, tam-headless** bir sisteme çıkarmak.

---

## Durum tespiti (audit özeti)

**Bugün çalışan:** Money_Prewar donöründen türetilmiş tek-mesh düz MISC kartı; MO2-aktif 6 kuponun 6'sı diskte her kapıdan geçiyor (clamp=3, z=0.600, bhkPhysicsSystem=1572 donörle SHA-256 identik, ESP'de PTRN×6+OBND). Audit'in eski "REFUTED clamp / PTRN=null" verdict'leri **yanlıştı** — 2 gün eski staging-folder yetimini ölçmüştü; shipped ağaç temiz.

**6 blokör + 2 otomasyon kuyruğu:**
| # | Blokör | Çözüm zemini | Lisans |
|---|---|---|---|
| 1 | Keyfi collision (Havok) | scipy/CoACD convex-decomp → NiflySharp (MOPP'tan kaç) | scipy BSD / CoACD MIT / NiflySharp GPL |
| 2 | Keyfi geometri + tangent (`_tri_header` kırılgan) | NiflySharp BSTriShape writer | GPL-3.0 |
| 3 | BGSM/BGEM materyal writer yok | MaterialLib (ousnius) | **MIT** |
| 4 | `fo4_nif_build` aracı yok | NiflySharp orkestrasyonu | GPL-3.0 |
| 5 | DDS yanlış renk-uzayı (98 lineer vs 99 sRGB) | texconv doğru bayraklar | **MIT** |
| 6 | Doc/memory/path drift | otonom düzeltme | — |
| K1 | In-game **görsel** render doğrulanmadı | Tier-3 harness + screenshot + vision-model | (kendi) |
| K2 | Collision GUI-only sanılıyordu | Gap-1 ile düşüyor (convex headless) | — |

**Stratejik sonuç:** Tavanların hiçbiri Ghidra-RE gerektirmiyor (community kütüphaneleri layout'u zaten veriyor). Ghidra'nın değeri **crash-decompile + offset-pin**'de kalıyor → ayrı eksen (Faz F).

---

## Faz haritası

| Faz | Konu | Blokör | Otonom/Gated | Efor |
|---|---|---|---|---|
| **A** | Hardening + temizlik | #6 | Otonom | S |
| **B** | Materyal + texture writer | #3, #5 | Otonom | S–M |
| **C** | Geometri writer (NiflySharp) | #2, #4 | Otonom (1 GPL kararı gated) | M |
| **D** | Headless convex collision | #1, K2 | Otonom | M–L |
| **E** | Otomatik görsel doğrulama | K1 + audit kapanışı | **Gated (oyun launch)** | M |
| **F** | Ghidra ekseni (ayrı) | — | **Gated** | S (BN-1) / L (BN-2) |

Efor: **S**=dakika-saat · **M**=gün-mertebesi · **L**=çok-adımlı/deneme içeren.

---

## Faz A — Hardening + temizlik (otonom, S)

Pipeline'ı ölçülebilir temiz bir baseline'a çek.

- **A1** Doc/memory drift düzelt: tool sayısı **37** (TASKS 36 / CLAUDE 34 yanlış); test **488** toplanıyor (412 değil); `fo4-flat-misc-render-3-causes` memory'sini **5 nedene** genişlet (collision + texture-clamp/double-sided + preview-transform + **OBND bounds** + **gerçek thickness**; ayrıca `BSDestructibleObjectData` node gotcha'sı).
- **A2** "IN-GAME PASS / SUCCESS" iddialarını (TASKS.md + memory) **"disk-validated, in-game pending"** olarak düzelt — gerçek render kanıtı Faz E'de gelecek.
- **A3** Path-disiplini: staging-folder yetim ağacını (NIF sha `397a15ab` / ESP `7e17e417`) `_stale/` olarak işaretle veya sil. **Tek source-of-truth = MO2 mods ağacı.**

**Doğrulama:** Gelecek auditler yalnızca MO2-aktif ağacı ölçer; doc sayıları gerçeğe oturur.

---

## Faz B — Materyal + texture writer (otonom, S–M)

Audit'in en somut iki defektini kapatır; ikisi de **MIT** (GPL-firewall temiz).

- **B1 — BGSM/BGEM writer.** `MaterialLib` (ousnius/Material-Editor, MIT, C#) referans alınır/port edilir → yeni `fo4_create_bgsm` MCP aracı. Format version-gated (FO4 retail = v2/v20 → `Version` uint'e dallan). Alpha/gloss/fresnel/emissive/tiling tam kontrol. Audit'in `buf[0x2a]=0x00` manuel yaması artık `AlphaTestRef` (byte) + `AlphaTest` (bool) **alanı** olarak yazılır.
  - **Çıktı:** 6 kuponun BGSM'i **kaynaktan reproducible** üretilir → audit'in "kaynaktan rebuild'de materyal regrese eder" riski kapanır.
- **B2 — DDS renk-uzayı.** texconv (MIT) doğru bayraklarla wrapper:
  - diffuse: `texconv -f BC7_UNORM_SRGB -srgb -m 0 -bc x -y` (DXGI 99)
  - normal: `texconv -f BC7_UNORM -m 0 -bc x -y` (DXGI 98, `-srgb` YOK)
  - 6 diffuse'u sRGB'ye re-encode + texconv'u PATH'e koy.
- **B3 — Validator kapısı.** `fo4_validate_nif`'e `textures_root` geçen **DDS varlık + format** kapısı ekle (diffuse=99, normal=98/BC5 doğrula). Audit: validator şu an DDS başlığını parse etmiyor.

**Doğrulama:** `make_coupon_assets.py` yeniden çalıştır → BGSM+DDS byte-doğru, validator yeni kapıdan geçer.

---

## Faz C — Geometri writer (NiflySharp, otonom + 1 GPL kararı, M)

Keyfi mesh + tangent yolu; `_tri_header` 100-vs-76 offset tahminini öldürür.

- **C1 — GPL-firewall kararı (gated checkpoint).** NiflySharp/nifly = **GPL-3.0**. Mevcut desen: GPL araçları **subprocess-izole** ([[cpp-toolchain-tier3]] firewall'u). NiflySharp .NET kütüphanesi → küçük bir CLI exe'ye sarılıp shell-out edilir (managed ama ayrı süreç). **Karar:** subprocess-izolasyon (önerilen, desene uygun) vs byte-poking'de kalma.
- **C2 — `fo4_nif_build` aracı.** NiflySharp ile BSTriShape geometri yaz: vertex/normal/UV/**tangent-bitangent** + BSLightingShaderProperty + material path + OBND/bounds recalc. Header'da tangent/UV flag'lerini doğru deklare et (yoksa motor yok sayar). Mirror-UV binormal işaret kontrolü.
- **C3** PyNifly fallback: karmaşık authoring için `blender --background --python` ile headless sür (geometri güvenilir; collision'a dokundurma).

**Doğrulama:** Düz olmayan bir test mesh'i (ör. eğri kart) → NiflySharp export → NifSkope "Update Tangent Space" ile karşılaştır → tangent/bounds doğru; validator geçer.

---

## Faz D — Headless convex collision (otonom, M–L)

Audit'in "gerçek tavan"ı. Numara: **MOPP'tan kaç** (MOPP yalnız üçgen-hassas concave için gerekir).

- **D1 — Convex hull üretici.** `scipy.spatial.ConvexHull` → `.vertices` (Vector4) + `.equations` (ax+by+cz+d düzlem = `bhkConvexVerticesShape` normal-düzlem formatı, birebir). Havok ölçeği (~nif/70) uygula.
- **D2 — Concave decomposition.** `coacd` (PyPI, MIT — NifSkope fo76utils GUI spell'inin altındaki *aynı* kütüphane) → N convex parça → `bhkListShape{ bhkConvexVerticesShape... }`. NiflySharp ile yaz.
- **D3 — Havok blok parametreleri.** `bhkRigidBody` (layer, motion type, mass, friction) + Havok material → vanilla donörlerden RE/kalibrasyon (sınırlı deneme; havok-settle testi Faz E ile otomatik doğrular).
- **D4 — Entegrasyon.** Convex yol = birincil headless üretici (mobilya/prop/buildable/mimari çoğunluğu). **Donör-splice = fallback** yalnız piksel-hassas concave (MOPP/compressed-mesh) nadir kuyruğu için.

**Doğrulama:** Custom mesh → convex collision → in-game **havok-settle** (Faz E otomatik): item zemine düşüp doğru oturuyor mu; `placeatme` + içine yürü → bloke ediyor mu.

---

## Faz E — Otomatik görsel doğrulama (gated: oyun launch, M)

Audit'in **#1 kalan riski** (in-game görsel render kanıtsız) + her fazın evrensel doğrulayıcısı. Community'de eşi yok.

- **E1 — Screenshot capture.** Tier-3 F4SE harness'i genişlet: `player.additem`/`placeatme` → engine screenshot cmd (veya DXGI desktop-duplication) ile pencere yakala. (Not: GPU+pencere şart — "headless"=gözetimsiz, GPU'suz değil; RTX 3080 mevcut.)
- **E2 — Vision-model verdict.** Screenshot'ı multimodal modele okut: "kupon Pip-Boy preview'da render etti mi? oryantasyon/scale doğru? texture doğru renk? collision havok-settle oturdu mu?" → otomatik PASS/FAIL. Boş-bölge piksel kontrolünden tam-semantik yargıya kadar.
- **E3 — Audit kapanışı.** Mevcut 6 kuponu E1+E2 ile çalıştır → "disk-validated"ı **"in-game verified"e** çevir. Tüm offline-döngüsel "PASS"lerin gerçek kapanışı budur.

**Doğrulama:** Bilerek bozuk bir asset (collision'sız / yanlış-renk DDS) → harness FAIL döndürmeli (yanlış-negatif yok).

---

## Faz F — Ghidra ekseni (gated, ayrı eksen)

Asset pipeline'dan **bağımsız**; audit sonrası **asset-loader RE use-case'i düştü** → değer crash-decompile + offset-pin'de. (Kurulum zaten tamam: bkz [[ghidra-mcp-integration]].)

- **F1 — BN-1 register (gated, S).** Repo-kökü `.mcp.json` + MANIFEST + TASKS; Claude Code restart. Diff sunulup onaylanacak.
- **F2 — BN-2 Fallout4.exe analizi (gated, L).** Steam'den kopyala → analyzeHeadless (saatler, çok-GB). **Demote edildi**: artık yalnız crash-decompile (OS-41) + OS-39 offset-pin için; asset RE için değil. Kullanıcı tetikler.

---

## Bağımlılık grafiği

```
A (hardening) ──► B (materyal+texture) ──────────────┐
                                                       ├─► E (görsel doğrulama) ──► audit kapanışı
C (NiflySharp geometri) ──► D (convex collision) ─────┘
   └─ C1 GPL kararı (gated)        └─ Havok kalibrasyonu D'de E ile doğrulanır

F (Ghidra) ── tamamen paralel, bağımsız
```

- **D, C'ye bağımlı** (ikisi de NiflySharp blok-writer'ı kullanır).
- **E keystone**: B'nin texture'ını, C'nin geometrisini, D'nin collision'ını oyun-içi doğrular → tüm pipeline self-verifying olur. Ama gated (oyun launch).
- **B bağımsız + en yüksek anlık değer** (2 somut audit defekti, MIT-temiz).

## Lisans / GPL-firewall

- **Temiz (doğrudan referans):** MaterialLib (MIT), texconv (MIT), scipy (BSD), CoACD (MIT).
- **GPL-3.0 (subprocess-izole):** NiflySharp / nifly → ayrı CLI exe, shell-out. Mevcut firewall desenine uygun (Faz C1 kararı).

## Açık kararlar (bekleme noktaları)

1. **C1** — NiflySharp GPL: subprocess-izolasyon (önerilen) vs byte-poking'de kalma.
2. **E** — oyun launch ne zaman (görsel doğrulama gated).
3. **F1** — Ghidra `.mcp.json` register onayı (diff sunulacak).
4. **F2** — Fallout4.exe ağır analiz tetiği.

## Önerilen sıra

**A → B** otonom hemen (ucuz, en somut defektler, MIT-temiz). Paralelde **C1 kararını** al → **C → D**. **E** ilk oyun-launch fırsatında (her şeyi doğrular). **F** ayrı eksende istediğin zaman.
