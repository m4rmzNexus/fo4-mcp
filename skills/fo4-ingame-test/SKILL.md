---
name: fo4-ingame-test
description: |
  Run a headless in-game Fallout 4 test through the Tier 3 F4SE runner plugin —
  launch the game via MO2, auto-load a save, run console commands against
  runtime FormIDs, capture the Papyrus result, and auto-quit. Use when the user
  wants to verify a quest/fragment/record actually fires in-game ("does this
  quest start?", "test my fragment in-game", "run an in-game smoke test",
  "did the stage fire?"), not just that it serializes on disk. Drives the
  fo4_run_ingame_test MCP tool. dry_run by default — a real launch is gated.
---

# fo4-ingame-test

Closes the gap between *disk-valid* and *runtime-valid*. Authoring tools
(`fo4-record-edit`, `fo4-quest-author`, `fo4-papyrus`) prove a record/script
serializes correctly; this skill proves it **actually does something when the
game loads it**. A native F4SE plugin reads a line-based job file, loads a save,
drives `Console::ExecuteCommand` on the main thread via `AddUITask`, then `qqq`
auto-quits — fully headless, ~25s, zero human clicks once preconditions are met.

## When to run

- After authoring a quest/fragment and you want to confirm it fires
  (`startquest` + `setstage` → Papyrus `[FAZ22]`-style sentinel).
- After a record edit, to confirm the runtime FormID resolves and behaves.
- As a smoke test before shipping (the cheapest real-world signal).

## Preconditions (human-gated — check first, the tool can't fix these)

These are the two infra blockers that gate every launch:

1. **Steam must be LOGGED IN.** With `ActiveUser=0`
   (`HKCU\Software\Valve\Steam\ActiveProcess\ActiveUser`), `Fallout4.exe` dies as
   a ~25MB DRM stub in <2s — the plugin never injects. The tool raises
   `ENV_FO4_NOT_DETECTED` before launching if you're logged out. **You can't
   script the login — it's a hard human step.**
2. **MO2 `ModOrganizer.ini` intact.** It points at the managed game; if it's
   wiped (a past workspace reorg did this), MO2 shows "managed game not found"
   and never launches. Restore from `.bak`, `base_directory =
   tools/mo2/portable-fo4-agentic`.

Also required once (already set up, but verify if results look empty):
- Runner plugin deployed as `mods/FO4MCP-Smoke/F4SE/Plugins/commonlibf4-template.dll`.
- Papyrus logging ON in the profile-local `Fallout4Custom.ini`
  (`[Papyrus] bEnableLogging/bEnableTrace/bLoadDebugInformation=1`).
- A loadable save exists (the runner uses `kQuickLoad` by default — a quicksave).

## Steps

1. **Build the spec.** A dict with these keys:

   | Key | Req | Meaning |
   |---|---|---|
   | `commands` | ✅ | `list[str]` console commands, in order. Use `{KEY}` placeholders for FormIDs. |
   | `resolves` | — | `[{key, plugin, form_id}]` — each `{KEY}` → runtime FormID via `LookupFormID(form_id, plugin)`. `form_id` is the **bare ObjectID** (e.g. `0x800`), the plugin's load-order prefix is folded in at runtime. |
   | `save` | — | `quickload` (default), `mostrecent`, or `coc:<cell>`. |
   | `success_pattern` | — | substring grepped in `Papyrus.0.log` (e.g. `FAZ22`). Present ⇒ success needs the match; absent ⇒ success = clean appear→sequence→exit. |
   | `settle_ms`/`gap_ms`/`post_ms` | — | settle before first cmd / gap between cmds / wait after last cmd before `qqq`. |
   | `appear_timeout_s`/`run_timeout_s` | — | how long to wait for the game window / for self-exit before force-kill. |

2. **Dry-run first (default).** Call `fo4_run_ingame_test(spec)` with
   `dry_run=True` (the default). It renders + validates the job file and returns
   the plan (`job_text`, `launch_argv`) **without writing or launching**. Show
   the user the rendered job; catch spec errors here.

3. **Execute (gated).** Once the plan looks right and preconditions hold, call
   with `dry_run=False`. The tool writes the job, kills stragglers, launches MO2
   via ShellExecute (`moshortcut://:F4SE`), polls for the real game (RAM>200MB to
   ignore the stub), waits for self-exit (else force-kills at `run_timeout_s`),
   then reads `runner-diag.log` + `Papyrus.0.log`.

4. **Read the result.** Key fields:
   - `success` — the headline verdict.
   - `appeared` / `exited` — did the real game launch / self-quit cleanly.
   - `sequence_completed` — did the plugin reach `qqq` (the command sequence ran).
   - `papyrus_matches` — the matched `success_pattern` lines (the actual proof).
   - `killed_hung` / `plugin_timed_out` — the failure signatures (see Guards).
   - `diag_tail` — last lines of the plugin diag; first thing to read on failure.

## Guards (hard-won, all binary/log-verified)

- **FormID, not editorID.** FO4 strips editorIDs at runtime, so
  `setstage MyQuest 10` silently no-ops. Always `resolve` the editorID-free
  ObjectID and drive the command with the `{KEY}` placeholder. This was the #1
  cause of "the test ran but nothing happened."
- **`save: quickload`, not `mostrecent`.** `kLoadMostRecentSave` no-ops headless
  (`mostRecentSaveGame` is NULL at the main menu); the game sits at MainMenu and
  looks hung. Use a quicksave or `coc:<cell>`.
- **`plugin_timed_out` + no `[tick]` logs = launch mechanism, not your test.**
  The runner must be launched by the shell (the tool already uses ShellExecute);
  a plain detached process leaves the game in our job object and `AddUITask`
  never drains. If you see the game reach ~2GB then freeze with no command logs,
  it's launch context, not the spec.
- **`appeared=False` in <2s = the ~25MB Steam stub.** Log into Steam and retry.
- **Don't over-trust a clean exit without `success_pattern`.** For anything that
  should produce a Papyrus effect, set `success_pattern` so success requires the
  log line — `sequence_completed` alone only proves `qqq` ran, not that your
  logic fired.

## Notes

- Pairs downstream of `fo4-quest-author` + `fo4-papyrus`: author the quest, build
  the fragment, then prove it fires here. The proven reference flow is the
  `MCPLoopTest` quest (`startquest {Q}` + `setstage {Q} 10` → `[FAZ22] ... fired`).
- The plugin falls back to a built-in MCPLoopTest default job if no job file is
  present, so the legacy `run-runner.ps1` smoke still works standalone.
- This is the one skill that genuinely needs the live game + Steam + a GPU — it
  is **not** CI-runnable. Treat it as a user-gated, machine-local verification
  step (like `fo4_build_previs`).
