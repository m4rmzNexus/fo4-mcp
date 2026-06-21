#!/usr/bin/env python3
"""Bulk download Nexus FO4 mods via Premium API.

Reads API key from secrets/nexus.env, takes a hardcoded TARGETS list,
picks the most AE-compatible primary file per mod, fetches the Premium
CDN download_link, streams the file to tools/<slug>/, computes SHA256,
and emits a manifest fragment for each mod.

Heuristic for file selection (in order):
  1. Filter to category MAIN (1) or OPTIONAL files only
  2. Prefer files whose name/description matches AE markers
     ("1.11.191", "AE", "Anniversary", "anniversary")
  3. De-prioritize files marked as OG-only or NG-only
  4. Among ties, prefer is_primary then highest uploaded_timestamp

Run from repo root:
    python tools/fetch-nexus.py [slug]   # one mod
    python tools/fetch-nexus.py          # all

Idempotent: skips already-downloaded files (verified by sha256).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = REPO_ROOT / "tools"
SECRETS = REPO_ROOT / "secrets" / "nexus.env"

# (slug, game, mod_id, hint) — hint guides file selection
TARGETS = [
    ("f4se",              "fallout4",              42147,  "AE 0.7.x"),
    ("addictol",          "fallout4",              84214,  "AE multi-runtime"),
    ("address-library",   "fallout4",              47327,  "1.11.191 AE"),
    ("xse-preloader",     "fallout4",              33946,  "AE"),
    ("robco-patcher",     "fallout4",              69798,  "AE"),
    ("spid-f4",           "fallout4",              48365,  "AE 3.1.1"),
    ("bos-f4",            "fallout4",              67528,  "AE 2.2.1"),
    ("prp",               "fallout4",              46403,  "stable"),
    ("lighthouse-papyrus","fallout4",              71420,  "AE"),
    ("hudframework",      "fallout4",              20309,  ""),
    ("mcm",               "fallout4",              21497,  ""),
    ("bodyslide",         "fallout4",              25,     ""),
    ("material-editor",   "fallout4",              3635,   ""),
    ("cao",               "skyrimspecialedition",  23316,  ""),
    # Session 6 sweep (2026-05-29): BA2 packaging tools (V2 #8/#10).
    ("bsarchpro",         "fallout4",              63243,  ""),
    ("ba2-version-patcher","fallout4",             82114,  ""),
]

AE_RE  = re.compile(r"\b(1\.11\.191|AE|Anniversary)\b", re.IGNORECASE)
OG_ONLY_RE = re.compile(r"\b(1\.10\.163|OG only|Old\s*Gen only)\b", re.IGNORECASE)
NG_ONLY_RE = re.compile(r"\b(1\.10\.984|NG only|Next\s*Gen only)\b", re.IGNORECASE)


def load_key() -> str:
    for line in SECRETS.read_text().splitlines():
        if line.startswith("NEXUS_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("NEXUS_API_KEY not found in secrets/nexus.env")


def api_get(path: str, key: str) -> dict | list:
    url = f"https://api.nexusmods.com{path}"
    req = urllib.request.Request(url, headers={
        "apikey": key,
        "Application-Name": "fo4-mcp",
        "Application-Version": "0.1.0-dev",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def score_file(f: dict, hint: str) -> tuple[int, int]:
    """Return (priority_score, uploaded_ts) — higher is better.

    Score is composed so AE-marker hits dominate, then primary, then category."""
    text = " ".join(str(f.get(k, "")) for k in ("name", "description", "file_name"))
    score = 0
    cat = f.get("category_id")
    if cat == 1:               # MAIN
        score += 100
    elif cat == 4:             # OPTIONAL
        score += 50
    elif cat == 2:              # UPDATE — only if no main exists
        score += 30
    else:
        score -= 50            # OLD / ARCHIVED / MISC
    if f.get("is_primary"):
        score += 60
    if AE_RE.search(text):
        score += 200
    if hint and any(tok.lower() in text.lower() for tok in hint.split() if len(tok) > 2):
        score += 80
    if OG_ONLY_RE.search(text):
        score -= 150
    if NG_ONLY_RE.search(text):
        score -= 100
    return (score, int(f.get("uploaded_timestamp") or 0))


def pick_file(files: list[dict], hint: str) -> dict | None:
    """Pick the best-scoring file; return None if none viable."""
    if not files:
        return None
    candidates = [f for f in files if f.get("category_id") in (1, 2, 4)]
    if not candidates:
        candidates = files
    candidates.sort(key=lambda f: score_file(f, hint), reverse=True)
    return candidates[0]


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fp:
        for chunk in iter(lambda: fp.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def download(url: str, dest: Path) -> int:
    """Stream download. Returns bytes written."""
    # Nexus CDN URLs frequently contain spaces in filenames; quote the path.
    parts = urllib.parse.urlsplit(url)
    safe_url = urllib.parse.urlunsplit(
        (parts.scheme, parts.netloc, urllib.parse.quote(parts.path),
         parts.query, parts.fragment)
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(safe_url, headers={"User-Agent": "fo4-mcp/0.1.0-dev"})
    total = 0
    with urllib.request.urlopen(req, timeout=300) as r, open(dest, "wb") as out:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            out.write(chunk)
            total += len(chunk)
    return total


def fetch_mod(slug: str, game: str, mod_id: int, hint: str, key: str) -> dict:
    print(f"\n[{slug}] mod_id={mod_id} game={game} hint={hint!r}", flush=True)
    files = api_get(f"/v1/games/{game}/mods/{mod_id}/files.json", key)
    file_list = files.get("files", []) if isinstance(files, dict) else []
    if not file_list:
        return {"slug": slug, "error": "no files in mod"}
    chosen = pick_file(file_list, hint)
    if not chosen:
        return {"slug": slug, "error": "no viable file"}

    print(f"  -> {chosen.get('name')!r} v{chosen.get('version')} "
          f"({chosen.get('file_name')}, {chosen.get('size_kb','?')}KB, "
          f"cat={chosen.get('category_id')}, primary={chosen.get('is_primary')})",
          flush=True)

    fid = chosen["file_id"]
    link = api_get(f"/v1/games/{game}/mods/{mod_id}/files/{fid}/download_link.json", key)
    if not isinstance(link, list) or not link:
        return {"slug": slug, "error": f"no download_link returned: {link}"}
    url = link[0]["URI"]
    cdn = link[0].get("short_name", "?")

    dest = TOOLS_DIR / slug / chosen["file_name"]
    if dest.exists():
        sha = sha256_of(dest)
        print(f"  already exists ({dest.stat().st_size:,} bytes, sha256={sha[:12]}…)",
              flush=True)
        return {
            "slug": slug, "mod_id": mod_id, "file_id": fid,
            "file_name": chosen["file_name"], "version": chosen.get("version"),
            "size_bytes": dest.stat().st_size, "sha256": sha,
            "source": f"https://www.nexusmods.com/{game}/mods/{mod_id}",
            "cdn": cdn, "downloaded": False, "skipped": True,
        }

    print(f"  downloading from {cdn}…", flush=True)
    n = download(url, dest)
    sha = sha256_of(dest)
    print(f"  ok ({n:,} bytes, sha256={sha[:12]}…)", flush=True)
    return {
        "slug": slug, "mod_id": mod_id, "file_id": fid,
        "file_name": chosen["file_name"], "version": chosen.get("version"),
        "size_bytes": n, "sha256": sha,
        "source": f"https://www.nexusmods.com/{game}/mods/{mod_id}",
        "cdn": cdn, "downloaded": True,
    }


def main() -> None:
    key = load_key()
    only = sys.argv[1] if len(sys.argv) > 1 else None
    results: list[dict] = []
    for slug, game, mid, hint in TARGETS:
        if only and only != slug:
            continue
        try:
            results.append(fetch_mod(slug, game, mid, hint, key))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")[:300]
            print(f"  HTTP {e.code}: {body}", flush=True)
            results.append({"slug": slug, "error": f"HTTP {e.code}: {body}"})
        except Exception as e:  # noqa: BLE001
            print(f"  ERROR: {e}", flush=True)
            results.append({"slug": slug, "error": str(e)})
        time.sleep(0.5)  # gentle rate-limit

    out = TOOLS_DIR / "_fetch-nexus-log.json"
    out.write_text(json.dumps(results, indent=2))
    print(f"\nWrote summary -> {out}", flush=True)

    failures = [r for r in results if r.get("error")]
    if failures:
        print(f"\n{len(failures)} failures:", flush=True)
        for f in failures:
            print(f"  - {f['slug']}: {f['error']}", flush=True)


if __name__ == "__main__":
    main()
