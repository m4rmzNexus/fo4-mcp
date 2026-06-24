# Faz E — Otomatik Görsel Render Doğrulama (SPEC)

**Tarih:** 2026-06-24
**Tür:** SPEC ONLY (`kind=spec`) — **hiçbir oyun launch'ı yapılmadı, hiçbir DLL rebuild edilmedi.**
**Roadmap:** `docs/blender-asset-pipeline-completion-roadmap.md` §Faz E (K1 + audit kapanışı).
**Kapatılan gap:** `fo4-flat-misc-render-3-causes` memory'sinin "in-game RENDER still PENDING" durumu
(düz MISC kupon Pip-Boy preview'ı diskte doğrulandı ama oyun-içi render kanıtsız).

> **GATED.** Bu belge bir *plan*. E1'in capture aşaması GERÇEK bir oyun launch'ı (`dry_run=False`)
> gerektirir: makine-kilitli, Steam-login gerektiren (yoksa FO4 ~25MB DRM stub olarak ölür ve plugin
> inject olmaz — `ingame_test.py:349-356`), kullanıcı-tetiklemeli bir adım. Bir gerçek render PASS'ı
> **asla** iz olmadan iddia edilemez (HARD RULE): staged PNG + diag jobid satırı + agent verdict üçlüsü
> şart. Bu belge yazıldı; yürütme açık bekleme noktası (Faz E bekleme noktası #2).

---

## 0. Tek-cümle akış

Bir item'ı oyuna yerleştir/equip et → deterministik bir frame'de **ekran görüntüsü yakala** →
yakalanan PNG'yi `staging/render-verify/` altına stage et → **pure-Python piksel pre-screen** (boş-preview
auto-FAIL) → **multimodal agent (bu Claude Code, Opus 4.8) görsel rubric** uygular → yapısal PASS/FAIL+reason.
Hepsi PROVEN `fo4_run_ingame_test` harness'inin üstüne biner — **yeni bir kanal kurulmaz, mevcut runner
genişletilir.**

```
spec{commands+capture}  ──render_job──►  ingame-job.txt (+ shot satırı)
        │                                       │
   fo4_run_ingame_test (dry_run=False)     runner DLL (RunTestSequence)
        │                                       │ post_ms penceresi:
        │                                       │   cmd... → [shot] AddUITask → qqq AddUITask
        ▼                                       ▼
  pre/post ScreenShot diff  ◄── ScreenShot<N>.png (oyun root'a YAZAR; biz sadece OKURUZ)
        │                       VEYA DXGI grab → staging/render-verify/<jobid>.png (tercih edilen)
        ▼
  shutil.copy → staging/render-verify/<jobid>.png   (check_write ALLOW)
        │
        ▼
  pure-Python pre-screen (variance/non-bg-fraction)  ── boş ise auto-FAIL
        │
        ▼
  ok({screenshot_path, render_prescreen, render_verdict=None})  ◄── envelope'da path döner
        │
        ▼
  PARENT AGENT: Read(screenshot_path) → 4-nokta rubric → render_verdict=PASS|FAIL + render_reason
```

---

## 1. `fo4_run_ingame_test`'i NASIL genişletir (kanal değil, mod)

Render-verify **mevcut tool'un bir modudur**, yeni bir tool değil. `server.py:483-497` wrapper'ı tüm
`spec` dict'ini değiştirmeden forward ettiği için yeni anahtarları taşır; sadece docstring'i güncellenir.
İsteğe bağlı ince bir `fo4_verify_render` convenience wrapper (aynı `_safe(lambda: ...)` deseni) eklenebilir
ama zorunlu değil.

### 1.1 Yeni `spec` anahtarları (`ingame_test.py` / `render_job`)

| Anahtar | Tip | Anlam |
|---|---|---|
| `capture` | dict\|None | render-verify'i AÇAR. `{"mode": "dxgi"\|"screenshot", "region"?: [x,y,w,h], "settle_ms"?: int}` |
| `capture.mode` | str | `"dxgi"` (tercih edilen — PNG'yi doğrudan `staging/`'e yazar) veya `"screenshot"` (engine console cmd, oyun root'a yazar, biz okur+kopyalarız) |
| `capture.region` | [int×4]\|None | preview pane crop kutusu `[x,y,w,h]`; pre-screen ve agent bunu kullanır. None = full frame |
| `capture.settle_ms` | int | son cmd ile shot arası ekstra bekleme (preview pane'in render etmesini garanti eder); default 1500 |

`render_job()` `navtest` ile **tamamen paralel** bir `shot` direktifi emit eder (mevcut `nav_line`
kalıbı, `_bad()` validasyon stili). Job dosyasına eklenecek satır:

```
shot <mode> <settle_ms> [x y w h]
```

Validasyon (mevcut `_navint` deseniyle, `render_job` içinde):

```python
# --- ILLUSTRATIVE (GATED — henüz koda inmedi) ---
shot_line: str | None = None
cap = spec.get("capture")
if cap is not None:
    if not isinstance(cap, dict):
        raise _bad("spec.capture must be a dict {mode, region?, settle_ms?}", {"capture": cap})
    mode = str(cap.get("mode", "dxgi")).strip()
    if mode not in ("dxgi", "screenshot"):
        raise _bad("capture.mode must be 'dxgi' or 'screenshot'", {"mode": mode})
    settle = cap.get("settle_ms", 1500)
    if not isinstance(settle, int) or isinstance(settle, bool) or settle < 0:
        raise _bad("capture.settle_ms must be a non-negative int", {"settle_ms": settle})
    region = cap.get("region")
    reg_txt = ""
    if region is not None:
        if (not isinstance(region, list) or len(region) != 4
                or not all(isinstance(v, int) and not isinstance(v, bool) and v >= 0 for v in region)):
            raise _bad("capture.region must be [x, y, w, h] non-negative ints", {"region": region})
        reg_txt = " " + " ".join(str(v) for v in region)
    shot_line = f"shot {mode} {settle}{reg_txt}"
# ... emit AFTER the cmd lines, BEFORE return (navtest ile aynı yerde):
# if shot_line: lines.append(shot_line)
```

> **Not (navtest mutual-exclusion):** `navtest` ile `capture` aynı koşuda mantıken çakışır (biri pathing
> poll'ü, diğeri frame yakalama yapar). Spec ikisi birlikte verilirse `_bad("navtest and capture are
> mutually exclusive")` ile reddetmeyi şart koşar — runner post_ms penceresi tek amaçlıdır.

### 1.2 Yeni dönüş anahtarları (`ok({...})` envelope)

| Anahtar | Tip | Kim doldurur |
|---|---|---|
| `screenshot_path` | str\|None | orchestrator — `staging/render-verify/<jobid>.png` (abs) |
| `render_prescreen` | dict\|None | orchestrator — `{variance, non_bg_fraction, blank, region}` |
| `render_verdict` | "PASS"\|"FAIL"\|None | **None** orchestrator'dan döner; PARENT AGENT görsel inceleme sonrası doldurur |
| `render_reason` | str\|None | aynı — agent'ın tek-satır gerekçesi |
| `shot_confirmed` | bool\|None | orchestrator — `[shot] ... jobid=<hex>` provenance satırı bu koşuya bağlandı mı (job_confirmed klonu) |

Orchestrator **asla** `render_verdict` üretmez — semantic yargı agent'ın işi. Orchestrator sadece
(a) frame'i deterministik yakalatır, (b) bu koşuya bağlar (provenance), (c) ucuz blank-FAIL pre-screen'i
hesaplar. `render_prescreen.blank == True` ise envelope zaten `render_verdict="FAIL"` (auto, agent'a
gerek yok) + `render_reason="blank preview region (variance below threshold)"` döndürür.

### 1.3 Capture sub-spec'in orchestrator akışı (`fo4_run_ingame_test`)

`screenshot` modu için `_list_crash_logs`/`_newest_new_crash` snapshot-diff kalıbının **birebir klonu**:

```python
# --- ILLUSTRATIVE (GATED) — _list_crash_logs/_newest_new_crash'in aynası ---
def _list_shots(game_root: Path) -> set[Path]:
    try:
        return {p for p in game_root.glob("ScreenShot*.png") if p.is_file()}
    except OSError:
        return set()

def _newest_new_shot(game_root: Path, before: set[Path]) -> Path | None:
    new = [p for p in _list_shots(game_root) if p not in before]
    return max(new, key=lambda p: p.stat().st_mtime) if new else None
```

Akış (mevcut appeared/exited/qqq yaşam döngüsüne eklenir):

1. **Launch öncesi:** `capture.mode == "screenshot"` ise `pre_shots = _list_shots(cfg.fo4_install_dir)`
   (crash-log baseline'ı ile birebir). `dxgi` modunda gerek yok — DLL doğrudan staging'e yazar.
2. **Koşu:** mevcut gibi. Runner DLL, `RunTestSequence` post_ms penceresinde shot'ı AddUITask ile fırlatır
   (§2) ve `[shot] <abs-path> jobid=<hex>` diag satırı yazar.
3. **Provenance gate (job_confirmed klonu):** diag'da `[shot] <path> jobid=<job_id>` satırını grep'le.
   Bu satır YOKSA veya jobid eşleşmiyorsa → `shot_confirmed=False`, `render_verdict=None`,
   `render_reason="no shot provenance for this job"`. Stale bir ScreenShot'ın sessiz false-PASS
   olmasını bu gate engeller (mevcut `jobid_echoed` mantığının aynısı).
4. **Readback + stage:**
   - `dxgi`: DLL zaten `staging/render-verify/<jobid>.png` yazdı; orchestrator sadece var-olduğunu
     doğrular + path'i döner.
   - `screenshot`: `shot = _newest_new_shot(cfg.fo4_install_dir, pre_shots)`; `shutil.copy(shot,
     staging/render-verify/<jobid>.png)`. **Bu bir READ + staging'e COPY'dir — oyun root'a yazılmaz.**
     `check_write(staged, cfg.repo_root)` ALLOW döner (staging/ → `WriteDisposition.ALLOW`, `safety.py:39`).
5. **Pre-screen:** §3'teki pure-Python metric. `blank` ise envelope `render_verdict="FAIL"` (auto).
6. **Envelope:** `screenshot_path` + `render_prescreen` + `shot_confirmed` döner; `render_verdict` ya
   auto-FAIL ya None (agent dolduracak).

**Yeniden kullanılan mevcut altyapı:** `_read_text(diag_path)`, `_tasklist_ws_mb` (WS>200MB = gerçek oyun,
25MB stub değil), appeared/exited/qqq döngüsü, `_newest_new_crash` (capture başarısa bile bir CTD
verdict'i ezer — crash → render_verdict zorla FAIL), `cfg.fo4_install_dir` (screenshot scan),
`cfg.fo4_user_docs` (Fallout4Prefs.ini `iScreenShotIndex`).

---

## 2. Native runner (`tools/commonlibf4-template/src/main.cpp`) değişiklikleri

### 2.1 `Job` struct + `LoadJob()`

`navtest` verb'inün (satır 167-176) **tam paraleli** bir `shot` verb'i:

```cpp
// --- ILLUSTRATIVE (GATED — DLL rebuild+redeploy gerektirir) ---
// struct Job içine (navtest alanlarının yanına):
bool        shot{ false };
std::string shotMode;        // "dxgi" | "screenshot"
int         shotSettleMs{ 1500 };
int         shotRegion[4]{ 0, 0, 0, 0 };  // x,y,w,h; hepsi 0 = full frame

// LoadJob() while-döngüsünde, navtest else-if'inin yanına:
} else if (verb == "shot") {
    j.shot = true;
    is >> j.shotMode >> j.shotSettleMs;
    is >> j.shotRegion[0] >> j.shotRegion[1] >> j.shotRegion[2] >> j.shotRegion[3];
}
```

### 2.2 `RunTestSequence()` — post_ms penceresine shot ekle

Capture, mevcut son-cmd ile `qqq` AddUITask arasına (satır 351-361) girer — PROVEN UI loop kanalı:

```cpp
// --- ILLUSTRATIVE (GATED) ---
// ... commands AddUITask döngüsünden sonra, qqq'dan ÖNCE:
if (g_job.shot) {
    std::this_thread::sleep_for(std::chrono::milliseconds(g_job.shotSettleMs));
    if (const auto t = F4SE::GetTaskInterface()) {
        t->AddUITask([]() {
            std::string path = CaptureFrame(g_job);   // §2.3: dxgi -> staging, screenshot -> console
            Diag("[shot] " + path + " jobid=" + (g_job.jobId.empty() ? "-" : g_job.jobId));
        });
    }
    std::this_thread::sleep_for(500ms);  // shot dosyaya insin, sonra qqq
} else if (!g_job.navtest) {
    std::this_thread::sleep_for(std::chrono::milliseconds(g_job.postMs));
}
```

`[shot] <abs path> jobid=<hex>` diag satırı, Python tarafının zaten grep'lediği `[job] loaded:...jobid=`
ve `[NAVTEST]...VERDICT=` satırlarının (`ingame_test.py:411,428`) provenance kalıbını aynen taklit eder.

### 2.3 `CaptureFrame()` — iki mekanizma

```cpp
// --- ILLUSTRATIVE (GATED) ---
std::string CaptureFrame(const Job& j) {
    if (j.shotMode == "screenshot") {
        // (a) Engine'in kendi screenshot komutu. bAllowScreenshot=1 zaten set
        //     (Fallout4.ini'de doğrulandı). ScreenShot<iScreenShotIndex>.png OYUN
        //     ROOT'una yazılır (read-only Steam dizini — ama OYUN yazar, biz değil).
        //     Python tarafı pre/post snapshot-diff ile newest-appeared'ı bulup
        //     staging'e KOPYALAR. Path'i Python çözecek; biz placeholder döneriz.
        RE::Console::ExecuteCommand("screenshot");
        return "(game-root ScreenShot; python resolves via snapshot-diff)";
    }
    // (b) TERCİH EDİLEN: DXGI/D3D11 backbuffer grab; PNG'yi DOĞRUDAN staging/'e yaz.
    //     read-only-root readback'i tamamen atlar, frame'i tam kontrol eder.
    //     Windows SDK + CommonLibF4 (cpp-toolchain-tier3, GPL YOK) ile derlenir.
    std::string out = R"(C:\Modding\fo4-mcp\staging\render-verify\)" + j.jobId + ".png";
    GrabBackbufferToPng(out, j.shotRegion);   // yeni src/capture.cpp/.h, mevcut xmake.lua
    return out;
}
```

DXGI yolu için yeni bir `src/capture.cpp`/`.h` mevcut `xmake.lua` ile derlenir.

---

## 3. Pure-Python pre-screen (`ingame_test.py`, GPL-temiz)

Agent daha bakmadan **en pahalı false-positive'i (boş preview)** öldüren ucuz bir metric. Pillow varsa
kullan; yoksa stdlib `zlib` ile ham PNG chunk parse — **GPL imaging lib YOK** (lisans kuralı):

```python
# --- ILLUSTRATIVE (GATED) ---
def _prescreen_png(png: Path, region: list[int] | None) -> dict[str, Any]:
    """Boş-preview tespiti: crop'un piksel varyansı + non-background fraction.
    Pillow varsa onunla; yoksa pure-stdlib PNG decode (zlib). MIT-temiz."""
    try:
        from PIL import Image          # Pillow (PIL license, permissive) — opsiyonel
        im = Image.open(png).convert("RGB")
        if region:
            x, y, w, h = region
            im = im.crop((x, y, x + w, y + h))
        px = list(im.getdata())
    except ImportError:
        px = _decode_png_stdlib(png, region)   # zlib-only fallback, no deps
    n = max(1, len(px))
    lum = [0.299 * r + 0.587 * g + 0.114 * b for (r, g, b) in px]
    mean = sum(lum) / n
    var = sum((v - mean) ** 2 for v in lum) / n
    bg = px[0]                                  # köşe pikseli = background referansı
    non_bg = sum(1 for p in px if max(abs(a - b) for a, b in zip(p, bg)) > 16) / n
    blank = var < 12.0 or non_bg < 0.01         # near-uniform crop = boş preview
    return {"variance": round(var, 2), "non_bg_fraction": round(non_bg, 4),
            "blank": blank, "region": region}
```

`blank == True` → orchestrator `render_verdict="FAIL"` döner, agent çağrılmaz. Bu, `fo4-flat-misc-render`
defektinin (blank Pip-Boy preview) tam imzasıdır — clamp-mode=None / PTRN=None / zero-thickness hepsi
boş bir crop üretir, yani pre-screen onları agent'tan ÖNCE yakalar.

> scipy 1.18.0 + numpy 2.5.0 (BSD, kurulu) daha ağır bir metric istenirse mevcut, ama MVP pre-screen'in
> hiçbirine ihtiyacı yok — stdlib yeter.

---

## 4. Judge = agent'ın kendi multimodal Read'i (yeni API yok)

Orchestrator `screenshot_path`'i envelope'da döndürür. **Parent Claude agent (bu Claude Code, Opus 4.8
multimodal) `Read(screenshot_path)` ile PNG'yi görsel olarak inceler** ve yapısal bir rubric uygular.
Üçüncü-parti model yok, harici LLM SDK yok, provider wiring yok — **mevcut agent yargıçtır.**

### 4.1 4-nokta rubric (agent uygular)

| # | Soru | FAIL imzası | Hangi audit defektini yakalar |
|---|---|---|---|
| 1 | Preview pane **boş değil mi**? (item geometrisi var, placeholder/boş silhouette değil) | uniform/blank crop | collision-crash, PTRN=None, clamp=None, zero-thickness |
| 2 | **Oryantasyon + scale** makul mu? (edge-on değil, tek-piksel çizgi değil, ekranı taşmıyor) | edge-on flat / dev ölçek | PTRN yanlış TRNS, OBND=0 framing |
| 3 | **Texture rengi** doğru mu? (yıkanmış/aşırı-parlak değil = sRGB-vs-lineer DDS defekti yok) | sönük/yanmış renkler | DDS yanlış renk-uzayı (98 lineer vs 99 sRGB) |
| 4 | (collision/havok-settle koşusu) item **zemine oturdu** mu, clip/float etmiyor mu? | havada/zemine batmış | havok blok parametreleri (Faz D) |

Çıktı: `render_verdict ∈ {PASS, FAIL}` + tek-satır `render_reason`. Pre-screen `blank=True` döndüyse
agent'a hiç gelmez (auto-FAIL). Pre-screen geçtiyse agent semantic katmanı uygular.

### 4.2 Lisans yüzeyi: SIFIR

Capture = engine'in kendi `screenshot` komutu (kütüphane yok) VEYA Windows SDK + CommonLibF4 DXGI grab
(GPL yok). Python PNG = Pillow (permissive) veya stdlib zlib. Judge = döngüdeki Claude agent (model SDK
yok). NiflySharp/nifly (GPL) Faz E'ye hiç dokunmaz.

---

## 5. Screenshot capture seçenekleri — tradeoff

| | (a) Engine `screenshot` komutu | (b) DXGI/D3D11 backbuffer grab **(TERCİH EDİLEN)** |
|---|---|---|
| Çıktı yeri | Oyun ROOT'u (read-only Steam) → Python kopyalar | Doğrudan `staging/render-verify/<jobid>.png` |
| Read-only sınırı | Oyun YAZAR, biz READ+copy (izinli ama hook'a kanıtlanmalı) | **Hiç dokunmaz** — temiz |
| Frame kontrolü | Engine ne verirse | **Tam kontrol** (region crop, exact frame) |
| Ek native kod | Yok | Yeni `src/capture.cpp/.h` + DLL rebuild/redeploy |
| Bağımlılık | `bAllowScreenshot=1` + Steam F12 overlay keybind'i çalmamalı | RTX 3080 + gerçek pencere (mevcut) |
| Provenance | snapshot-diff (`_newest_new_shot`) + `[shot] jobid` | DLL doğrudan `<jobid>.png` yazar + `[shot] jobid` |
| Risk | stale ScreenShot false-PASS (snapshot-diff + jobid gate ile kapanır) | daha çok native surface debug |

**Karar (önerilen):** **(b) DXGI**, çünkü read-only-root coupling'i tamamen kaldırır ve `staging/`'e
doğrudan yazarak `check_write` ALLOW yolundan geçer. **(a)** daha düşük efor (DLL rebuild yok) ama
read-only readback'i bir kez canlı kutuda doğrulanmalı. İkisi de spec'te tutuldu; appetite'a göre seçilir.
**MVP başlangıcı (a) ile mümkün** (sıfır native değişiklik), **prod yol (b)**.

---

## 6. Gating — neden kullanıcı-tetiklemeli launch ŞART

- **Capture aşaması gerçek bir oyun launch'ı gerektirir** (`dry_run=False`). Bu makine-kilitli + uzun.
- **Steam login şart:** logout iken FO4 ~25MB DRM stub olarak açılır, plugin inject olmaz; orchestrator
  bunu `_steam_active_user()==0` ile zaten reddeder (`ingame_test.py:349-356`).
- **GPU + gerçek pencere şart:** "headless" burada *gözetimsiz-ama-GPU'lu* demek, GPU'suz değil. RTX 3080
  mevcut; gerçekten headless bir CI kutusu siyah frame üretir.
- **DXGI yolu** ek olarak runner DLL'in rebuild+redeploy'unu gerektirir (tooling adımı).
- **(a) yolu** read-only-folder readback'inin canlı kutuda bir kez doğrulanmasını gerektirir.

Bu, `fo4_run_ingame_test`'in kendi gate'ini ve roadmap Faz E'yi ("Gated: oyun launch") aynen yansıtır.
Bekleme noktası = roadmap §Açık kararlar #2.

---

## 7. Acceptance criteria — flat-MISC "in-game render pending" gap'ini kapatan

`fo4-flat-misc-render-3-causes` memory'sini "disk-validated, in-game pending" → "in-game verified"e
çevirmek için **6 shipped kuponun her biri** aşağıdaki tam zinciri geçmeli. PASS ancak ve ancak hepsi
doğruysa:

**AC-1 (provenance gate).** Diag'da `[shot] <abs path> jobid=<THIS-run-hex>` satırı var; `shot_confirmed=True`.
Stale/eksik shot → otomatik geçersiz (asla false-PASS).

**AC-2 (staged artifact).** `screenshot_path` `staging/render-verify/<jobid>.png` altında, dosya var,
`check_write` ALLOW (Steam/Docs'a yazılmamış). Bu, iddianın **izi**dir (HARD RULE).

**AC-3 (pre-screen geçti).** `render_prescreen.blank == False` — preview crop varyansı eşiğin üstünde,
non-bg-fraction > %1. (Boş = clamp/PTRN/thickness defektlerinin imzası.)

**AC-4 (agent verdict = PASS).** Parent agent `Read(screenshot_path)` ile 4-nokta rubric'i (§4.1)
uyguladı: (1) preview boş değil + (2) oryantasyon/scale makul + (3) texture rengi doğru (sRGB defekti
yok) + (4) (varsa) havok-settle oturmuş → `render_verdict="PASS"` + gerekçe.

**AC-5 (no crash).** `crashed == False` — aynı koşuda yeni bir `crash-*.log` belirmedi (mevcut
`_newest_new_crash` gate). Bir CTD render_verdict'i zorla FAIL eder.

**AC-6 (ADVERSARIAL CONTROL — zorunlu, roadmap §Doğrulama).** Bilerek BOZUK bir asset AYNI harness'ten
geçirilir ve verdict **FAIL** dönmeli. En az bir bozuk varyant:
  - collision'sız nif (havok blob yok) → crash veya boş-preview FAIL, **veya**
  - yanlış-renk-uzayı DDS (lineer-olarak-encode edilmiş diffuse) → rubric #3 FAIL, **veya**
  - mesh'siz / clamp=None nif → blank-preview pre-screen auto-FAIL.

  > **Bir broken control'ü PASS eden pipeline kendisi bozuktur ve tüm doğrulama geçersizdir.** Bu negatif
  > test spec'in parçası, opsiyonel değil. False-positive (boş-değil-ama-YANLIŞ render) audit'in #1 riski;
  > savunma = adversarial control + pre-screen + sıkı rubric, asla tek çıplak görsel bakış değil.

**Gap kapanışı:** AC-1..AC-5 her 6 kuponda PASS **VE** AC-6 broken-control FAIL ⟹ `fo4-flat-misc-render`
memory + TASKS.md "in-game pending" → "in-game verified" (iz: 6× staged PNG + diag jobid satırları +
agent verdict'leri + broken-control FAIL trace'i).

---

## 8. Örnek spec (ILLUSTRATIVE — GATED, çalıştırılmadı)

Bir kuponu envantere ekle, Pip-Boy MISC preview'ını aç, DXGI ile yakala:

```jsonc
// fo4_run_ingame_test(spec, dry_run=False)  ← GATED: gerçek launch
{
  "save": "quickload",
  "resolves": [
    { "key": "COUPON", "plugin": "PrewarCoupons.esp", "form_id": "0x800" }
  ],
  "commands": [
    "player.additem {COUPON} 1",
    "tm",                          // HUD gizle (deterministik frame)
    "showinventory"                // (illüstratif) MISC preview'ı framele
  ],
  "capture": {
    "mode": "dxgi",                // PNG'yi doğrudan staging/render-verify/<jobid>.png'e
    "settle_ms": 2000,             // preview pane render etsin
    "region": [620, 180, 680, 720] // Pip-Boy 3D preview pane crop
  },
  "appear_timeout_s": 240,
  "run_timeout_s": 180
}
```

Beklenen envelope (orchestrator döner; `render_verdict` agent doldurur):

```jsonc
{
  "ok": true,
  "screenshot_path": "C:\\Modding\\fo4-mcp\\staging\\render-verify\\<jobid>.png",
  "shot_confirmed": true,
  "render_prescreen": { "variance": 84.3, "non_bg_fraction": 0.21, "blank": false, "region": [620,180,680,720] },
  "render_verdict": null,          // ← parent agent Read(screenshot_path) sonrası PASS|FAIL
  "render_reason": null,
  "crashed": false,
  "appeared": true, "exited": true, "sequence_completed": true
}
```

---

## 9. Riskler (audit'ten taşındı)

1. **False-positive (#1 risk):** boş-değil ama YANLIŞ render (mirror-UV, yanlış-renk DDS, placeholder
   mesh) PASS okunabilir. Azaltma = **zorunlu adversarial control** (AC-6) + piksel pre-screen + sıkı
   rubric; asla tek çıplak görsel bakış.
2. **Read-only sınırı:** (a) yolu ScreenShot'ı read-only oyun ROOT'una yazar. OYUN yazar (bizim tool
   değil), biz READ+copy ederiz; PreToolUse path hook'unu tetiklemediği bir kez doğrulanmalı. (b) DXGI
   yolu sorunu tamamen atlar → güvenli primary.
3. **Determinizm:** load ortasında / HUD açıkken / preview pane render etmeden alınan shot yanıltır.
   Açık kamera/HUD setup cmd'leri (`tm`/`tfc`/Pip-Boy-aç) + shot öncesi settle gap şart; flaky load
   timing bilinen runner gerçeği (plugin zaten `GetParentCell`'i poll'ler, load mesajına güvenmez).
4. **"Headless" = gözetimsiz-GPU'lu, GPU'suz değil:** capture gerçek pencere + RTX 3080 ister (mevcut).
5. **Provenance:** önceki koşudan kalma bir ScreenShot bu koşununki sanılabilir. pre/post snapshot-diff
   + `[shot] jobid` echo gate ile azaltılır (mevcut `job_confirmed` mantığının klonu); o olmadan stale
   görüntü sessiz false-PASS olur.
6. **(a) bağımlılığı:** `bAllowScreenshot=1` kalmalı + Steam F12 overlay keybind'i çalmamalı; console
   `screenshot` komut yolu simüle keypress'ten daha güvenilir.
7. **(b) bedeli:** DLL rebuild+redeploy + yeni derlenen capture unit (daha çok native debug surface) —
   (a)'dan ağır ama read-only-folder coupling'i kaldırır; appetite'a göre seç.

---

## 10. Bağımlılıklar + entegrasyon noktaları (özet)

| Dosya | Değişiklik |
|---|---|
| `mcp-server/fo4_mcp/ingame_test.py` | `render_job` → `shot` direktif emitter + `capture` validasyonu (`navtest` paraleli); `fo4_run_ingame_test` → `_list_shots`/`_newest_new_shot` (capture-a), shot provenance gate (`job_confirmed` klonu), `_prescreen_png`, yeni envelope anahtarları |
| `tools/commonlibf4-template/src/main.cpp` | `Job`'a shot alanları; `LoadJob()`'a `shot` verb (`navtest` paraleli, satır 167-176); `RunTestSequence()`'a post_ms penceresinde shot AddUITask (satır 351-361 arası); `CaptureFrame()`; `[shot] <path> jobid=` diag satırı |
| `tools/commonlibf4-template/src/capture.cpp/.h` (yeni) | DXGI/D3D11 backbuffer grab (sadece (b) yolu); mevcut `xmake.lua` ile derlenir |
| `mcp-server/fo4_mcp/server.py:483-497` | `fo4_run_ingame_test` docstring'ine `capture`/render alanları (yeni tool kaydı YOK); opsiyonel `fo4_verify_render` ince wrapper |
| `mcp-server/fo4_mcp/safety.py` | değişiklik YOK — `staging/render-verify/` zaten `staging/` ALLOW'una düşer (satır 39) |
| `mcp-server/fo4_mcp/config.py` | değişiklik YOK — `fo4_install_dir` + `fo4_user_docs` zaten çözülü |
| `mcp-server/tests/test_ingame_test.py` | yeni: `render_job` shot-line emit + capture-validasyon birim testleri (pure, launch'sız — `navtest` testlerinin paraleli) |

---

## Kapanış

Bu SPEC, PROVEN `fo4_run_ingame_test` harness'ine **yeni `spec.capture` modu** + **runner `shot`
direktifi** + **pure-Python blank-preview pre-screen** + **agent'ın kendi multimodal Read'i ile 4-nokta
rubric judge** ekleyerek otomatik in-game görsel render doğrulamasını tanımlar. Yeni kanal, yeni API,
yeni model SDK YOK. Capture aşaması GATED (kullanıcı-tetiklemeli oyun launch). Flat-MISC "in-game render
pending" gap'i, 6 kuponun §7 acceptance criteria'sını (provenance + staged PNG + pre-screen + agent PASS
+ no-crash) **VE** zorunlu adversarial broken-control FAIL'ini geçmesiyle kapanır — asla iz olmadan.
