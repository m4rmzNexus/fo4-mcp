# Pre-War Coupons — Pipeline Diagnosis & Hardening Plan

**Source:** `fo4-pipeline-hardening` ultracode workflow (2026-06-23, 37 agents / 570K tokens:
5 diagnose · 12 research+verify · 6 audit · synth + adversarial critic). Runtime FO4 1.11.221 AE.

> This doc = the workflow's synthesized plan + the adversarial critic + the on-disk empirical
> confirmations done after the run. Read the **Reconciled verdict** first — it overrides the plan
> where the critic/empirics corrected it.

---

## Reconciled verdict (plan + critic + disk-confirmed)

**Two real, independent defects — both born in the MISC writer / BGSM template, both fixed in one P0 pass:**

1. **All-zero Object Bounds (`OBND = 0,0,0,0,0,0`) on every coupon MISC** — CONFIRMED (measured;
   vanilla PrewarMoney = `-7,-3,0 / 7,3,4`; coupons are the only `objectBoundsZero:true` records).
   FO4 uses OBND to frame the Pip-Boy 3D inventory preview / Inspect camera. Zero box ⇒ **blank
   preview + dead Inspect**. This is the confirmed cause of the inventory/inspect symptom.
   Systematic writer gap: `mutagen-cli` MISC branch never assigns `ObjectBounds` → 12 zero bytes.
2. **BGSM `AlphaTest=1` from the WRONG template** — CONFIRMED on disk: deployed `coupon_*.bgsm` is
   byte-pattern-identical to `Note.BGSM` (AlphaTest@0x2a=**1**, TwoSided@0x30=1), vs the intended prop
   template `DN101Note.BGSM` (AlphaTest=**0**, TwoSided=0). Critic's correction stands; the plan's
   "IsDecal=1" claim was **wrong** (IsDecal@0x2f=0 in BOTH templates). With AlphaTest=1, any diffuse
   fragment with alpha<127 is discarded — a plausible **world no-show** mechanism.
   - Empirical nuance: the *source* PNG is **RGB (no alpha)**, so the BC7 DDS alpha is likely opaque
     (255) ⇒ AlphaTest=1 may be harmless on THIS texture. But **`AlphaTest=0` is correct for an opaque
     card regardless** (zero downside) and removes it as a variable in one shot.

**Ruled out (do not re-investigate):** plugin load / FormID (`0A000800` correct, index 0x0A, ESL bit
clear, MO2-VFS confirmed) · NIF geometry (structurally sound, bound radius ~6.15 — the earlier
"radius=0 culled" was a **buggy decoder artifact**, also garbage on the known-good vanilla donor) ·
asset paths (all 18 resolve) · havok collision (crash-free + pickupable, donor-spliced) · DDS validity
(BC7 1024² 11-mip; one cosmetic nit: diffuse is BC7 *linear* 98 where a color map wants sRGB 99 → wrong
gamma, NOT invisibility) · record type (MISC is correct — vanilla PrewarMoney IS a MiscItem; do NOT
revert to BOOK).

**Critic's load-bearing catches folded in:**
- Rebuild MUST be `dotnet publish -c Release -r win-x64 --self-contained false -o tools/mutagen-cli`
  — NOT `dotnet build` (publish≠build; verify `mutagen-cli.dll` sha256).
- The MISC read-back **already emits `objectBoundsZero`** (Program.cs ~L731-751) — only the *write* is
  missing, and only `tools.py` needs to surface the existing `misc` detail block. Descope "new" tools.
- `modelHasData` is just `Model != null` — it does NOT detect MODT absence, so "MODT absent" is
  unevidenced and a weak no-show candidate. Treat MODT as P1 hardening, not a P0 cause.
- Do NOT adopt the plan's "canonical NIF layout" blindly — the critic showed it ALSO decodes garbage.
  The fixed decoder (P1-1) must be derived empirically against `Money_Prewar.nif` as a golden file.

---

## P0 — Immediate fix (in order; disk-verifiable before any launch)

1. **OBND writer** — `tools/mutagen-cli/src/Program.cs`: add `short[]? ObjectBounds` to `RecordSpec`;
   in `case "misc"` set `misc.ObjectBounds` (default `-7,-3,0 / 7,3,4`, or tighter z `…/7,3,1` for a
   flat card). (Read-back already reports `objectBoundsZero`.)
2. **Python passthrough** — `mcp-server/fo4_mcp/tools.py` MISC/BOOK normalizer: accept+forward
   `objectBounds` (len-6 Int16), default for model-bearing MISC.
3. **Rebuild** — `dotnet publish … -o C:/Modding/fo4-mcp/tools/mutagen-cli` (verify dll sha256 changed).
4. **Spec** — `staging/coupon-mod/prewar-coupons-spec.json`: add `objectBounds` + `value:8` to all 6.
5. **BGSM AlphaTest=0** — patch the 6 deployed `coupon_*.bgsm` (byte 0x2a → 0); fix the template going
   forward (P1-7). Opaque card, zero downside.
6. **Re-author + redeploy** the esp; **verify on disk** `objectBoundsZero==false`, `value==8`,
   BGSM AlphaTest==0.
7. **In-game eyeball (user-gated, MO2→F4SE only)** — `player.additem 0A000800 1` (Pip-Boy art+name+
   inspect) and `player.placeatme 0A000800 1` (world render). Direct Steam launch shifts index → don't.

---

## P1 / P2 — Permanent pipeline (prevent recurrence)

Per-subsystem robust recipe + deliverable (full detail in the workflow output). Dependency-ordered:

- **P1-1** Fix `nif_tri_decode.py` to a *donor-validated* FO4 BSTriShape layout (golden-file test). The
  current decoder is wrong (garbage on vanilla donor) — every "invisible mesh" verdict from it is
  untrustworthy until fixed. **P1-2 depends on this.**
- **P1-2** `fo4_validate_nif` — Layer-0 offline gate (renderable geometry + non-zero bound + OBND
  non-zero + MODL/BGSM/DDS chain resolves + **BGSM-AlphaTest-vs-diffuse-alpha cross-check**). The layer
  that would have caught this silent no-show class.
- **P1-3** MODT auto-fill (splice donor `Model.Data`) — needs a real `Model.Data != null` check first.
- **P1-4** Surface the existing CLI `misc` detail block through `tools.py fo4_inspect_record` (few lines).
- **P1-5** `fo4_splice_collision` MCP tool (structured block-type diff + post-splice byte-equality).
- **P1-6** `dds_header_audit.py` + recorded `texconv_convert.py` (fix diffuse linear→sRGB 98→99).
- **P1-7** `fo4_create_bgsm` (BA2-extracted *prop* presets, fixed 63-byte-header round-trip);
  reconcile `make_bgsm.py` drift (its template path is deleted → throws; deployed BGSMs came from
  `Note.BGSM`, not what the docstring claims). Lock `Materials\Props\NoteLowPoly.BGSM` as prop template.
- **P2** `fo4_nif_build` (EEVEE_NEXT fix + `cfg.blender_exe` + post-validate), `fo4_render_preview`,
  `fo4-mesh-author` skill, `build_coupon_mod.py` one-shot orchestrator, YNAM/ZNAM/keyword polish,
  Layer-1 `item_spawn` T3 job (use `cgf Debug.Notification` — `getitemcount` goes to console not Papyrus),
  RESUME.md update (mod IS deployed; MO2-launch-only; lock canonical NIF pipeline).

## Open risks
- In-game confirmation pending (user-gated). After P0 the most likely outcome is full success; residual
  risk if the *world* model still missing → investigate MODT (P1-3).
- OBND default is cloned from a money pile; a thin card may want tighter z. Any non-zero box fixes the
  symptom; tune for tidy inspect framing.
- Direct-launch FormID shift (0x0A→0x09) is a latent footgun — resolve by EditorID/`GetFormFromFile`
  in harnesses; document MO2-launch-only.

---

## Coupon collection showcase (separate planned feature)
Player-home settlement display board that auto-fills as the set is collected (PlaceAtNode +
Enable/Disable per-coupon refs; FO4 Papyrus has no node-hide). Deferred to P1+ after this pipeline is
hardened. See memory `coupon-collection-showcase`.
