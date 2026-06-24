# Faz F — Ghidra-MCP `.mcp.json` register önerisi (PROPOSAL ONLY)

> **Bu bir öneri belgesidir — hiçbir config dosyası yazılmadı.** Sadece bu markdown
> üretildi. Repo kökü `.mcp.json`'ı yazmak (=Claude Code MCP server kaydı) **açık
> kullanıcı onayı + Claude Code restart** gerektirir (CLAUDE.md §3 + §1 "karar/GUI
> gerektiren işi yapma → bekleme noktası"). Aşağıdaki içerik **donduruldu + diff
> olarak sunuldu**; kullanıcı onayladıktan sonra yazılır.
>
> İlgili memory: [[ghidra-mcp-integration]] · runbook: `docs/ghidra-mcp-setup.md`
> · roadmap kalemi: TASKS.md Session 11 "Faz F (gated): `.mcp.json` register (BN-1)".

---

## 0. Özet (TL;DR)

bethington/ghidra-mcp 5.14.1 köprüsü (`bridge_mcp_ghidra.py`) zaten `tools/`'ta kurulu
ve uçtan-uca kanıtlanmış (headless server kendi `commonlibf4-template.dll`'imizi
decompile etti). Geriye **tek adım** kaldı: bu köprüyü Claude Code'a bir **stdio MCP
server** olarak repo kökü `.mcp.json`'da kaydetmek.

- `.mcp.json` **yalnızca köprüyü** başlatır. Köprü = `stdio ⇄ HTTP(:8089)` çoğullayıcı.
- **Ghidra backend** (HTTP :8089'u host eden) AYRI başlatılır (Yol A GUI / Yol B headless)
  ve asıl ağır/gated adımdır. Köprü, backend yokken de açılır ama her çağrı
  "connection refused" verir → **"önce Ghidra'yı başlat" adımı zorunlu**.
- **Fallout4.exe analizi** = saatlerce süren, çok-GB DB, kullanıcı-tetikli ayrı iş (BN-2).

Üç bağımsız gate (hepsi tasarım gereği açık bırakıldı):
| Gate | Ne | Durum |
|---|---|---|
| **BN-1** | repo kökü `.mcp.json` yazımı + Claude Code restart | bu belge ile sunuldu, **yazılmadı** |
| Backend | Ghidra :8089'u host etmeli (Yol A/B) | `.mcp.json` bunu başlatmaz — ayrı |
| **BN-2** | Fallout4.exe full analiz (kopyala→import, saatler) | kullanıcı-tetikli, scope dışı |

---

## 1. Önerilen repo kökü `.mcp.json` (TAM içerik — frozen)

**Hedef path:** `C:/Modding/fo4-mcp/.mcp.json` (henüz YOK — doğrulandı; repo kökü
`CLAUDE.md`/`TASKS.md` kardeşi). Claude Code server'ları **repo kökünden** başlatır
(köprü dizininden değil) ve server şemasında `cwd` anahtarı **yoktur** → bu yüzden
hem köprü yolu hem python interpreter **mutlak yol** olarak verilir.

```json
{
  "mcpServers": {
    "ghidra-mcp": {
      "command": "C:/Users/m4rmz/AppData/Local/Programs/Python/Python312/python.exe",
      "args": [
        "C:/Modding/fo4-mcp/tools/ghidra-mcp/bridge_mcp_ghidra.py",
        "--transport", "stdio",
        "--lazy",
        "--default-groups", "listing,function,program"
      ],
      "env": {
        "GHIDRA_MCP_URL": "http://127.0.0.1:8089",
        "GHIDRA_DEBUGGER_URL": "http://127.0.0.1:8099",
        "PYTHONIOENCODING": "utf-8"
      }
    }
  }
}
```

### Neden tam bu içerik (load-bearing kararlar)

- **`command` = mutlak python (Python312)** — upstream şablon `"python"` (PATH'e
  güvenir) kullanıyor; bizde CLAUDE.md/ENV bu interpreter'ı pinliyor ve `mcp`+`requests`
  bağımlılıkları onda mevcut (doğrulandı). Mutlak yol = deterministik launch.
- **`args[0]` = mutlak köprü yolu** — upstream `tools/ghidra-mcp/.mcp.json` göreceli
  `"bridge_mcp_ghidra.py"` veriyor; Claude Code repo kökünden başlattığı ve `cwd` yok
  olduğu için göreceli yol **kırılır**. Mutlak yol bunu çözer.
- **`--lazy` AÇIKÇA verildi** — köprüde `--lazy` **default OFF** (arg parser
  line 2214-2217: `default=False`, help: "not recommended for Claude Code"). Omit
  edilirse 251 aracın tamamı yüklenir ve tool-context boğulur — lazy modun var olma
  sebebi tam bu failure mode. **Bizim use-case'imiz için açıkça pasifleştirilemez.**
- **`--default-groups listing,function,program`** — bağlanınca yalnız çekirdek
  decompile/list/xref/search yüklenir (~3 grup); diğer ~248 araç **talep üzerine**
  `search_tools()`/`list_tool_groups()`/`load_tool_group()` ile keşfedilir (Claude Code
  `tools/list_changed` destekler). Bu zaten köprünün default grup seti ama açıkça
  veriliyor (drift'e karşı).
- **`PYTHONIOENCODING=utf-8` ZORUNLU (cosmetic DEĞİL)** — köprünün help/log metni
  U+2194 `⇄` (ve `—` em-dash) içerir; bu Windows konsolunda default cp1252 codec'i
  bunu encode edemez → `UnicodeEncodeError` ile startup'ta **çöker**. Bu env var
  düşerse server hiç açılmaz. (Reality-check: `--help` utf-8 ile EXIT=0; bkz §5.)
- **`GHIDRA_MCP_URL=http://127.0.0.1:8089`** — köprünün backend'i bulduğu adres
  (köprü `GHIDRA_MCP_URL` env'ini okur; default `http://127.0.0.1:8089`). Loopback.
- **`GHIDRA_DEBUGGER_URL=http://127.0.0.1:8099`** — debugger proxy server adresi.
  Default başlatılmaz ve scope dışı (runtime debug'ı Tier-3 F4SE veriyor). Zararsız;
  yalnız debugger backend'i ayağa kalkarsa anlam kazanır. Upstream şablonla uyum için
  tutuldu.

---

## 2. Upstream şablon ile fark (neden kopyalamadık)

Mirror alınacak şablon: `tools/ghidra-mcp/.mcp.json` (zaten env'leri taşıyor ama
Claude Code repo-root scope'una uygun değil):

```json
{
  "mcpServers": {
    "ghidra-mcp": {
      "command": "python",                       // ← mutlak Python312'ye değişti
      "args": ["bridge_mcp_ghidra.py",           // ← mutlak yola değişti (cwd yok)
               "--transport", "stdio"],          // ← --lazy + --default-groups eklendi
      "env": { GHIDRA_MCP_URL, GHIDRA_DEBUGGER_URL, PYTHONIOENCODING }  // ← aynen korundu
    }
  }
}
```

3 zorunlu adaptasyon: (1) `command` → mutlak python, (2) `args[0]` → mutlak köprü yolu,
(3) lazy flag çifti eklendi. Env bloğu birebir korundu.

---

## 3. `tools/MANIFEST.md` eklentisi (öneri — YAML-blok konvansiyonuna uyumlu)

`tools/MANIFEST.md`'de **henüz ghidra girdisi yok** (doğrulandı). Aşağıdaki blok,
dosyanın per-tool YAML konvansiyonuna (`name`/`version`/`source`/`binary_path`/
`license`/`downloaded`/`sha256`/`notes`) uyacak şekilde, mantıken JDK/Maven
kardeşlerinin yanına (CommonLibF4/template clone bloklarından sonra) eklenir:

```yaml
## ghidra-mcp (bethington — native-RE ekseni)

name: ghidra-mcp (bethington)
version: 5.14.1
source: https://github.com/bethington/ghidra-mcp
asset: git clone (built extension: target/GhidraMCP-5.14.1.{jar,zip})
binary_path: tools/ghidra-mcp/bridge_mcp_ghidra.py   # stdio<->HTTP(:8089) köprüsü
binary_path_alts: |
  tools/ghidra-mcp/target/GhidraMCP-5.14.1.zip   # Ghidra extension (deploy)
  tools/ghidra-mcp/target/GhidraMCP-5.14.1.jar   # plugin jar
  tools/ghidra/ghidra_12.1.2_PUBLIC/             # Ghidra 12.1.2 (kardeş, ayrı girdi)
  tools/jdk/jdk-21.0.11+10/                       # JDK 21 (ReSaver shim'iyle paylaşımlı)
  tools/apache-maven-3.9.9/                       # Maven 3.9.9 (build backend)
license: Apache-2.0 (temiz — GPL contagion YOK; ama dağıtılmaz, tools/ gitignored)
downloaded: 2026-06-24
sha256: N/A (git clone + Maven-built artifact; provenance = upstream repo + reproducible build)
notes: |
  Native reverse-engineering ekseni. Köprü (`bridge_mcp_ghidra.py`) = stdio ⇄ HTTP(:8089)
  çoğullayıcı; proje Python312 ile çalışır (mcp + requests bağımlılıkları mevcut —
  doğrulandı). Ghidra (GUI plugin VEYA headless server) HTTP :8089'u host eder; köprü
  yalnız multiplex eder, backend'i AYRI başlatırsın. Lazy mod
  (`--lazy --default-groups listing,function,program`) 251 aracı context'ten uzak tutar;
  ~3 çekirdek grup connect'te yüklenir, gerisi talep üzerine (search_tools/load_tool_group).
  Headless server Windows'ta PROVEN — kendi commonlibf4-template.dll'imizi PDB-sembolüyle
  decompile etti (224 REST endpoint). **.mcp.json register = Faz F user-gated (BN-1; bu
  belge frozen content + diff sunuyor).** Fallout4.exe analizi = saatler, kullanıcı-tetikli
  (BN-2): önce exe'yi `tools/ghidra/projects/bin/`'e KOPYALA, sonra import — Steam Data'nın
  YAZMA tarafına ASLA dokunma. Decompile DB'leri (`tools/ghidra/projects/`) gitignored,
  dağıtılmaz (Address Library / CommonLibF4 RE-artefakt duruşuyla aynı, Karar 7).
  Kurulum + Yol A/B runbook: docs/ghidra-mcp-setup.md. PYTHONIOENCODING=utf-8 ZORUNLU
  (köprü help/log'unda U+2194 '⇄' var → cp1252 konsolunda yoksa UnicodeEncodeError startup-crash).
```

---

## 4. `TASKS.md` backlog girdisi (öneri)

Session 11 satırındaki **"Faz F (gated): `.mcp.json` register (BN-1, diff sunulacak)"**
kalemi şu şekilde güncellenir (checkbox done-with-design, BN-2 açık kalır):

```text
[~]→[x design-frozen] Faz F / Ghidra-MCP .mcp.json register (BN-1):
  - Önerilen repo-kökü .mcp.json içeriği DONDURULDU + diff sunuldu
    → docs/faz-f-ghidra-register-proposal.md
  - Köprü komutu reality-checked: `python312 bridge_mcp_ghidra.py --transport stdio
    --lazy --default-groups listing,function,program` → --help EXIT=0
  - PYTHONIOENCODING=utf-8 LOAD-BEARING kanıtlandı (yoksa U+2194 cp1252 startup-crash)
  - mutlak python + mutlak köprü yolu zorunlu (Claude Code'da cwd anahtarı yok →
    göreceli upstream yol kırılır)
  - --lazy AÇIKÇA verilmeli (köprüde default OFF; omit = 251 araç context-flood)
  - KALAN kullanıcı adımı: .mcp.json diff'ini onayla → dosyayı yaz → Claude Code restart
  - BN-2 (Fallout4.exe analizi, saatler) AÇIK / kullanıcı-tetikli kalır
```

§Kullanıcı-gated backlog'a iki net madde:
- **BN-1:** `.mcp.json` yaz + Claude Code restart (içerik §1'de frozen).
- **BN-2:** Fallout4.exe analizi (§6 runbook; saatler, çok-GB DB).

---

## 5. Reality-check kanıtı

Bu belge yazılmadan önce doğrulananlar (bu makinede, bu oturum):

| Kontrol | Komut | Sonuç |
|---|---|---|
| Köprü argümanları parse oluyor mu | `python312 bridge_mcp_ghidra.py --help` (env `PYTHONIOENCODING=utf-8`) | **EXIT=0**; `--transport`/`--lazy`/`--no-lazy`/`--default-groups` listelendi |
| utf-8 load-bearing mi | yukarıdaki — `⇄`/`—` içeren help metni | utf-8 ile temiz render; çıplak cp1252'de `UnicodeEncodeError` (research bulgusu) |
| `--lazy` default'u | arg parser line 2214-2217 | `default=False` (OFF) → açıkça verilmeli |
| `--default-groups` default'u | arg parser line 2225-2231 | `listing,function,program` (açıkça verildi, drift-koruma) |
| repo-kökü `.mcp.json` var mı | `Test-Path C:/Modding/fo4-mcp/.mcp.json` | **False** (yok — yeni yazılacak) |
| python yolu çözülüyor mu | `Get-Command ...Python312\python.exe` | çözüldü; `mcp`+`requests` mevcut (research) |

---

## 6. Kullanıcı-onay adımları (review → approve → restart → analiz)

### Adım 1 — `.mcp.json` diff'i incele (BN-1)
- §1'deki içerik = yazılacak tam dosya. Yeni dosya olduğundan diff = tüm içerik (add).
- Doğrula: mutlak python yolu doğru, mutlak köprü yolu doğru, 3 env var mevcut.

### Adım 2 — Onayla + yaz
- Kullanıcı onayı sonrası ajan `C:/Modding/fo4-mcp/.mcp.json`'ı §1 içeriğiyle yazar
  (tek dosya, repo kökü). Bu **tek gated yazma** işidir.

### Adım 3 — Claude Code restart
- Yeni MCP server kaydı **restart olmadan etkin olmaz** (kaydet yetmez). Kullanıcı
  Claude Code'u yeniden başlatır. Restart sonrası `ghidra-mcp` server'ı listede görünür
  ama **backend yoksa çağrılar "connection refused" verir** (beklenen).

### Adım 4 — Ghidra backend'i başlat (her oturumda, `.mcp.json`'ın parçası DEĞİL)
İki yoldan biri (detay: `docs/ghidra-mcp-setup.md`):

- **Yol B — Headless server (bu makinede PROVEN, otonom/CI):**
  ```text
  JAVA_HOME=C:/Modding/fo4-mcp/tools/jdk/jdk-21.0.11+10
  java -Xmx4g -Dghidra.home="<ghidra>" -Dapplication.name=GhidraMCP \
    -classpath "<Framework/Features/Processors */lib/*.jar + GhidraMCP.jar>" \
    com.xebyte.headless.GhidraMCPHeadlessServer --port 8089 --bind 127.0.0.1 --file "<binary>"
  ```
- **Yol A — GUI plugin (en çok test edilen):**
  ```text
  python -m tools.setup deploy --ghidra-path "<ghidra>"   # extension kur (Ghidra restart)
  "tools/ghidra/ghidra_12.1.2_PUBLIC/ghidraRun.bat"        # proje+binary aç → plugin :8089'u host eder
  ```
Backend ayakta + program açıkken `decompile_function` C kodu döndürür → kanal çalışıyor.

### Adım 5 — Fallout4.exe analizi (BN-2, saatler, kullanıcı-tetikli)
> **Steam Data'nın YAZMA tarafına ASLA dokunma. Önce KOPYALA, sonra import.**

```text
# 1) exe'yi tools/ altına kopyala (kaynağı oku, tools/'a yaz — CLAUDE.md safe-write)
copy "C:\Program Files (x86)\Steam\steamapps\common\Fallout 4\Fallout4.exe" `
     "C:\Modding\fo4-mcp\tools\ghidra\projects\bin\Fallout4.exe"

# 2) headless analyzer ile import (PDB yan yanaysa sembolleri otomatik yükler)
JAVA_HOME=C:/Modding/fo4-mcp/tools/jdk/jdk-21.0.11+10
"tools/ghidra/ghidra_12.1.2_PUBLIC/support/analyzeHeadless.bat" `
  "C:\Modding\fo4-mcp\tools\ghidra\projects" Fallout4 `
  -import "C:\Modding\fo4-mcp\tools\ghidra\projects\bin\Fallout4.exe" -overwrite
```
- Saatler sürer, çok-GB proje DB (`tools/ghidra/projects/Fallout4.{gpr,rep}` — gitignored).
- Sonra Yol B headless server'ı `--file Fallout4.exe` ile başlat → köprü üzerinden analiz.

---

## 7. Lisans + güvenlik notları

- **ghidra-mcp = Apache-2.0** (temiz; GPL contagion yok). **Ghidra = Apache-2.0.**
  **JDK = GPLv2+CE** (yalnız toolchain). Hepsi `tools/` altında, gitignored, dağıtılmaz
  (Karar 7).
- Köprü **subprocess** olarak çağrılır (`.mcp.json` üzerinden stdio çocuk process) —
  MIT python'a **import edilmez**. mutagen-cli/Spriggit ile aynı subprocess-izolasyon
  deseni. MIT repomuzda lisans değişikliği YOK.
- Decompile DB'leri (`tools/ghidra/projects/`) gitignored + dağıtılmaz (Address Library /
  CommonLibF4 RE-artefakt duruşuyla aynı).
- Güvenlik (runbook'tan): `GHIDRA_MCP_ALLOW_SCRIPTS` **off** (default), `--bind 127.0.0.1`
  loopback-only (auth token gereksiz), istenirse `GHIDRA_MCP_FILE_ROOT` =
  `tools/ghidra/projects`'e sabitle.

---

## 8. Riskler / footgun'lar (özet)

1. **`cwd` anahtarı yok** → upstream göreceli köprü yolu repo kökünden kırılır → **mutlak
   yol şart** (bu öneride uygulandı).
2. **`PYTHONIOENCODING=utf-8` zorunlu** → düşerse `⇄` (U+2194) cp1252 startup-crash.
3. **Mutlak python yolu hardcoded** → python taşınır/venv beklenirse kırılır; CLAUDE.md/ENV
   bu interpreter'ı pinlediği için kabul edildi.
4. **Backend yokken köprü açılır ama her çağrı hata verir** → "broken server" gibi görünür;
   "önce Ghidra'yı başlat" adımını (§6 Adım 4) belgele.
5. **`--lazy` default OFF** → açıkça verilmeli; omit = 251 araç context-flood (lazy'nin
   önlemek için var olduğu tam failure mode).
6. **`GHIDRA_DEBUGGER_URL=:8099`** default başlatılmaz (scope dışı, Tier-3 F4SE runtime
   debug veriyor) → zararsız ama ayağa kalkmamış bir yeteneği ima eder.
7. **Restart unutulur** → `.mcp.json` kaydedilse de Claude Code restart olmadan server
   kayıt olmaz; kullanıcı **restart etmeli**, sadece save yetmez.
