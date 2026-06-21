# V2 backlog

Items deliberately deferred past the MVP. Each has a reason and a "what V2
needs to do" so a future session can pick it up without re-investigating.

Created Session 5 (2026-05-28).

---

## 1. CK Papyrus backend (`fo4_papyrus_build(backend="ck")`)

**Status:** ✅ VALIDATED + CLOSED "won't-wire" (2026-06-05). Caprica (MIT) stays the
sole backend. The CK toolchain is now proven working and reproducible, but its
bytecode is functionally identical to Caprica's, so wiring it adds no value.

**Closed 2026-06-05 (blocker lifted → Option B executed → step-7 gate failed-to-justify).**
Download/TLS block cleared, so the 32-bit VC++ 2012 runtime was obtained WITHOUT admin:
official MS `vcredist_x86.exe` → `wix burn extract` (WiX v5, not fee-gated v7) →
`expand` the minimum-runtime cab → `MSVCP110.dll`/`MSVCR110.dll` (x86, v11.00.51106.1)
staged under `tools/vc110-x86/`. With `PATH` prepended by that dir and cwd = the Steam
`Papyrus Compiler/`: `PapyrusAssembler.exe` no longer dies `0xC0000135` (step 5), a real
CK compile of `TestScript.psc` produces `TestScript.pex` exit 0 (step 6), and the
Champollion `--asm` diff vs the Caprica fixture is **cosmetic only** — identical
instruction stream; differences are timestamps, `::temp0`/`::temp1` register names,
local ordering, and CK emitting unused `.flag` declarations Caprica prunes (step 7).
Per the step-7 decision criterion, equivalent bytecode → CK adds no value (and costs an
EULA-proprietary compiler + Steam-CK dependency + staged x86 runtime). `backend="ck"`
raises by design. Full evidence + the exact working invocation (to re-open only if
applied-flag fidelity ever matters): `research/p0/ck-papyrus/2026-06-05-runtime-context.md`.

<details><summary>original deferral rationale (kept for history)</summary>

**Status:** deferred (formal). Caprica is the supported MVP backend (Session 4
decision D2).

**Why deferred:** Bethesda's `PapyrusCompiler.exe` (and `PapyrusAssembler.exe`)
do not run standalone — launched directly they fail with
`STATUS_DLL_NOT_FOUND (0xC0000135)`. They expect the Creation Kit launcher's
runtime context (working dir, DLL search path, registry state). Caprica (MIT,
`tools/caprica/Caprica.exe`) compiles the same `.psc` with a clean CLI and no
launcher dependency, so it is the default and only wired backend.

See `research/p0/papyrus/2026-05-15-bytecode-diff.md`.

**Root cause re-pinned 2026-06-05 (ultracode sweep — supersedes the "launcher
runtime context" guess):** the blocker is a **missing 32-bit VC++ 2012
redistributable**, NOT cwd/env/launcher. `PapyrusCompiler.exe` now runs
standalone (exit 0; .NET Fx 3.5 installed), but `PapyrusAssembler.exe` (x86)
imports `MSVCP110.dll`/`MSVCR110.dll` and dies `0xC0000135` — only x64 copies
exist; `SysWOW64\MSVCP110/MSVCR110.dll` are absent. MO2-launching CK unblocked
the *editor*, not the standalone assembler (a hard machine-level missing-DLL, no
VFS helps). **What V2 needs:** (a) install `vcredist_x86.exe` OR stage the two
32-bit DLLs under `tools/vc110-x86/` (download-gated by the SSL/clock block, same
as #8) — never into the read-only Steam `Papyrus Compiler/` dir; (b) wrapper =
`run_tool(PapyrusCompiler.exe, [obj-no-ext, -f=<flg>, -i=dir1;dir2, -o=<gated>],
cwd="Papyrus Compiler/", env=PATH-prepend dll_dir)`; (c) **gate wiring on a
Caprica-vs-CK `.pex` bytecode diff** — if equivalent, close "won't do". Caprica
(MIT) stays default. Spec: `research/p0/ck-papyrus/2026-06-05-runtime-context.md`.

</details>

---

## 2. Record-scoped Mutagen CLI for `fo4_inspect_record` — ✅ SHIPPED (2026-06-05)

**Status:** SHIPPED. `tools/mutagen-cli/mutagen-cli.exe` is now the preferred
backend for `fo4_inspect_record`; Spriggit serialize stays as the fallback.

**Shipped 2026-06-05 (blocker lifted).** The NuGet/TLS block (ahead sandbox clock →
cert-expiry) cleared — `ssl_verify_result=0` on api.nuget.org — so the §6 plan ran:
restore smoke-test (12.9s, verified) → reality-checked the Mutagen 0.53.1 API by
compiling a probe (`new ModPath`, `Fallout4Mod.CreateFromBinaryOverlay`,
`EnumerateMajorRecords`, `LoquiRegistration.GetRegister().Name`) → implemented →
`dotnet publish` (net9, framework-dependent) → elbow-tested 7 cases → wired with a
backend-agreement test. **Design landed on Option A** (not B): the probe showed the
three asserted fields come free and identical to Spriggit — `FormKey.ToString()`
→ `000800:test_armor.esp` and Loqui name → `GlobalInt` (== Spriggit
`MutagenObjectType`) — so the heavy serialization package was NOT pulled in. The
`yaml` field is a compact top-level stub on this backend (no consumer reads it;
full field-tree fidelity stays a Spriggit feature, reachable via the fallback).
**Reality-check surprise:** the binary overlay reads a plugin's own records WITHOUT
resolving masters, so the spec's master-resolution risk (binding a Data dir) did
not apply. Source version-controlled at `tools/mutagen-cli/src/` (2 files, gitignore
exception); published binary + bin/obj ignored. Backend reported via a new `backend`
field in the response (`"mutagen-cli"` | `"spriggit"`). 4 new tests incl. a live
two-backend agreement check (both binaries present). See
`research/p0/mutagen-cli/2026-06-05-record-query.md`.

<details><summary>original deferred spec (kept for history)</summary>

**Status:** working via Spriggit serialize; performance upgrade deferred.

**Why:** `fo4_inspect_record` currently serializes the *whole* plugin via
Spriggit and scans the YAML tree for the target record. Correct, but O(plugin
size) per call — slow for `Fallout4.esm`-scale masters. Synthesis was rejected
as a backend (no record-query CLI; see
`research/p0/synthesis/2026-05-28-cli-argv.md`).

**What V2 needs:** a small custom `Mutagen.Bethesda.Fallout4` console app that
loads a plugin and dumps a single record by FormKey/EditorID, kept behind the
same subprocess GPL boundary. Removes the full-serialize cost.

**Spec done 2026-06-05 (ultracode sweep), build blocked.** Full paste-ready spec
in `research/p0/mutagen-cli/2026-06-05-record-query.md`: net9 console app, argv
`--plugin <path> --record <FormID|EditorID> [--format json|yaml]`, streams
`EnumerateMajorRecords()` and breaks at first match (no temp-dir write); `.csproj`
refs `Mutagen.Bethesda.Fallout4 0.53.1` (+ serialization pkg to keep the `yaml`
field stable); `dotnet publish -c Release -r win-x64 --self-contained false -o
tools/mutagen-cli` (net8+net9 SDK present). **BLOCKED on NuGet restore:** ahead
sandbox clock → TLS cert-expiry (same class as #8); do NOT disable verify. When
unblocked: restore smoke test → reality-check the 0.53.1 read/serialize API
against a fixture → implement → wire as preferred backend with Spriggit fallback +
backend-agreement test. Must preserve `_norm_formid` (low-6-hex) semantics.

</details>

---

## 3. ESL-flag read/write — ✅ DONE (Session 6, 2026-06-05, ultracode sweep)

**Shipped — pure-Python, the Mutagen precondition was wrong.** The Light Master
bit `0x0200` lives in the TES4 record flags uint32 at absolute file offset 8;
reading/flipping it needs no Mutagen CLI (item 2), just a header edit like
`fo4_ba2_version_patch`. Two tools: `fo4_read_esl_flag` (read-only — closes the
gap where `light` was an extension guess; detects an ESL-flagged `.esp`) and
`fo4_set_esl_flag(plugin, output_path, enable=)` (gated output staging/fixtures +
`.bak` + eligibility-verdict warning). Verified against 5 real files (.esm=0x81,
CC .esl=0x281). 13 tests. Spec: `research/p0/esl-flag/2026-06-05-flag-write.md`.

---

## 4. Version-aware BA2 packing

**Status:** reference fact captured; no tool yet.

**Why:** this AE/NG install mixes BA2 header versions — v1 (original) and
v7/v8 (next-gen update) coexist (see
`research/p0/spriggit/2026-05-28-ng-ba2.md`). A BA2 packer that writes the
wrong version byte produces archives the target runtime won't load.

**What V2 needs:** any future `fo4_pack_ba2` (BSArch/Archive2 wrapper) must take
an explicit version arg and default it to match the detected runtime (OG vs NG).
Spriggit is unaffected — it serializes plugins, not archives.

---

## 5. CLASSIC headless invocation

**Status:** not needed for MVP (native crash-log parser used instead).

**Why:** CLASSIC v9's native CLI is GUI-primary and exposes no usable headless
scan (see `research/p0/classic/2026-05-28-format-notes.md`).
`fo4_analyze_crash_log` parses the raw crash log directly.

**What V2 needs:** if CLASSIC's mod-conflict database lookups (FormID ->
known-bad-mod) become desirable, solve the headless invocation (settings-driven
`SCAN Custom Path` + `Disable CLI Progress`, or a newer CLASSIC build) and parse
its AUTOSCAN markdown as an enrichment layer over the native parser.

---

## 6. Skill pack (`skills/`)

**Status:** T0 foundation + T1 composite + T2 release + T3 runtime DONE. 8 skills:
fo4-setup-check, fo4-record-edit, fo4-crash-debug, fo4-papyrus (T0);
fo4-armor-swap, fo4-quest-author (T1); fo4-package-release (T2);
fo4-ingame-test (T3, wraps `fo4_run_ingame_test`).

**What's left:** discovery deploy (junction into `.claude/skills/`); Codex-CLI
variant if desired; new skills as the tools below land.

---

# Session 6 sweep additions (2026-05-29)

From a FO4 2026 best-practice + tooling sweep (parallel agent). Sources are in
`TASKS.md` §Best-practice log. Each is a candidate MCP tool; per the project
rule, the task is recorded HERE first, built later. Autonomous = no user needed;
gated = needs the user (install/consent/irreversible op).

## 7. `fo4_check_esl_eligibility` — ✅ DONE (Session 6, 2026-05-29)

**Shipped.** Read-only Spriggit-serialize backend; reports new-record count, max
ObjectID, new cell/worldspace count, referenced-master lower bound, and an
advisory verdict (esm-flag / esl-eligible / esl-needs-compaction / plain-esp /
no-new-records), with a SPID `<0x800` warning. Verdict logic factored into the
pure `_esl_verdict` (8 unit tests) + 1 fixture integration test. Wired in
server.py. Flag-writing/compaction stay gated (#3, #14). Powers
`fo4-package-release` + `fo4-armor-swap`.

## 8. `fo4_pack_ba2` via BSArchPro (autonomous)

Wrap BSArchPro (mods/63243; actively-maintained BSArch successor, outputs OG v1
AND NG v7/v8). Enforce naming `<Mod> - Main.ba2` / `<Mod> - Textures.ba2`
(load-bearing — wrong name = game won't auto-attach). Default v1 for max compat.
Supersedes old V2 #4.

**BLOCKED on download (2026-05-29):** `tools/fetch-nexus.py bsarchpro` fails with
`SSL: CERTIFICATE_VERIFY_FAILED: certificate has expired` — the sandbox clock is
set to a future date, so live TLS certs read as expired and cert verification
can't pass (swapping CA bundles won't fix a clock-ahead). Not disabling verify
(the Nexus API key rides that header). User approved download + gitignore/no-
distribution when it's unblocked. TARGETS entry already added to fetch-nexus.py.
Until then, pack BA2s manually with `tools/xedit/BSArch64.exe`; downgrade with
the shipped `fo4_ba2_version_patch`. See TASKS #U3.

## 9. `fo4_generate_fomod` — ✅ DONE (Session 6, 2026-05-29)

**Shipped.** ElementTree codegen of `fomod/info.xml` + `fomod/ModuleConfig.xml`
from a spec (name/author/version + required_files + install_steps/groups/plugins).
Validates group/plugin type enums (warns, doesn't fail, on non-standard). Output
gated to staging/fixtures. Pure (no subprocess) → 5 unit tests. Wired in
server.py. Powers `fo4-package-release` step 6.

## 10. `fo4_ba2_version_patch` — ✅ DONE (Session 6, 2026-05-29)

**Shipped — pure-Python header rewrite, no download needed** (chose "rewrite in
code" over wrapping the Nexus tool, which is download-blocked). Rewrites the BA2
version uint32 (NG v7/v8 ↔ OG v1); body untouched; verified against offset in
real archives (HUDFramework v1 GNRL, game NG v8 GNRL). Gated output + `.bak`;
warns on DX10 texture downgrade (version flip alone may not satisfy OG texture
loaders). Pure `_patch_ba2_version_bytes` + real-BA2 integration test (9 tests).

## 11. Config-correctness linter — ✅ DONE (`fo4_lint_engine_config`, 2026-05-29)

**Shipped.** Parses an Addictol/Buffout engine-config TOML (tomllib) and flags:
(a) no-op settings (e.g. `nMaxPapyrusOpsPerFrame` with `bBakaMaxPapyrusOps=false`),
(b) bad scaleform values (multiple-of-8, 8..2048), (c) double-patching — if a
plugins_dir is given and Addictol coexists with standalone Buffout4/X-Cell/Baka
DLLs (Addictol already bundles them). Ruleset derived from the real Addictol.toml.
Pure `_lint_engine_config` (6 unit tests) + file/double-patch tests (10 total).
Verified clean against the real config (no false positives). Advisory neighbor to
`fo4_analyze_crash_log`.

## 12. `fo4_build_lod` via xLODGen — ✅ DONE as argv-builder (2026-06-05, ultracode sweep)

**Shipped, but generation stays user-driven.** xLODGen is a GUI fork of xEdit —
`-autoload/-autoexit` only skip the module-select dialog; worldspace selection +
"Build meshes" is interactive, so there is NO headless LOD generation. The tool
constructs + validates the verified argv (`-fo4 -o:"<dir>" [-d:/-p:/-m:] -lodgen
-autoload -autoexit`), gates the output dir (staging/fixtures), and defaults to
`dry_run=True` returning the command for the user to run interactively (best as
an MO2 tool so the VFS supplies the load order). License UNVERIFIED — flagged in
the docstring/envelope/MANIFEST. 7 tests. See TASKS #U4 +
`research/p0/xlodgen/2026-06-05-cli-probe.md`.

## 13. `fo4_build_previs` — ✅ DONE (2026-06-05, ultracode sweep; see TASKS #U1b)

**Shipped.** CK *precombine/previs CLI flags* run headless WITH CKPE:
`CreationKit.exe -GeneratePrecombined:<esp> clean all`,
`-GeneratePreVisData:<esp> clean all`, `-CompressPSG:<esp>`, `-BuildCDX:<esp>`.
Tool: `step in {precombined,previs,compress_psg,build_cdx,full}` (full = ordered
pipeline). CreationKit.exe resolved from `cfg.fo4_install_dir`. **dry_run=True by
default** (returns validated argv WITHOUT executing — a real run is long/machine-
locked/irreversible, user-triggered). CK Data output (Meshes\Precombined, Vis,
.csg/.cdx) intentionally not check_write-gated (CK owns Data; the run is the
explicit trigger). 14 tests. Remaining: one user-driven `dry_run=False` smoke run
on a tiny plugin to confirm the `clean all` token before treating as battle-
tested. (PJM `-script:` merge step still manual; corrects V2 #1's assumption.)

**Prerequisite (user-gated):** Creation Kit Platform Extended (CKPE, Perchik71,
LGPLv3, mods/51165). Needed for reliable batch CK runs. Install touches the CK
dir `C:/.../Fallout 4 1946160/` which is **read-only Steam space** — resolve via
junction or MO2-launch, NOT a direct Steam-dir write. Long machine-locked runs.
Strategic capability for quest authoring; its own milestone. LGPL → subprocess-isolate.

## 14. `fo4_compact_formids` — ✅ DONE as safe-gating (2026-06-05; see TASKS #U2)

ESL FormID compaction. **Irreversible + save-breaking.** Shipped as SAFE GATING +
planning, not a silent destructive run: requires `confirm=True` AND
`saves_backed_up=True` (else returns a refusal envelope), makes a `.bak` before
any write, defaults `dry_run=True` (returns plan + documented xEdit cmd, zero side
effects). Reality-check: xEdit's "Compact FormIDs for ESL" is a GUI context-menu
action with no community-confirmed reliable headless script, so the tool opens the
`.bak`-protected plugin and the user performs the menu action
(`automatable: gui-required`). 8 tests.

## Note: AWKCR deprecated

Not a tool — a standing rule. AWKCR (Armor & Weapon Keywords Community Resource)
is discouraged for new authoring in 2025+ (heavy, conflict-prone, stalled). New
armor mods use vanilla keywords + a minimal custom set. Baked into
`fo4-armor-swap`.

---

# Save-edit / save-cleaning layer (user-requested, 2026-05-29)

From a parallel-agent research sweep. `fo4_backup_saves` (the archival half) is
already shipped; this is the EDIT half. Task recorded first per project rule.

## 15. `fo4_inspect_save` — read-only save report (autonomous; BUILD-NEXT for this layer)

Copy save → parse → report: plugins present/missing, change-form counts per
plugin, unattached/undefined script-instance counts, active-script/queued-thread
count, size breakdown. **Read-only, zero corruption risk — the safe autonomous
win.** Tells the user exactly what stale state a mod removal left behind.

**Format:** `.fos` magic `FO4_SAVEGAME`; header → screenshot → form-version →
plugin list → light-plugin list → file-location table → global-data (block 1001
= Papyrus VM) → change-forms → formID array. Compression: none / zlib / **LZ4** —
a parser MUST handle LZ4 or it breaks/corrupts on compressed saves (the #1 gotcha;
the prototype below misses it). Reality-check against a REAL AE save before trust.

## 16. `fo4_clean_save_{undefined,changeforms,unattached}` (USER-GATED by design)

**✅ BOTH BACKENDS SHIPPED (2026-06-05).** (A) `fo4_clean_save_changeforms` = native
pure-Python (#16-A). (B) `fo4_clean_save_papyrus(mode=undefined|unattached)` = headless
ReSaver (Apache-2.0) Java shim (#16-B) — the JRE/JDK block lifted, so Temurin JDK 21 was
downloaded (no admin), `tools/resaver-shim/CleanShim.java` (~90 lines) compiled against
`ReSaver.jar`, and the spec's exact API ran first try: `ESS.readESS` → `Papyrus.remove*`
→ `ESS.writeESS`, re-reading its own output as a corruption oracle. **Validated on real
saves:** no-op output byte-size-identical + re-read by our independent Python parser;
`unattached` removed 1 instance on a 5 MB save; `undefined` scaled to a 79 MB / 630k-
script-instance save. Headless confirmed (Swing models only, no display; `System.exit()`
for the non-daemon pool). Gated: `confirm=True`, staging-only `check_write` (fail-closed
first), ReSaver `.bak`, and **`unattached` needs `accept_unattached_risk=True`** (engine-
normal in FO4). 6 tests (5 gating + 1 live integration). Refuses cleanly if the JDK/shim
toolchain is not built. Did NOT reimplement the Papyrus VM in Python — drove ReSaver's
battle-tested engine. See `research/p0/save-clean/2026-06-05-write-path.md` (§ "Backend B
EXECUTED").

<details><summary>original spec (kept for history)</summary>

**Write-path spec done 2026-06-05 (ultracode sweep):**
`research/p0/save-clean/2026-06-05-write-path.md`. Split by difficulty: **(A)
`fo4_clean_save_changeforms` = ✅ SHIPPED (2026-06-05)** — native pure-Python write
path: full-body span-walker + ChangeForm drop by user-named removed plugins (never
auto-pick) + 100-byte FLT rebuild (6 absolute offsets + live count); flat list, no
cross-ref fixup. Gated output + confirm + .bak; 10 tests. Proven by a byte-identical
no-op roundtrip on a real 5.07 MB AE save (walker reaches EOF exactly). **(B)
`undefined`/`unattached` = deep Papyrus-VM (GlobalData 1001) graph surgery** → use
a ~150-line Apache-2.0 ReSaver Java shim (`ESS.readESS` → `removeUndefinedElements`
/`removeUnattachedInstances` → `ESS.writeESS`); do NOT reimplement the VM in
Python. **Blocked:** no Java/JRE + JRE download SSL-blocked (#8 class). Confirmed:
FO4 saves are NOT compressed on read OR write (the #15 "MUST handle LZ4" note is a
Skyrim-SE carryover, wrong for FO4). Recommend building (A) first; validate with a
no-op roundtrip on a real AE save before trusting any writer.

</details>

Cleaning is **damage control, not safe uninstall.** FO4-specific: unattached
instances are engine-NORMAL — blind removal corrupts good saves (FallrimTools
warns this). So: output to staging only, diff-gate, never in place, explicit
confirm, loud warning on `unattached`. `undefined` (defining plugin gone) is the
safer class; `changeforms` requires the user to name the missing plugins (never
auto-pick). Plus `fo4_apply_cleaned_save` as a separate gated copy-back step.

## Backends + verdict

- **ReSaver / FallrimTools** — `github.com/mdfairch/FallrimTools`, **Apache-2.0**
  (CORRECTION: author is **Mark Fairchild / mdfairch**, NOT ousnius; license is
  permissive Apache-2.0, the rare non-GPL tool in this stack — no contagion).
  FO4 first-class, handles LZ4+zlib. **Shipped CLI canNOT clean headlessly**
  (Picocli wired only to GUI-launch flags + a single `-i/--inventory` dump). BUT
  the engine is Swing-free + public: `ESS.readESS/writeESS`, `Papyrus.
  removeUnattachedInstances/removeUndefinedElements`, `ESS.removeChangeForms`.
  **Backend A (recommended/trustworthy):** a ~150-line Apache-2.0 Java shim over
  `ReSaver.jar` → JSON-in/out headless `report`/`clean`. Cost: write the shim +
  bundle a JRE in `tools/` (download-blocked now).
- **`pub-struct/fo4-save-cleaner`** — MIT, Python, real CLI (`--analyze-only`,
  `--remove-all-mods`, `-o`). **Backend B (fast/low-trust):** unproven (0 stars),
  reverse-engineered, and **no LZ4 decompress** → uncompressed saves only. Treat
  as reference/prototype, NOT a trusted writer until compression + roundtrip are
  validated on the user's real saves.
- **No Mutagen/.NET `.fos` parser exists.** A native Python parser is feasible
  (format is documented) but is a real build (LZ4 + ChangeForm + Papyrus VM) and
  must be validated against a real AE save.

**Verdict:** feasible near-term, but cleaning stays user-gated by design; don't
drive ReSaver's GUI. Sequence: `fo4_inspect_save` (read-only) → FallrimTools
Apache-2.0 Java shim → gated `clean_*` on top → separate gated apply. All of it
is currently blocked on a tool download (FallrimTools jar / JRE / pub-struct) —
same SSL/clock block as #8/#A2 — OR a from-scratch native parser. `fo4_backup_saves`
is the shipped precondition; always run it first.

---

# Native-code RE axis (Ghidra integration) — research milestone (2026-06-05)

**Status:** research-only; build NOT started. Opens a NEW capability axis — native
DLL / reverse-engineering tooling, parallel to the existing data/Papyrus axis (all
current 18 tools are ESP/BA2/save/previs/config). Serves the persona's "kendi DLL
açık (CommonLibF4)" side, a real but secondary track. Evaluated by a parallel agent
(2026-06-05).

**Decision criterion (the whole call hinges on this):** *am I extracting my own
addresses, or leaning on the community Address Library / versionlib?*
- Leaning on versionlib → integration is **not worth it** (duplicate work, marginal
  gain).
- Doing my own RE → **net gain**, especially the version-diff porting tool.

**Why it fits this project (when it fits):**
- **Headless:** Ghidra `analyzeHeadless` + post-scripts → no GUI block, matches the
  "don't freeze a signature without a hand-tested CLI" rule (unlike xLODGen/ReSaver).
- **Apache-2.0** → entirely outside the GPL-contagion concern; Karar-7 clean.
- Native RE need is real for F4SE-style plugins: RVA/address, struct & vtable
  offsets, hook targets, AOB signatures.

**Candidate tools (grouped by value):**

High value (novel; not a community duplicate):
- **`fo4_diff_versions`** — RVA-shift report between two `Fallout4.exe` builds
  (e.g. 1.10.x → 1.11.x NG). THE killer app: port the DLL before Address Library
  updates; stale offsets after a runtime update are the #1 crash-wave cause.
- **`fo4_find_signature`** — AOB signature + call-site analysis for a hook target
  nobody has documented yet → feeds a CommonLibF4 hook stub.
- **crash decompile depth** — extend `fo4_analyze_crash_log`: today Buffout gives
  the symbol *name* only; decompiling the faulting RVA shows *why* (which member
  null-deref, which branch). Turns crash debug from name → root cause.

Medium value (duplicate if you lean on community DB):
- **`fo4_resolve_address`** — Address Library ID↔RVA. meh321's DB already exists;
  only valuable for your own novel addresses.
- **`fo4_dump_struct`** — vtable/member offsets → C++ header. CommonLibF4 already
  documents these; only for undocumented/new engine areas.

**Prerequisites + boundaries (honest):**
- **Heavy:** JVM + first auto-analysis takes minutes → an analysis-DB cache is
  mandatory (e.g. `tools/ghidra-projects/`), else every call is slow.
- `Fallout4.exe` is read-only Steam space (Karar 4) → import a **COPY** into
  Ghidra; never write to the original.
- Value is entirely conditional on doing native-DLL work. Pure quest+armor
  authoring leaves this axis idle.
- Medium-value tools (resolve_address, dump_struct) are marginal if you rely on
  the community versionlib.

**Net:** the real wins are `fo4_diff_versions` + `fo4_find_signature` + crash
decompile. Without those, Ghidra is "installed for its own sake." Build only when
native-DLL work is active AND the goal is own-RE over versionlib. License is clean
(Apache-2.0); the only build cost is the analysis-cache plumbing + COPY-of-exe
discipline.

---

# Record authoring axis (NPC / quest / dialogue) — epic (2026-06-05)

**Status:** Faz 0 PROVEN; **Faz 1 + 1.1 + 1.2 (rich ARMO) + Faz 2 (quest skeleton) + Faz 2.1a
(quest dialogue topics) + Faz 2.1b (INFO conditions) + Faz 2.1c (quest aliases) +
Faz 2.1d (Papyrus VMAD binding) + Faz 2.1e (SCEN scenes) + Faz 2.1f (quest stage script
fragments) + Faz 2.1g (quest alias fragments) + Faz 2.2 (fragment `.pex` loop) SHIPPED (2026-06-05/06)** —
`fo4_create_record` authors NPC (Race/Class/factions), Armor (keywords/value/weight/
armor-rating/biped slots), and Quest records
(type/flags/stages/objectives + quest-nested dialogue: DIAL → INFO → spoken lines + INFO
conditions gating when a line fires + quest aliases: QuestReferenceAlias cast slots with
ForcedReference/UniqueActor fill + find-matching-ref conditions + Papyrus VMAD: attach
scripts by .psc name with typed properties + SCEN scenes: Scene records back-linked to the
quest with a cast of actors by alias ID, flow phases with conditions, and a dialogue-action
timeline referencing topics + stage script fragments: a QF fragment script + per-stage
Fragment_* entries, metadata only + alias script fragments: per-alias OnBegin/OnEnd scripts
bound by alias ID into QuestAdapter.Aliases, metadata only + the fragment `.pex` loop: a fragment
`.psc` compiles via fo4_papyrus_build to the exact `.pex` the metadata names). **Faz 2.2a (2026-06-06)
fixed the QUST stage writer (QSDT marker + RunOnStart) — in-game fragment root-cause A.**

**Faz 3 — new-world-content quest (roadmap LOCKED 2026-06-06):** a 17-agent / 5-phase planning
workflow (`wf_5ec027a8-368`) locked the full 13-phase roadmap (W0–W12) for authoring a quest that
CREATES world content — placed refs/cells, deep NPC + template chain, FACT, Story-Manager start,
AI packages, locations, voice/lip, FaceGen. Canonical: **`docs/world-content-quest-roadmap.md`** +
TASKS.md W0–W12 tree. The Mutagen-vs-CK boundary is locked (record authoring = agent-automatable;
navmesh-gen / previs-regen / FaceGen / TTS = human-gated CK batch). **V2-deferred by that roadmap
(tracked, not forgotten):** SMEN event-node authoring, PACK ProcedureTree/PackageAdapter/idle-anims,
multi-plugin merge code-path (create_record writes one plugin / one FormID allocator), exterior
worldspace LAND/terrain generation, AI-TTS voice (vs silent-subtitled MVP), TERM + NOTE exposition
records (14 TERM + 6 NOTE in the Remnants dump), workshop STAT→COBJ buildables. The pre-Faz-3 niche
items (QuestLocationAlias/QuestCollectionAlias, SceneActionStartScene) are folded into roadmap W6.7/W9.
Opens the second major capability the persona actually wants: creating content
(NPCs, quests, dialogue), not just inspecting/optimizing it. The other 21 tools
read or transform existing records; `fo4_create_record` is the first that *creates* one.

**Why not reverse-engineer CK (decided 2026-06-05):** CK's authoring is a GUI with
no automation surface (no CLI/COM/scripting API for record creation), and RE-ing its
internals to create records re-solves an already-solved problem — Mutagen reimplements
the ESP/ESM model from scratch. RE effort is reserved for CK-*exclusive computations*
(previs/FaceGen/lip), and even those go through CK's existing batch CLI first. CK RE
for authoring = rejected.

**Faz 0 — round-trip proof (✅ DONE 2026-06-05):** exported the CC quest mod
`ccOTMFO4001-Remnants.esl` → Spriggit YAML → re-imported (same filename) → re-exported
→ diffed. **375/393 records byte-identical; Quests/Scenes/Npcs/Dialogue ZERO diff.**
The full QUST→SCEN→alias→VMAD(Papyrus)→dialogue graph round-trips semantically lossless.
Only cosmetic diffs: package-data `Key` reorder (11 files) + worldspace `-0`→`0` (7).
→ Mutagen-driven authoring is viable. Evidence:
`research/p0/authoring/2026-06-05-quest-roundtrip-proof.md`.

**Faz 1 — MVP record writer (✅ SHIPPED 2026-06-05):** extended the read-only
`tools/mutagen-cli/` with a `create` subcommand (JSON spec → `new Fallout4Mod` →
`AddNew(Npc|Armor)` → `WriteToBinary`); the query path is untouched (dispatch on
`args[0]=="create"`). Wrapped as `fo4_create_record` (gated output staging/fixtures +
`confirm_overwrite` + `.bak`; requires the writer binary, no Spriggit fallback). MVP
scope: NPC + ARMO, EditorID + optional Name, no graph/Race/Class → a structurally-valid
plugin, not yet in-game-functional. **Reality-check (two independent engine paths):**
generated a 401-byte `.esp`, FormKeys in the ESL-safe range (0x800+), re-read via the
overlay query AND Spriggit's full importer (records land in the correct type folders,
Name round-trips). 10 tests (4 spec-validation + 3 gating + 3 live integration).
Spriggit YAML stays the git-tracking/diff layer.

**Faz 1.1 — richer NPC fields (✅ SHIPPED 2026-06-05):** the `create` spec now
takes per-NPC `race` + `class` FormLinks and a `factions` list ({faction, rank}).
The writer parses each `"<6hex>:<master>"` FormKey, sets the link, and lets
Mutagen's master-iterate auto-add the referenced master to the header. **Round-trip
proof is built into the tool:** after `WriteToBinary` it re-opens the file from disk
and reads `race`/`class`/`factionCount` + the master list back into the response.
Verified end-to-end with HumanRace (`013746:Fallout4.esm`) + MinutemenFaction
(`068043:Fallout4.esm`): 442-byte `.esp`, `masters: ["Fallout4.esm"]`, race + 1
faction read back. +4 tests (3 NPC-field validation + 1 live race/faction
round-trip) → 14 create tests, 223 suite. ARMO richer fields (keywords/value/
armor-rating/biped) = Faz 1.2 if needed; quest graph = Faz 2.

**Faz 1.2 — rich ARMO fields (✅ SHIPPED 2026-06-06):** the `create` spec now takes,
for `type: "Armor"`, a `keywords` FormLink list (→ `armo.Keywords`), `value` (Int32),
`weight` (Single), `armorRating` (DNAM **UInt16**, 0–65535), and `bipedSlots`
(`BipedObjectFlag` names OR'd into `BipedBodyTemplate.FirstPersonFlags`). The MVP
deliberately defers fields that need file/ARMA coupling (world-model NIFs, ARMA
armatures, object-mod templates, race/enchant/destructible). **Reality-check by reflection
FIRST** (CLAUDE.md §4): a throwaway probe confirmed `Armor.Value`=Int32, `Weight`=Single,
`ArmorRating`=**UInt16** (not float), `Keywords`=`ExtendedList<IFormLinkGetter<IKeywordGetter>>`
(add `new FormLink<IKeywordGetter>(fk)`), `BipedBodyTemplate` (concrete class, ctor `()`,
settable `FirstPersonFlags`). Keywords/value/weight/armorRating/biped-slots are now
read back from disk (`check.Armors` loop — armor had **no** read-back before, so this
also closes the round-trip-proof gap for ARMO). Biped-slot names are mirrored in Python
(`_BIPED_OBJECT_FLAGS`) for a clean early reject; the CLI's `Enum.TryParse` stays
authoritative. **Two independent engines:** in-tool read-back (`value:250`, `weight:12.5`,
`armorRating:110`, `keywordCount:2`, `bipedSlotCount:3`, `masters:["Fallout4.esm"]`) AND
Spriggit YAML (`Keywords`/`Value`/`Weight`/`ArmorRating`/`BipedBodyTemplate.FirstPersonFlags`
all present). +3 tests (2 ARMO-field validation + 1 live rich-armor round-trip) → 35 create
tests, 244 suite.

**Faz 2 — quest skeleton (✅ SHIPPED 2026-06-06):** the `create` spec now authors
`type: "Quest"` records: `questType` (`Quest.TypeEnum` name), `flags` (`Quest.Flag`
names, OR'd onto `Quest.Data`), `stages` ({index, logEntry} → `QuestStage` +
`QuestLogEntry`), `objectives` ({index, text} → `QuestObjective`). **Design decision:
direct Mutagen C# codegen** (not YAML-authoring → `spriggit_import`) — consistent with
the existing writer, typed + validated, and the truly-independent verifier (CK/xEdit/
game) is manual either way since Spriggit is itself Mutagen-based. API reality-checked
by reflection first (flags/type live on `Quest.Data`, a sub-object — not direct Quest
properties; `Quest.Data` is settable-nullable so guarded with `??= new QuestData()`).
Read-back proof built in: re-opens the file and reports `name`/`questType`/`stageCount`/
`objectiveCount`. Verified e2e: "The Concord Errand", SideQuests, 3 stages + 2
objectives → 000800, all read back. +4 tests → 18 create / 227 suite.

**Faz 2.1a — quest dialogue topics (✅ SHIPPED 2026-06-06):** the `create` quest spec
now authors `topics` — quest-nested `DialogTopic` (DIAL) → `DialogResponses` (INFO) →
`DialogResponse` (spoken lines). Each topic takes `editorId`/`name`/`subtype`
(`SubtypeEnum`)/`category` (`CategoryEnum`); each response takes `prompt` + optional
`speaker` FormLink (INpc); each line takes `text` + `responseNumber` (Byte, auto-
sequenced when 0) + optional `emotion` FormLink (IKeyword). API reality-checked by
reflection first: `DialogTopic`/`DialogResponses` are major records constructed via
`new DialogTopic(mod, editorId)` (FormKey minted from the mod allocator); `DialogResponse`
is a sub-record (`ctor()`, no FormKey); `DialogTopic.Quest` is the quest back-link.
Read-back proof built in: re-opens the file and reports `topicCount`/`infoCount`/
`lineCount`. Verified e2e: "The Concord Errand" with 2 topics / 2 INFO / 3 lines →
quest 000800, topics 000801/000803, INFO 000802/000804, all read back; an independent
Spriggit export confirmed the topics serialize under `Quests/.../DialogTopics/.../
Responses/` exactly as the probe predicted; the spoken-line text + prompt persist in
the INFO YAML. +3 tests → 21 create / 230 suite.

**Faz 2.1b — INFO conditions (✅ SHIPPED 2026-06-06):** each response (`DialogResponses`)
now takes a `conditions` list that gates when the line fires. API reality-checked by
reflection: FO4's condition model is far simpler than Skyrim's — `Condition` has only 2
concrete subclasses (`ConditionFloat`/`ConditionGlobal`) and `ConditionData` has only 2
(one being a **generic `FunctionConditionData`** with a `Function` enum + 2 typed param
slots), so ALL 479 `Condition.Function` names (GetStage=58, GetIsID=72, GetQuestRunning=56,
…) work through one code path — no per-function classes. A condition spec = `function`
(required) + `comparison` (`CompareOperator`, default EqualTo) + `value` (float, default 1)
+ `param1`/`param2` (FormKey "<hex>:<modkey>" → record slot, int → number slot, else string)
+ `runOn` (`Condition.RunOnType`, default Subject). Condition record-params auto-add their
master like any FormLink. Read-back adds `conditionCount`. Verified e2e + Spriggit: a
"Gated" quest with GetStage>=10 + GetIsID==1 → `conditionCount: 2`, masters auto-added
from the param FormKeys; the Spriggit INFO YAML shows `ConditionFloat`/`GreaterThanOrEqualTo`/
`FunctionConditionData`/`GetStage`/`ParameterOneRecord` exactly as authored. +2 tests →
23 create / 232 suite. The same `ConditionFloat` builder is reusable for quest-objective
target conditions, alias fill conditions, and `Quest.DialogConditions` when those land.

**Faz 2.1c — quest aliases (✅ SHIPPED 2026-06-06):** `Quest.Aliases` now takes a list
of `QuestReferenceAlias` cast slots. API reality-checked by reflection: `Quest.Aliases`
= `ExtendedList<AQuestAlias>` (abstract base, 3 concrete subclasses — `QuestReferenceAlias`
/`QuestLocationAlias`/`QuestCollectionAlias`); none are major records — each is keyed by a
quest-local `ID` (UInt32), NOT a FormKey. MVP authors the dominant `QuestReferenceAlias`:
`id` (auto-sequenced by list order when omitted) + `name` + `flags` (`AQuestAlias.Flag`:
Optional/QuestObject/Essential/…) + fill via `ForcedReference` (point at a placed REFR) or
`UniqueActor` (a unique NPC) + `conditions` (find-matching-ref — **reuses the 2.1b
`BuildCondition`/`_norm_conditions`** verbatim). The `Aliases` list is a nullable optional
group (null until first alias — guarded with `??= new()`, same pattern as `Quest.Data`).
Composes with dialogue: a dialogue condition references an alias by its int ID (e.g.
`GetIsAliasRef` param1=0), which the existing int-param shape-dispatch already handles.
Read-back adds `aliasCount`. Verified e2e + Spriggit: a "Cast" quest with alias 0
"QuestGiver" (ForcedReference + Optional/QuestObject) + alias 1 "TargetActor" (GetIsID
condition) → `aliasCount: 2`, `Fallout4.esm` auto-added from the ForcedReference + condition
param; the Spriggit YAML shows `Aliases` → 2× `QuestReferenceAlias` with `ID`/`Name`/`Flags`/
`ForcedReference`/`Conditions`(→`FunctionConditionData`/`GetIsID`) exactly as authored. +3
tests → 26 create / 235 suite.

**Faz 2.1d — Papyrus VMAD binding (✅ SHIPPED 2026-06-06):** `Quest.VirtualMachineAdapter`
now takes a `scripts` list — attach a compiled `.psc` to the quest by class name with typed
properties. API reality-checked by reflection: `Quest.VirtualMachineAdapter` = `QuestAdapter`
(settable, null on a fresh quest → another nullable optional group, `??= new()`); its
`Scripts` = `ExtendedList<ScriptEntry>` (`Name` = the .psc class, `Flags` = `ScriptEntry.Flag`
Local/Inherited/…, `Properties` = `ExtendedList<ScriptProperty>`). FO4 models each Papyrus
property type as its own class — MVP covers the 5 scalars: `object` → `ScriptObjectProperty`
(`Object` FormLink **or** `Alias` Int16 index), `int`/`float`/`bool`/`string` →
`Script{Int,Float,Bool,String}Property` (`Data`); list/struct/variable variants deferred.
Value-bearing props are flagged `Edited` (what CK sets). The adapter's VMAD header is written
`Version 6 / ObjectFormat 2` (the FO4 standard — `Version`/`ObjectFormat` are value-type
fields defaulting to 0, so they MUST be set explicitly). The property value passes through
the Python layer with its JSON type intact (not str-coerced); the CLI dispatches on `type`
and type-checks the value. Read-back adds `scriptCount` + `scriptPropertyCount`. Verified e2e
+ Spriggit + raw-byte: a "Scripted" quest with `MyQuestScript` and 6 properties (object→
Fallout4.esm FormKey, object→alias 0, int 3, float 0.5, bool false, string) → `scriptCount: 1`,
`scriptPropertyCount: 6`, `Fallout4.esm` auto-added from the object property; the Spriggit YAML
shows `VirtualMachineAdapter`→`Scripts`→`MyQuestScript` with each property under its correct
`ScriptObjectProperty`/`ScriptIntProperty`/… subclass (`Object: …`/`Alias: 0`/`Data: …`); a
direct byte read of the `VMAD` subrecord confirmed `Version=6, ObjectFormat=2, scriptCount=1`
(the property round-trip itself validates ObjectFormat — a wrong format would garble the
property layout). +3 tests → 29 create / 238 suite.

**Faz 2.1e — SCEN scenes (✅ SHIPPED 2026-06-06):** `Quest.Scenes` now takes a list of
`Scene` records — scripted multi-actor dialogue that ties the quest's cast (2.1c aliases),
the condition builder (2.1b), and dialogue topics (2.1a) into a playable timeline. API
reality-checked by reflection: `Quest.Scenes` = `ExtendedList<Scene>` (a nested list like
`DialogTopics`, NOT a nullable optional group — no `??= new()`); `Scene` is a major record
(`new Scene(mod, editorId)`) back-linked via `Scene.Quest`. A `SceneActor` is keyed by
`ID` (UInt32) which IS the quest alias ID — there is no separate alias link, the cast comes
straight from the 2.1c aliases. `ScenePhase` carries `Name` + `StartConditions`/
`CompletionConditions` (`ExtendedList<Condition>` — the 2.1b `BuildCondition` reused
verbatim). The riskiest piece was `SceneAction.Type`: it is an `ASceneActionType` (not the
`TypeEnum` directly), with two concrete subclasses — `SceneActionTypicalType` (holds the
`TypeEnum`: Dialog/Package/Timer/PlayerDialogue/NpcResponseDialogue/Radio) and
`SceneActionStartScene` (deferred niche). MVP authors `SceneActionTypicalType` actions with
`AliasID` (the performing actor, `Int32`), `Topic` (`IFormLinkNullable<IDialogTopicGetter>`),
`StartPhase`/`EndPhase` (`UInt32`), and `Flags`. **Topic resolution:** a scene action
references a topic by its editorId (resolved against the topics authored in the same spec
via an editorId→FormKey map built during the topics pass) or by a raw "<6hex>:<master>"
FormKey. Read-back adds `sceneCount` + `sceneActionCount`. Verified e2e + Spriggit: a
"Staged" quest with alias 0 + topic `STQ_Hello` + a scene (BeginOnQuestStart/StopOnQuestEnd,
1 actor, 1 phase with a GetStage≥10 condition, 1 Dialog action) → `sceneCount: 1`,
`sceneActionCount: 1`, `Fallout4.esm` auto-added from the ForcedReference + phase condition
param; the Spriggit YAML nests the scene under `Quests/.../Scenes/`, with `Flags`, `Phases`
(→`ConditionFloat`/`GetStage`), `Actors`, `Actions` (→`SceneActionTypicalType`, `AliasID: 0`,
`Topic: 000801` — the editorId resolved to the topic's FormKey — `StartPhase`/`EndPhase`/
`Flags`), and `Quest: 000800` back-link, all exactly as authored. +3 tests → 32 create /
241 suite. **Remaining Faz 2.1 surface:** quest stage/alias script *fragments*
(`QuestAdapter.Fragments`/`Aliases` — inline fragment code keyed to stages/aliases, distinct
from 2.1d's whole-script binding), niche `QuestLocationAlias`/`QuestCollectionAlias` +
`CreateRef` alias fill, and `SceneActionStartScene` / package-timer-camera action variants.

**Faz 2.1f — quest stage script fragments (✅ SHIPPED 2026-06-06):** `QuestAdapter` (the same
object 2.1d created for `Scripts`) now also takes a single QF fragment script + per-stage
fragment entries — the metadata that fires a `Fragment_*` Papyrus function when the quest
reaches a given stage. Taken **probe-first** (an understand-workflow + an authoritative DLL
reflection pass) since this was the roadmap's highest-reality-check item; the feared "unprobed
scary model" turned out clean. Reflection enumerated `QuestAdapter.Script` (`ScriptEntry`, the
`QF_<eid>_<formid>` fragment script), `QuestAdapter.Fragments` (`ExtendedList<QuestScriptFragment>`
— plain struct: `Stage`/`StageIndex`/`ScriptName`/`FragmentName`/`Unknown`/`Unknown2`, no FormKey),
and `QuestAdapter.Aliases` (per-alias fragments — `Property` + nested VMAD, **deferred**). The
**critical field-value came from Spriggit ground-truth** (the real `ccOTMFO4001-Remnants.esl`
`QF_ccOTMFO4001_Quest`, 21 fragments): **`Unknown2` is always `1`** (the C# default 0 is not
CK-faithful → hardcoded), `StageIndex` only set when two fragments share a stage,
`ScriptName`=`<mod>:Fragments:quests:QF_<eid>_<formid>`, `FragmentName`=`Fragment_Stage_<NNNN>_Item_<NN>`.
**Scope = metadata only** (structurally valid, not in-game-runnable without the matching `.pex`,
which is compiled separately via `fo4_papyrus_build` / Caprica — same decoupling caveat as 2.1d's
whole-script binding; FO4 logs a missing-script warning, it does not crash). Composition: factored
a `BuildScriptEntry` C# helper (shared by `Scripts` + the fragment `Script`) and a
`_norm_script_properties` Python helper (shared by the `scripts` + `fragments` validators) — DRY,
no drift. Spec = a single `fragments` object on the quest: `{scriptName, flags?, properties?,
stages:[{stage, stageIndex?, fragmentName}]}`. Read-back adds `fragmentCount` + `fragmentScriptName`.
**Closed a real round-trip gap:** Faz 0 + all prior 2.1 tests ran on fragment-less quests, so
`QuestAdapter.Fragments` round-trip was *unproven* (flagged by the understand-workflow's risk
agent); now proven by two engines. Verified e2e + Spriggit: a "Fragmented" quest (2.1d whole-script
binding + QF fragment script + 3 stage fragments incl. a duplicate-stage pair) → `fragmentCount: 3`,
`fragmentScriptName` round-tripped, `scriptCount: 1` (coexists), `masters: []`; the Spriggit YAML
showed `VirtualMachineAdapter.{Scripts, Script, Fragments}` with `Unknown2: 1` / `StageIndex: 1`
on the dup only — structurally identical to the real Remnants quest. +3 tests → 38 create / 247
suite. **Remaining:** quest *alias* fragments (`QuestAdapter.Aliases`), the `.psc`/Caprica/in-game
fragment loop (Faz 2.2), niche alias types, `SceneActionStartScene`, Faz 3 voice/lip.

**Faz 2.1g — quest alias script fragments (✅ SHIPPED 2026-06-06):** the piece 2.1f deferred —
`QuestAdapter.Aliases`. Each `QuestFragmentAlias` binds one quest alias (by ID) to its OnBegin/OnEnd
fragment script(s). Taken **probe-first** again (understand-workflow over on-disk Spriggit YAML +
authoritative DLL reflection). Reflection: `QuestAdapter.Aliases` is a regular non-null
`ExtendedList<QuestFragmentAlias>`; `QuestFragmentAlias` = `Property:ScriptObjectProperty` +
`Version:Int16` + `ObjectFormat:UInt16` + `Scripts:ExtendedList<ScriptEntry>`; `ScriptObjectProperty`
= `Alias:Int16` (the bound alias ID) + `Object:IFormLink` + `Name`/`Flags`/`Unused` (the xEdit
Object-Union). **Field values from on-disk Spriggit ground-truth** (Remnants `EncEncounter_Patrol01`
+ DLC02Workshop attack quests, no re-serialize needed): each entry serializes as `Property:{Name:'',
Object:<this quest>, Alias:<id>}` + `Scripts:[{Name:...}]`, with **`Version`/`ObjectFormat` omitted**
(Spriggit suppresses the `6`/`2` defaults). So the writer sets `Version 6 / ObjectFormat 2`,
`Property.Name=""`, `Property.Object=this quest`, `Property.Alias=<id>` — and there is **no
`Unknown2`** at the alias level (nothing CK-non-default to hardcode, unlike stage fragments).
**Scope = metadata only** (same `.pex` decoupling as 2.1d/2.1f). Composition: factored a Python
`_norm_script_entry` helper (shared by the `scripts` + alias-fragment-`scripts` validators); the C#
block reuses `BuildScriptEntry`. Spec = `aliasFragments:[{alias, scripts:[ScriptSpec]}]` (binding
`Object`/`Name`/`Version`/`ObjectFormat` auto). Read-back adds `aliasFragmentCount`. **Closed a real
round-trip gap:** 2.1f proved only `Fragments`, never `Aliases` — now proven by two engines. Verified
e2e + Spriggit: an "AliasFragmented" quest (2 own aliases + 2 alias fragments, one with an int prop) →
`aliasFragmentCount: 2`, `aliasCount: 2` (own aliases coexist), `masters: []` (binding Object = the
quest itself); the Spriggit YAML showed `VirtualMachineAdapter.Aliases` with each `Property:{Name:'',
Object:000800:..., Alias:N}` + `Scripts` (int prop as `ScriptIntProperty Data:5`), `Version`/
`ObjectFormat` omitted — structurally identical to the real Remnants alias fragments; Spriggit's `-c`
deserialize-back check passed. +3 tests → 41 create / 250 suite. **Remaining:** the `.psc`/Caprica/
in-game fragment loop (Faz 2.2), niche alias types (`QuestLocationAlias`/`QuestCollectionAlias`),
`SceneActionStartScene`, Faz 3 voice/lip.

**Faz 2.2 — quest fragment `.pex` loop (✅ SHIPPED 2026-06-06):** closes the fragment arc — 2.1d/2.1f/
2.1g write fragment *metadata* pointing at a `.pex` that didn't exist; Faz 2.2 produces it and proves
the name matches. No new tool (Caprica via `fo4_papyrus_build` already compiles), but a **probe found
`fo4_papyrus_build` couldn't compile *any* real fragment** — all are namespaced (`Fragments:Quests:`):
(1) auto-import added the source's *immediate parent*, so Caprica aborted with `namespace
'Fragments:Quests' does not match expected namespace ''`; (2) the non-recursive `produced` glob
(`*.pex`) missed the namespace-subdir output, reporting `ok:false` on a successful compile. **Surgical
fixes:** `_papyrus_import_root` derives the namespace ROOT from the declared `Scriptname`'s `:`-depth
and adds it to imports; `produced` uses `rglob` + `as_posix`. Both land in the default MCP-wrapper code
path (it exposes only `source_paths`+`output_dir`), so fragments now compile out of the box. **Two-engine
e2e:** fixture `fixtures/papyrus-test/src/Fragments/Quests/QF_MCPLoopQuest_01000800.psc` (CK-faithful
`Extends Quest Hidden Const` + `Fragment_Stage_0010_Item_00`); the metadata writer reads back
`fragmentScriptName = Fragments:Quests:QF_MCPLoopQuest_01000800` (`masters:[]`) and Caprica produces
`Fragments/Quests/QF_MCPLoopQuest_01000800.pex` — `scriptName.replace(":","/")+".pex"` == the produced
path, so the `.pex` FO4 loads is exactly the one the quest names. **Scope = authoring→compile binding;**
in-game firing (deploy `.pex` to `Data/Scripts/` + load quest + advance stage) is **user-gated**, same
decoupling caveat as 2.1d/f/g. +2 tests (`_papyrus_import_root` unit + namespaced-fragment compile) →
252 suite. See `research/p0/authoring/2026-06-05-quest-roundtrip-proof.md` → Faz 2.2.

**Faz 3 — voice + lip (deferred milestone):** `.fuz` voice via xVASynth, `.lip`
sync via FaceFXWrapper. Untouched; separate track. Dialogue records author fine
without audio (silent/subtitle-only is valid).

**DIAL/INFO topic-tree probe (✅ DONE 2026-06-06):** Faz 0 proved *scene-action*
dialogue; this probe confirmed the **DIAL/INFO topic-tree** path too. Round-tripped
`DLCworkshop01.esm` (633 KB, 1375 records — it carries a real topic tree:
`DLC02WorkshopSummonedToRelaxCheering` + 3 INFO responses) via export→import(same
name)→export→diff: **15 files differ, DialogTopics/Branches/Responses ZERO diff** —
dialogue is byte-identical; the 15 diffs are the same two cosmetic classes as Faz 0
(`-0` rotation + package-data key reorder), none touching dialogue. Reflection also
confirmed Mutagen's DIAL/INFO model is complete and that **FO4 dialogue is
quest-nested** (`DialogTopic.Quest` FormLink; Spriggit nests DialogTopics/Branches
under the owning quest, not top-level like Skyrim) — so Faz 2.1 attaches dialogue under
the Faz 2 quest skeleton. Evidence:
`research/p0/authoring/2026-06-06-dial-info-roundtrip-probe.md`.
