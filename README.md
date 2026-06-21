# fo4-mcp — Agentic Fallout 4 Modding via MCP

> A [Model Context Protocol](https://modelcontextprotocol.io) server that lets AI coding agents
> (Claude Code, Codex CLI) author Fallout 4 mods **end-to-end** — records, Papyrus scripts,
> dialogue, voice, navmesh — and validate them in a **running game**.

![license](https://img.shields.io/badge/license-MIT-blue) ![tests](https://img.shields.io/badge/tests-393%20passing-brightgreen) ![python](https://img.shields.io/badge/python-3.11%2B-blue) ![mcp](https://img.shields.io/badge/MCP-stdio-purple)

Fallout 4's modding stack — Mutagen, Spriggit, Caprica, F4SE / CommonLibF4, the Creation Kit,
MO2 / LOOT, Buffout 4 / Addictol — is powerful but fragmented and largely GUI-bound. **fo4-mcp**
puts it behind a single MCP server so an agent can plan and build a mod the way a human modder
would, but **programmatically, diff-gated, and test-driven**.

**34 MCP tools · 393 tests · MIT.**

---

## What it can do

- **Author records without the Creation Kit** — NPCs, armor, quests (stages / objectives / reference
  aliases / dialogue / scenes / Papyrus fragments), interior cells + placed references, factions,
  leveled lists, Story-Manager nodes, AI packages, locations, door teleports — through Mutagen, with
  a Spriggit round-trip as the diff gate.
- **Dialogue that actually surfaces** — quest-nested DIAL/INFO wired into player **DialogBranches**, so
  topics appear in the in-game dialogue wheel (a bare DIAL/INFO never does).
- **Visible armor with zero new art** — reference existing in-game ARMA addons so a custom reward
  renders without authoring a mesh.
- **Compile Papyrus** (Caprica) — quest / alias / magic-effect fragments, with the vanilla, F4SE, and
  Lighthouse include paths resolved.
- **Voice & FaceGen** — bake silent-subtitled `.fuz` (LipGen + xWMAEncode + FUZE, headless) and drive
  Creation-Kit FaceGen export.
- **Navmesh** — interior navmesh is Mutagen-authorable **and** proven in-game-pathable; exterior stays
  a CK handoff with a generated checklist.
- **Ship hygiene** — ESL-eligibility, BA2 packing + header-version patch, FOMOD generation, engine-config
  lint, aggregate release preflight.
- **In-game testing** — a Tier-3 F4SE runner launches the game headless via MO2, runs console commands
  against resolved FormIDs, greps the Papyrus log for a verdict, and auto-quits.

## Showcase — "Yolcu Kerem", authored end-to-end

A complete demo quest built entirely through the tools (no Creation Kit for the record work): a
travelling NPC arrives in the Commonwealth with branching dialogue, a small kill-quest, and an armor
reward. A single `fo4_create_record` spec assembles the NPC, the quest (stages, objectives, reference
aliases, **DialogBranches**, Papyrus fragment bindings), the placed actors (additive cell-override),
and the reward armor. The dialogue surfaces in the wheel, the armor renders, and the **reward chain
was validated in a running game** through the in-game test runner.

## Capabilities (34 tools)

| Group | Tools |
|---|---|
| **Core** | `fo4_get_environment` · `fo4_read_load_order` (MO2 + AppData merge) · `fo4_inspect_record` (Spriggit) · `fo4_spriggit_export` / `_import` (diff-gated) · `fo4_papyrus_build` (Caprica) · `fo4_analyze_crash_log` (native Buffout/Addictol) |
| **Plugin / ESL** | `fo4_check_esl_eligibility` · `fo4_read_esl_flag` / `fo4_set_esl_flag` · `fo4_plan_plugin_format` · `fo4_set_master_flag` · `fo4_compact_formids` |
| **Authoring** | `fo4_create_record` (NPC / ARMO / QUST + dialogue / scenes / fragments / glue / faction / leveled-list + cells + Story-Manager + activators + AI packages + locations + door-links) · `fo4_lint_npc_template` |
| **World / Story Manager** | `fo4_place_into_cell` (REFR/ACHR override, additive by default) · `fo4_check_previs_safety` (precombine/previs BLOCKING gate) · `fo4_inspect_sm_tree` |
| **CK / voice** | `fo4_navmesh_handoff` · `fo4_voice_handoff` · `fo4_bake_voice_assets` (headless `.fuz`) · `fo4_build_facegen` · `fo4_build_seq` · `fo4_release_preflight` |
| **Packaging / hygiene** | `fo4_generate_fomod` · `fo4_lint_engine_config` · `fo4_ba2_version_patch` · `fo4_pack_ba2` · `fo4_build_previs` · `fo4_build_lod` |
| **Saves** | `fo4_backup_saves` · `fo4_inspect_save` · `fo4_clean_save_changeforms` · `fo4_clean_save_papyrus` |
| **Runtime test** | `fo4_run_ingame_test` (Tier-3 F4SE in-game runner) |

Alongside the server, a **skill pack** (`skills/`) gives Claude Code task-level workflows:
setup-check, record-edit, Papyrus, armor-swap, quest-author, package-release, crash-debug, in-game-test.

## Architecture

```
agent (Claude Code / Codex CLI)
        │  MCP protocol (stdio)
        ▼
   fo4-mcp server (Python)
        │  subprocess boundary
        ▼
   Mutagen · Spriggit · Caprica · Creation Kit · CLASSIC · ...
        │
        ▼
   Fallout 4 install / user data   (READ-ONLY)
   staging/                        (generated output)
```

**Subprocess-wrap pattern:** most underlying tools are GPL-3.0 (Mutagen, Spriggit, Synthesis,
Buffout/Addictol). To eliminate any library-link contagion, fo4-mcp calls every binary across a
**process boundary** and never imports them.

## Install & use

**Prerequisites**

- Windows with a Fallout 4 install (Steam, AE 1.11.221). It is treated as a **read-only** data source.
- Python **3.11+**
- **.NET 9 SDK** — required by Spriggit and the bundled `mutagen-cli` writer.
- The third-party tool binaries (Mutagen via Synthesis, Spriggit, Caprica, the Creation Kit, …) are
  **not shipped** (see *Licensing*); the server invokes them as subprocesses.

```bash
cd mcp-server
python -m venv .venv
.venv\Scripts\activate            # Windows
pip install -e ".[dev]"

cp .env.example .env              # point at your FO4 / MO2 paths — all optional, auto-detected
pytest                            # 393 tests
fo4-mcp                           # run the stdio MCP server
```

**Add it to Claude Code:**

```bash
claude mcp add fo4-mcp -- fo4-mcp
```

or in an MCP client config:

```json
{ "mcpServers": { "fo4-mcp": { "command": "fo4-mcp" } } }
```

## Safety model

- The Fallout 4 install, the Creation Kit, and the user save / INI folders are **read-only data
  sources** — the server never writes to them.
- Every write passes a path boundary; generated output lands in `staging/`, and binary writes are
  **diff-gated** (serialize → review → deserialize).
- Secrets are gitignored and never committed; CI enforces a privacy guard + a GPL-import firewall.

## Licensing

This repository is **MIT** (`LICENSE`). The third-party tools it drives are GPL-3.0 and others; they
are invoked across a process boundary and **never linked or redistributed**, so there is no license
contagion. Mod outputs you generate are yours — the project claims no copyright over them.

---

## Türkçe özet

**fo4-mcp**, Fallout 4 modlama yığınını (Mutagen, Spriggit, Caprica, F4SE / CommonLibF4, Creation Kit,
MO2) tek bir **MCP server**'ının ardına koyar; böylece bir AI ajanı (Claude Code) bir modu uçtan uca —
kayıtlar, Papyrus, diyalog, ses, navmesh — **programatik, diff-kapılı ve test-güdümlü** olarak üretebilir.

- **34 MCP tool · 393 test · MIT.**
- Creation Kit olmadan kayıt üretimi: NPC / zırh / quest (stage, objective, alias, **diyalog çarkı için
  DialogBranch**, Papyrus fragment), hücre + yerleştirilmiş ref, fraksiyon, leveled list, Story Manager,
  AI paket, lokasyon, kapı-link — hepsi Mutagen ile, Spriggit round-trip diff-kapısıyla.
- **İç-mekân navmesh** Mutagen ile üretilebilir **ve** oyun-içi yürünebilir kanıtlandı; exterior CK'ya
  checklist'le devredilir.
- **Headless in-game test**: F4SE runner oyunu MO2 üzerinden başlatır, konsol komutlarını çözülmüş
  FormID'lere uygular, Papyrus log'undan verdict toplar, kendini kapatır.
- **Güvenlik:** oyun kurulumu salt-okunur; çıktılar `staging/`'e yazılır; GPL tool'lar subprocess ile
  izole edilir, asla dağıtılmaz.
- **Vitrin — "Yolcu Kerem":** Commonwealth'e gelen, dallı diyaloglu, mini-quest'li, zırh-ödüllü uçtan-uca
  demo questi; ödül zinciri çalışan oyunda doğrulandı.

Kurulum ve Claude Code'a ekleme için yukarıdaki *Install & use* bölümüne bakın.

---

## Contributing & security

See [`CONTRIBUTING.md`](CONTRIBUTING.md), [`SECURITY.md`](SECURITY.md), and
[`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md). CI runs pytest, a GPL-import firewall, and a privacy guard
(`.github/workflows/ci.yml`).
