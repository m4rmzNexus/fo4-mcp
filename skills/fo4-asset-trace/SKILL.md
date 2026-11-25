---
name: fo4-asset-trace
description: Trace a Fallout 4 object's model, material, texture and file providers when selecting vanilla assets, checking a port, or diagnosing a missing or purple mesh.
---

# Trace a Fallout 4 asset

`fo4_trace_catalog_asset(catalog, query, max_paths=100)` reads a Heybeli-format
SQLite catalog (tables `sources`, `assets`, `records`, `models`, `shapes`,
`materials`, `issues` ...). `query` is an exact EditorID, a `plugin:hex` FormKey
(e.g. `fallout4.esm:0e0b94`) or a virtual Data path (e.g.
`materials/architecture/shacks/shackwirefencing01.bgsm`). `catalog` may be
absolute or relative to the fo4-mcp repo root.

## Which catalog

Use the catalog built for the requested game setup. On this workspace:

- `C:\GameDev\mods\fallout\projects\Heybeli\asset-arsivi\Fallout4.sqlite`
  (about 2.9 GB, built 2026-11-21 from the game 1.11.240 `Data`, the enabled mods
  of the MO2 Heybeli profile and its overwrite folder). Read-only for this tool.
  Contents and a direct CLI (`bak.py --ara`, `--geometri`, `--fizik`) are
  described in `asset-arsivi\KULLANIM.md` next to it.

A catalog is a snapshot. When the profile, the mod list or the game has changed
since it was built, the current MO2 priority may differ; check the current
profile before saying what the player sees.

## Steps

1. **Pick the entry point.** For a building kit, start with one identifiable
   static record. For a missing texture, start with the reported material path.
   For a port, start with the vanilla record you are matching.
2. **Trace.** Call the tool and read each provider's references separately
   (base game BA2, loose file, mod). A missing row means the path was absent
   when the catalog was built.
3. **Read the issues first.** Check reported decoder issues and truncation
   (`max_paths`) before drawing conclusions from missing links.
4. **Mind what the catalog does not cover.** Shape materials and material
   texture paths are part of a model's dependencies; material swaps on records
   and shared geometry can also change the result.

## Related checks

- **A downloaded release:** `fo4_check_release_zip` on that artifact with the
  expected custom paths; pass the catalog to identify external providers
  (`fo4-package-release`).
- **A visual or collision defect:** compare a known-good placed object with the
  affected object under the same profile. A reference resolving on disk, object
  bounds, collision and the rendered result are separate observations. The
  [coupon diagnosis](../../docs/coupon-pipeline-diagnosis.md) documents a blank
  inventory preview and a separate material defect found on the same item.
