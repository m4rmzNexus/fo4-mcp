# papyrus-test fixture

Minimal Papyrus source for TBD #2 — Caprica vs Bethesda PapyrusCompiler
bytecode comparison. The script intentionally covers three idioms that
expose compiler divergence:

- `Event OnInit()` — engine event binding
- `Function Greet(string name)` — string concatenation
- `int Function Add(int a, int b)` — typed return value

Compile both ways, then compare `.pex` outputs:

```bash
# Caprica
tools/caprica/Caprica.exe --game fo4 \
  -i "C:/Program Files (x86)/Steam/steamapps/common/Fallout 4/Data/Scripts/Source/Base" \
  -o fixtures/papyrus-test/caprica/ \
  fixtures/papyrus-test/src/TestScript.psc

# CK official forward compiler
"C:/Program Files (x86)/Steam/steamapps/common/Fallout 4 1946160/Papyrus Compiler/PapyrusCompiler.exe" \
  fixtures/papyrus-test/src/TestScript.psc \
  -f="Institute_Papyrus_Flags.flg" \
  -i="C:/Program Files (x86)/Steam/steamapps/common/Fallout 4/Data/Scripts/Source/Base" \
  -o="fixtures/papyrus-test/ck/"

# Binary diff
fc /b fixtures/papyrus-test/caprica/TestScript.pex \
      fixtures/papyrus-test/ck/TestScript.pex
```

Result lands in `research/p0/papyrus/<date>-bytecode-diff.md`.
