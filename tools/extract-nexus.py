#!/usr/bin/env python3
"""Extract Nexus-downloaded archives in each tools/<slug>/ folder.

For each slug we know was downloaded by fetch-nexus.py (see TARGETS in that
file), find the archive (.zip or .7z), extract in-place, locate the primary
.exe / .dll / installer, and print a binary_path candidate for MANIFEST.md.

Uses stdlib zipfile for .zip and shells out to tools/wrye-bash/Mopy/bash/
compiled/7z.exe for .7z (bundled with Wrye Bash).
"""
from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS = REPO_ROOT / "tools"
SEVEN_ZIP = TOOLS / "wrye-bash" / "Mopy" / "bash" / "compiled" / "7z.exe"

SLUGS = [
    "f4se", "addictol", "address-library", "xse-preloader",
    "robco-patcher", "spid-f4", "bos-f4", "prp",
    "lighthouse-papyrus", "hudframework", "mcm",
    "bodyslide", "material-editor", "cao", "mo2",
]


def find_archive(d: Path) -> Path | None:
    """Find the largest archive in d (.7z or .zip)."""
    cands = [p for p in d.iterdir() if p.suffix.lower() in (".7z", ".zip")]
    cands.sort(key=lambda p: p.stat().st_size, reverse=True)
    return cands[0] if cands else None


def extract_zip(archive: Path, dest: Path) -> None:
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(dest)


def extract_7z(archive: Path, dest: Path) -> None:
    if not SEVEN_ZIP.exists():
        raise RuntimeError(f"7z.exe not found at {SEVEN_ZIP}")
    result = subprocess.run(
        [str(SEVEN_ZIP), "x", "-y", f"-o{dest}", str(archive)],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"7z failed: {result.stderr[-500:]}")


def find_primary_binary(d: Path, slug: str) -> Path | None:
    """Heuristic: pick the largest .exe at shallowest depth."""
    exes = list(d.rglob("*.exe"))
    if not exes:
        # F4SE plugin? look for .dll
        dlls = list(d.rglob("*.dll"))
        if dlls:
            # Prefer the slug-named DLL, else largest
            slug_clean = slug.replace("-", "").lower()
            for dll in dlls:
                if slug_clean in dll.name.lower().replace("-", "").replace("_", ""):
                    return dll
            dlls.sort(key=lambda p: p.stat().st_size, reverse=True)
            return dlls[0]
        return None
    # Filter out installer side-files
    exes = [e for e in exes if "uninstall" not in e.name.lower()
            and "redist" not in e.name.lower()
            and "vcredist" not in e.name.lower()]
    if not exes:
        return None
    # Prefer shallowest depth, then largest size
    exes.sort(key=lambda p: (len(p.relative_to(d).parts), -p.stat().st_size))
    return exes[0]


def process(slug: str) -> dict:
    d = TOOLS / slug
    if not d.exists():
        return {"slug": slug, "skipped": "no dir"}

    archive = find_archive(d)
    if archive is None:
        # Already extracted earlier or no archive — just locate binary
        bp = find_primary_binary(d, slug)
        return {
            "slug": slug, "archive": None,
            "binary_path": str(bp.relative_to(REPO_ROOT)) if bp else None,
        }

    # Skip extraction if a sibling .exe/.dll already exists from prior run
    existing_bins = [p for p in d.iterdir() if p.is_file()
                     and p.suffix.lower() in (".exe", ".dll")
                     and p.name not in {"vc_redist.x64.exe"}]
    extracted_dirs = [p for p in d.iterdir() if p.is_dir()]
    if existing_bins or extracted_dirs:
        # Already extracted at least once
        bp = find_primary_binary(d, slug)
        return {
            "slug": slug, "archive": archive.name,
            "binary_path": str(bp.relative_to(REPO_ROOT)) if bp else None,
            "note": "previously extracted",
        }

    print(f"[{slug}] extracting {archive.name}…", flush=True)
    try:
        if archive.suffix.lower() == ".zip":
            extract_zip(archive, d)
        else:
            extract_7z(archive, d)
    except Exception as e:
        return {"slug": slug, "error": f"extract failed: {e}"}

    bp = find_primary_binary(d, slug)
    return {
        "slug": slug, "archive": archive.name,
        "binary_path": str(bp.relative_to(REPO_ROOT)) if bp else None,
    }


def main() -> None:
    only = sys.argv[1] if len(sys.argv) > 1 else None
    results = []
    for slug in SLUGS:
        if only and slug != only:
            continue
        r = process(slug)
        print(f"  {slug:22s} -> {r.get('binary_path') or r.get('error') or r.get('skipped') or '(no binary)'}",
              flush=True)
        results.append(r)
    print("\n=== Summary ===")
    for r in results:
        line = f"  {r['slug']:22s}"
        if r.get("error"):
            line += f"  ERROR: {r['error']}"
        elif r.get("binary_path"):
            line += f"  binary_path = {r['binary_path']}"
        else:
            line += "  (no binary found — F4SE plugin or installer-only?)"
        print(line)


if __name__ == "__main__":
    main()
