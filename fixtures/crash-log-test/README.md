# crash-log-test fixture

Two synthetic crash log samples for `fo4_analyze_crash_log` stub
(Phase E, Session 5) and CLASSIC v9 parse stability check (secondary
research question #3).

- `seed/buffout-sample.log` — upstream Buffout 4 OG-style format
  (FO4 1.10.984). Tab-aligned MODULES, decimal-only PLUGINS index.
- `seed/addictol-sample.log` — Addictol NG-fork format (FO4 1.11.191 AE).
  JSON-line MODULES, `[hex:dec]` PLUGINS index — divergence flagged in
  `docs/archive/stack-review-session-3.md`.

Both are minimal and obviously synthetic. They are NOT real crash dumps;
the addresses and instruction offsets are fabricated. Sufficient for
parser smoke tests and CLASSIC output diff but NOT for runtime fault
analysis.
