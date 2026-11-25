"""Read recorded providers and model/material references from a Heybeli-format catalog."""
from __future__ import annotations

import json
import sqlite3
from collections import deque
from contextlib import closing, contextmanager
from pathlib import Path

from .errors import ErrorCode, Fo4McpError, ok


def virtual_path(value: str) -> str:
    return value.rstrip("\0").replace("\\", "/").lower()


def material_links(fields: dict):
    """Bethesda material paths may be relative to their virtual Data subdirectory."""
    for slot, value in fields.items():
        if not isinstance(value, str):
            continue
        path = virtual_path(value)
        if path.endswith(".dds"):
            root = "textures/"
        elif path.endswith((".bgsm", ".bgem")):
            root = "materials/"
        else:
            continue
        yield slot, root + ("/" + path).rsplit("/" + root, 1)[-1].lstrip("/")


def providers(db, path):
    return db.execute(
        "SELECT a.id, s.provider, s.kind, s.path FROM assets a "
        "JOIN sources s ON s.id=a.source WHERE a.path=? ORDER BY a.id", (path,)
    ).fetchall()


@contextmanager
def open_catalog(catalog: Path):
    if not catalog.is_file():
        raise Fo4McpError(ErrorCode.PATH_NOT_FOUND, "Catalog file not found", {"catalog": str(catalog)})
    try:
        with closing(sqlite3.connect(catalog.resolve().as_uri() + "?mode=ro", uri=True)) as db:
            db.execute("PRAGMA trusted_schema=OFF")
            yield db
    except (sqlite3.Error, ValueError, TypeError, AttributeError) as exc:
        raise Fo4McpError(ErrorCode.INVALID_ARGUMENT, f"Cannot read asset catalog: {exc}") from exc


def inspect_catalog(catalog: Path, query: str, max_paths: int = 100) -> dict:
    if not query.strip() or not 1 <= max_paths <= 500:
        raise Fo4McpError(ErrorCode.INVALID_ARGUMENT, "Supply a query and max_paths from 1 to 500")
    with open_catalog(catalog) as db:
        return ok(_inspect(db, catalog, query.strip(), max_paths))


def _inspect(db, catalog, query, limit):
    key = virtual_path(query)
    records = []
    pending = deque()
    if "/" in key:
        pending.append(key)
    else:
        column = "formkey" if ":" in key else "editor"
        for rid, formkey, editor, sig, provider in db.execute(
            f"SELECT r.id,r.formkey,r.editor,r.type,s.provider FROM effective r "
            f"JOIN sources s ON s.id=r.source WHERE r.{column}=? "
            + ("COLLATE NOCASE" if column == "editor" else ""), (key,)
        ):
            paths = sorted({p for p, in db.execute("SELECT path FROM record_assets WHERE record=?", (rid,)) if p})
            records.append(dict(formkey=formkey, editor=editor, type=sig, provider=provider, assets=paths))
            pending.extend(paths)
    assets = {}
    while pending and len(assets) < limit:
        path = pending.popleft()
        if path in assets:
            continue
        variants = []
        assets[path] = variants
        for aid, provider, kind, source in providers(db, path):
            deps = {}
            issues = [row[0] for row in db.execute("SELECT reason FROM issues WHERE asset=?", (aid,))]
            if path.endswith(".nif"):
                for block, mat in db.execute("SELECT block,material FROM shapes WHERE asset=?", (aid,)):
                    if mat and mat.endswith((".bgsm", ".bgem")):
                        deps[f"shape_{block}"] = mat
            elif path.endswith((".bgsm", ".bgem")):
                row = db.execute("SELECT fields FROM materials WHERE asset=?", (aid,)).fetchone()
                if row:
                    deps.update(material_links(json.loads(row[0])))
            variants.append(dict(provider=provider, kind=kind, file=source, references=deps, issues=issues))
            pending.extend(deps.values())
    return dict(catalog=str(catalog), evidence="catalog_snapshot", query=query, records=records,
                assets=assets, absent=[p for p, copies in assets.items() if not copies],
                truncated=any(p not in assets for p in pending))
