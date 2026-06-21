# fo4-mcp

Fallout 4 modding tool'larını MCP üzerinden AI agent'lara (Claude Code, Codex CLI) expose eden server. `C:\Modding\` repo'sunda Phase 0 kararlarına dayanır.

## Mimari

```
agent (Claude Code / Codex)
        │  MCP protocol (stdio)
        ▼
   fo4-mcp server (Python)
        │  subprocess
        ▼
   tools/<name>/<exe>   (Mutagen via Synthesis, Spriggit, Caprica, CLASSIC, ...)
        │
        ▼
   FO4 install / user data (READ-ONLY)
   C:\Modding\staging      (write OK, generated outputs)
   C:\Modding\fixtures     (write only with diff+approval)
```

**Subprocess-wrap pattern:** çoğu underlying tool GPL-3.0 lisanslı (Mutagen, Spriggit, Synthesis, Buffout/Addictol). Library-link contagion riskini elimine etmek için fo4-mcp tüm bu binary'leri **process boundary** üzerinden çağırır (asla import etmez). License: `docs/karar-7-license-strategy.md` (Karar 7 → MIT).

## Tool seti — 34 fonksiyonel

Tam tablo (gruplu) için kök [`README.md`](../README.md) → *Capabilities*. Çekirdek (Karar 3 MVP):
`fo4_get_environment` · `fo4_read_load_order` (MO2 + AppData, base_directory-aware) ·
`fo4_inspect_record` (Spriggit backend) · `fo4_spriggit_export` / `_import` (diff-gated) ·
`fo4_papyrus_build` (Caprica) · `fo4_analyze_crash_log` (native parser). Üzerine: authoring
(`fo4_create_record`), world/Story-Manager, CK/voice, paketleme, save, ve Tier-3 in-game test.

## Path safety

Tüm write attempts `safety.check_write()` üzerinden geçer (Karar 4 tablosu). Default: read-only her yer, sadece `C:\Modding\staging\`, `research/`, ve diff-gated `fixtures/`, `staging/*.psc`, `staging/*.ini` yazılabilir. Steam install klasörüne yazma koşulsuz yasak.

## Geliştirme

```bash
# Repo root'tan
cd mcp-server
python -m venv .venv
.venv\Scripts\activate         # Windows
pip install -e ".[dev]"

# .env dosyasını oluştur
cp .env.example .env
# (gerekirse path'leri düzenle)

# Test
pytest

# Server'ı manuel çalıştır (stdio mode)
fo4-mcp
```

## Durum

34/34 tool fonksiyonel, 393 test PASS, PreToolUse hook wired (Edit|Write +
Bash|PowerShell). Mimari + güvenlik modeli + kurulum: kök [`README.md`](../README.md).

## Klasör yapısı

```
mcp-server/
  pyproject.toml
  .env.example
  README.md
  fo4_mcp/
    __init__.py
    server.py            MCP entrypoint + tool registry
    config.py            env paths, .env loader
    safety.py            Karar 4 path boundary
    subprocess_wrap.py   ortak runner + ToolResult
    manifest.py          tools/MANIFEST.md parser
    errors.py            structured error envelope
    tools.py             core tool implementations + pure helpers
    facegen.py voice_bake.py seq.py previs.py ck_run.py   CK/voice pipeline
    ingame_test.py       Tier-3 F4SE in-game runner orchestrator
  scripts/
    precheck_path.py     PreToolUse hook (Edit|Write + Bash|PowerShell path gate)
  tests/                 28 test modülü, 393 test
```
