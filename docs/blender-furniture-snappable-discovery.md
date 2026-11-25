# Blender → FO4: Furniture + Snappable Building Objects — Discovery & Roadmap

> 2026-06-24. RE'd end-to-end against vanilla (`Fallout4.esm` + BA2 nifs) **and** two real Nexus mods
> (BuildingBlocks-Foundations #8907, Children Chairs #24097). Builds on the solved static-prop pipeline
> (PyNifly export → collision splice → clamp-mode patch → record). Detail artifacts in `staging/re-furn/`:
> `connectpoint_format.md`, `FURN-system-RE.md`, `pynifly-furniture-snap-capability.md`.

## TL;DR — feasibility

| Target | Verdict | Net new work over the static-prop path |
|---|---|---|
| **Usable furniture (chair/bench)** | ✅ **Achievable now, pure-Mutagen** | nif = our SOLVED static+collision path (no special node). All "sit" behavior is in a new **FURN** record (SNAM markers + vanilla anim keywords). |
| **Snappable building piece (wall/floor/foundation)** | ✅ **Achievable, +1 nif feature** | nif additionally needs a **BSConnectPoint::Parents (CPA)** block. PyNifly keeps it but **rotates it 90°/pass (bug)** → inject deterministically (prototype built). esp = STAT (no keywords) + **COBJ** recipe + menu FLST. |

Both are real-mod-confirmed. Notably, **BuildingBlocks ships the exact donor-collision-splice technique this project invented** (its 2148 B Havok block == vanilla `ShackFoundation01`), validating our approach in the wild.

---

## 1. Workshop snap-build system

### NIF — `BSConnectPoint::Parents` (byte-decoded)
```
NiExtraData.Name (u32 string-idx) -> "CPA"
u32 NumConnectPoints
entry[] {
  Root        : sized-string (u32 len + latin1)   # "WorkshopConnectPoints", or "" = root-parented
  VariableName: sized-string                       # the P-* snap name
  Rotation    : quaternion WXYZ (4× f32)           # identity = (1,0,0,0)
  Translation : 3× f32                             # game units; 128 = one shack module
  Scale       : f32                                # 1.0 in vanilla
}
```
Two pieces snap when **VariableName matches AND transforms are opposing/mirrored**. Keep translations on the **128-unit module grid**.

### Connect-point taxonomy
- **Snap mates** (often several per piece, one per edge): `P-Floor`, `P-Wall01`, `P-Ceiling`, `P-Corner01`, `P-Balcony01`, `P-WallFlatEnd01`, `P-FoundationSide`, `P-FoundationStack`. The **`-Dif`** suffix = "won't self-snap" (forces a wall to mate a corner, not another wall).
- **Workshop-self family** (one per piece, placement behavior — NOT mates): `P-WS-Origin` (grab/pivot, vanilla sinks Z≈−14), `P-WS-Rotation`, `P-WS-SinkMax`.

### ESP record stack (vanilla `workshop_ShackWoodWall` chain)
1. **STAT** base (e.g. `0E0B94`) — MODL → nif. **No KWDA** (snapping is 100% nif-driven). But carries `PTRN` (icon transform), `PRPS` (workshop resource props), `DNAM` (max snap-angle 90°), and an embedded `NVNM` (settlers path over it).
2. *(optional)* **FLST** of STAT variants → one menu entry cycles variants.
3. **COBJ** recipe (`workshop_co_ShackWoodWall` `06FA7D`): `CNAM`→STAT/FLST, `BNAM`→workbench keyword (`WorkshopWorkbenchTypeExterior` `05A0C8`), `FVPA`→components (`c_Wood`×8 `c_Steel`×2), `FNAM`→category filter keyword, `INTV`→priority.
4. **FLST menu tree** — the recipe lands in a submenu iff its `FNAM` keyword is a leaf of that submenu's `WorkshopMenu*` FLST (Build ▸ Wood ▸ Walls). Integrate by **overriding `WorkshopMenu01Build` `106DA3`** to add your category FLST, OR a runtime `FormList.AddForm` installer Quest (Children-Chairs pattern — conflict-friendly, needs uninstall ritual).
5. **WorkshopParent** ownership is **runtime/automatic** via `WorkshopItemKeyword` linked-ref — no record edit needed.

---

## 2. Furniture (FURN) system

### NIF — just a static mesh + collision
`LoungeChair01.nif` = 7 blocks (mesh + shader + textureset + BSXFlags + collision). **No furniture-marker node.** Same layout as our coupon → already-solved path. *(Caveat: some vanilla furniture e.g. `FederalistChair01` DOES embed a `BSFurnitureMarkerNode` + `P-WS-AutoPlace` connect point — optional, per-asset.)*

### ESP — FURN record (this is the real work)
- **MODL**→nif, **OBND** bounds.
- **SNAM** = array of 24-byte seat markers: `offset X/Y/Z (f32, rel. to model origin) + rotation Z (rad) + keyword (FormID|NULL) + entry-dir flags (u8) + pad`. 1 marker = single seat; the diner booth has 4.
- **MNAM** = active-markers/flags bitfield (e.g. `0x40000001` = IP0 + Has-Model).
- **KWDA** = anim driver — reuse `AnimFurnChairSitAnims` etc. → **vanilla sit animation comes FREE, zero new anim work**. (`FurnitureClassRelaxation/Work` classify it.)
- **WBDT** = workbench type (0=plain chair, 2=Weapons, 5=Chem/Cook, 7=Armor…).
- *(optional)* **CITC/CTDA** condition to gate users (Children Chairs uses `GetIsRace HumanChildRace`).
- *(optional)* **PRPS + PTRN + COBJ** to make it settlement-buildable.

**ACTI/FURN/MSTT:** usable-with-sit-anim ⇒ **FURN**; activate-to-script ⇒ ACTI; havok-movable ⇒ MSTT; decorative ⇒ STAT.

---

## 3. PyNifly capability (round-trip-proven, 27.2.0 / Blender 5.1)

| Feature | Verdict | Fix |
|---|---|---|
| Static mesh / multi-shape (13× BSTriShape) | **OK** | — |
| BSLightingShaderProperty clamp mode | **lossy** (3→-1) | patch +0x3c→3 (only matters for flat-MISC inventory preview) |
| Collision (bhk*) | **corrupts** (regen→crash) | donor splice (relaxed/index-match for multi-shape) |
| **BSConnectPoint::Parents (CPA)** | **survives but rotates +90°/pass (bug)** | **inject deterministically** — do NOT trust PyNifly's points |
| NiStringExtraData / BSXFlags | OK | — |

**Connect-point injector prototyped** (`tools/blender/scripts/inject_connectpoints.py`): CPA encode/decode is byte-exact (re-encodes the vanilla 960B/13-pt block identically); header surgery (append "CPA" string + block-type, append block, ref from root NiNode ExtraDataList, bump `sizes[0]`, re-emit groups) re-parses cleanly. Pending NifSkope/in-game validation. → productionize as `nif_ops.fo4_inject_connectpoints`.

---

## 4. Modder patterns (from the 2 downloaded mods)

- **BuildingBlocks (3ds Max + NifSkope):** reused **vanilla connect-point names verbatim** on the 128-grid; one shared CPA+collision template across all 41 pieces; **spliced the vanilla shack-foundation Havok box** (donor-collision, same as us); ESM (STAT no-KWDA + COBJ + custom filter KYWD + category FLST) + thin ESP that overrides `WorkshopMenu01Build`.
- **Children Chairs (NifSkope-only, no remesh):** "scaled" meshes = **one float edit** — BSTriShape Scale (offset +64) 1.0→0.82 + Havok shape scale; reused vanilla FURN keywords 100%; runtime `FormList.AddForm` menu injection + uninstall chem.

---

## 5. Roadmap — turning this into a pipeline

**NIF tooling (extend `nif_ops.py`):**
- [ ] `fo4_inject_connectpoints` — productionize the prototype; runs LAST (after collision/clamp). MCP tool.
- [ ] collision splice **relaxed/index-match mode** for multi-shape pieces (current splice asserts `types==types`).
- [ ] `fo4_validate_nif` extensions: connect-point presence/grid-alignment check for snap pieces.
- [ ] *(cheap bonus)* BSTriShape Scale patch (offset +64) — author a scaled variant of a vanilla mesh.

**Writer (mutagen-cli) record types:**
- [ ] **FURN** — SNAM markers + MNAM + KWDA + WBDT (+ optional CITC/CTDA, PRPS, PTRN). The usable-chair MVP.
- [ ] **STAT** with workshop fields (PTRN/PRPS/DNAM) — buildable base. *(plain STAT may already exist; add the workshop subrecords.)*
- [ ] **COBJ** — constructible recipe (CNAM/BNAM/FVPA/FNAM/INTV). The build-menu entry.
- [ ] Menu integration: FLST-override helper **or** an AddForm installer-script generator. *(KYWD/FLST writers exist.)*

**Validation:** snap-mate + sit-reachable are engine-internal → confirm via `fo4_run_ingame_test` (same gate as navmesh/fragments).

**Suggested MVP order:** (1) usable chair (FURN + existing static path — fastest, high value) → (2) snappable foundation (CPA injector + relaxed splice + STAT/COBJ + menu).
