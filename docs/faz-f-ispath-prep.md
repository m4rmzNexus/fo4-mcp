# Faz F-prep — IsPath* signature recovery + CTD root-cause (Track F-prep, autonomous)

**Status:** autonomous analysis DONE (everything below is on-disk-verifiable). The two *resolution*
paths are gated (C++ rebuild + in-game, or the Ghidra BN-2 compute session). This doc makes both
turnkey. Date: 2026-06-25.

## Why this exists

The headless in-game navmesh test (`tools/commonlibf4-template/src/main.cpp`, `NavSampleOnce`
lines ~276–282) **disables** the three `Actor::IsPath*` predicates:

```cpp
// A-in-game RE isolation (2026-06-21): the IsPath* predicates are TEMPORARILY disabled to
// test whether the pathing-time CTD is these vfunc reads (a possible address-library/runtime
// mismatch) vs the authored navmesh itself.
s.pathing = false;  s.pathValid = false;  s.pathComplete = false;
```

The navtest verdict therefore rests on **displacement alone** (`moved > 32.0f`), a weaker signal
than the engine's own pathing predicates. F-prep recovers what's needed to safely re-enable them.

## The three functions (fuzzy-match seed — verified from the vendored headers)

All three are non-virtual member functions `bool Actor::fn(void)` (implicit `this` = `Actor*`),
called by **`REL::Relocation` (address-library REL::ID)**, NOT vtable lookup. Source:
`tools/commonlibf4-template/lib/commonlibf4/include/RE/A/Actor.h:424-443` +
`include/RE/IDs.h:38-40`.

| function | C++ signature | CommonLibF4 REL::ID (NG db) |
|---|---|---|
| `IsPathValid`     | `bool Actor::IsPathValid()`     | **2230279** |
| `IsPathing`       | `bool Actor::IsPathing()`       | **2234312** |
| `IsPathingComplete` | `bool Actor::IsPathingComplete()` | **2230274** |

These IDs are version-independent; CommonLibF4 resolves ID→runtime-offset at load via the Address
Library version DB for the running build.

## ROOT-CAUSE HYPOTHESIS (primary) — missing 1.11.221 versionlib bin

On-disk facts (verifiable now):
- Game runtime = **1.11.221.0** (`Fallout4.exe` ProductVersion).
- Address Library present = **"All In One" 1.11.191 release** (`tools/address-library/F4SE/Plugins/`
  has `version-1-11-{137,159,169,191}-0.bin`; **no `version-1-11-221-0.bin`**).

A REL::ID call (IsPath*) needs the bin for the *exact* running build. With no 1.11.221 bin,
CommonLibF4's ID→offset lookup fails or falls back to a stale offset → the call jumps to the wrong
address → CTD. A vtable call (e.g. anything resolved through the object's vptr) is unaffected,
which is why `GetPosition`-based sampling still runs. This asymmetry is exactly the observed
behaviour (navtest loads + samples position fine; only the IsPath* reads crash).

## Resolution paths (both gated — present to user)

### Path 1 — obtain the 1.11.221 versionlib bin (CHEAP; no Ghidra) ⭐ recommended first
1. Download the current Address Library that covers 1.11.221 (Nexus 47327; downloads unblocked
   2026-06-05). Drop `version-1-11-221-0.bin` into `tools/address-library/F4SE/Plugins/` and into
   the deployed game `Data/F4SE/Plugins/`.
2. Re-enable the predicates in `main.cpp` (`s.pathing = actor->IsPathing();` etc.).
3. Rebuild the F4SE DLL (`xmake`, the user-gated C++ step — [[tier3-ingame-channel-proven]]) +
   redeploy; re-run the headless navtest. **Verify:** no CTD + `anyPathValid`/`anyPathing` now report
   true on the authored navmesh (a stronger PASS than displacement-only).
- If this fixes it, **Ghidra is not needed for IsPath at all** — the whole BN-2 motivation for this
  predicate collapses to a missing data file.

### Path 2 — Ghidra BN-2 fuzzy-match (the original plan; only if Path 1 fails)
Use the seed table above against the analyzed 1.11.221 `Fallout4.exe` DB
(`tools/ghidra/projects/fo4mcp_pilot.rep`) once BN-2 has run full auto-analysis:
- Search heuristics for each function: tiny leaf `bool(Actor*)` reading a pathing/movement
  controller field off `this`; cross-reference call sites near `AIProcess`/`MovementControllerNPC`.
- `bulk_fuzzy_match_functions` is a **ghidra-mcp server procedure** (not a local file) — it runs only
  with the Ghidra backend up (gated BN-1 register + BN-2 analysis). Feed it the 3 signatures; pin the
  recovered RVA offsets as hardcoded `REL::Offset` in `main.cpp` (bypassing the REL::ID db entirely).

## What is autonomously DONE vs gated
- **DONE (this doc):** signatures + REL::IDs extracted + verified; CTD root-cause hypothesis with
  on-disk evidence (runtime 1.11.221 vs versionlib 1.11.191 gap); both resolution paths scripted.
- **GATED:** the bin download+C++ rebuild+in-game re-test (Path 1), or BN-1/BN-2 Ghidra compute
  (Path 2). Both need a user trigger; pick Path 1 first (a data file beats an RE session).
