# Ghidra-MCP — kurulum + çalıştırma + context-dostu kullanım

Native-RE ekseni (roadmap **OS-41/OS-39**). Ghidra'yı bir MCP server'ı arkasına koyup
ajanın (Claude Code) FO4 binary'lerini decompile/analiz etmesini sağlar. Lazy tool-loading
ile 251 araç context'i boğmaz. **Neden** + faz planı: `~/.claude/plans/iridescent-rolling-parrot.md`.

> **Konum bağlamı:** Bu, Steam game folder'a yazmaz. Fallout4.exe analiz edilecekse **kopyası**
> `tools/ghidra/projects/`'e alınır (kaynağı oku, `tools/`'a yaz). Decompile DB'leri gitignored,
> dağıtılmaz — mevcut RE duruşuyla (Address Library, CommonLibF4) aynı. Lisans: **Apache-2.0** (temiz).

## Kurulu bileşenler (hepsi `tools/`, gitignored)

| Bileşen | Sürüm | Yol |
|---|---|---|
| Ghidra | 12.1.2 PUBLIC | `tools/ghidra/ghidra_12.1.2_PUBLIC/` |
| JDK (Temurin) | 21.0.11+10 | `tools/jdk/jdk-21.0.11+10/` (mevcut, ReSaver shim'iyle paylaşımlı) |
| Maven | 3.9.9 | `tools/apache-maven-3.9.9/` |
| ghidra-mcp (bethington) | 5.14.1 | `tools/ghidra-mcp/` (Apache-2.0) |
| → built extension | — | `tools/ghidra-mcp/target/GhidraMCP-5.14.1.{jar,zip}` |

Mimari: `Claude Code ⇄ (stdio) bridge_mcp_ghidra.py ⇄ (HTTP :8089) Ghidra` —
Ghidra ya GUI plugin ya da headless server olarak HTTP :8089'u host eder.

## Build (gerektiğinde yeniden)

```bash
export JAVA_HOME=C:/Modding/fo4-mcp/tools/jdk/jdk-21.0.11+10
export PATH="$JAVA_HOME/bin:C:/Modding/fo4-mcp/tools/apache-maven-3.9.9/bin:$PATH"
cd C:/Modding/fo4-mcp/tools/ghidra-mcp
python -m tools.setup ensure-prereqs --ghidra-path "C:\Modding\fo4-mcp\tools\ghidra\ghidra_12.1.2_PUBLIC"  # Ghidra JAR'larını .m2'ye kur (tek sefer)
python -m tools.setup build                                                                                  # GhidraMCP-*.zip + *.jar üret
```

## Bir binary'yi analiz et (Ghidra projesine al)

Ghidra'nın kendi headless analyzer'ı (Fallout4.exe için de aynı mekanizma):

```bash
export JAVA_HOME=C:/Modding/fo4-mcp/tools/jdk/jdk-21.0.11+10
"tools/ghidra/ghidra_12.1.2_PUBLIC/support/analyzeHeadless.bat" \
  "C:\Modding\fo4-mcp\tools\ghidra\projects" <ProjeAdı> \
  -import "<binary.exe|dll>" -overwrite
```

- Proje DB → `tools/ghidra/projects/<ProjeAdı>.{gpr,rep}` (gitignored).
- PDB varsa (`.pdb` yan yana) Ghidra otomatik sembol yükler → near-perfect isimler.
- **Fallout4.exe (Faz 5, ağır):** önce Steam'den kopyala (`tools/ghidra/projects/bin/`'e), sonra import.
  Saatler sürer, çok-GB DB. Steam Data'ya ASLA yazma.

## Çalıştırma (iki yol)

### Yol A — GUI plugin (en çok test edilen, masaüstü)
```bash
python -m tools.setup deploy --ghidra-path "C:\Modding\fo4-mcp\tools\ghidra\ghidra_12.1.2_PUBLIC"  # extension'ı kur (Ghidra'yı patch'ler/restart eder)
"tools/ghidra/ghidra_12.1.2_PUBLIC/ghidraRun.bat"   # Ghidra GUI; projeyi+binary'yi aç → plugin :8089'u host eder
```

### Yol B — Headless server (GUI'siz, otonom/CI)
```bash
export JAVA_HOME=C:/Modding/fo4-mcp/tools/jdk/jdk-21.0.11+10
# CLASSPATH = GhidraMCP.jar + Ghidra Framework/Features/Processors jar'ları + lib/* (Windows ';' ayracı)
java -Xmx4g -Dghidra.home="<ghidra>" -Dapplication.name=GhidraMCP \
  -classpath "<classpath>" com.xebyte.headless.GhidraMCPHeadlessServer \
  --port 8089 --bind 127.0.0.1 --file "<binary>"
```
(Classpath kurulum scripti: `docker/entrypoint.sh` mantığı — Framework/Features/Processors `*/lib/*.jar` glob'u.)

### Bridge (her iki yolda da Claude Code'a stdio köprüsü)
```bash
python tools/ghidra-mcp/bridge_mcp_ghidra.py --transport stdio --lazy --default-groups listing,function,program
```
Claude Code kaydı için repo kökü `.mcp.json` (Faz 4'te diff+onayla eklenir).

## Context-dostu: lazy tool loading

251 araç var → eager modda ajan tool-context'ini boğar. **Çözüm: lazy mod.**

- `--lazy --default-groups listing,function,program` → bağlanınca SADECE bu çekirdek grup yüklenir (~core decompile/list/xref/search).
- Gerisi **talep üzerine** keşfedilir (Claude Code `tools/list_changed` destekler → çalışır):
  - `search_tools("<keyword>")` — TÜM katalogu ara; her sonuç callable mı + gereken `load_tool_group(...)` çağrısını söyler.
  - `list_tool_groups()` — kategoriler + yüklü/değil durumu.
  - `load_tool_group("<grup>")` / `unload_tool_group("<grup>")` — runtime'da grup yükle/bırak.
  - `check_tools("a,b")` — şu an callable mı doğrula.
- Liste eksik görünürse fallback: `--no-lazy` (hepsini yükle) veya `--default-groups`'u genişlet.

### Grup → kullanım eşlemesi (hangi task için neyi lazy-load et)

| İhtiyaç (roadmap) | Lazy-load grubu | Tipik araçlar |
|---|---|---|
| Crash-decompile, genel keşif | **default** (`listing,function,program`) | `decompile_function`, `list_functions`, `get_xrefs_to`, `search_functions_by_name` |
| OS-39 offset-pinning (sürümler arası) | cross-binary / diff | fonksiyon-hash + fuzzy match |
| Struct türetme, crash kök-neden, asset-loader layout | data-flow / pcode | P-code value propagation, emülasyon |
| Bulguyu DB'ye belgele | datatype | `create_struct`, `add_struct_field` |
| Toplu işlem (context tasarrufu) | batch | `batch_decompile`, `batch_*` |
| **Kapalı tut** | debugger, ghidra-server | runtime'ı Tier-3 F4SE veriyor; solo author |

## Güvenlik / env

- `GHIDRA_MCP_ALLOW_SCRIPTS` — **off (default)**; `/run_script_inline` kapalı kalsın.
- Loopback-only (`--bind 127.0.0.1`) → `GHIDRA_MCP_AUTH_TOKEN` gereksiz (sadece dışarı açılırsa şart).
- `GHIDRA_MCP_FILE_ROOT` — `tools/ghidra/projects` köküne sabitle (path-traversal koruması, opsiyonel).
- `JAVA_OPTS=-Xmx4g -XX:+UseG1GC` (Fallout4.exe ölçeğinde RAM).

## Doğrulama (kurulum sağlık)

- Build: `python -m tools.setup build` → BUILD SUCCESS + `target/GhidraMCP-*.zip`.
- MCP katmanı: `cd tools/ghidra-mcp && python -m pytest tests/unit/ -o addopts="" -q` → bridge/setup/catalog yeşil
  (yalnız `test_gradle_tasks.py` JAVA_HOME-env kusuruyla düşebilir — Maven kullandığımız için alakasız).
- Binary: `analyzeHeadless ... -import <dll>` → "found N functions" + proje DB oluşur.
- Loop: server :8089 ayakta + program açıkken `decompile_function` C döndürür.
