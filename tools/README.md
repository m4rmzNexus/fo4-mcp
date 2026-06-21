# tools/

Third-party Fallout 4 modding araç binary'leri. Bu klasörün içeriği `.gitignore` ile commit dışı (binary bloat'tan kaçınmak için), ama üç meta dosya commit edilir:

- **`MANIFEST.md`** — otomatik indirilen tool'lar: ad, versiyon, kaynak URL, indirme tarihi, hash. `fo4-mcp` subprocess çağrılarında bu dosya source-of-truth olur.
- **`MANUAL-DOWNLOADS.txt`** — auth/login gerektiren ve kullanıcının manuel indirmesi gereken tool'lar (F4SE, Nexus-only F4SE plugin'leri, Creation Kit). Her giriş için kaynak link + beklenen hedef path + neden gerekli.
- **`.gitkeep`** — boş klasör tutucu.

## Klasör konvansiyonu

Her tool kendi alt klasöründe yaşar:

```
tools/
  mutagen/           Mutagen.Bethesda.Synthesis CLI (.NET) ya da Synthesis runner içinde
  spriggit/          Spriggit.CLI / Spriggit.UI
  synthesis/         Synthesis runner
  caprica/           Caprica Papyrus compiler
  champollion/       Champollion Papyrus decompiler
  xedit/             FO4Edit
  classic/           CLASSIC crash log analyzer
  mo2/               Mod Organizer 2 (kullanıcının tercihine göre)
  addictol/          AddictolCrashLogger (Buffout 4 yerine)
  f4se/              F4SE — MANUEL indirme gerekli
  robco/             RobCo Patcher — MANUEL (Nexus auth)
  spid-f4/           SPID-F4 — MANUEL (Nexus auth)
  bos-f4/            BaseObjectSwapperF4 — MANUEL (Nexus auth)
  buffout4/          Buffout 4 — MANUEL (Nexus auth, Addictol tercih edilir)
  ck/                Creation Kit — MANUEL (Bethesda.net launcher)
```

## Subprocess-wrap pattern

`fo4-mcp` server bu binary'leri **library-link değil subprocess çağrısı** ile kullanır. Sebep: çoğu (Mutagen, Spriggit, Synthesis, Buffout/Addictol) GPL-3.0 lisanslı — library link contagion riskini elimine etmek için.

`MANIFEST.md`, server tarafında path resolver olarak okunur:

```python
# pseudo
manifest = read_yaml_frontmatter("tools/MANIFEST.md")
spriggit_exe = manifest["spriggit"]["binary_path"]
subprocess.run([spriggit_exe, "serialize", ...])
```

## Yenileme

Tool yeni versiyon yayınladığında:
1. Eski klasörü sil veya `tools/<name>.old/` olarak arşivle
2. Yeni binary'yi indir
3. `MANIFEST.md`'yi güncelle (versiyon + tarih + hash)
4. Smoke test: `tools/<name>/<exe> --version`
