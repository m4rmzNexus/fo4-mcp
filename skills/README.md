# fo4-mcp skill pack

Claude Code skills that drive the `fo4-mcp` MCP tools into end-to-end Fallout 4
mod authoring workflows. Each skill is a `<name>/SKILL.md` with YAML frontmatter
(`name` + `description`) and a markdown body following one shared pattern:

> **tool chain → inline best-practice guards → scannable output shape**

Design + decisions: `docs/phase-0-decisions.md` (Karar 2 persona, Karar 3 tools),
backlog item `docs/V2-backlog.md` #6.

## Tiers

**T0 — foundation (built; 100% backed by the 7 working MCP tools):**

| Skill | Tool chain | What it does |
|---|---|---|
| `fo4-setup-check` | get_environment + read_load_order | Pre-authoring readiness; go/no-go. Read-only. |
| `fo4-record-edit` | inspect → spriggit_export → (YAML edit) → spriggit_import | The core safe record loop, diff-gated. |
| `fo4-crash-debug` | analyze_crash_log + read_load_order | Crash triage with a grounded culprit + fix. |
| `fo4-papyrus` | papyrus_build (Caprica) | Compile `.psc → .pex` with resolved includes. |

**T1 — composite authoring (planned):** `fo4-armor-swap` (continues the
`fixtures/armor-swap-test` flow), `fo4-quest-author`.

**T2 — release / hygiene (planned):** `fo4-package-release` (ESL eligibility,
PRP/precombine safety, FOMOD; BA2 packing is a V2 gap — manual BSArch for now).

**T3 — runtime verification (built):** `fo4-ingame-test` (drives the
`fo4_run_ingame_test` MCP tool — a headless Tier 3 F4SE in-game smoke test:
job file → MO2 launch → console commands by runtime FormID → Papyrus capture →
auto-quit). User-gated: needs the live game + a Steam login, so it is **not**
CI-runnable. Proves *runtime*-valid, where T0/T1 prove *disk*-valid.

## Community best-practice guards (woven into each skill)

- Precombine/previs breakage warning on CELL/STAT edits (PRP context).
- FormID hygiene — new records ≥ `0x800` (SPID drops below).
- Masters-first load order; LOOT sort suggestion.
- ESL budget headroom (<2048 new records to qualify for a light flag).
- Spriggit ESP→YAML serialization for version control.
- `staging/`-only writes; the Steam `Data/` folder stays read-only.

## Making them discoverable in Claude Code

These live in the repo's `skills/` (canonical, git-tracked). Claude Code
discovers project skills from `.claude/skills/<name>/SKILL.md`. To use them as
`/fo4-...` in this project, junction each into `.claude/skills/` (Windows):

```powershell
New-Item -ItemType Junction -Path ".claude\skills\fo4-setup-check" `
         -Target "skills\fo4-setup-check"
# repeat per skill
```

(or copy, or add `skills/` to your Claude Code skills path). The junctions are
local filesystem links, not committed — `skills/` stays the single source.

## Gaps these skills route around (manual GUI or V2)

- Mesh/slider/material/texture authoring → BodySlide, OutfitStudio, Material
  Editor, CAO (GUI; skills orchestrate around them).
- BA2 packing → V2 (`docs/V2-backlog.md` #4); manual BSArch (`tools/xedit`).
- Navmesh, precombine generation, scenes, dialogue/voice → Creation Kit (GUI).
- Record-scoped (fast) inspect on master-scale plugins → V2 (#2).
