# Fallout 4 agent skills

Skills that drive the `fo4-mcp` MCP tools into end-to-end Fallout 4 mod
authoring workflows. Each skill is a `<name>/SKILL.md` with YAML frontmatter
(`name` + `description`) and a body following one pattern:
**tool chain -> inline best-practice guards -> scannable output**. Choose the
workflow matching the requested outcome; the connected server's tool list
(`tools/list`) decides which operations are available on this checkout.

| Request | Skill |
|---|---|
| Check runtime, MO2 profile or missing authoring tools | [Setup check](fo4-setup-check/SKILL.md) |
| Inspect or edit a plugin record | [Record edit](fo4-record-edit/SKILL.md) |
| Find a model, texture or provider | [Asset trace](fo4-asset-trace/SKILL.md) |
| Adapt an existing design to Fallout 4 art, scale and gameplay | [Asset adaptation](fo4-asset-adapt/SKILL.md) |
| Change an armor record | [Armor swap](fo4-armor-swap/SKILL.md) |
| Compile a Papyrus script | [Papyrus](fo4-papyrus/SKILL.md) |
| Build or repair a quest and its dialogue | [Quest author](fo4-quest-author/SKILL.md) |
| Package a release or review a ZIP | [Package release](fo4-package-release/SKILL.md) |
| Test behavior in a running game | [In-game test](fo4-ingame-test/SKILL.md) |
| Diagnose a crash log | [Crash debug](fo4-crash-debug/SKILL.md) |

## Shared guards (woven into each skill)

- Writes land in `staging/` (or diff-gated `fixtures/`); the game `Data/` stays read-only.
- New records at ObjectID >= `0x800` (SPID drops lower ids); ESL caps at `0xFFF`.
- Masters-first load order; ESL budget headroom (< 2048 new records for a light flag).
- Precombine/previs warning on CELL or placed-reference edits.
- Spriggit ESP <-> YAML round trip with a diff gate before any overwrite.
- Disk-valid, clean-profile install and observed in-game behavior are reported separately.

## Making them discoverable

The canonical files live here under `skills/` (git-tracked). Clients discover
project skills through local directory junctions (not committed; edit the
canonical file so every client sees the same text):

```powershell
# from the fo4-mcp repo root; Claude Code uses .claude\skills, Codex uses .agents\skills
foreach ($s in Get-ChildItem skills -Directory) {
  foreach ($dst in '.claude\skills', '.agents\skills') {
    New-Item -ItemType Directory -Force $dst | Out-Null
    if (-not (Test-Path "$dst\$($s.Name)")) {
      New-Item -ItemType Junction -Path "$dst\$($s.Name)" -Target $s.FullName | Out-Null
    }
  }
}
```

The tools themselves need a connected fo4-mcp server from the intended checkout
(see `mcp-server/README.md`).

## Gaps the skills route around

- Skinned meshes, sliders and weighting: OutfitStudio / BodySlide (GUI).
- Navmesh beyond isolated interiors, precombine generation, CK-only scenes:
  Creation Kit (the CK tools here are gated launchers).
- Recorded voice: `fo4_voice_handoff` lists the lines; silent placeholders only.
