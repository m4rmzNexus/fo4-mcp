# Changelog

All notable changes to **fo4-mcp** are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
The README carries only the most recent entry under *What's new*; the full history lives here.

## [Unreleased]

### Added — authoring: readable notes & loot injection (2026-06-21)

- **`Book` / Note record type** in `fo4_create_record`. Authors a BOOK as a readable note:
  `name` → title, `text` → `BookText` (the body shown when read), plus the shared
  `value` / `weight` / `keywords` fields. `Teaches` is set to `BookTeachesNothing`, so the note
  grants no perk. The mesh (`Model`) is optional (see *visual pipeline* below) — the note is still
  readable from the Pip-Boy without one. Round-trips byte-exact (the body is re-read from disk).
- **`LeveledItemOverride` record type** — loot injection into an **existing** (master) leveled list.
  Loads the `sourcePlugin`, finds the target `LVLI` by FormKey, `DeepCopy`s it (FormKey preserved →
  a true override, so the vanilla entries carry forward), and **adds** the new entries.
  **Additive by default**; `clearExisting` opt-in wipes the vanilla entries. The owning master
  (e.g. `Fallout4.esm`) auto-adds on write from the preserved FormKey. Mirrors the existing
  `CellOverride` path; no LinkCache / load-order needed.
- **`lvli-find` mutagen-cli subcommand** — reverse-lookup that streams a plugin's leveled lists and
  reports every `LVLI` whose entries reference a target FormKey (e.g. *which lists distribute Sugar
  Bombs*). The discovery step the loot-injection workflow needs to pick an injection point.
  Read-only: `mutagen-cli lvli-find --plugin <path> --contains <6hex:master> [--max N]`.

### Added — visual pipeline: world-model art via material swap (2026-06-21)

- **Book `model` + `materialSwap`** in `fo4_create_record`. A book can now carry a world-model nif
  (`model` → MODL, e.g. `Interface\Newspaper\DN101Note.nif`) and a `materialSwap` FormKey. The swap
  rides on the `Model`, not the Book — matching the engine (a placed model gets the swap). With a
  model the item shows its art in-world / in the inventory render; without one it stays a plain note.
- **`MaterialSwap` (MSWP) record type** — a retexture map. `substitutions` is a list of
  `{original, replacement}` `.bgsm` paths: the engine swaps the original material (the one the nif
  references) for the replacement (ours, pointing at a custom `.dds`). The Grognak-comic / perk-magazine
  recipe — how Bethesda reskins a shared mesh per item without authoring a new nif. Read-back proves
  the substitution count + each path pair.
- **BGSM v2 material writer** (`staging/coupon-mod/make_bgsm.py`) — emits per-coupon `.bgsm` materials
  from a vanilla template (`DN101Note.BGSM`) by swapping only the diffuse texture path and keeping the
  header + normal/specular + opaque shader-param tail byte-for-byte (round-trip proven). FO4 ships no
  material authoring tool; this fills the gap with a structural (no full semantic decode) template swap.

### Fixed

- **Non-ASCII string corruption in authored records.** `InvariantGlobalization` was dropping the
  Windows-1252 code page, so characters like `¢`, `—`, `™`, `©` were serialized as the Unicode
  replacement character `U+FFFD`. Removed it from the writer's `.csproj`; authored strings now
  round-trip byte-exact. Affects every text field (`BookText`, `Message`, record `Name`, …), not
  just coupons.

### Demo

- **Pre-War Coupons** (`staging/coupon-mod/`) — the first content mod built on the new authoring
  surface. Six lore-flavoured, unusable old-world brand coupons (Cram™, BlamCo™, Slocum's Joe,
  Nuka-Cola, a Vault-Tec Vault 111 deposit receipt, a RobCo employee discount card) authored as
  readable notes, distributed through a weighted rarity leveled list (Common 25% · Uncommon 17% ·
  Rare 8% each) that is injected into the vanilla `LL_Food_Packaged` (`067396`) packaged-food list —
  so coupons turn up alongside Sugar Bombs and the like. **Each coupon now shows its own generated
  art in-world**: six images → BC7 `.dds` → per-coupon `.bgsm` → an MSWP per coupon that swaps the
  `DN101Note.nif` paper material, wired onto each book's `Model`. The full chain (book → MSWP →
  `.bgsm` → `.dds`) is disk-validated; the in-game eyeball is the remaining user step. Assembled as a
  loose-file mod folder (`staging/coupon-mod/PrewarCoupons/`).
  *Known nuance:* the coupon list is one entry among the list's 15, so a coupon appears **instead
  of** a food item on its roll (~6–7% of packaged-food rolls), not in addition to it — a refinement
  for a later pass.

### Tests

- +9 in `test_tools_create_record.py`: book value validation, leveled-item-override source/target
  validation, a book non-ASCII byte-exact round-trip, the `LL_Food_Packaged` injection (vanilla
  entries preserved + coupon list appended + master auto-added), MSWP substitution validation
  (empty list + missing path), an MSWP round-trip, and a book carrying a model + a MaterialSwap link
  (both round-tripped). Suite: **402 passing**.
