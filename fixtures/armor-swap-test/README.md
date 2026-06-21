# armor-swap-test fixture

Test substrate for Spriggit roundtrip identity, `fo4_inspect_record`, and
ESL-eligibility testing.

> **Naming note:** the directory name `armor-swap-test` is historical. The
> committed fixture is **not** an armor record — it is a single `GlobalInt`
> (see below). The name is kept because tests reference this path; renaming
> it would churn fixture paths for no benefit.

## seed/test_armor.esp

A minimal, **fully original synthetic** Fallout 4 ESP — **no copyrighted
Bethesda content, zero masters**. It contains exactly one record:

- Type: `GlobalInt` (GLOB)
- EditorID: `TestArmorSwapFlag`
- FormKey: `000800:test_armor.esp` (self-referencing; ObjectID `0x800`, the
  ESL-safe range)
- Value: `1`, flag `Constant`
- Plugin author (CNAM): `fo4-mcp-fixture`; description (SNAM): *"Minimal
  synthetic plugin for Spriggit roundtrip tests (one GlobalInt, no
  copyrighted content)."*

Because it declares **no `MAST` masters** and references no vanilla record,
it embeds nothing from `Fallout4.esm`. An equivalent can be regenerated from
scratch with `fo4_create_record` (an `AddNew` `global` or `armor` record) —
it is never cloned from game data.

## Why this fixture

Spriggit's job is to serialize/deserialize Bethesda plugins to text so they
can be diff'd in git. The roundtrip identity question is: does
`serialize → deserialize` produce a byte-identical ESP, or only a
semantically-equivalent one? The answer determines whether
`fo4_spriggit_import` can run silently or must always surface a diff before
writing.

A single-record ESP keeps the YAML small enough to inspect by eye, which is
critical for diagnosing any drift between original and roundtrip. The
committed Spriggit serialization lives under `seed/yaml/`.
