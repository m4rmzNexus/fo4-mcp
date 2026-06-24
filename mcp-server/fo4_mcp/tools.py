"""fo4-mcp tool implementations (Karar 3 + follow-ons).

Each tool is a thin function that:
  1. Validates inputs
  2. Resolves the underlying binary via Manifest (when it wraps one)
  3. Calls run_tool() across the subprocess GPL boundary
  4. Parses output into a structured response
  5. Returns ok({...}) or raises Fo4McpError

The 6 MVP tools (env, load_order, inspect_record, spriggit export/import,
papyrus_build, analyze_crash_log) are all functional; follow-on tools from
the FO4 sweep (e.g. check_esl_eligibility, generate_fomod) land here too.
Writes are gated through safety.check_write (Karar 4). Pure helpers are
factored out so the verdict/parse logic is unit-testable without binaries.
"""

from __future__ import annotations

import logging
import re
import struct
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Literal

from .config import Config
from .errors import (
    ErrorCode,
    Fo4McpError,
    NotImplementedYetError,
    PathForbiddenError,
    ToolBinaryMissingError,
    ok,
)
from .manifest import Manifest
from .safety import WriteDisposition, check_write
from .subprocess_wrap import run_tool

log = logging.getLogger(__name__)


# ---- Tool 1: env detection ---------------------------------------------------

def fo4_get_environment(cfg: Config) -> dict[str, Any]:
    """Report on the FO4 install + user data + MO2 detection.

    This is the only MVP tool that's fully functional out of the gate
    because it just reads filesystem state — no underlying binary call.
    """
    fo4 = cfg.fo4_install_dir
    runtime_version = _detect_runtime_version(fo4) if fo4 else None
    f4se_version    = _detect_f4se_version(fo4)    if fo4 else None
    mo2 = cfg.mo2_instance_dir

    return ok({
        "fo4": {
            "install_dir":     str(fo4) if fo4 else None,
            "runtime_version": runtime_version,
            "found":           fo4 is not None,
        },
        "f4se": {
            "version": f4se_version,
            "found":   f4se_version is not None,
        },
        "mo2": {
            "instance_dir": str(mo2) if mo2 else None,
            "found":        mo2 is not None,
            "fallback":     "vanilla %LOCALAPPDATA%/Fallout4/plugins.txt",
        },
        "user_data": {
            "documents":     str(cfg.fo4_user_docs)    if cfg.fo4_user_docs    else None,
            "localappdata":  str(cfg.fo4_localappdata) if cfg.fo4_localappdata else None,
        },
        "repo_root": str(cfg.repo_root),
        "tools_dir": str(cfg.tools_dir),
    })


def _detect_runtime_version(fo4_dir: Path) -> str | None:
    r"""Read Fallout4.exe version. Stub: returns None until implemented.

    Real impl: read PE version resource via pefile or a powershell call to
    Get-Item .\Fallout4.exe | Select VersionInfo.
    """
    exe = fo4_dir / "Fallout4.exe"
    return f"present (size={exe.stat().st_size})" if exe.exists() else None


def _detect_f4se_version(fo4_dir: Path) -> str | None:
    """Look for f4se_loader.exe and Data/F4SE/."""
    loader = fo4_dir / "f4se_loader.exe"
    if not loader.exists():
        return None
    f4se_data = fo4_dir / "Data" / "F4SE"
    return f"loader present, Data/F4SE/={'yes' if f4se_data.exists() else 'no'}"


# ---- Tool 2: load order ------------------------------------------------------

# Official base masters — always active, implicit, never listed in plugins.txt.
# Order matches the engine's hardcoded load sequence.
_BASE_MASTERS: tuple[str, ...] = (
    "Fallout4.esm",
    "DLCRobot.esm",
    "DLCworkshop01.esm",
    "DLCCoast.esm",
    "DLCworkshop02.esm",
    "DLCworkshop03.esm",
    "DLCNukaWorld.esm",
    "DLCUltraHighResolution.esm",
)
_BASE_MASTERS_LOWER = frozenset(m.lower() for m in _BASE_MASTERS)


def _classify_plugin(name: str) -> dict[str, Any]:
    """Derive type + light-flag heuristics from a plugin filename.

    .esl is always a light master. .esm is a full master. .esp is a regular
    plugin (may carry an ESL flag in its header, but that requires reading the
    record — out of scope for a filename-only classifier, flagged via `light`
    being None to mean 'unknown without header read')."""
    lower = name.lower()
    if lower.endswith(".esl"):
        return {"type": "esl", "light": True}
    if lower.endswith(".esm"):
        return {"type": "esm", "light": False}
    if lower.endswith(".esp"):
        return {"type": "esp", "light": None}
    return {"type": "other", "light": None}


_PLUGIN_EXTS = (".esp", ".esm", ".esl")


def _light_flag_from_path(path: Path) -> bool | None:
    """Read the real ESL (light master) flag (bit 0x0200) from a plugin's TES4
    header. The flags uint32 sits at file offset 8 (LE). Returns True/False, or
    None if the file is unreadable / not a TES4 plugin (caller then falls back
    to the filename heuristic). Shares the offset with esl_flag._read_tes4_flags."""
    try:
        with path.open("rb") as fh:
            head = fh.read(12)
    except OSError:
        return None
    if len(head) < 12 or head[:4] != b"TES4":
        return None
    return bool(int.from_bytes(head[8:12], "little") & 0x0200)


def _index_plugin_files(cfg: Config, mo2_mods_dir: Path | None) -> dict[str, Path]:
    """Best-effort name->path index for resolvable plugins, so the load order
    can report the *real* light flag instead of the extension guess. Scans MO2
    mod folders (each is a Data root) first, then the game Data dir; first hit
    wins (plugin names are effectively unique). Empty when nothing resolves —
    then every entry stays on the filename heuristic."""
    index: dict[str, Path] = {}
    search_dirs: list[Path] = []
    if mo2_mods_dir is not None and mo2_mods_dir.is_dir():
        search_dirs.extend(sorted(p for p in mo2_mods_dir.iterdir() if p.is_dir()))
    if cfg.fo4_install_dir is not None:
        search_dirs.append(cfg.fo4_install_dir / "Data")
    for d in search_dirs:
        if not d.is_dir():
            continue
        try:
            for f in d.iterdir():
                if f.suffix.lower() in _PLUGIN_EXTS and f.is_file():
                    index.setdefault(f.name.lower(), f)
        except OSError:
            continue
    return index


def _parse_plugins_txt(text: str) -> list[tuple[str, bool]]:
    """Parse a Fallout 4 plugins.txt body.

    Format: one plugin per line. A leading `*` marks the plugin as enabled
    (FO4 / post-Skyrim convention); no prefix means present-but-disabled.
    Lines starting with `#` are comments. Blank lines are skipped.
    Returns [(name, enabled), ...] preserving file order.
    """
    out: list[tuple[str, bool]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        enabled = line.startswith("*")
        name = line[1:].strip() if enabled else line
        if name:
            out.append((name, enabled))
    return out


def _read_ccc_names(ccc_path: Path) -> set[str]:
    """Read Fallout4.ccc (Creation Club manifest) -> set of lowercased names."""
    if not ccc_path.exists():
        return set()
    try:
        text = ccc_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return set()
    return {ln.strip().lower() for ln in text.splitlines() if ln.strip()}


def _mo2_selected_profile(ini_text: str) -> str | None:
    """Extract `selected_profile` from a ModOrganizer.ini body.

    MO2 stores it under [General], sometimes wrapped as
    `selected_profile=@ByteArray(Default)`, sometimes plain
    `selected_profile=Default`."""
    for raw in ini_text.splitlines():
        line = raw.strip()
        if line.lower().startswith("selected_profile"):
            _, _, val = line.partition("=")
            val = val.strip()
            if val.startswith("@ByteArray(") and val.endswith(")"):
                val = val[len("@ByteArray(") : -1]
            return val.strip().strip('"') or None
    return None


def _mo2_base_directory(ini_text: str) -> str | None:
    """Extract `[Settings] base_directory` from a ModOrganizer.ini body.

    For a portable instance the folder holding ModOrganizer.ini and the
    folder holding mods/ + profiles/ can differ: MO2 writes the latter as
    `base_directory`. The value may be `@ByteArray(...)`-wrapped and uses
    INI-escaped backslashes (`\\\\`). Returns None when unset (the instance
    dir itself is then the data root)."""
    for raw in ini_text.splitlines():
        line = raw.strip()
        if line.lower().startswith("base_directory"):
            _, _, val = line.partition("=")
            val = val.strip()
            if val.startswith("@ByteArray(") and val.endswith(")"):
                val = val[len("@ByteArray(") : -1]
            val = val.replace("\\\\", "\\").strip().strip('"')
            return val or None
    return None


def _annotate(name: str, enabled: bool, ccc: set[str], *, implicit_base: bool, index: int) -> dict[str, Any]:
    info = _classify_plugin(name)
    return {
        "index":         index,
        "name":          name,
        "enabled":       enabled,
        "type":          info["type"],
        "light":         info["light"],
        "cc":            name.lower() in ccc or name.lower().startswith("cc"),
        "implicit_base": implicit_base,
    }


def fo4_read_load_order(cfg: Config) -> dict[str, Any]:
    """Combined MO2 active profile + AppData plugins.txt readout.

    Resolution:
      1. If an MO2 instance is configured (ModOrganizer.ini + a selectable
         profile with plugins.txt) -> read that profile's plugins.txt.
      2. Otherwise -> read %LOCALAPPDATA%/Fallout4/plugins.txt (vanilla).
    Base masters (Fallout4.esm + official DLC) are always prepended as
    implicit, enabled entries since the engine loads them regardless of
    plugins.txt. Each entry is annotated: type (esm/esl/esp), light-flag,
    CC origin, enabled state, load index.
    """
    warnings: list[str] = []
    ccc = _read_ccc_names((cfg.fo4_install_dir / "Fallout4.ccc")) if cfg.fo4_install_dir else set()

    source = "vanilla"
    active_profile: str | None = None
    plugins_txt_path: Path | None = None
    instance_dir: str | None = None
    mo2_mods_dir: Path | None = None

    mo2 = cfg.mo2_instance_dir
    if mo2 is not None:
        ini = mo2 / "ModOrganizer.ini"
        if ini.exists():
            ini_text = ini.read_text(encoding="utf-8", errors="replace")
            profile = _mo2_selected_profile(ini_text)
            base = _mo2_base_directory(ini_text)
            # mods/ + profiles/ live under base_directory when set, else under
            # the folder holding ModOrganizer.ini.
            data_root = Path(base) if base else mo2
            cand = (data_root / "profiles" / profile / "plugins.txt") if profile else None
            if cand and cand.exists():
                source = "mo2"
                active_profile = profile
                plugins_txt_path = cand
                instance_dir = str(mo2)
                mo2_mods_dir = data_root / "mods"
            else:
                warnings.append(
                    f"MO2 instance at {mo2} has no usable profile plugins.txt "
                    f"(selected_profile={profile!r}); falling back to vanilla"
                )
        else:
            warnings.append(
                f"MO2_INSTANCE_DIR={mo2} is not an onboarded instance "
                "(no ModOrganizer.ini); falling back to vanilla. "
                "Run the MO2 portable first-launch to create it."
            )

    if plugins_txt_path is None:
        if cfg.fo4_localappdata is None:
            raise Fo4McpError(
                ErrorCode.PATH_NOT_FOUND,
                "no MO2 instance and %LOCALAPPDATA%/Fallout4 not detected",
                {"mo2_instance_dir": str(mo2) if mo2 else None},
            )
        plugins_txt_path = cfg.fo4_localappdata / "plugins.txt"

    parsed: list[tuple[str, bool]] = []
    if plugins_txt_path.exists():
        parsed = _parse_plugins_txt(plugins_txt_path.read_text(encoding="utf-8", errors="replace"))
    else:
        warnings.append(f"plugins.txt not found at {plugins_txt_path} (game may not have been run)")

    plugins: list[dict[str, Any]] = []
    idx = 0
    seen = set()
    # Prepend base masters only when we can verify them against the install —
    # without fo4_install_dir we can't tell which DLC the user owns, so we
    # leave them out rather than guess.
    if cfg.fo4_install_dir is not None:
        for base in _BASE_MASTERS:
            if not (cfg.fo4_install_dir / "Data" / base).exists():
                continue
            plugins.append(_annotate(base, True, ccc, implicit_base=True, index=idx))
            seen.add(base.lower())
            idx += 1

    for name, enabled in parsed:
        if name.lower() in _BASE_MASTERS_LOWER and name.lower() in seen:
            continue  # don't double-list a base master if plugins.txt repeats it
        plugins.append(_annotate(name, enabled, ccc, implicit_base=False, index=idx))
        idx += 1

    # Upgrade the light flag from the filename guess to the real TES4 header bit
    # wherever the plugin file resolves (closes the ESL-flagged-.esp gap). Each
    # entry gets light_source: "header" (read) or "extension" (filename guess).
    file_index = _index_plugin_files(cfg, mo2_mods_dir)
    for p in plugins:
        src = "extension"
        resolved = file_index.get(p["name"].lower())
        if resolved is not None:
            flag = _light_flag_from_path(resolved)
            if flag is not None:
                p["light"] = flag
                src = "header"
                if flag and p["type"] == "esp":
                    p["esl_flagged_esp"] = True
        p["light_source"] = src

    enabled_count = sum(1 for p in plugins if p["enabled"])
    return ok({
        "source":         source,
        "active_profile": active_profile,
        "instance_dir":   instance_dir,
        "plugins_path":   str(plugins_txt_path),
        "count":          {"total": len(plugins), "enabled": enabled_count},
        "plugins":        plugins,
        "warnings":       warnings,
    })


# ---- Tool 3: record inspect --------------------------------------------------

def _norm_formid(s: str) -> str | None:
    """Normalize a FormID-ish string to 6-hex-upper, or None if not hex.

    Accepts '0x24A0FE', '24a0fe', 'FE000800'. Strips an 8-digit load-order
    prefix down to the low 6 digits for comparison against Spriggit FormKeys
    (which store the 6-digit in-mod id)."""
    t = s.strip().lower()
    if t.startswith("0x"):
        t = t[2:]
    if not t or any(c not in "0123456789abcdef" for c in t):
        return None
    t = t.lstrip("0") or "0"
    return t.upper().zfill(6)[-6:]


def _extract_record_fields(text: str) -> dict[str, str | None]:
    """Pull EditorID / FormKey / MutagenObjectType from a record YAML body
    via simple top-level key scan (no YAML dep needed)."""
    out: dict[str, str | None] = {"editor_id": None, "form_key": None, "record_type": None}
    for raw in text.splitlines():
        if raw[:1] in (" ", "-", "\t"):
            continue  # skip nested
        key, _, val = raw.partition(":")
        k, v = key.strip(), val.strip()
        if k == "EditorID":
            out["editor_id"] = v or None
        elif k == "FormKey":
            out["form_key"] = v or None
        elif k == "MutagenObjectType":
            out["record_type"] = v or None
    return out


def fo4_inspect_record(cfg: Config, manifest: Manifest, plugin: str, record_id: str) -> dict[str, Any]:
    """Inspect a single record in a plugin by FormID (hex) or EditorID.

    Two backends, preferred in order:

    1. `mutagen-cli` (research/p0/mutagen-cli/) — a thin Mutagen.Bethesda.Fallout4
       console app that streams the records with a binary overlay and stops at
       the first match. No temp-dir, no whole-tree serialize: O(records-until-
       match) instead of O(plugin size). Used automatically when the binary is
       present (built into tools/mutagen-cli/). Returns the same form_key /
       editor_id / record_type; its `yaml` is a compact top-level stub (the full
       field tree stays a Spriggit feature). `backend` reports which path ran.
    2. Spriggit serialize (fallback) — serializes the whole plugin to a YAML
       tree and locates the matching record file. Full field-tree fidelity, but
       O(plugin size) per call: slow for Fallout4.esm-scale masters. Synthesis
       was rejected as a backend (research/p0/synthesis/2026-05-28-cli-argv.md:
       GUI/pipeline runner, no record-query verb).

    Args:
        plugin:    plugin path (read-only; may live in the Steam Data folder)
        record_id: FormID hex ('24A0FE', '0x24A0FE', 'FE000800') or EditorID
    """
    import tempfile

    plugin_path = Path(plugin)
    if not plugin_path.is_absolute():
        plugin_path = (cfg.repo_root / plugin_path).resolve()
    if not plugin_path.exists():
        raise Fo4McpError(
            ErrorCode.PATH_NOT_FOUND,
            f"plugin not found: {plugin_path}",
            {"plugin": str(plugin_path)},
        )

    want_formid = _norm_formid(record_id)
    want_editor = record_id.strip().lower()

    cli = _mutagen_cli_binary(cfg, manifest)
    if cli is not None:
        return _inspect_record_via_cli(cfg, cli, plugin_path, record_id, want_formid)

    binary = _spriggit_binary(cfg, manifest)
    version = _spriggit_version(manifest, None)

    with tempfile.TemporaryDirectory() as td:
        out_dir = Path(td) / "yaml"
        args = [
            "serialize",
            "-i", str(plugin_path),
            "-o", str(out_dir),
            "-g", _SPRIGGIT_GAME_RELEASE,
            "-p", _SPRIGGIT_PACKAGE,
            "-v", version,
        ]
        result = run_tool(binary, args, timeout=cfg.subprocess_timeout, env_extra=_spriggit_env())
        if not out_dir.exists():
            raise Fo4McpError(
                ErrorCode.SUBPROCESS_FAILED,
                "Spriggit serialize produced no output",
                {"exit_code": result.exit_code, "stderr_tail": result.stderr[-1000:]},
            )

        matches: list[dict[str, Any]] = []
        for f in sorted(out_dir.rglob("*.yaml")):
            if f.name in ("RecordData.yaml",):
                continue
            body = f.read_text(encoding="utf-8", errors="replace")
            fields = _extract_record_fields(body)
            fk = fields["form_key"] or ""
            fk_id = _norm_formid(fk.split(":", 1)[0]) if ":" in fk else None
            eid = (fields["editor_id"] or "").lower()
            hit = (want_formid is not None and fk_id == want_formid) or (
                eid and eid == want_editor
            )
            if hit:
                matches.append({
                    "file":        str(f.relative_to(out_dir)).replace("\\", "/"),
                    "editor_id":   fields["editor_id"],
                    "form_key":    fields["form_key"],
                    "record_type": fields["record_type"],
                    "yaml":        body,
                })

    return ok({
        "plugin":      str(plugin_path),
        "query":       record_id,
        "matched_as":  "formid" if want_formid else "editorid",
        "found":       bool(matches),
        "match_count": len(matches),
        "records":     matches,
        "backend":     "spriggit",
    })


def _inspect_record_via_cli(
    cfg: Config, cli: Path, plugin_path: Path, record_id: str, want_formid: str | None
) -> dict[str, Any]:
    """Fast-path backend: one mutagen-cli call, parse its single-object JSON.

    exit 0 = found, 1 = not found, 2 = bad args / load error. The matched
    record's `yaml` is a compact top-level stub built from the same keys the
    Spriggit path emits (MutagenObjectType/FormKey/EditorID), so the response
    shape is stable across backends; full field-tree fidelity stays a Spriggit
    feature."""
    import json

    result = run_tool(
        cli,
        ["--plugin", str(plugin_path), "--record", record_id],
        timeout=cfg.subprocess_timeout,
        env_extra=_spriggit_env(),
    )
    if result.exit_code == 2 or result.timed_out:
        raise Fo4McpError(
            ErrorCode.SUBPROCESS_FAILED,
            "mutagen-cli failed to load the plugin or parse arguments",
            {"exit_code": result.exit_code, "stderr_tail": result.stderr[-1000:]},
        )

    matches: list[dict[str, Any]] = []
    if result.exit_code == 0 and result.stdout.strip():
        obj = json.loads(result.stdout)
        if obj.get("found"):
            rt, fk, eid = obj.get("recordType"), obj.get("formKey"), obj.get("editorId")
            stub = "".join(
                f"{k}: {v}\n"
                for k, v in (("MutagenObjectType", rt), ("FormKey", fk), ("EditorID", eid))
                if v
            )
            matches.append({
                "file":        None,
                "editor_id":   eid,
                "form_key":    fk,
                "record_type": rt,
                "yaml":        stub,
            })

    return ok({
        "plugin":      str(plugin_path),
        "query":       record_id,
        "matched_as":  "formid" if want_formid else "editorid",
        "found":       bool(matches),
        "match_count": len(matches),
        "records":     matches,
        "backend":     "mutagen-cli",
    })


# ---- Tool 3j: create record (authoring writer) ------------------------------

# Record types the mutagen-cli `create` subcommand can author.
_CREATE_SUPPORTED_TYPES = ("npc", "armor", "quest", "keyword", "formlist", "message", "global", "faction", "levelednpc", "leveleditem", "leveleditemoverride", "cell", "celloverride", "smqn", "activator", "location", "locationreftype", "encounterzone", "package", "book", "misc", "materialswap", "outfit", "weapon", "static", "door", "light", "container", "ingestible", "ingredient", "constructibleobject", "cobj")

# Papyrus VMAD script-property value types the writer maps to ScriptProperty subclasses.
_SCRIPT_PROPERTY_TYPES = ("object", "int", "float", "bool", "string")
# SceneAction.TypeEnum names (the "typical" action types; StartScene deferred).
_SCENE_ACTION_TYPES = (
    "dialog", "package", "timer", "playerdialogue", "npcresponsedialogue", "radio",
)
# BipedObjectFlag names (ARMO body slots; mirrors Mutagen FO4 enum, case-insensitive).
# The CLI's Enum.TryParse is authoritative; this gives a clean early reject.
_BIPED_OBJECT_FLAGS = frozenset((
    "hairtop", "hairlong", "facegenhead", "body", "lefthand", "righthand",
    "torsounderarmor", "leftarmunderarmor", "rightarmunderarmor",
    "leftlegunderarmor", "rightlegunderarmor", "torsoarmor", "leftarmarmor",
    "rightarmarmor", "leftlegarmor", "rightlegarmor", "headband", "eyes", "beard",
    "mouth", "neck", "ring", "scalp", "decapitation", "unnamed54", "unnamed55",
    "unnamed56", "unnamed57", "unnamed58", "shield", "pipboy", "fx",
))

# OS-01: Weapon.AnimationTypes names (case-insensitive early reject; CLI Enum.TryParse is
# authoritative). The weapon "type" — drives the held-animation set.
_WEAPON_ANIM_TYPES = frozenset((
    "handtohandmelee", "onehandsword", "onehanddagger", "onehandaxe", "onehandmace",
    "twohandsword", "twohandaxe", "bow", "staff", "gun", "grenade", "mine",
))


def _norm_conditions(conds: Any, loc: str) -> list[dict[str, Any]]:
    """Validate + normalize a condition list (shared by INFO responses and quest
    aliases — same FunctionConditionData shape). Each condition needs a 'function'
    name; comparison/value/param1/param2/runOn are optional. The CLI does the
    authoritative Condition.Function / CompareOperator / RunOnType enum parse and
    the param FormKey parse.

    Run-on payload (Faz 3 / W1): runOn='QuestAlias' takes an explicit 'aliasRunOn'
    int (alias id -> Unknown3; required so it can't silently default to alias 0);
    runOn='Reference' takes a 'reference' FormLink -> the Reference slot (distinct
    from the function params). Each rejects the wrong runOn."""
    if not isinstance(conds, list):
        raise Fo4McpError(ErrorCode.INVALID_ARGUMENT, f"{loc} must be a list", {})
    out: list[dict[str, Any]] = []
    for c, cd in enumerate(conds):
        cloc = f"{loc}[{c}]"
        if not isinstance(cd, dict):
            raise Fo4McpError(ErrorCode.INVALID_ARGUMENT, f"{cloc} must be an object", {})
        fn = str(cd.get("function", "")).strip()
        if not fn:
            raise Fo4McpError(ErrorCode.INVALID_ARGUMENT, f"{cloc} needs a 'function' name", {})
        centry: dict[str, Any] = {"function": fn}
        if cd.get("comparison") is not None:
            centry["comparison"] = str(cd["comparison"]).strip()
        if cd.get("value") is not None:
            try:
                centry["value"] = float(cd["value"])
            except (TypeError, ValueError):
                raise Fo4McpError(
                    ErrorCode.INVALID_ARGUMENT, f"{cloc}.value must be a number", {}
                )
        else:
            centry["value"] = 1.0
        for pk in ("param1", "param2"):
            if cd.get(pk) is not None:
                centry[pk] = str(cd[pk]).strip()
        if cd.get("runOn") is not None:
            centry["runOn"] = str(cd["runOn"]).strip()
        # Faz 3 / W1: QuestAlias run-on (alias id -> Unknown3) + Reference run-on slot.
        # Alias ids are 0-based, so 0 is valid; the footgun is the silent default 0 when
        # runOn=QuestAlias and no alias is given -> require an explicit aliasRunOn instead.
        run_on = centry.get("runOn", "").lower()
        if cd.get("aliasRunOn") is not None:
            if run_on != "questalias":
                raise Fo4McpError(
                    ErrorCode.INVALID_ARGUMENT,
                    f"{cloc}.aliasRunOn requires runOn='QuestAlias'", {})
            try:
                centry["aliasRunOn"] = int(cd["aliasRunOn"])
            except (TypeError, ValueError):
                raise Fo4McpError(
                    ErrorCode.INVALID_ARGUMENT,
                    f"{cloc}.aliasRunOn must be an integer alias id", {})
            if centry["aliasRunOn"] < 0:
                raise Fo4McpError(
                    ErrorCode.INVALID_ARGUMENT, f"{cloc}.aliasRunOn must be >= 0", {})
        elif run_on == "questalias":
            raise Fo4McpError(
                ErrorCode.INVALID_ARGUMENT,
                f"{cloc} runOn='QuestAlias' needs an explicit aliasRunOn "
                "(else it silently targets alias 0)", {})
        if cd.get("reference") is not None:
            if run_on != "reference":
                raise Fo4McpError(
                    ErrorCode.INVALID_ARGUMENT,
                    f"{cloc}.reference requires runOn='Reference'", {})
            centry["reference"] = str(cd["reference"]).strip()
        out.append(centry)
    return out


def _norm_script_properties(props: Any, loc: str) -> list[dict[str, Any]]:
    """Validate + normalize a Papyrus script property list (shared by the quest
    whole-script binding, Faz 2.1d, and the fragment script, Faz 2.1f). Values pass
    through with their JSON type intact — the CLI type-checks value-vs-type and is
    authoritative. 'object' may instead fill from an alias index."""
    if not isinstance(props, list):
        raise Fo4McpError(ErrorCode.INVALID_ARGUMENT, f"{loc} must be a list", {})
    out: list[dict[str, Any]] = []
    for k, p in enumerate(props):
        ploc = f"{loc}[{k}]"
        if not isinstance(p, dict):
            raise Fo4McpError(ErrorCode.INVALID_ARGUMENT, f"{ploc} must be an object", {})
        pname = str(p.get("name", "")).strip()
        if not pname:
            raise Fo4McpError(ErrorCode.INVALID_ARGUMENT, f"{ploc} needs a 'name'", {})
        ptype = str(p.get("type", "")).strip().lower()
        if ptype not in _SCRIPT_PROPERTY_TYPES:
            raise Fo4McpError(
                ErrorCode.INVALID_ARGUMENT,
                f"{ploc}.type must be one of {list(_SCRIPT_PROPERTY_TYPES)}",
                {"type": p.get("type")},
            )
        pentry: dict[str, Any] = {"name": pname, "type": ptype}
        # value passes through with its JSON type intact (the CLI type-checks
        # value-vs-type); do NOT str()-coerce it.
        if p.get("value") is not None:
            pentry["value"] = p["value"]
        if p.get("alias") is not None:
            try:
                pentry["alias"] = int(p["alias"])
            except (TypeError, ValueError):
                raise Fo4McpError(
                    ErrorCode.INVALID_ARGUMENT, f"{ploc}.alias must be an integer", {}
                )
        out.append(pentry)
    return out


def _norm_script_entry(s: Any, loc: str) -> dict[str, Any]:
    """Validate + normalize one Papyrus ScriptEntry spec (name + optional flags +
    typed properties) into {name, flags?, properties?}. Shared by the quest whole-
    script binding (Faz 2.1d) and alias fragment scripts (Faz 2.1g). The CLI is
    authoritative on the ScriptEntry.Flag enum + property value-vs-type."""
    if not isinstance(s, dict):
        raise Fo4McpError(ErrorCode.INVALID_ARGUMENT, f"{loc} must be an object", {})
    name = str(s.get("name", "")).strip()
    if not name:
        raise Fo4McpError(ErrorCode.INVALID_ARGUMENT, f"{loc} needs a 'name'", {})
    entry: dict[str, Any] = {"name": name}
    if s.get("flags") is not None:
        entry["flags"] = str(s["flags"]).strip()
    props = s.get("properties")
    if props is not None:
        entry["properties"] = _norm_script_properties(props, f"{loc}.properties")
    return entry


def _norm_placed_refs(refs: Any, loc: str) -> list[dict[str, Any]]:
    """Validate + normalize a placed-reference list (W4 — REFR/ACHR children of a
    cell). Each needs a 'base' FormKey; position/rotation are optional [x,y,z] float
    triples; scale/editorId/persistent optional. The CLI does the authoritative
    FormKey parse (and auto-adds the base's master)."""
    if not isinstance(refs, list):
        raise Fo4McpError(ErrorCode.INVALID_ARGUMENT, f"{loc} must be a list", {})
    out: list[dict[str, Any]] = []
    for k, p in enumerate(refs):
        ploc = f"{loc}[{k}]"
        if not isinstance(p, dict):
            raise Fo4McpError(ErrorCode.INVALID_ARGUMENT, f"{ploc} must be an object", {})
        base = str(p.get("base", "")).strip()
        if not base:
            raise Fo4McpError(ErrorCode.INVALID_ARGUMENT, f"{ploc} needs a 'base' FormKey", {})
        entry: dict[str, Any] = {"base": base}
        if p.get("editorId") is not None:
            entry["editorId"] = str(p["editorId"]).strip()
        for vk in ("position", "rotation"):
            if p.get(vk) is not None:
                v = p[vk]
                if not isinstance(v, list) or len(v) != 3:
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"{ploc}.{vk} must be [x,y,z] (3 numbers)", {})
                try:
                    entry[vk] = [float(x) for x in v]
                except (TypeError, ValueError):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT, f"{ploc}.{vk} must be 3 numbers", {})
        if p.get("scale") is not None:
            try:
                entry["scale"] = float(p["scale"])
            except (TypeError, ValueError):
                raise Fo4McpError(
                    ErrorCode.INVALID_ARGUMENT, f"{ploc}.scale must be a number", {})
        if p.get("persistent") is not None:
            entry["persistent"] = bool(p["persistent"])
        tp = p.get("teleport")
        if tp is not None:
            # W8.5: XTEL door-link — destination door + spawn position/rotation.
            if not isinstance(tp, dict) or not str(tp.get("door", "")).strip():
                raise Fo4McpError(
                    ErrorCode.INVALID_ARGUMENT, f"{ploc}.teleport needs a 'door' FormKey", {})
            te: dict[str, Any] = {"door": str(tp["door"]).strip()}
            for vk in ("position", "rotation"):
                if tp.get(vk) is not None:
                    v = tp[vk]
                    if not isinstance(v, list) or len(v) != 3:
                        raise Fo4McpError(
                            ErrorCode.INVALID_ARGUMENT,
                            f"{ploc}.teleport.{vk} must be [x,y,z] (3 numbers)", {})
                    try:
                        te[vk] = [float(x) for x in v]
                    except (TypeError, ValueError):
                        raise Fo4McpError(
                            ErrorCode.INVALID_ARGUMENT,
                            f"{ploc}.teleport.{vk} must be 3 numbers", {})
            entry["teleport"] = te
        out.append(entry)
    return out


def fo4_create_record(
    cfg: Config,
    manifest: Manifest,
    spec: dict[str, Any],
    output_plugin: str,
    *,
    confirm_overwrite: bool = False,
) -> dict[str, Any]:
    """Author a new plugin from a record spec via the mutagen-cli writer.

    Spec -> Mutagen `new Fallout4Mod` -> AddNew(Npc|Armor) -> WriteToBinary. This
    is the Faz 1 authoring path proven viable by the round-trip test (research/
    p0/authoring/2026-06-05-quest-roundtrip-proof.md): Mutagen reimplements the
    ESP/ESM model, so records are created in code — CK is not needed to author.

    Output is safety-gated (staging/ or fixtures/; never the Steam Data/ source).
    Writing a real plugin is never silent: an existing target is left untouched
    unless confirm_overwrite=True, in which case it is backed up to `<name>.bak`
    first.

    Scope: NPC, ARMO, and QUST records. NPCs accept Race/Class FormLinks + faction
    memberships (Faz 1.1); Armors accept keyword FormLinks + value/weight + armor
    rating (DNAM UInt16) + biped body slots (BipedObjectFlag names, Faz 1.2); Quests
    accept type/flags + stages (with log entries) +
    objectives (Faz 2) + quest-nested dialogue topics (DIAL -> INFO -> spoken lines,
    Faz 2.1a) + INFO conditions (ConditionFloat + generic FunctionConditionData, any
    of the 479 Condition.Function names, Faz 2.1b) + quest aliases (QuestReferenceAlias
    cast slots: id/name/flags + ForcedReference/UniqueActor fill + find-matching-ref
    conditions, Faz 2.1c) + Papyrus VMAD binding (QuestAdapter: attach scripts by .psc
    name with typed properties — object/int/float/bool/string, FO4 VMAD v6/objfmt2,
    Faz 2.1d) + SCEN scenes (Scene records back-linked to the quest: a cast of actors
    by alias ID, flow phases with start/completion conditions, and a timeline of
    "typical" actions — Dialog/Package/Timer/... — each referencing a topic by editorId
    or FormKey, Faz 2.1e) + quest stage script fragments (QuestAdapter: a single QF
    fragment script + per-stage entries that fire a Fragment_* function at each stage;
    metadata only — compile the matching .pex via fo4_papyrus_build, Faz 2.1f) + quest
    alias script fragments (per-alias fragment scripts bound by alias ID into
    QuestAdapter.Aliases; metadata only, Faz 2.1g). Any FormLink into a master auto-adds
    that master to the header (including condition + alias-fill + script-object-property
    + scene-condition record params). The result is a *structurally* valid plugin
    (re-readable by Mutagen), and the written fields are read back from disk into the
    response as a round-trip proof. The .pex/in-game fragment loop + niche scene/alias
    variants are the next authoring surface (ahead).

    Args:
        spec:              {"records": [{"type": "Npc"|"Armor"|"Weapon"|"Quest"|"Keyword"|"FormList"|"Message"|"Global"|"Faction"|"LeveledNpc"|"LeveledItem"|"Cell"|"Outfit"|"Static"|"Door"|"Light"|"Container"|"Ingestible"|"Ingredient"|"ConstructibleObject",
                           "editorId": str, "name": str?,
                           # NPC-only:
                           "race": "<6hex>:<master>"?, "class": "<6hex>:<master>"?,
                           "factions": [{"faction": "<6hex>:<master>", "rank": int}]?,
                           # NPC full-field (W3b) — FormLink scalars + AI enums + keywords/inventory/perks:
                           "voice": "<6hex>:<master>"?, "combatStyle": "<6hex>:<master>"?,
                           "defaultOutfit": "<6hex>:<master>"?, "attackRace": "<6hex>:<master>"?,
                           "skin": "<6hex>:<master>"?,  # worn-armor override
                           "aggression": "Unaggressive|Aggressive|VeryAggressive|Frenzied"?,
                           "confidence": "Cowardly|Cautious|Average|Brave|Foolhardy"?,
                           "assistance": "HelpsNobody|HelpsAllies|HelpsFriendsAndAllies"?,
                           "responsibility": "AnyCrime|ViolenceAgainstEnemies|PropertyCrimeOnly|NoCrime"?,
                           "mood": "Neutral|Angry|Fear|Happy|Sad|Surprised|Puzzled|Disgusted"?,
                           "keywords": ["<6hex>:<master>"]?,  # NPC + Armor share this field
                           "inventory": [{"item": "<6hex>:<master>", "count": int}]?,  # CNTO, count>=0
                           "perks": [{"perk": "<6hex>:<master>", "rank": int}]?,  # rank 0..255
                           # NPC template-chain (W3c) — FaceGen inheritance:
                           "defaultTemplate": "<6hex>:<master>"?,  # NPC_ or LVLN template source
                           "useTemplateActors": [str]?,  # TemplateActorType flags OR'd (Traits|Stats|Factions|SpellList|AiData|AiPackages|ModelOrAnimation|BaseData|Inventory|Script|DefPackList|AttackData|Keywords)
                           # NPC actor flags (OS-14) — Essential/Protected guard a quest-critical NPC:
                           "flags": [str]?,  # Npc.Flag names (Essential|Protected|Invulnerable|Unique|Respawn|...)
                           # Armor-only:
                           "keywords": ["<6hex>:<master>"]?, "value": int?,
                           "weight": float?, "armorRating": int?,  # 0..65535
                           "bipedSlots": [str]?,  # BipedObjectFlag names, e.g. TorsoArmor
                           # Weapon-only (OS-01) — DNAM stats + FormLinks + model/keywords:
                           "value": int?, "weight": float?,
                           "baseDamage": int?, "ammoCapacity": int?,  # 0..65535
                           "speed": float?, "reach": float?, "minRange": float?, "maxRange": float?,  # >=0
                           "animationType": str?,  # Gun|Bow|OneHandSword|TwoHandAxe|Grenade|Mine|...
                           "ammo": "<6hex>:<master>"?,         # AMMO FormLink
                           "attackSound": "<6hex>:<master>"?,  # SNDR FormLink
                           "equipSound": "<6hex>:<master>"?,   # SNDR FormLink
                           "attachParentSlots": ["<6hex>:<master>"]?,  # AKEY keyword FormLinks
                           "model": str?, "materialSwap": "<6hex>:<master>"?,
                           "objectBounds": [x1,y1,z1,x2,y2,z2]?,
                           # Outfit (OS-14): items = worn-piece FormLinks (ARMO/LVLI/NPC_).
                           "items": ["<6hex>:<master>"]?,
                           # Static/Door/Light/Container/Ingestible/Ingredient (OS-02):
                           # share model/materialSwap/keywords/flags; LIGH/ALCH add value/weight;
                           # LIGH adds radius (uint); CONT adds inventory; ALCH/INGR add effects.
                           "radius": int?,  # LIGH only
                           "inventory": [{"item": "<6hex>:<master>", "count": int}]?,  # CONT only
                           "effects": [{"baseEffect": "<6hex>:<master>",  # MGEF (required)
                             "magnitude": float?, "area": int?, "duration": int?}]?,  # ALCH/INGR only
                           # ConstructibleObject / COBJ (OS-08) — a crafting recipe:
                           "createdObject": "<6hex>:<master>",       # recipe output (required)
                           "workbenchKeyword": "<6hex>:<master>",    # bench type (required)
                           "createdObjectCount": int?,               # default 1
                           "menuArtObject": "<6hex>:<master>"?,
                           "components": [{"component": "<6hex>:<master>", "count": int}]?,
                           "categories": ["<6hex>:<master>"]?,       # workshop-menu filter KYWDs
                           "conditions": [{...like INFO conditions...}]?,  # recipe gates
                           # Keyword: editorId (+ name) only — a bare KYWD.
                           # Message-only:
                           "text": str?,  # MESG body (Description); title|name -> Name
                           # OS-11: message-box flags + menu buttons (choice dialogs):
                           "flags": [str]?,  # Message.Flag (MessageBox|DelayInitialDisplay)
                           "menuButtons": [{"text": str,  # the choice text (required)
                             "conditions": [{...like INFO conditions...}]?}]?,
                           # FormList-only:
                           "items": ["<6hex>:<master>"]?,  # FLST entries (any record)
                           # Global-only:
                           "globalType": "float"|"int"|"short"?,  # default float
                           "globalValue": float?,  # the Data scalar
                           # Faction-only (+ "flags": [str]? faction flags, e.g. TrackCrime):
                           "interfactionRelations": [{"faction": "<6hex>:<master>",
                             "reaction": "Neutral"|"Enemy"|"Ally"|"Friend"}]?,
                           # OS-11: ranks (gendered titles) + vendor/merchant data:
                           "ranks": [{"number": int?, "title": str?,  # title fills both genders
                             "titleFemale": str?, "insignia": str?}]?,  # unless titleFemale overrides
                           "vendorValues": {"startHour": int?, "endHour": int?, "radius": int?,  # 0..65535
                             "buysStolen": bool?, "buysNonStolen": bool?, "buyEverything": bool?}?,
                           # LeveledNpc / LeveledItem (W3d/W3e) — flags reuse the "flags" key:
                           "entries": [{"reference": "<6hex>:<master>",  # INpcSpawn (LVLN) | IItem (LVLI)
                             "level": int?, "count": int?}]?,  # level/count 1..32767, default 1
                           "flags": [str]?,  # LVLN: Calculate{FromAllLevelsLessThanOrEqualPlayer,ForEachItemInCount,All}; LVLI: ...,UseAll
                           "chanceNone": int?,  # OS-11: 0..100% chance the list yields nothing
                           # Cell-only (W4) — a new INTERIOR cell + nested placed refs.
                           # name -> display cell name; block/subblock are auto-derived from the FormID.
                           "lightingTemplate": "<6hex>:<master>"?,  # LTMP — omit it and the cell renders black
                           "waterHeight": float?,  # XCLW
                           "location": "<6hex>:<master>"?,        # XLCN
                           "encounterZone": "<6hex>:<master>"?,   # XEZN
                           "imageSpace": "<6hex>:<master>"?,      # XCIM
                           "acousticSpace": "<6hex>:<master>"?,   # XCAS
                           "music": "<6hex>:<master>"?,           # XCMO
                           "placedObjects": [{"base": "<6hex>:<master>",  # REFR base (required)
                             "editorId": str?, "position": [x,y,z]?, "rotation": [x,y,z]?,
                             "scale": float?, "persistent": bool?}]?,  # default -> Temporary
                           "placedNpcs": [{"base": "<6hex>:<master>",  # ACHR base (required)
                             "editorId": str?, "position": [x,y,z]?, "rotation": [x,y,z]?,
                             "scale": float?, "persistent": bool?}]?,
                           # Quest-only:
                           "questType": str?, "flags": [str]?,
                           "stages": [{"index": int, "logEntry": str?,
                             "runOnStart": bool?}]?,  # runOnStart=startup stage (INDX 0x02);
                             # every logEntry auto-gets a QSDT marker (engine-required)
                           "objectives": [{"index": int, "text": str?,
                             # W2: objective flags + QSTA targets (compass markers):
                             "flags": ["OrWithPrevious"|"NoStatsTracking"]?,
                             "targets": [{"aliasId": int,  # the quest alias the marker points at
                               "flags": ["CompassMarkerIgnoresLocks"|"Hostile"|"UseStraightLinePathing"]?,
                               "keyword": "<6hex>:<master>"?,  # LCRT location keyword
                               "conditions": [<same as INFO conditions>]?}]?}]?,
                           # DLBR branches make topics surface in the dialogue wheel (Kerem-polish).
                           # A bare topic (no branch) never appears when the player activates the NPC.
                           "branches": [{"editorId": str,  # mints a DialogBranch FormKey
                             "startingTopic": str,   # entry topic editorId (in-spec) or "<6hex>:<master>"
                             "category": str?,       # DialogBranch.CategoryType; default Player
                             "flags": [str]?}]?,     # DialogBranch.Flag; default ["TopLevel"]
                           "topics": [{"editorId": str?, "name": str?,
                             "subtype": str?, "category": str?,
                             "branch": str?,  # owning branch editorId (in-spec) or FormKey -> topic surfaces
                             "responses": [{"prompt": str?,  # the wheel button text (player-facing)
                               "speaker": "<6hex>:<master>"?,
                               "formKey": "<6hex>:<master>"?,  # OS-04: pin the INFO id (stable TIF name)
                               "lines": [{"text": str?, "responseNumber": int?,
                                 "emotion": "<6hex>:<master>"?}]?,
                               "conditions": [{"function": str, "comparison": str?,
                                 "value": float?, "param1": str?, "param2": str?,
                                 "runOn": str?,  # RunOnType; default Subject
                                 "aliasRunOn": int?,  # runOn=QuestAlias: explicit alias id (->Unknown3)
                                 "reference": "<6hex>:<master>"?  # runOn=Reference: target ref
                                 }]?,
                               "setParentQuestStage": {"onBegin": int?, "onEnd": int?}?,  # SNAM stage advance
                               "fragment": {"scriptName": str,  # OS-04: TIF VMAD — line runs Papyrus
                                 "flags": str?, "onBegin": str?, "onEnd": str?,  # >=1 of onBegin/onEnd
                                 "properties": [{...like script properties...}]?}?}]?}]?,
                           "aliases": [{"id": int?, "name": str?, "flags": [str]?,
                             "type": "reference"|"location"?,  # default reference
                             "forcedReference": "<6hex>:<master>"?,  # [reference] fill
                             "uniqueActor": "<6hex>:<master>"?,      # [reference] fill
                             "specificLocation": "<6hex>:<master>"?, # [location] fill (LCTN)
                             "referenceAliasLocation": int?,  # [location] = location of alias <id>
                             "externalAliasQuest": "<6hex>:<master>"?,  # [location/reference] external quest
                             "externalAliasId": int?,  # [location/reference] alias id in that quest
                             "fromEvent": str?,  # 4-char event sig (FindMatchingRefFromEvent)
                             "conditions": [{...same as INFO conditions...}]?}]?,
                           "scripts": [{"name": str, "flags": str?,
                             "properties": [{"name": str, "type":
                               "object"|"int"|"float"|"bool"|"string",
                               "value": <FormKey str|int|float|bool|str>?,
                               "alias": int?}]?}]?,
                           "scenes": [{"editorId": str, "flags": [str]?,
                             "actors": [{"id": int}]?,  # id = quest alias ID
                             "phases": [{"name": str?,
                               "startConditions": [{...like INFO conditions...}]?,
                               "completionConditions": [{...}]?}]?,
                             "actions": [{"type": "Dialog"|"PlayerDialogue"|...,
                               "actor": int?, "topic": "<topic editorId|6hex:master>"?,
                               "startPhase": int?, "endPhase": int?,
                               "flags": [str]?}]?}]?,
                           "fragments": {"scriptName": str, "flags": str?,
                             "properties": [{...like script properties...}]?,
                             "stages": [{"stage": int, "stageIndex": int?,
                               "fragmentName": str}]?},
                           "aliasFragments": [{"alias": int,  # quest alias ID
                             "scripts": [{...same shape as 'scripts'...}]}]?,
                           # Package-only (W7) — a template-bound PACK:
                           "packageTemplate": "<6hex>:<master>"?,  # PKDT template (e.g. 002CB0 Travel)
                           "packageType": "Package"|"PackageTemplate"?,
                           "ownerQuest": "<6hex>:<master>"?, "combatStyle": "<6hex>:<master>"?,
                           "flags": [str]?, "conditions": [{...like INFO conditions...}]?,
                           # W7-Data: one location data-input. The slot is resolved by
                           # name against the live template (needs the FO4 install), so
                           # only the target value travels here:
                           "dataLocation": {"target": "<6hex>:<master>",  # ref/cell/keyword
                             "targetType": "reference"|"cell"|"keyword"?,  # default reference
                             "radius": int?,  # units, default 0
                             "input": str?}?  # template input Name (default: first location slot)
                           }]}
        output_plugin:     destination plugin path, .esp/.esm/.esl (safety-gated)
        confirm_overwrite: required to overwrite an existing plugin
    """
    import json
    import shutil
    import tempfile

    # --- validate the spec up front (clean errors before touching the CLI) ---
    if not isinstance(spec, dict):
        raise Fo4McpError(
            ErrorCode.INVALID_ARGUMENT,
            "spec must be an object with a 'records' list",
            {"spec_type": type(spec).__name__},
        )
    records = spec.get("records")
    if not isinstance(records, list) or not records:
        raise Fo4McpError(
            ErrorCode.INVALID_ARGUMENT,
            "spec.records must be a non-empty list",
            {},
        )
    norm_records: list[dict[str, Any]] = []
    for i, r in enumerate(records):
        if not isinstance(r, dict):
            raise Fo4McpError(
                ErrorCode.INVALID_ARGUMENT, f"spec.records[{i}] must be an object", {}
            )
        rtype = str(r.get("type", "")).strip()
        eid = str(r.get("editorId", "")).strip()
        if rtype.lower() not in _CREATE_SUPPORTED_TYPES:
            raise Fo4McpError(
                ErrorCode.INVALID_ARGUMENT,
                f"spec.records[{i}].type '{rtype}' unsupported "
                f"(Npc, Armor, Weapon, Quest, Keyword, FormList, Message, Global, Faction, "
                f"LeveledNpc, LeveledItem, LeveledItemOverride, Cell, CellOverride, Smqn, "
                f"Activator, Location, LocationRefType, EncounterZone, Package, Book, Misc, "
                f"MaterialSwap, Outfit, Static, Door, Light, Container, Ingestible, "
                f"Ingredient, ConstructibleObject)",
                {"supported": list(_CREATE_SUPPORTED_TYPES)},
            )
        if not eid and rtype.lower() not in ("celloverride", "leveleditemoverride"):
            # an override (cell / leveled-item) identifies its target by FormKey (the master's
            # editorId carries forward via DeepCopy), so it needs no editorId.
            raise Fo4McpError(
                ErrorCode.INVALID_ARGUMENT, f"spec.records[{i}] missing editorId", {}
            )
        rec: dict[str, Any] = {"type": rtype, "editorId": eid}
        if r.get("name") is not None:
            rec["name"] = str(r["name"])
        # Faz 1.1: richer NPC FormLink fields. Light-validate shape here; the CLI
        # does the authoritative FormKey parse and auto-adds referenced masters.
        if rtype.lower() == "npc":
            if r.get("race") is not None:
                rec["race"] = str(r["race"]).strip()
            if r.get("class") is not None:
                rec["class"] = str(r["class"]).strip()
            # W7: bind existing AI packages (PACK FormLinks) -> npc.Packages (ordered = priority).
            pkgs = r.get("packages")
            if pkgs is not None:
                if not isinstance(pkgs, list):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].packages must be a list", {})
                rec["packages"] = [str(x).strip() for x in pkgs]
            facs = r.get("factions")
            if facs is not None:
                if not isinstance(facs, list):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].factions must be a list", {}
                    )
                norm_facs: list[dict[str, Any]] = []
                for j, f in enumerate(facs):
                    if not isinstance(f, dict) or not str(f.get("faction", "")).strip():
                        raise Fo4McpError(
                            ErrorCode.INVALID_ARGUMENT,
                            f"spec.records[{i}].factions[{j}] needs a 'faction' FormKey",
                            {},
                        )
                    try:
                        rank = int(f.get("rank", 0))
                    except (TypeError, ValueError):
                        raise Fo4McpError(
                            ErrorCode.INVALID_ARGUMENT,
                            f"spec.records[{i}].factions[{j}].rank must be an integer",
                            {},
                        )
                    if not -128 <= rank <= 127:
                        raise Fo4McpError(
                            ErrorCode.INVALID_ARGUMENT,
                            f"spec.records[{i}].factions[{j}].rank out of range (-128..127)",
                            {"rank": rank},
                        )
                    norm_facs.append({"faction": str(f["faction"]).strip(), "rank": rank})
                rec["factions"] = norm_facs
            # W3b full-field: scalar FormLink fields (CLI does authoritative FormKey parse).
            for fld in ("voice", "combatStyle", "defaultOutfit", "attackRace", "skin"):
                if r.get(fld) is not None:
                    rec[fld] = str(r[fld]).strip()
            # W3b: AI personality enums (CLI does authoritative Enum.TryParse on the name).
            for fld in ("aggression", "confidence", "assistance", "responsibility", "mood"):
                if r.get(fld) is not None:
                    val = str(r[fld]).strip()
                    if not val:
                        raise Fo4McpError(
                            ErrorCode.INVALID_ARGUMENT,
                            f"spec.records[{i}].{fld} must be a non-empty enum name", {}
                        )
                    rec[fld] = val
            # W3b: keywords (FormLink list; same shape as armor keywords).
            npc_kws = r.get("keywords")
            if npc_kws is not None:
                if not isinstance(npc_kws, list):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].keywords must be a list", {}
                    )
                norm_npc_kws: list[str] = []
                for j, kw in enumerate(npc_kws):
                    if not str(kw).strip():
                        raise Fo4McpError(
                            ErrorCode.INVALID_ARGUMENT,
                            f"spec.records[{i}].keywords[{j}] must be a non-empty FormKey", {}
                        )
                    norm_npc_kws.append(str(kw).strip())
                rec["keywords"] = norm_npc_kws
            # W3b: inventory (CNTO) — list of {item FormKey, count>=0}.
            inv = r.get("inventory")
            if inv is not None:
                if not isinstance(inv, list):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].inventory must be a list", {}
                    )
                norm_inv: list[dict[str, Any]] = []
                for j, it in enumerate(inv):
                    if not isinstance(it, dict) or not str(it.get("item", "")).strip():
                        raise Fo4McpError(
                            ErrorCode.INVALID_ARGUMENT,
                            f"spec.records[{i}].inventory[{j}] needs an 'item' FormKey", {}
                        )
                    try:
                        count = int(it.get("count", 1))
                    except (TypeError, ValueError):
                        raise Fo4McpError(
                            ErrorCode.INVALID_ARGUMENT,
                            f"spec.records[{i}].inventory[{j}].count must be an integer", {}
                        )
                    if count < 0:
                        raise Fo4McpError(
                            ErrorCode.INVALID_ARGUMENT,
                            f"spec.records[{i}].inventory[{j}].count must be >= 0", {"count": count}
                        )
                    norm_inv.append({"item": str(it["item"]).strip(), "count": count})
                rec["inventory"] = norm_inv
            # W3b: perks (PerkPlacement) — list of {perk FormKey, rank 0-255}.
            pks = r.get("perks")
            if pks is not None:
                if not isinstance(pks, list):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].perks must be a list", {}
                    )
                norm_pks: list[dict[str, Any]] = []
                for j, pk in enumerate(pks):
                    if not isinstance(pk, dict) or not str(pk.get("perk", "")).strip():
                        raise Fo4McpError(
                            ErrorCode.INVALID_ARGUMENT,
                            f"spec.records[{i}].perks[{j}] needs a 'perk' FormKey", {}
                        )
                    try:
                        rank = int(pk.get("rank", 0))
                    except (TypeError, ValueError):
                        raise Fo4McpError(
                            ErrorCode.INVALID_ARGUMENT,
                            f"spec.records[{i}].perks[{j}].rank must be an integer", {}
                        )
                    if not 0 <= rank <= 255:
                        raise Fo4McpError(
                            ErrorCode.INVALID_ARGUMENT,
                            f"spec.records[{i}].perks[{j}].rank out of range (0..255)", {"rank": rank}
                        )
                    norm_pks.append({"perk": str(pk["perk"]).strip(), "rank": rank})
                rec["perks"] = norm_pks
            # W3c: template-chain — defaultTemplate FormLink + useTemplateActors flag
            # names. CLI is authoritative for both the FormKey parse and the
            # TemplateActorType names (Traits|Stats|Factions|SpellList|AiData|AiPackages|
            # ModelOrAnimation|BaseData|Inventory|Script|DefPackList|AttackData|Keywords).
            if r.get("defaultTemplate") is not None:
                rec["defaultTemplate"] = str(r["defaultTemplate"]).strip()
            uta = r.get("useTemplateActors")
            if uta is not None:
                if not isinstance(uta, list):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].useTemplateActors must be a list", {}
                    )
                norm_uta: list[str] = []
                for j, fl in enumerate(uta):
                    if not str(fl).strip():
                        raise Fo4McpError(
                            ErrorCode.INVALID_ARGUMENT,
                            f"spec.records[{i}].useTemplateActors[{j}] must be a non-empty flag name", {}
                        )
                    norm_uta.append(str(fl).strip())
                rec["useTemplateActors"] = norm_uta
            # OS-14: actor flags (Essential/Protected/...). Author-facing key is `flags`; mapped
            # to npcFlags to avoid the C# Quest/Faction Flags-field collision. CLI does the
            # authoritative Npc.Flag enum parse.
            nfl = r.get("flags")
            if nfl is not None:
                if not isinstance(nfl, list):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].flags must be a list of flag names", {}
                    )
                norm_nfl: list[str] = []
                for j, fl in enumerate(nfl):
                    if not str(fl).strip():
                        raise Fo4McpError(
                            ErrorCode.INVALID_ARGUMENT,
                            f"spec.records[{i}].flags[{j}] must be a non-empty flag name", {}
                        )
                    norm_nfl.append(str(fl).strip())
                rec["npcFlags"] = norm_nfl
        # Faz 1.2: richer ARMO. Keyword FormKeys are shape-checked here (CLI does the
        # authoritative parse + auto-adds masters); value/weight/armorRating ranges and
        # biped-slot flag names are validated here too.
        elif rtype.lower() == "armor":
            kws = r.get("keywords")
            if kws is not None:
                if not isinstance(kws, list):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].keywords must be a list", {}
                    )
                norm_kws: list[str] = []
                for j, kw in enumerate(kws):
                    if not str(kw).strip():
                        raise Fo4McpError(
                            ErrorCode.INVALID_ARGUMENT,
                            f"spec.records[{i}].keywords[{j}] must be a non-empty FormKey",
                            {},
                        )
                    norm_kws.append(str(kw).strip())
                rec["keywords"] = norm_kws
            if r.get("value") is not None:
                try:
                    value = int(r["value"])
                except (TypeError, ValueError):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].value must be an integer", {}
                    )
                if value < 0:
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].value must be >= 0", {"value": value}
                    )
                rec["value"] = value
            if r.get("weight") is not None:
                try:
                    weight = float(r["weight"])
                except (TypeError, ValueError):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].weight must be a number", {}
                    )
                if weight < 0:
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].weight must be >= 0", {"weight": weight}
                    )
                rec["weight"] = weight
            if r.get("armorRating") is not None:
                try:
                    rating = int(r["armorRating"])
                except (TypeError, ValueError):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].armorRating must be an integer", {}
                    )
                if not 0 <= rating <= 65535:
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].armorRating out of range (0..65535)",
                        {"armorRating": rating},
                    )
                rec["armorRating"] = rating
            slots = r.get("bipedSlots")
            if slots is not None:
                if not isinstance(slots, list):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].bipedSlots must be a list", {}
                    )
                norm_slots: list[str] = []
                for j, s in enumerate(slots):
                    name = str(s).strip()
                    if not name:
                        raise Fo4McpError(
                            ErrorCode.INVALID_ARGUMENT,
                            f"spec.records[{i}].bipedSlots[{j}] must be a non-empty flag name",
                            {},
                        )
                    if name.lower() not in _BIPED_OBJECT_FLAGS:
                        raise Fo4McpError(
                            ErrorCode.INVALID_ARGUMENT,
                            f"spec.records[{i}].bipedSlots[{j}] '{name}' is not a BipedObjectFlag",
                            {"slot": name},
                        )
                    norm_slots.append(name)
                rec["bipedSlots"] = norm_slots
            # Kerem-polish: ARMA addon links (worn mesh) + Race. An ARMO with no armatures
            # renders nothing equipped; reference existing (vanilla) ARMA FormKeys for a visible
            # armor with zero new art (CLI does the authoritative parse + auto-adds masters).
            arms = r.get("armatures")
            if arms is not None:
                if not isinstance(arms, list):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].armatures must be a list", {}
                    )
                norm_arms: list[str] = []
                for j, aa in enumerate(arms):
                    if not str(aa).strip():
                        raise Fo4McpError(
                            ErrorCode.INVALID_ARGUMENT,
                            f"spec.records[{i}].armatures[{j}] must be a non-empty FormKey", {}
                        )
                    norm_arms.append(str(aa).strip())
                rec["armatures"] = norm_arms
            if r.get("race") is not None:
                rec["race"] = str(r["race"]).strip()
        # OS-01: WEAP weapon. value/weight reuse the shared item ranges; DNAM stats are
        # range-checked here (baseDamage/ammoCapacity UInt16; speed/reach/min/maxRange >=0);
        # animationType is checked against _WEAPON_ANIM_TYPES. The CLI does the authoritative
        # FormKey parse (ammo/attackSound/equipSound) + Enum.TryParse + master auto-add.
        elif rtype.lower() == "weapon":
            if r.get("value") is not None:
                try:
                    wval = int(r["value"])
                except (TypeError, ValueError):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].value must be an integer", {})
                if wval < 0:
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].value must be >= 0", {"value": wval})
                rec["value"] = wval
            if r.get("weight") is not None:
                try:
                    wwt = float(r["weight"])
                except (TypeError, ValueError):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].weight must be a number", {})
                if wwt < 0:
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].weight must be >= 0", {"weight": wwt})
                rec["weight"] = wwt
            for fld in ("baseDamage", "ammoCapacity"):
                if r.get(fld) is not None:
                    try:
                        v = int(r[fld])
                    except (TypeError, ValueError):
                        raise Fo4McpError(
                            ErrorCode.INVALID_ARGUMENT,
                            f"spec.records[{i}].{fld} must be an integer", {})
                    if not 0 <= v <= 65535:
                        raise Fo4McpError(
                            ErrorCode.INVALID_ARGUMENT,
                            f"spec.records[{i}].{fld} out of range (0..65535)", {"value": v})
                    rec[fld] = v
            for fld in ("speed", "reach", "minRange", "maxRange"):
                if r.get(fld) is not None:
                    try:
                        v = float(r[fld])
                    except (TypeError, ValueError):
                        raise Fo4McpError(
                            ErrorCode.INVALID_ARGUMENT,
                            f"spec.records[{i}].{fld} must be a number", {})
                    if v < 0:
                        raise Fo4McpError(
                            ErrorCode.INVALID_ARGUMENT,
                            f"spec.records[{i}].{fld} must be >= 0", {"value": v})
                    rec[fld] = v
            anim = r.get("animationType")
            if anim is not None:
                anim_s = str(anim).strip()
                if anim_s.lower() not in _WEAPON_ANIM_TYPES:
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].animationType '{anim_s}' is not a Weapon.AnimationType",
                        {"animationType": anim_s})
                rec["animationType"] = anim_s
            for fld in ("ammo", "attackSound", "equipSound", "model", "materialSwap"):
                if r.get(fld) is not None:
                    rec[fld] = str(r[fld]).strip()
            for lst in ("keywords", "attachParentSlots"):
                v = r.get(lst)
                if v is not None:
                    if not isinstance(v, list):
                        raise Fo4McpError(
                            ErrorCode.INVALID_ARGUMENT,
                            f"spec.records[{i}].{lst} must be a list", {})
                    norm_l: list[str] = []
                    for j, kw in enumerate(v):
                        if not str(kw).strip():
                            raise Fo4McpError(
                                ErrorCode.INVALID_ARGUMENT,
                                f"spec.records[{i}].{lst}[{j}] must be a non-empty FormKey", {})
                        norm_l.append(str(kw).strip())
                    rec[lst] = norm_l
            ob = r.get("objectBounds")
            if ob is not None:
                if not isinstance(ob, list) or len(ob) != 6:
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].objectBounds must be [x1,y1,z1,x2,y2,z2]", {})
                try:
                    obi = [int(v) for v in ob]
                except (TypeError, ValueError):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].objectBounds must be 6 integers", {})
                if any(v < -32768 or v > 32767 for v in obi):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].objectBounds values must be Int16 (-32768..32767)", {})
                rec["objectBounds"] = obi
        # Faz 2: quest skeleton (Name handled above). The CLI validates the enum
        # names (questType/flags); stage/objective index ranges are checked here.
        elif rtype.lower() == "quest":
            if r.get("questType") is not None:
                rec["questType"] = str(r["questType"]).strip()
            flags = r.get("flags")
            if flags is not None:
                if not isinstance(flags, list):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].flags must be a list of flag names", {}
                    )
                rec["flags"] = [str(x).strip() for x in flags]
            for field, text_key in (("stages", "logEntry"), ("objectives", "text")):
                items = r.get(field)
                if items is None:
                    continue
                if not isinstance(items, list):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].{field} must be a list", {}
                    )
                norm_items: list[dict[str, Any]] = []
                for j, it in enumerate(items):
                    if not isinstance(it, dict):
                        raise Fo4McpError(
                            ErrorCode.INVALID_ARGUMENT,
                            f"spec.records[{i}].{field}[{j}] must be an object", {}
                        )
                    try:
                        idx = int(it["index"])
                    except (KeyError, TypeError, ValueError):
                        raise Fo4McpError(
                            ErrorCode.INVALID_ARGUMENT,
                            f"spec.records[{i}].{field}[{j}] needs an integer 'index'", {}
                        )
                    if not 0 <= idx <= 0xFFFF:
                        raise Fo4McpError(
                            ErrorCode.INVALID_ARGUMENT,
                            f"spec.records[{i}].{field}[{j}].index out of range (0..65535)",
                            {"index": idx},
                        )
                    entry: dict[str, Any] = {"index": idx}
                    if it.get(text_key) is not None:
                        entry[text_key] = str(it[text_key])
                    # Faz 2.2a: stages only — RunOnStart flag (INDX 0x02; the engine runs
                    # this stage's fragment when the quest starts). The CLI always emits a
                    # QSDT marker per log entry (mandatory; no flag needed here).
                    if field == "stages" and it.get("runOnStart"):
                        entry["runOnStart"] = True
                    # W2: objectives only — flags (QuestObjective.Flag) + QSTA targets
                    # [{aliasId, flags(Quest.TargetFlag), keyword? LCRT, conditions?}].
                    # The CLI does the authoritative flag-enum + keyword FormKey parse;
                    # target conditions reuse the shared condition builder.
                    if field == "objectives":
                        if it.get("flags") is not None:
                            if not isinstance(it["flags"], list):
                                raise Fo4McpError(
                                    ErrorCode.INVALID_ARGUMENT,
                                    f"spec.records[{i}].objectives[{j}].flags must be a list", {}
                                )
                            entry["flags"] = [str(x).strip() for x in it["flags"]]
                        tgts = it.get("targets")
                        if tgts is not None:
                            if not isinstance(tgts, list):
                                raise Fo4McpError(
                                    ErrorCode.INVALID_ARGUMENT,
                                    f"spec.records[{i}].objectives[{j}].targets must be a list", {}
                                )
                            norm_tgts: list[dict[str, Any]] = []
                            for k, tg in enumerate(tgts):
                                if not isinstance(tg, dict):
                                    raise Fo4McpError(
                                        ErrorCode.INVALID_ARGUMENT,
                                        f"spec.records[{i}].objectives[{j}].targets[{k}] must be an object", {}
                                    )
                                try:
                                    alias_id = int(tg["aliasId"])
                                except (KeyError, TypeError, ValueError):
                                    raise Fo4McpError(
                                        ErrorCode.INVALID_ARGUMENT,
                                        f"spec.records[{i}].objectives[{j}].targets[{k}] needs an integer 'aliasId'", {}
                                    )
                                tnorm: dict[str, Any] = {"aliasId": alias_id}
                                if tg.get("flags") is not None:
                                    if not isinstance(tg["flags"], list):
                                        raise Fo4McpError(
                                            ErrorCode.INVALID_ARGUMENT,
                                            f"spec.records[{i}].objectives[{j}].targets[{k}].flags must be a list", {}
                                        )
                                    tnorm["flags"] = [str(x).strip() for x in tg["flags"]]
                                if tg.get("keyword") is not None:
                                    tnorm["keyword"] = str(tg["keyword"]).strip()
                                if tg.get("conditions") is not None:
                                    tnorm["conditions"] = _norm_conditions(
                                        tg["conditions"],
                                        f"spec.records[{i}].objectives[{j}].targets[{k}].conditions",
                                    )
                                norm_tgts.append(tnorm)
                            entry["targets"] = norm_tgts
                    norm_items.append(entry)
                rec[field] = norm_items
            # Faz 2.1: quest-nested dialogue. Validate the topic -> response -> line
            # shape here; the CLI does the authoritative enum/FormKey parse (subtype/
            # category enums, speaker/emotion FormKeys) and mints the DIAL/INFO FormKeys.
            topics = r.get("topics")
            if topics is not None:
                if not isinstance(topics, list):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].topics must be a list", {}
                    )
                norm_topics: list[dict[str, Any]] = []
                for j, t in enumerate(topics):
                    tloc = f"spec.records[{i}].topics[{j}]"
                    if not isinstance(t, dict):
                        raise Fo4McpError(
                            ErrorCode.INVALID_ARGUMENT, f"{tloc} must be an object", {}
                        )
                    topic: dict[str, Any] = {}
                    if t.get("name") is not None:
                        topic["name"] = str(t["name"])
                    # Kerem-polish: "branch" links a topic to its owning DLBR so it surfaces.
                    for key in ("editorId", "subtype", "category", "branch"):
                        if t.get(key) is not None:
                            topic[key] = str(t[key]).strip()
                    resps = t.get("responses")
                    if resps is not None:
                        if not isinstance(resps, list):
                            raise Fo4McpError(
                                ErrorCode.INVALID_ARGUMENT,
                                f"{tloc}.responses must be a list", {}
                            )
                        norm_resps: list[dict[str, Any]] = []
                        for k, resp in enumerate(resps):
                            rloc = f"{tloc}.responses[{k}]"
                            if not isinstance(resp, dict):
                                raise Fo4McpError(
                                    ErrorCode.INVALID_ARGUMENT, f"{rloc} must be an object", {}
                                )
                            rentry: dict[str, Any] = {}
                            if resp.get("prompt") is not None:
                                rentry["prompt"] = str(resp["prompt"])
                            if resp.get("speaker") is not None:
                                rentry["speaker"] = str(resp["speaker"]).strip()
                            lines = resp.get("lines")
                            if lines is not None:
                                if not isinstance(lines, list):
                                    raise Fo4McpError(
                                        ErrorCode.INVALID_ARGUMENT,
                                        f"{rloc}.lines must be a list", {}
                                    )
                                norm_lines: list[dict[str, Any]] = []
                                for m, ln in enumerate(lines):
                                    lloc = f"{rloc}.lines[{m}]"
                                    if not isinstance(ln, dict):
                                        raise Fo4McpError(
                                            ErrorCode.INVALID_ARGUMENT, f"{lloc} must be an object", {}
                                        )
                                    lentry: dict[str, Any] = {}
                                    if ln.get("text") is not None:
                                        lentry["text"] = str(ln["text"])
                                    if ln.get("emotion") is not None:
                                        lentry["emotion"] = str(ln["emotion"]).strip()
                                    if ln.get("responseNumber") is not None:
                                        try:
                                            rn = int(ln["responseNumber"])
                                        except (TypeError, ValueError):
                                            raise Fo4McpError(
                                                ErrorCode.INVALID_ARGUMENT,
                                                f"{lloc}.responseNumber must be an integer", {}
                                            )
                                        if not 0 <= rn <= 255:
                                            raise Fo4McpError(
                                                ErrorCode.INVALID_ARGUMENT,
                                                f"{lloc}.responseNumber out of range (0..255)",
                                                {"responseNumber": rn},
                                            )
                                        lentry["responseNumber"] = rn
                                    norm_lines.append(lentry)
                                rentry["lines"] = norm_lines
                            # Faz 2.1b: INFO conditions gate when this response fires.
                            conds = resp.get("conditions")
                            if conds is not None:
                                rentry["conditions"] = _norm_conditions(
                                    conds, f"{rloc}.conditions"
                                )
                            # P0: script-free INFO -> owning-quest stage advance (SNAM SetParentQuestStage).
                            # {onBegin?, onEnd?}; a wheel pick sets the quest stage with no Papyrus.
                            sps = resp.get("setParentQuestStage")
                            if sps is not None:
                                if not isinstance(sps, dict):
                                    raise Fo4McpError(
                                        ErrorCode.INVALID_ARGUMENT,
                                        f"{rloc}.setParentQuestStage must be an object", {}
                                    )
                                sentry: dict[str, Any] = {}
                                for skey in ("onBegin", "onEnd"):
                                    if sps.get(skey) is not None:
                                        try:
                                            sv = int(sps[skey])
                                        except (TypeError, ValueError):
                                            raise Fo4McpError(
                                                ErrorCode.INVALID_ARGUMENT,
                                                f"{rloc}.setParentQuestStage.{skey} must be an integer", {}
                                            )
                                        if not -1 <= sv <= 32767:
                                            raise Fo4McpError(
                                                ErrorCode.INVALID_ARGUMENT,
                                                f"{rloc}.setParentQuestStage.{skey} out of range (-1..32767)",
                                                {skey: sv},
                                            )
                                        sentry[skey] = sv
                                if sentry:
                                    rentry["setParentQuestStage"] = sentry
                            # OS-04: pin the INFO FormKey so the TIF_<eid>_<8hex> fragment-script
                            # name stays stable across re-authoring (the CLI validates it is in the
                            # mod's own slot).
                            if resp.get("formKey") is not None:
                                rentry["formKey"] = str(resp["formKey"]).strip()
                            # OS-04: per-INFO TIF VMAD fragment — the line runs Papyrus
                            # (Fragment_Begin/Fragment_End). {scriptName, onBegin?, onEnd?, flags?,
                            # properties?}; at least one of onBegin/onEnd is required. Metadata only;
                            # the .pex is compiled separately via fo4_papyrus_build (like quest
                            # fragments). The CLI is authoritative on the VMAD model.
                            ifrag = resp.get("fragment")
                            if ifrag is not None:
                                ifloc = f"{rloc}.fragment"
                                if not isinstance(ifrag, dict):
                                    raise Fo4McpError(
                                        ErrorCode.INVALID_ARGUMENT,
                                        f"{ifloc} must be an object", {}
                                    )
                                ifscript = str(ifrag.get("scriptName", "")).strip()
                                if not ifscript:
                                    raise Fo4McpError(
                                        ErrorCode.INVALID_ARGUMENT,
                                        f"{ifloc} needs a 'scriptName'", {}
                                    )
                                if ifrag.get("onBegin") is None and ifrag.get("onEnd") is None:
                                    raise Fo4McpError(
                                        ErrorCode.INVALID_ARGUMENT,
                                        f"{ifloc} needs at least one of 'onBegin'/'onEnd'", {}
                                    )
                                ifentry: dict[str, Any] = {"scriptName": ifscript}
                                if ifrag.get("flags") is not None:
                                    ifentry["flags"] = str(ifrag["flags"]).strip()
                                if ifrag.get("onBegin") is not None:
                                    ifentry["onBegin"] = str(ifrag["onBegin"]).strip()
                                if ifrag.get("onEnd") is not None:
                                    ifentry["onEnd"] = str(ifrag["onEnd"]).strip()
                                ifprops = ifrag.get("properties")
                                if ifprops is not None:
                                    ifentry["properties"] = _norm_script_properties(
                                        ifprops, f"{ifloc}.properties"
                                    )
                                rentry["fragment"] = ifentry
                            norm_resps.append(rentry)
                        topic["responses"] = norm_resps
                    norm_topics.append(topic)
                rec["topics"] = norm_topics
            # Kerem-polish: DLBR dialogue branches — a bare DIAL/INFO never surfaces in the
            # dialogue wheel. A Player/TopLevel branch pointing at an entry topic is what makes
            # the topic appear when the player activates the NPC. The CLI validates the
            # category/flag enums + resolves startingTopic (in-spec editorId or FormKey).
            branches = r.get("branches")
            if branches is not None:
                if not isinstance(branches, list):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].branches must be a list", {}
                    )
                norm_branches: list[dict[str, Any]] = []
                for j, b in enumerate(branches):
                    bloc = f"spec.records[{i}].branches[{j}]"
                    if not isinstance(b, dict):
                        raise Fo4McpError(
                            ErrorCode.INVALID_ARGUMENT, f"{bloc} must be an object", {}
                        )
                    if not str(b.get("startingTopic") or "").strip():
                        raise Fo4McpError(
                            ErrorCode.INVALID_ARGUMENT,
                            f"{bloc}.startingTopic is required (the entry topic the branch surfaces)",
                            {},
                        )
                    branch: dict[str, Any] = {"startingTopic": str(b["startingTopic"]).strip()}
                    for key in ("editorId", "category"):
                        if b.get(key) is not None:
                            branch[key] = str(b[key]).strip()
                    bflags = b.get("flags")
                    if bflags is not None:
                        if not isinstance(bflags, list):
                            raise Fo4McpError(
                                ErrorCode.INVALID_ARGUMENT, f"{bloc}.flags must be a list", {}
                            )
                        branch["flags"] = [str(f).strip() for f in bflags]
                    norm_branches.append(branch)
                rec["branches"] = norm_branches
            # Faz 2.1c: quest aliases (QuestReferenceAlias cast slots, keyed by a
            # quest-local id). Validate shape here; the CLI validates the flag enums +
            # the forcedReference/uniqueActor FormKeys, reuses the INFO condition
            # builder for find-matching-ref conditions, and auto-sequences alias ids
            # by list order when omitted.
            aliases = r.get("aliases")
            if aliases is not None:
                if not isinstance(aliases, list):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].aliases must be a list", {}
                    )
                norm_aliases: list[dict[str, Any]] = []
                for j, a in enumerate(aliases):
                    aloc = f"spec.records[{i}].aliases[{j}]"
                    if not isinstance(a, dict):
                        raise Fo4McpError(
                            ErrorCode.INVALID_ARGUMENT, f"{aloc} must be an object", {}
                        )
                    aentry: dict[str, Any] = {}
                    if a.get("id") is not None:
                        try:
                            aid = int(a["id"])
                        except (TypeError, ValueError):
                            raise Fo4McpError(
                                ErrorCode.INVALID_ARGUMENT,
                                f"{aloc}.id must be an integer", {}
                            )
                        if not 0 <= aid <= 0xFFFFFFFF:
                            raise Fo4McpError(
                                ErrorCode.INVALID_ARGUMENT,
                                f"{aloc}.id out of range (0..4294967295)", {"id": aid}
                            )
                        aentry["id"] = aid
                    if a.get("name") is not None:
                        aentry["name"] = str(a["name"])
                    afl = a.get("flags")
                    if afl is not None:
                        if not isinstance(afl, list):
                            raise Fo4McpError(
                                ErrorCode.INVALID_ARGUMENT,
                                f"{aloc}.flags must be a list of flag names", {}
                            )
                        aentry["flags"] = [str(x).strip() for x in afl]
                    for key in ("forcedReference", "uniqueActor"):
                        if a.get(key) is not None:
                            aentry[key] = str(a[key]).strip()
                    aconds = a.get("conditions")
                    if aconds is not None:
                        aentry["conditions"] = _norm_conditions(
                            aconds, f"{aloc}.conditions"
                        )
                    # W6.7: location/collection alias + event-fill. Pass-through;
                    # the CLI validates alias type, the FormKeys, the 4-char event
                    # signature, and the mutual exclusivity of fill modes.
                    if a.get("type") is not None:
                        atype = str(a["type"]).strip().lower()
                        if atype == "collection":
                            # Mutagen v0.53.1 can't round-trip a multi-member
                            # QuestCollectionAlias (it duplicates the last member on
                            # reopen) — blocked to avoid silently corrupting the QUST.
                            raise Fo4McpError(
                                ErrorCode.INVALID_ARGUMENT,
                                f"{aloc}.type 'collection' is not supported "
                                "(Mutagen can't round-trip collection aliases); use "
                                "'reference' or 'location'", {})
                        if atype not in ("reference", "location"):
                            raise Fo4McpError(
                                ErrorCode.INVALID_ARGUMENT,
                                f"{aloc}.type must be 'reference' or 'location'",
                                {"type": atype})
                        aentry["type"] = atype
                    for key in ("specificLocation", "externalAliasQuest", "fromEvent"):
                        if a.get(key) is not None:
                            aentry[key] = str(a[key]).strip()
                    for key in ("referenceAliasLocation", "externalAliasId"):
                        if a.get(key) is not None:
                            try:
                                aentry[key] = int(a[key])
                            except (TypeError, ValueError):
                                raise Fo4McpError(
                                    ErrorCode.INVALID_ARGUMENT,
                                    f"{aloc}.{key} must be an integer alias id", {})
                    norm_aliases.append(aentry)
                rec["aliases"] = norm_aliases
            # Faz 2.1d: Papyrus VMAD binding. Validate the script -> property shape
            # here; the CLI attaches them to the QuestAdapter, picks the ScriptProperty
            # subclass per `type`, validates the ScriptEntry.Flag enum + object-property
            # FormKeys (auto-adding masters), and writes the FO4 VMAD header (v6/objfmt2).
            scripts = r.get("scripts")
            if scripts is not None:
                if not isinstance(scripts, list):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].scripts must be a list", {}
                    )
                norm_scripts = [
                    _norm_script_entry(s, f"spec.records[{i}].scripts[{j}]")
                    for j, s in enumerate(scripts)
                ]
                rec["scripts"] = norm_scripts
            # Faz 2.1f: quest stage script fragments. A single QF fragment script
            # (scriptName + optional flags/properties -> QuestAdapter.Script) plus
            # per-stage entries (stages[] -> QuestAdapter.Fragments) that fire a
            # Fragment_* function when the quest reaches that stage. Metadata only;
            # the .pex bytecode is compiled separately via fo4_papyrus_build. The CLI
            # is authoritative on the model (Unknown2 etc.) + property value types.
            fragments = r.get("fragments")
            if fragments is not None:
                floc = f"spec.records[{i}].fragments"
                if not isinstance(fragments, dict):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT, f"{floc} must be an object", {}
                    )
                fscript = str(fragments.get("scriptName", "")).strip()
                if not fscript:
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT, f"{floc} needs a 'scriptName'", {}
                    )
                fentry: dict[str, Any] = {"scriptName": fscript}
                if fragments.get("flags") is not None:
                    fentry["flags"] = str(fragments["flags"]).strip()
                fprops = fragments.get("properties")
                if fprops is not None:
                    fentry["properties"] = _norm_script_properties(
                        fprops, f"{floc}.properties"
                    )
                fstages = fragments.get("stages")
                if fstages is not None:
                    if not isinstance(fstages, list):
                        raise Fo4McpError(
                            ErrorCode.INVALID_ARGUMENT, f"{floc}.stages must be a list", {}
                        )
                    norm_fstages: list[dict[str, Any]] = []
                    for k, st in enumerate(fstages):
                        stloc = f"{floc}.stages[{k}]"
                        if not isinstance(st, dict):
                            raise Fo4McpError(
                                ErrorCode.INVALID_ARGUMENT, f"{stloc} must be an object", {}
                            )
                        try:
                            stage = int(st["stage"])
                        except (KeyError, TypeError, ValueError):
                            raise Fo4McpError(
                                ErrorCode.INVALID_ARGUMENT,
                                f"{stloc} needs an integer 'stage'", {}
                            )
                        if not 0 <= stage <= 0xFFFF:
                            raise Fo4McpError(
                                ErrorCode.INVALID_ARGUMENT,
                                f"{stloc}.stage out of range (0..65535)", {"stage": stage}
                            )
                        fragname = str(st.get("fragmentName", "")).strip()
                        if not fragname:
                            raise Fo4McpError(
                                ErrorCode.INVALID_ARGUMENT,
                                f"{stloc} needs a 'fragmentName'", {}
                            )
                        stentry: dict[str, Any] = {"stage": stage, "fragmentName": fragname}
                        if st.get("stageIndex") is not None:
                            try:
                                stentry["stageIndex"] = int(st["stageIndex"])
                            except (TypeError, ValueError):
                                raise Fo4McpError(
                                    ErrorCode.INVALID_ARGUMENT,
                                    f"{stloc}.stageIndex must be an integer", {}
                                )
                        norm_fstages.append(stentry)
                    fentry["stages"] = norm_fstages
                rec["fragments"] = fentry
            # Faz 2.1g: quest ALIAS script fragments. Each entry binds one quest alias
            # (by ID) to its fragment script(s) (OnBegin/OnEnd) -> QuestAdapter.Aliases.
            # The CLI sets the binding Property (alias ID + this quest) + Version 6 /
            # ObjectFormat 2. Metadata only — the .pex is compiled separately via
            # fo4_papyrus_build, like stage fragments. Scripts reuse the 2.1d shape.
            alias_fragments = r.get("aliasFragments")
            if alias_fragments is not None:
                aloc = f"spec.records[{i}].aliasFragments"
                if not isinstance(alias_fragments, list):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT, f"{aloc} must be a list", {}
                    )
                norm_afs: list[dict[str, Any]] = []
                for j, af in enumerate(alias_fragments):
                    afloc = f"{aloc}[{j}]"
                    if not isinstance(af, dict):
                        raise Fo4McpError(
                            ErrorCode.INVALID_ARGUMENT, f"{afloc} must be an object", {}
                        )
                    try:
                        alias_id = int(af["alias"])
                    except (KeyError, TypeError, ValueError):
                        raise Fo4McpError(
                            ErrorCode.INVALID_ARGUMENT,
                            f"{afloc} needs an integer 'alias'", {}
                        )
                    if not 0 <= alias_id <= 0x7FFF:
                        raise Fo4McpError(
                            ErrorCode.INVALID_ARGUMENT,
                            f"{afloc}.alias out of range (0..32767)", {"alias": alias_id}
                        )
                    af_scripts = af.get("scripts")
                    if not isinstance(af_scripts, list) or not af_scripts:
                        raise Fo4McpError(
                            ErrorCode.INVALID_ARGUMENT,
                            f"{afloc} needs a non-empty 'scripts' list", {}
                        )
                    norm_afs.append({
                        "alias": alias_id,
                        "scripts": [
                            _norm_script_entry(s, f"{afloc}.scripts[{k}]")
                            for k, s in enumerate(af_scripts)
                        ],
                    })
                rec["aliasFragments"] = norm_afs
            # Faz 2.1e: SCEN scenes. Validate the scene -> actors/phases/actions
            # shape here; the CLI mints each Scene (back-linked to the quest), maps
            # actors by alias ID, builds phase conditions (reusing 2.1b), and wraps
            # each action in SceneActionTypicalType (resolving its topic by editorId
            # against this spec's topics, or by FormKey).
            scenes = r.get("scenes")
            if scenes is not None:
                if not isinstance(scenes, list):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].scenes must be a list", {}
                    )
                norm_scenes: list[dict[str, Any]] = []
                for j, sc in enumerate(scenes):
                    scloc = f"spec.records[{i}].scenes[{j}]"
                    if not isinstance(sc, dict):
                        raise Fo4McpError(
                            ErrorCode.INVALID_ARGUMENT, f"{scloc} must be an object", {}
                        )
                    eid = str(sc.get("editorId", "")).strip()
                    if not eid:
                        raise Fo4McpError(
                            ErrorCode.INVALID_ARGUMENT, f"{scloc} needs an 'editorId'", {}
                        )
                    scentry: dict[str, Any] = {"editorId": eid}
                    if sc.get("flags") is not None:
                        if not isinstance(sc["flags"], list):
                            raise Fo4McpError(
                                ErrorCode.INVALID_ARGUMENT, f"{scloc}.flags must be a list", {}
                            )
                        scentry["flags"] = [str(f).strip() for f in sc["flags"]]
                    actors = sc.get("actors")
                    if actors is not None:
                        if not isinstance(actors, list):
                            raise Fo4McpError(
                                ErrorCode.INVALID_ARGUMENT, f"{scloc}.actors must be a list", {}
                            )
                        norm_actors: list[dict[str, Any]] = []
                        for k, a in enumerate(actors):
                            if not isinstance(a, dict):
                                raise Fo4McpError(
                                    ErrorCode.INVALID_ARGUMENT,
                                    f"{scloc}.actors[{k}] must be an object", {}
                                )
                            try:
                                aid = int(a["id"])
                            except (KeyError, TypeError, ValueError):
                                raise Fo4McpError(
                                    ErrorCode.INVALID_ARGUMENT,
                                    f"{scloc}.actors[{k}] needs an integer 'id' (the quest alias ID)",
                                    {},
                                )
                            if aid < 0:
                                raise Fo4McpError(
                                    ErrorCode.INVALID_ARGUMENT,
                                    f"{scloc}.actors[{k}].id must be >= 0", {"id": aid}
                                )
                            norm_actors.append({"id": aid})
                        scentry["actors"] = norm_actors
                    phases = sc.get("phases")
                    if phases is not None:
                        if not isinstance(phases, list):
                            raise Fo4McpError(
                                ErrorCode.INVALID_ARGUMENT, f"{scloc}.phases must be a list", {}
                            )
                        norm_phases: list[dict[str, Any]] = []
                        for k, ph in enumerate(phases):
                            phloc = f"{scloc}.phases[{k}]"
                            if not isinstance(ph, dict):
                                raise Fo4McpError(
                                    ErrorCode.INVALID_ARGUMENT, f"{phloc} must be an object", {}
                                )
                            phentry: dict[str, Any] = {}
                            if ph.get("name") is not None:
                                phentry["name"] = str(ph["name"])
                            if ph.get("startConditions") is not None:
                                phentry["startConditions"] = _norm_conditions(
                                    ph["startConditions"], f"{phloc}.startConditions"
                                )
                            if ph.get("completionConditions") is not None:
                                phentry["completionConditions"] = _norm_conditions(
                                    ph["completionConditions"], f"{phloc}.completionConditions"
                                )
                            norm_phases.append(phentry)
                        scentry["phases"] = norm_phases
                    actions = sc.get("actions")
                    if actions is not None:
                        if not isinstance(actions, list):
                            raise Fo4McpError(
                                ErrorCode.INVALID_ARGUMENT, f"{scloc}.actions must be a list", {}
                            )
                        norm_actions: list[dict[str, Any]] = []
                        for k, ac in enumerate(actions):
                            acloc = f"{scloc}.actions[{k}]"
                            if not isinstance(ac, dict):
                                raise Fo4McpError(
                                    ErrorCode.INVALID_ARGUMENT, f"{acloc} must be an object", {}
                                )
                            atype = str(ac.get("type", "")).strip()
                            if atype.lower() not in _SCENE_ACTION_TYPES:
                                raise Fo4McpError(
                                    ErrorCode.INVALID_ARGUMENT,
                                    f"{acloc}.type must be one of {list(_SCENE_ACTION_TYPES)}",
                                    {"type": ac.get("type")},
                                )
                            acentry: dict[str, Any] = {"type": atype}
                            if ac.get("actor") is not None:
                                try:
                                    acentry["actor"] = int(ac["actor"])
                                except (TypeError, ValueError):
                                    raise Fo4McpError(
                                        ErrorCode.INVALID_ARGUMENT,
                                        f"{acloc}.actor must be an integer (an actor's alias ID)", {}
                                    )
                            if ac.get("topic") is not None:
                                acentry["topic"] = str(ac["topic"]).strip()
                            for pk in ("startPhase", "endPhase"):
                                if ac.get(pk) is not None:
                                    try:
                                        acentry[pk] = int(ac[pk])
                                    except (TypeError, ValueError):
                                        raise Fo4McpError(
                                            ErrorCode.INVALID_ARGUMENT,
                                            f"{acloc}.{pk} must be an integer", {}
                                        )
                            if ac.get("flags") is not None:
                                if not isinstance(ac["flags"], list):
                                    raise Fo4McpError(
                                        ErrorCode.INVALID_ARGUMENT,
                                        f"{acloc}.flags must be a list", {}
                                    )
                                acentry["flags"] = [str(f).strip() for f in ac["flags"]]
                            norm_actions.append(acentry)
                        scentry["actions"] = norm_actions
                    norm_scenes.append(scentry)
                rec["scenes"] = norm_scenes
        # W1.5 glue records (Faz 3). Keyword is bare (editorId + shared name); the
        # others add their own minimal fields. The CLI does the authoritative
        # construction (abstract-Global subclass dispatch, FormKey parse via TryKey,
        # int/short range) — Python validates shape and passes through.
        elif rtype.lower() == "keyword":
            # Bare KYWD: editorId-only (+ shared name handled above). No keyword-
            # specific MVP fields; the elif exists so the type is accepted and
            # future fields (color/type) have a home.
            pass
        elif rtype.lower() == "formlist":
            items = r.get("items")
            if items is not None:
                if not isinstance(items, list):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].items must be a list", {}
                    )
                norm_fl_items: list[str] = []
                for j, it in enumerate(items):
                    if not str(it).strip():
                        raise Fo4McpError(
                            ErrorCode.INVALID_ARGUMENT,
                            f"spec.records[{i}].items[{j}] must be a non-empty FormKey",
                            {},
                        )
                    norm_fl_items.append(str(it).strip())
                rec["items"] = norm_fl_items
        elif rtype.lower() == "message":
            # text -> Description (body). "title" is the message-friendly alias for
            # Name and OVERWRITES the shared name set above (title wins — intended).
            if r.get("text") is not None:
                rec["text"] = str(r["text"])
            if r.get("title") is not None:
                rec["name"] = str(r["title"])
            # OS-11: flags (Message.Flag — MessageBox is needed for buttons to render) +
            # menuButtons (choice dialogs; each {text required, conditions? -> _norm_conditions}).
            flags = r.get("flags")
            if flags is not None:
                if not isinstance(flags, list):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].flags must be a list of flag names", {})
                rec["flags"] = [str(x).strip() for x in flags]
            btns = r.get("menuButtons")
            if btns is not None:
                if not isinstance(btns, list):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].menuButtons must be a list", {})
                norm_btns: list[dict[str, Any]] = []
                for j, b in enumerate(btns):
                    if not isinstance(b, dict) or not str(b.get("text", "")).strip():
                        raise Fo4McpError(
                            ErrorCode.INVALID_ARGUMENT,
                            f"spec.records[{i}].menuButtons[{j}] needs a 'text'", {})
                    nb: dict[str, Any] = {"text": str(b["text"])}
                    if b.get("conditions") is not None:
                        nb["conditions"] = _norm_conditions(
                            b["conditions"], f"spec.records[{i}].menuButtons[{j}].conditions")
                    norm_btns.append(nb)
                rec["menuButtons"] = norm_btns
        elif rtype.lower() in ("book", "misc"):
            # BOOK/note OR MISC clutter (coupon): value/weight reuse the shared item ranges;
            # keywords is a FormKey list; model = world-model nif (+ optional materialSwap).
            # BOOK adds text -> BookText (readable body) + name -> title; MISC has no text/note
            # UI and gets picked straight into inventory (the pickupable-coupon record type).
            if r.get("text") is not None:
                rec["text"] = str(r["text"])
            if r.get("value") is not None:
                try:
                    bval = int(r["value"])
                except (TypeError, ValueError):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].value must be an integer", {})
                if bval < 0:
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].value must be >= 0", {"value": bval})
                rec["value"] = bval
            if r.get("weight") is not None:
                try:
                    bwt = float(r["weight"])
                except (TypeError, ValueError):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].weight must be a number", {})
                if bwt < 0:
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].weight must be >= 0", {"weight": bwt})
                rec["weight"] = bwt
            kws = r.get("keywords")
            if kws is not None:
                if not isinstance(kws, list):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].keywords must be a list", {})
                rec["keywords"] = [str(k).strip() for k in kws]
            # Visual: model = world-model nif path (MODL); materialSwap = MSWP FormKey that
            # retextures it. Both optional — without them the note is still readable.
            if r.get("model") is not None:
                rec["model"] = str(r["model"]).strip()
            if r.get("materialSwap") is not None:
                rec["materialSwap"] = str(r["materialSwap"]).strip()
            # OBND: object bounds [x1,y1,z1,x2,y2,z2] (Int16). A model-bearing MISC needs a
            # non-zero box or FO4 can't frame the inventory preview / Inspect (the coupon no-show
            # bug). Optional — the CLI defaults to PrewarMoney's flat-card box when omitted.
            ob = r.get("objectBounds")
            if ob is not None:
                if not isinstance(ob, list) or len(ob) != 6:
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].objectBounds must be [x1,y1,z1,x2,y2,z2]", {})
                try:
                    obi = [int(v) for v in ob]
                except (TypeError, ValueError):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].objectBounds must be 6 integers", {})
                if any(v < -32768 or v > 32767 for v in obi):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].objectBounds values must be Int16 (-32768..32767)", {})
                rec["objectBounds"] = obi
            # PTRN: Preview Transform — FormKey of a TRNS that frames the model in the Pip-Boy/
            # Inspect preview (a SEPARATE render path from the world model). Without it a flat
            # item default-frames edge-on -> blank preview. e.g. "1CF028:Fallout4.esm" (OverdueBook).
            pt = r.get("previewTransform")
            if pt is not None:
                pts = str(pt).strip()
                if pts:
                    rec["previewTransform"] = pts
        elif rtype.lower() == "materialswap":
            # MSWP: a retexture map. substitutions = [{original, replacement}] .bgsm paths
            # (Data-relative, "Materials\...\x.bgsm"). The CLI does the authoritative add.
            subs = r.get("substitutions")
            if not isinstance(subs, list) or not subs:
                raise Fo4McpError(
                    ErrorCode.INVALID_ARGUMENT,
                    f"spec.records[{i}] (materialSwap) needs a non-empty 'substitutions' list", {})
            norm_subs: list[dict[str, Any]] = []
            for j, s in enumerate(subs):
                if not isinstance(s, dict):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].substitutions[{j}] must be an object", {})
                orig = str(s.get("original", "")).strip()
                repl = str(s.get("replacement", "")).strip()
                if not orig or not repl:
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].substitutions[{j}] needs both 'original' and 'replacement'",
                        {})
                norm_subs.append({"original": orig, "replacement": repl})
            rec["substitutions"] = norm_subs
        elif rtype.lower() == "global":
            # globalType selects the concrete subclass (float|int|short; default
            # float); globalValue is the Data scalar. The CLI does the authoritative
            # construct + per-subclass int/short range check.
            gtype = r.get("globalType")
            if gtype is not None:
                gtype_s = str(gtype).strip().lower()
                if gtype_s not in ("float", "int", "short"):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].globalType '{gtype}' invalid (float|int|short)",
                        {"globalType": gtype},
                    )
                rec["globalType"] = gtype_s
            if r.get("globalValue") is not None:
                try:
                    rec["globalValue"] = float(r["globalValue"])
                except (TypeError, ValueError):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].globalValue must be a number", {}
                    )
        # W3.5: FACT faction. flags (reuses the quest "flags" key, list of Faction.FactionFlag
        # names) + interfactionRelations [{faction FormKey, reaction CombatReaction name}].
        # The CLI does the authoritative enum parse (flag/reaction) + FormKey parse.
        elif rtype.lower() == "faction":
            flags = r.get("flags")
            if flags is not None:
                if not isinstance(flags, list):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].flags must be a list of flag names", {}
                    )
                rec["flags"] = [str(x).strip() for x in flags]
            rels = r.get("interfactionRelations")
            if rels is not None:
                if not isinstance(rels, list):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].interfactionRelations must be a list", {}
                    )
                norm_rels: list[dict[str, Any]] = []
                for j, rel in enumerate(rels):
                    if not isinstance(rel, dict) or not str(rel.get("faction", "")).strip():
                        raise Fo4McpError(
                            ErrorCode.INVALID_ARGUMENT,
                            f"spec.records[{i}].interfactionRelations[{j}] needs a 'faction' FormKey",
                            {},
                        )
                    if not str(rel.get("reaction", "")).strip():
                        raise Fo4McpError(
                            ErrorCode.INVALID_ARGUMENT,
                            f"spec.records[{i}].interfactionRelations[{j}] needs a 'reaction'",
                            {},
                        )
                    norm_rels.append({
                        "faction": str(rel["faction"]).strip(),
                        "reaction": str(rel["reaction"]).strip(),
                    })
                rec["interfactionRelations"] = norm_rels
            # OS-11: ranks (member titles — gendered; a single 'title' fills both, 'titleFemale'
            # overrides) + vendorValues (merchant data: trade hours/radius + 3 buy/sell bools).
            ranks = r.get("ranks")
            if ranks is not None:
                if not isinstance(ranks, list):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].ranks must be a list", {})
                norm_ranks: list[dict[str, Any]] = []
                for j, rk in enumerate(ranks):
                    if not isinstance(rk, dict):
                        raise Fo4McpError(
                            ErrorCode.INVALID_ARGUMENT,
                            f"spec.records[{i}].ranks[{j}] must be an object", {})
                    nr: dict[str, Any] = {}
                    if rk.get("number") is not None:
                        try:
                            num = int(rk["number"])
                        except (TypeError, ValueError):
                            raise Fo4McpError(
                                ErrorCode.INVALID_ARGUMENT,
                                f"spec.records[{i}].ranks[{j}].number must be an integer", {})
                        if not 0 <= num <= 4294967295:
                            raise Fo4McpError(
                                ErrorCode.INVALID_ARGUMENT,
                                f"spec.records[{i}].ranks[{j}].number out of range (0..4294967295)",
                                {"number": num})
                        nr["number"] = num
                    if rk.get("title") is not None:
                        nr["title"] = str(rk["title"])
                    if rk.get("titleFemale") is not None:
                        nr["titleFemale"] = str(rk["titleFemale"])
                    if rk.get("insignia") is not None:
                        nr["insignia"] = str(rk["insignia"]).strip()
                    norm_ranks.append(nr)
                rec["ranks"] = norm_ranks
            vv = r.get("vendorValues")
            if vv is not None:
                if not isinstance(vv, dict):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].vendorValues must be an object", {})
                norm_vv: dict[str, Any] = {}
                for hf in ("startHour", "endHour", "radius"):
                    if vv.get(hf) is not None:
                        try:
                            hv = int(vv[hf])
                        except (TypeError, ValueError):
                            raise Fo4McpError(
                                ErrorCode.INVALID_ARGUMENT,
                                f"spec.records[{i}].vendorValues.{hf} must be an integer", {})
                        if not 0 <= hv <= 65535:
                            raise Fo4McpError(
                                ErrorCode.INVALID_ARGUMENT,
                                f"spec.records[{i}].vendorValues.{hf} out of range (0..65535)",
                                {"value": hv})
                        norm_vv[hf] = hv
                for bf in ("buysStolen", "buysNonStolen", "buyEverything"):
                    if vv.get(bf) is not None:
                        norm_vv[bf] = bool(vv[bf])
                # only author a VendorValues subrecord when something was actually
                # set — an empty/all-None dict must not turn a non-vendor faction
                # into a degenerate all-zero vendor.
                if norm_vv:
                    rec["vendorValues"] = norm_vv
        # W3d/W3e: LVLN/LVLI leveled lists. flags (reuses the quest "flags" key; CLI does the
        # authoritative LeveledNpc.Flag/LeveledItem.Flag parse — note bit 4 is CalculateAll for
        # LVLN vs UseAll for LVLI) + entries [{reference FormKey, level/count int 1..32767}].
        # chanceNone/Global/MaxCount/FilterKeywordChances deferred (§2 — refinements).
        elif rtype.lower() in ("levelednpc", "leveleditem", "leveleditemoverride"):
            flags = r.get("flags")
            if flags is not None:
                if not isinstance(flags, list):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].flags must be a list of flag names", {}
                    )
                rec["flags"] = [str(x).strip() for x in flags]
            entries = r.get("entries")
            if entries is not None:
                if not isinstance(entries, list):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].entries must be a list", {}
                    )
                norm_entries: list[dict[str, Any]] = []
                for j, en in enumerate(entries):
                    if not isinstance(en, dict) or not str(en.get("reference", "")).strip():
                        raise Fo4McpError(
                            ErrorCode.INVALID_ARGUMENT,
                            f"spec.records[{i}].entries[{j}] needs a 'reference' FormKey", {}
                        )
                    try:
                        level = int(en.get("level", 1))
                        count = int(en.get("count", 1))
                    except (TypeError, ValueError):
                        raise Fo4McpError(
                            ErrorCode.INVALID_ARGUMENT,
                            f"spec.records[{i}].entries[{j}] level/count must be integers", {}
                        )
                    if not 1 <= level <= 32767:
                        raise Fo4McpError(
                            ErrorCode.INVALID_ARGUMENT,
                            f"spec.records[{i}].entries[{j}].level out of range (1..32767)", {"level": level}
                        )
                    if not 1 <= count <= 32767:
                        raise Fo4McpError(
                            ErrorCode.INVALID_ARGUMENT,
                            f"spec.records[{i}].entries[{j}].count out of range (1..32767)", {"count": count}
                        )
                    norm_entries.append({
                        "reference": str(en["reference"]).strip(), "level": level, "count": count,
                    })
                rec["entries"] = norm_entries
            # OS-11: chanceNone (loot tuning — % chance the list yields nothing; 0-100 int).
            if r.get("chanceNone") is not None:
                try:
                    cn = int(r["chanceNone"])
                except (TypeError, ValueError):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].chanceNone must be an integer", {})
                if not 0 <= cn <= 100:
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].chanceNone out of range (0..100)", {"chanceNone": cn})
                rec["chanceNone"] = cn
            # W3e-inject: LeveledItemOverride grafts the entries above onto an EXISTING (master)
            # LVLI. Needs sourcePlugin (holds the target list) + target (the LVLI FormKey). ADDITIVE
            # unless clearExisting wipes the vanilla entries. The CLI DeepCopies it as an override.
            if rtype.lower() == "leveleditemoverride":
                sp = str(r.get("sourcePlugin", "")).strip()
                if not sp:
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}] (leveledItemOverride) needs 'sourcePlugin'", {})
                rec["sourcePlugin"] = sp
                tgt = str(r.get("target", "")).strip()
                if not tgt:
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}] (leveledItemOverride) needs 'target' (LVLI FormKey)", {})
                rec["target"] = tgt
                if r.get("clearExisting") is not None:
                    rec["clearExisting"] = bool(r["clearExisting"])
        elif rtype.lower() == "cell":
            # W4 interior CELL + nested placed refs (REFR/ACHR). FormLink scalars are
            # light-validated here; the CLI does the authoritative FormKey parse + master
            # auto-add, computes the block/subblock from the cell's FormID, and nests the
            # refs in Cell.Temporary (or .Persistent when persistent=true).
            for fld in ("lightingTemplate", "location", "encounterZone",
                        "imageSpace", "acousticSpace", "music"):
                if r.get(fld) is not None:
                    rec[fld] = str(r[fld]).strip()
            if r.get("waterHeight") is not None:
                try:
                    rec["waterHeight"] = float(r["waterHeight"])
                except (TypeError, ValueError):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].waterHeight must be a number", {})
            for fld in ("placedObjects", "placedNpcs"):
                if r.get(fld) is not None:
                    rec[fld] = _norm_placed_refs(r[fld], f"spec.records[{i}].{fld}")
            # A-disk: optional isolated-interior navmesh (auto-triangulated floor). The CLI
            # generates the vertex grid + edge-link adjacency; here we shape-check the floor box.
            nv = r.get("navmesh")
            if nv is not None:
                if not isinstance(nv, dict):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].navmesh must be an object", {})
                floor = nv.get("floor")
                if (not isinstance(floor, (list, tuple)) or len(floor) != 4):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].navmesh.floor must be [minX,minY,maxX,maxY]", {})
                norm_nv: dict[str, Any] = {"floor": [float(v) for v in floor]}
                if nv.get("z") is not None:
                    norm_nv["z"] = float(nv["z"])
                for fld in ("divisionsX", "divisionsY"):
                    if nv.get(fld) is not None:
                        norm_nv[fld] = int(nv[fld])
                if nv.get("navi") is not None:
                    norm_nv["navi"] = bool(nv["navi"])  # A-in-game RE toggle: also author a NAVI entry
                rec["navmesh"] = norm_nv
        elif rtype.lower() == "celloverride":
            # W5: add refs to an existing master cell. Needs sourcePlugin (the plugin holding
            # the cell) + the target cell FormKey. The CLI DeepCopies it as an override.
            sp = str(r.get("sourcePlugin", "")).strip()
            if not sp:
                raise Fo4McpError(
                    ErrorCode.INVALID_ARGUMENT,
                    f"spec.records[{i}] (cellOverride) needs 'sourcePlugin'", {})
            rec["sourcePlugin"] = sp
            tc = str(r.get("cell", "")).strip()
            if not tc:
                raise Fo4McpError(
                    ErrorCode.INVALID_ARGUMENT,
                    f"spec.records[{i}] (cellOverride) needs 'cell' (target FormKey)", {})
            rec["cell"] = tc
            if r.get("clearExisting") is not None:
                rec["clearExisting"] = bool(r["clearExisting"])
            for fld in ("placedObjects", "placedNpcs"):
                if r.get(fld) is not None:
                    rec[fld] = _norm_placed_refs(r[fld], f"spec.records[{i}].{fld}")
        elif rtype.lower() == "smqn":
            # W6 Story Manager Quest Node. parent/previousSibling FormLinks; flags reuse the
            # shared key (AStoryManagerNode.Flag); conditions reuse the INFO/alias builder;
            # quests = [{quest FormKey, hoursUntilReset?}].
            for fld in ("parent", "previousSibling"):
                if r.get(fld) is not None:
                    rec[fld] = str(r[fld]).strip()
            flags = r.get("flags")
            if flags is not None:
                if not isinstance(flags, list):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].flags must be a list of flag names", {})
                rec["flags"] = [str(x).strip() for x in flags]
            for fld in ("maxConcurrentQuests", "maxNumQuestsToRun"):
                if r.get(fld) is not None:
                    try:
                        v = int(r[fld])
                    except (TypeError, ValueError):
                        raise Fo4McpError(
                            ErrorCode.INVALID_ARGUMENT,
                            f"spec.records[{i}].{fld} must be an integer", {})
                    if v < 0:
                        raise Fo4McpError(
                            ErrorCode.INVALID_ARGUMENT, f"spec.records[{i}].{fld} must be >= 0", {})
                    rec[fld] = v
            if r.get("hoursUntilReset") is not None:
                try:
                    rec["hoursUntilReset"] = float(r["hoursUntilReset"])
                except (TypeError, ValueError):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].hoursUntilReset must be a number", {})
            if r.get("conditions") is not None:
                rec["conditions"] = _norm_conditions(
                    r["conditions"], f"spec.records[{i}].conditions")
            quests = r.get("quests")
            if quests is not None:
                if not isinstance(quests, list):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT, f"spec.records[{i}].quests must be a list", {})
                norm_q: list[dict[str, Any]] = []
                for j, sq in enumerate(quests):
                    if not isinstance(sq, dict) or not str(sq.get("quest", "")).strip():
                        raise Fo4McpError(
                            ErrorCode.INVALID_ARGUMENT,
                            f"spec.records[{i}].quests[{j}] needs a 'quest' FormKey", {})
                    qe: dict[str, Any] = {"quest": str(sq["quest"]).strip()}
                    if sq.get("hoursUntilReset") is not None:
                        try:
                            qe["hoursUntilReset"] = float(sq["hoursUntilReset"])
                        except (TypeError, ValueError):
                            raise Fo4McpError(
                                ErrorCode.INVALID_ARGUMENT,
                                f"spec.records[{i}].quests[{j}].hoursUntilReset must be a number", {})
                    norm_q.append(qe)
                rec["quests"] = norm_q
        elif rtype.lower() in ("activator", "location"):
            # W6.5 ACTI / W8 LCTN — name (generic) + keywords; location also parentLocation.
            if rtype.lower() == "location" and r.get("parentLocation") is not None:
                rec["parentLocation"] = str(r["parentLocation"]).strip()
            kws = r.get("keywords")
            if kws is not None:
                if not isinstance(kws, list):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT, f"spec.records[{i}].keywords must be a list", {})
                rec["keywords"] = [str(k).strip() for k in kws]
            # W6.5-gap: ACTI control-script VMAD binding (same script-entry shape as quests).
            if rtype.lower() == "activator":
                acti_scripts = r.get("scripts")
                if acti_scripts is not None:
                    if not isinstance(acti_scripts, list):
                        raise Fo4McpError(
                            ErrorCode.INVALID_ARGUMENT,
                            f"spec.records[{i}].scripts must be a list", {})
                    rec["scripts"] = [
                        _norm_script_entry(s, f"spec.records[{i}].scripts[{j}]")
                        for j, s in enumerate(acti_scripts)
                    ]
        elif rtype.lower() == "outfit":
            # OS-14 OTFT — items = a bare FormLink list of worn pieces (ARMO/LVLI/NPC_).
            items = r.get("items")
            if items is not None:
                if not isinstance(items, list):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].items must be a list", {})
                norm_otft: list[str] = []
                for j, it in enumerate(items):
                    if not str(it).strip():
                        raise Fo4McpError(
                            ErrorCode.INVALID_ARGUMENT,
                            f"spec.records[{i}].items[{j}] must be a non-empty FormKey", {})
                    norm_otft.append(str(it).strip())
                rec["items"] = norm_otft
        elif rtype.lower() in ("static", "door", "light", "container",
                               "ingestible", "ingredient"):
            # OS-02 — common world base records. They share model/materialSwap/keywords/flags;
            # LIGH/ALCH add value/weight/radius; CONT adds inventory; ALCH/INGR add effects.
            # The CLI does the authoritative FormKey/enum parse + master auto-add.
            for fld in ("model", "materialSwap"):
                if r.get(fld) is not None:
                    rec[fld] = str(r[fld]).strip()
            kws = r.get("keywords")
            if kws is not None:
                if not isinstance(kws, list):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].keywords must be a list", {})
                rec["keywords"] = [str(k).strip() for k in kws]
            flags = r.get("flags")
            if flags is not None:
                if not isinstance(flags, list):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].flags must be a list of flag names", {})
                rec["flags"] = [str(x).strip() for x in flags]
            if r.get("value") is not None:
                try:
                    bval = int(r["value"])
                except (TypeError, ValueError):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].value must be an integer", {})
                if bval < 0:
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].value must be >= 0", {"value": bval})
                rec["value"] = bval
            if r.get("weight") is not None:
                try:
                    bwt = float(r["weight"])
                except (TypeError, ValueError):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].weight must be a number", {})
                if bwt < 0:
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].weight must be >= 0", {"weight": bwt})
                rec["weight"] = bwt
            ob = r.get("objectBounds")
            if ob is not None:
                if not isinstance(ob, list) or len(ob) != 6:
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].objectBounds must be [x1,y1,z1,x2,y2,z2]", {})
                try:
                    obi = [int(v) for v in ob]
                except (TypeError, ValueError):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].objectBounds must be 6 integers", {})
                if any(v < -32768 or v > 32767 for v in obi):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].objectBounds values must be Int16 (-32768..32767)", {})
                rec["objectBounds"] = obi
            # LIGH radius (UInt32)
            if rtype.lower() == "light" and r.get("radius") is not None:
                try:
                    rad = int(r["radius"])
                except (TypeError, ValueError):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].radius must be an integer", {})
                if rad < 0:
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].radius must be >= 0", {"radius": rad})
                rec["radius"] = rad
            # CONT inventory ([{item, count>=0}]) — reuses the NPC inventory shape.
            if rtype.lower() == "container":
                inv = r.get("inventory") if r.get("inventory") is not None else r.get("items")
                if inv is not None:
                    if not isinstance(inv, list):
                        raise Fo4McpError(
                            ErrorCode.INVALID_ARGUMENT,
                            f"spec.records[{i}].inventory must be a list", {})
                    norm_inv: list[dict[str, Any]] = []
                    for j, it in enumerate(inv):
                        if not isinstance(it, dict) or not str(it.get("item", "")).strip():
                            raise Fo4McpError(
                                ErrorCode.INVALID_ARGUMENT,
                                f"spec.records[{i}].inventory[{j}] needs an 'item' FormKey", {})
                        try:
                            count = int(it.get("count", 1))
                        except (TypeError, ValueError):
                            raise Fo4McpError(
                                ErrorCode.INVALID_ARGUMENT,
                                f"spec.records[{i}].inventory[{j}].count must be an integer", {})
                        if count < 0:
                            raise Fo4McpError(
                                ErrorCode.INVALID_ARGUMENT,
                                f"spec.records[{i}].inventory[{j}].count must be >= 0",
                                {"count": count})
                        norm_inv.append({"item": str(it["item"]).strip(), "count": count})
                    rec["inventory"] = norm_inv
            # ALCH/INGR effects ([{baseEffect required, magnitude, area, duration}]).
            if rtype.lower() in ("ingestible", "ingredient"):
                effs = r.get("effects")
                if effs is not None:
                    if not isinstance(effs, list):
                        raise Fo4McpError(
                            ErrorCode.INVALID_ARGUMENT,
                            f"spec.records[{i}].effects must be a list", {})
                    norm_effs: list[dict[str, Any]] = []
                    for j, ef in enumerate(effs):
                        if not isinstance(ef, dict) or not str(ef.get("baseEffect", "")).strip():
                            raise Fo4McpError(
                                ErrorCode.INVALID_ARGUMENT,
                                f"spec.records[{i}].effects[{j}] needs a 'baseEffect' FormKey", {})
                        try:
                            mag = float(ef.get("magnitude", 0))
                            area = int(ef.get("area", 0))
                            dur = int(ef.get("duration", 0))
                        except (TypeError, ValueError):
                            raise Fo4McpError(
                                ErrorCode.INVALID_ARGUMENT,
                                f"spec.records[{i}].effects[{j}] magnitude/area/duration must be numbers",
                                {})
                        norm_effs.append({
                            "baseEffect": str(ef["baseEffect"]).strip(),
                            "magnitude": mag, "area": area, "duration": dur,
                        })
                    rec["effects"] = norm_effs
        elif rtype.lower() in ("constructibleobject", "cobj"):
            # OS-08 COBJ recipe — createdObject + workbenchKeyword required; components
            # [{component, count 0..65535}]; categories = KYWD FormLink list; conditions reuse
            # _norm_conditions (CLI BuildCondition is authoritative). createdObjectCount >= 0.
            co = str(r.get("createdObject", "")).strip()
            if not co:
                raise Fo4McpError(
                    ErrorCode.INVALID_ARGUMENT,
                    f"spec.records[{i}] (constructibleObject) needs 'createdObject' (output FormKey)",
                    {})
            rec["createdObject"] = co
            wb = str(r.get("workbenchKeyword", "")).strip()
            if not wb:
                raise Fo4McpError(
                    ErrorCode.INVALID_ARGUMENT,
                    f"spec.records[{i}] (constructibleObject) needs 'workbenchKeyword'", {})
            rec["workbenchKeyword"] = wb
            if r.get("createdObjectCount") is not None:
                try:
                    coc = int(r["createdObjectCount"])
                except (TypeError, ValueError):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].createdObjectCount must be an integer", {})
                if not 0 <= coc <= 65535:
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].createdObjectCount out of range (0..65535)",
                        {"createdObjectCount": coc})
                rec["createdObjectCount"] = coc
            if r.get("menuArtObject") is not None:
                rec["menuArtObject"] = str(r["menuArtObject"]).strip()
            comps = r.get("components")
            if comps is not None:
                if not isinstance(comps, list):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].components must be a list", {})
                norm_comps: list[dict[str, Any]] = []
                for j, c in enumerate(comps):
                    if not isinstance(c, dict) or not str(c.get("component", "")).strip():
                        raise Fo4McpError(
                            ErrorCode.INVALID_ARGUMENT,
                            f"spec.records[{i}].components[{j}] needs a 'component' FormKey", {})
                    try:
                        cnt = int(c.get("count", 1))
                    except (TypeError, ValueError):
                        raise Fo4McpError(
                            ErrorCode.INVALID_ARGUMENT,
                            f"spec.records[{i}].components[{j}].count must be an integer", {})
                    if not 1 <= cnt <= 65535:
                        raise Fo4McpError(
                            ErrorCode.INVALID_ARGUMENT,
                            f"spec.records[{i}].components[{j}].count out of range (1..65535)",
                            {"count": cnt})
                    norm_comps.append({"component": str(c["component"]).strip(), "count": cnt})
                rec["components"] = norm_comps
            cats = r.get("categories")
            if cats is not None:
                if not isinstance(cats, list):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].categories must be a list", {})
                norm_cats: list[str] = []
                for j, cat in enumerate(cats):
                    if not str(cat).strip():
                        raise Fo4McpError(
                            ErrorCode.INVALID_ARGUMENT,
                            f"spec.records[{i}].categories[{j}] must be a non-empty FormKey", {})
                    norm_cats.append(str(cat).strip())
                rec["categories"] = norm_cats
            if r.get("conditions") is not None:
                rec["conditions"] = _norm_conditions(
                    r["conditions"], f"spec.records[{i}].conditions")
        elif rtype.lower() == "encounterzone":
            # W8 ECZN — flags + location/owner FormLinks + min/max level + rank (0..255).
            flags = r.get("flags")
            if flags is not None:
                if not isinstance(flags, list):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT, f"spec.records[{i}].flags must be a list", {})
                rec["flags"] = [str(x).strip() for x in flags]
            for fld in ("location", "owner"):
                if r.get(fld) is not None:
                    rec[fld] = str(r[fld]).strip()
            for fld in ("minLevel", "maxLevel", "rank"):
                if r.get(fld) is not None:
                    try:
                        v = int(r[fld])
                    except (TypeError, ValueError):
                        raise Fo4McpError(
                            ErrorCode.INVALID_ARGUMENT,
                            f"spec.records[{i}].{fld} must be an integer", {})
                    if not 0 <= v <= 255:
                        raise Fo4McpError(
                            ErrorCode.INVALID_ARGUMENT,
                            f"spec.records[{i}].{fld} out of range (0..255)", {"value": v})
                    rec[fld] = v
        elif rtype.lower() == "package":
            # W7 AI package — template-bind MVP (PackageTemplate + type + flags + conditions +
            # ownerQuest + combatStyle). The Data input-map is the deferred research gate.
            for fld in ("packageTemplate", "packageType", "ownerQuest", "combatStyle"):
                if r.get(fld) is not None:
                    rec[fld] = str(r[fld]).strip()
            flags = r.get("flags")
            if flags is not None:
                if not isinstance(flags, list):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT, f"spec.records[{i}].flags must be a list", {})
                rec["flags"] = [str(x).strip() for x in flags]
            if r.get("conditions") is not None:
                rec["conditions"] = _norm_conditions(
                    r["conditions"], f"spec.records[{i}].conditions")
            # W7-Data: one location data-input (Travel "Place to Travel" / Sandbox
            # "Location"). The slot index is resolved by name against the live template
            # writer-side, so only the target value + radius travel in the spec.
            dl = r.get("dataLocation")
            if dl is not None:
                if not isinstance(dl, dict):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].dataLocation must be an object", {})
                if not rec.get("packageTemplate"):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].dataLocation requires packageTemplate "
                        "(the input slot is defined by the template)", {})
                target = dl.get("target")
                if not target:
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].dataLocation.target is required "
                        "(FormKey of the reference/cell/keyword)", {})
                ttype = str(dl.get("targetType", "reference")).strip().lower()
                if ttype not in ("reference", "cell", "keyword"):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].dataLocation.targetType must be "
                        "reference|cell|keyword", {"value": ttype})
                try:
                    radius = int(dl.get("radius", 0))
                except (TypeError, ValueError):
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].dataLocation.radius must be an integer", {})
                if radius < 0:
                    raise Fo4McpError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"spec.records[{i}].dataLocation.radius must be >= 0",
                        {"value": radius})
                norm_dl: dict[str, Any] = {
                    "targetType": ttype,
                    "target": str(target).strip(),
                    "radius": radius,
                }
                if dl.get("input") is not None:
                    norm_dl["input"] = str(dl["input"]).strip()
                rec["dataLocation"] = norm_dl
        # locationRefType: bare (editorId only) — no extra fields.
        norm_records.append(rec)

    # --- resolve + gate output (fail-closed before any existence check) ---
    out = Path(output_plugin)
    if not out.is_absolute():
        out = (cfg.repo_root / out).resolve()
    disposition = check_write(out, cfg.repo_root)  # raises PathForbiddenError on DENY
    if out.suffix.lower() not in (".esp", ".esm", ".esl"):
        raise Fo4McpError(
            ErrorCode.INVALID_ARGUMENT,
            f"output_plugin must end in .esp/.esm/.esl: {out.name}",
            {"output_plugin": str(out)},
        )

    # --- require the writer binary (unlike inspect_record, no fallback exists) ---
    cli = _mutagen_cli_binary(cfg, manifest)
    if cli is None:
        raise Fo4McpError(
            ErrorCode.TOOL_BINARY_MISSING,
            "mutagen-cli writer not built (tools/mutagen-cli/) — required for fo4_create_record",
            {"tool": "mutagen-cli"},
        )

    # --- existing target without confirm: refuse, do not write ---
    if out.exists() and not confirm_overwrite:
        return ok({
            "ok":                 True,
            "wrote":              False,
            "overwrite_required": True,
            "output_plugin":      str(out),
            "output_disposition": disposition.value,
            "existing_sha256":    _sha256_file(out),
            "records":            norm_records,
            "message": (
                "target plugin exists; not overwritten. Call again with "
                "confirm_overwrite=true to back up (.bak) + replace."
            ),
        })

    # --- write path (new target, or confirmed overwrite) ---
    out.parent.mkdir(parents=True, exist_ok=True)
    backup_path: str | None = None
    if out.exists() and confirm_overwrite:
        backup = out.with_suffix(out.suffix + ".bak")
        shutil.copy2(out, backup)
        backup_path = str(backup)

    # W7-Data: packages with a location data-input resolve their slot index by name
    # against the live template, which lives in the FO4 Data dir — pass it through.
    needs_masters = any(rec.get("dataLocation") for rec in norm_records)
    masters_args: list[str] = []
    if needs_masters:
        if cfg.fo4_install_dir is None:
            raise Fo4McpError(
                ErrorCode.INVALID_ARGUMENT,
                "dataLocation requires the FO4 install (template lookup); "
                "FO4_INSTALL_DIR not set and auto-detect failed", {})
        masters_dir = cfg.fo4_install_dir / "Data"
        if not masters_dir.is_dir():
            raise Fo4McpError(
                ErrorCode.INVALID_ARGUMENT,
                f"FO4 Data dir not found for template lookup: {masters_dir}", {})
        masters_args = ["--masters-dir", str(masters_dir)]

    with tempfile.TemporaryDirectory() as td:
        spec_file = Path(td) / "spec.json"
        spec_file.write_text(json.dumps({"records": norm_records}), encoding="utf-8")
        result = run_tool(
            cli,
            ["create", "--spec", str(spec_file), "--out", str(out), *masters_args],
            timeout=cfg.subprocess_timeout,
            env_extra=_spriggit_env(),  # ensure the net9 runtime is discoverable
        )

    if not result.ok or not out.exists():
        raise Fo4McpError(
            ErrorCode.SUBPROCESS_FAILED,
            "mutagen-cli failed to write the plugin",
            {"exit_code": result.exit_code, "stderr_tail": result.stderr[-1000:]},
        )

    created = norm_records
    masters: list[str] = []
    if result.stdout.strip():
        try:
            parsed = json.loads(result.stdout)
            created = parsed.get("records", norm_records)
            masters = parsed.get("masters", [])
        except json.JSONDecodeError:
            pass

    return ok({
        "wrote":              True,
        "output_plugin":      str(out),
        "output_disposition": disposition.value,
        "backup_path":        backup_path,
        "record_count":       len(created),
        "records":            created,
        "masters":            masters,
        "mvp_note": (
            "structurally-valid plugin; authors NPC (Race/Class/factions + W3b "
            "full-field: voice/combatStyle/defaultOutfit/attackRace/skin + AI "
            "personality enums [aggression/confidence/assistance/responsibility/"
            "mood] + keywords/inventory[CNTO]/perks + W3c template-chain "
            "[defaultTemplate + useTemplateActors flags]), Armor "
            "(keywords/value/weight/armorRating/biped slots), and Quest skeletons "
            "(type/flags/stages/objectives [W2: + flags + QSTA targets: alias-pointed "
            "compass markers with target flags/LCRT keyword/conditions]) with quest-nested dialogue topics "
            "(DIAL->INFO->lines), INFO conditions (any Condition.Function), quest "
            "aliases (QuestReferenceAlias: flags/ForcedReference/UniqueActor/"
            "conditions), Papyrus VMAD script binding (named scripts + typed "
            "properties), SCEN scenes (actors by alias ID + phases with "
            "conditions + dialogue-action timeline referencing topics), and quest "
            "stage script fragments (QF fragment script + per-stage Fragment_* "
            "entries) + quest alias fragments (per-alias OnBegin/OnEnd scripts "
            "bound by alias ID into QuestAdapter.Aliases); fragment metadata only, "
            "compile the .pex via fo4_papyrus_build. Glue records: Keyword (bare KYWD), "
            "FormList (FLST FormLink items), Message (MESG text/title), Global "
            "(GLOB float|int|short + value), Faction (FACT flags + interfaction "
            "relations), and leveled lists (W3d/W3e: LeveledNpc/LeveledItem — "
            "entries[reference,level,count] + calc flags). World content (W4): "
            "interior Cell (IsInteriorCell + LightingTemplate/location/imageSpace/... + "
            "nested placed refs — REFR placedObjects + ACHR placedNpcs with base/"
            "position/rotation/scale, into Temporary or Persistent; block/subblock "
            "auto-derived from the FormID). CellOverride (W5): add refs to an existing "
            "master cell (DeepCopy override, see fo4_place_into_cell). Story Manager (W6): "
            "smqn (StoryManagerQuestNode — event-driven quest auto-start: parent/"
            "previousSibling SM-tree links + flags + conditions + quests). World base "
            "records (W6.5/W8): Activator (ACTI name + keywords; model/VMAD deferred), "
            "Location (LCTN name/parentLocation/keywords), LocationRefType (LCRT bare), "
            "EncounterZone (ECZN flags/location/owner/min-max level/rank). AI packages "
            "(W7): Package (PACK template-bind — PackageTemplate + type + flags + "
            "conditions + ownerQuest; W7-Data: one location data-input "
            "[Travel 'Place to Travel' / Sandbox 'Location'] — slot index resolved by "
            "name against the live template, target = reference|cell|keyword + radius) "
            "+ NPC 'packages' binding. FormLinks auto-add their masters."
        ),
        "stderr_tail":        result.stderr[-500:],
    })


# ---- Tool 3b: world-placement into existing cells (Faz 3 / W5) ---------------

def _resolve_source_plugin(cfg: Config, cell: str, source_plugin: str | None) -> Path:
    """Resolve the plugin holding the target cell. Explicit source_plugin wins; otherwise
    derive the master from the cell FormKey ('<6hex>:<master>') and look in the FO4 install
    Data dir (read-only data source)."""
    if source_plugin:
        p = Path(source_plugin)
        if not p.is_absolute():
            p = (cfg.repo_root / p).resolve()
        return p
    if ":" not in cell:
        raise Fo4McpError(
            ErrorCode.INVALID_ARGUMENT,
            "cell must be a FormKey '<6hex>:<master>' (or pass source_plugin)",
            {"cell": cell})
    master = cell.split(":", 1)[1].strip()
    if cfg.fo4_install_dir is None:
        raise Fo4McpError(
            ErrorCode.INVALID_ARGUMENT,
            f"cannot locate '{master}': FO4 install dir unknown; pass source_plugin",
            {"cell": cell})
    return cfg.fo4_install_dir / "Data" / master


def _cell_info(cfg: Config, manifest: Manifest, source: Path, cell: str) -> dict[str, Any]:
    """Run the mutagen-cli cell-info verb -> precombine/previs signals for one cell."""
    import json
    cli = _mutagen_cli_binary(cfg, manifest)
    if cli is None:
        raise Fo4McpError(
            ErrorCode.TOOL_BINARY_MISSING,
            "mutagen-cli not built (tools/mutagen-cli/) — required for cell previs check",
            {"tool": "mutagen-cli"})
    if not source.exists():
        raise Fo4McpError(
            ErrorCode.INVALID_ARGUMENT, f"source plugin not found: {source}", {"source": str(source)})
    # the cell-info verb takes a bare FormID or EditorID (the query-path contract); a full
    # FormKey '<6hex>:<master>' must be split to its object-id part (':' breaks NormFormId).
    record = cell.split(":", 1)[0] if ":" in cell else cell
    result = run_tool(
        cli, ["cell-info", "--plugin", str(source), "--record", record],
        timeout=cfg.subprocess_timeout, env_extra=_spriggit_env())
    if not result.stdout.strip():
        raise Fo4McpError(
            ErrorCode.SUBPROCESS_FAILED, "mutagen-cli cell-info failed",
            {"exit_code": result.exit_code, "stderr_tail": result.stderr[-500:]})
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        raise Fo4McpError(
            ErrorCode.SUBPROCESS_OUTPUT_UNPARSEABLE, "cell-info emitted no JSON",
            {"stdout_tail": result.stdout[-500:]})


def fo4_check_previs_safety(
    cfg: Config, manifest: Manifest, cell: str, source_plugin: str | None = None
) -> dict[str, Any]:
    """Read-only previs/precombine safety check for editing a cell (Faz 3 / W5 BLOCKING
    precondition).

    Adding or moving a placed reference in a cell that carries precombined geometry / previs
    invalidates them: the engine keeps using the stale precombined meshes, so a new ref may be
    invisible or occluded and the cell can show visual holes — until previs is REGENERATED in
    the Creation Kit (a GPU/CK-bound human step, batched in W12). Returns the precombine/previs
    signals + a verdict so fo4_place_into_cell can gate on it. safe=True only when the cell has
    neither precombines nor previs (editing won't break visuals). Read-only."""
    source = _resolve_source_plugin(cfg, cell, source_plugin)
    info = _cell_info(cfg, manifest, source, cell)
    if not info.get("found"):
        raise Fo4McpError(
            ErrorCode.INVALID_ARGUMENT, f"cell '{cell}' not found in {source.name}", {"cell": cell})
    has_pre = bool(info.get("hasPrecombines"))
    has_pvs = bool(info.get("hasPrevis"))
    safe = not (has_pre or has_pvs)
    verdict = (
        "SAFE — no precombines/previs; placing loose refs won't break visuals"
        if safe else
        "UNSAFE — cell is precombined/previs'd; placing refs needs a CK previs regen "
        "(W12) or the new refs may be invisible + the cell may show holes")
    return ok({
        "found":          True,
        "cell":           info.get("formKey", cell),
        "editorId":       info.get("editorId"),
        "source_plugin":  str(source),
        "hasPrecombines": has_pre,
        "hasPrevis":      has_pvs,
        "safe":           safe,
        "verdict":        verdict,
        "signals": {k: info.get(k) for k in (
            "combinedMeshes", "combinedMeshReferences", "preCombinedFilesTimestamp",
            "preVisFilesTimestamp", "persistentCount", "temporaryCount", "interior")},
    })


def _cell_navmesh_list(cfg: Config, manifest: Manifest, plugin: Path) -> list[dict[str, Any]]:
    """Run the mutagen-cli cell-navmesh-list verb -> per-cell navmesh coverage for every
    cell in the plugin (interior + worldspace-parented exterior)."""
    import json
    cli = _mutagen_cli_binary(cfg, manifest)
    if cli is None:
        raise Fo4McpError(
            ErrorCode.TOOL_BINARY_MISSING,
            "mutagen-cli not built (tools/mutagen-cli/) — required for navmesh handoff",
            {"tool": "mutagen-cli"})
    result = run_tool(
        cli, ["cell-navmesh-list", "--plugin", str(plugin)],
        timeout=cfg.subprocess_timeout, env_extra=_spriggit_env())
    if not result.stdout.strip():
        raise Fo4McpError(
            ErrorCode.SUBPROCESS_FAILED, "mutagen-cli cell-navmesh-list failed",
            {"exit_code": result.exit_code, "stderr_tail": result.stderr[-500:]})
    try:
        return json.loads(result.stdout).get("cells", [])
    except json.JSONDecodeError:
        raise Fo4McpError(
            ErrorCode.SUBPROCESS_OUTPUT_UNPARSEABLE, "cell-navmesh-list emitted no JSON",
            {"stdout_tail": result.stdout[-500:]})


def _dialogue_dump(
    cfg: Config, manifest: Manifest, plugin: Path, quest: str
) -> dict[str, Any]:
    """Run the mutagen-cli dialogue-dump verb -> a quest's player-dialogue wiring
    (DLBR + DIAL + INFO) re-read from the on-disk binary: per-INFO setStageOnBegin/
    setStageOnEnd (SNAM), the TIF VMAD fragment subtree, link/scene fields, and each
    condition's correctly-rendered params (OS-13). Read-only; the round-trip seam the
    dialogue tests assert against. Mirrors _cell_navmesh_list."""
    import json
    cli = _mutagen_cli_binary(cfg, manifest)
    if cli is None:
        raise Fo4McpError(
            ErrorCode.TOOL_BINARY_MISSING,
            "mutagen-cli not built (tools/mutagen-cli/) — required for dialogue-dump",
            {"tool": "mutagen-cli"})
    result = run_tool(
        cli, ["dialogue-dump", "--plugin", str(plugin), "--quest", quest],
        timeout=cfg.subprocess_timeout, env_extra=_spriggit_env())
    if not result.stdout.strip():
        raise Fo4McpError(
            ErrorCode.SUBPROCESS_FAILED, "mutagen-cli dialogue-dump failed",
            {"exit_code": result.exit_code, "stderr_tail": result.stderr[-500:]})
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        raise Fo4McpError(
            ErrorCode.SUBPROCESS_OUTPUT_UNPARSEABLE, "dialogue-dump emitted no JSON",
            {"stdout_tail": result.stdout[-500:]})


def fo4_navmesh_handoff(cfg: Config, manifest: Manifest, plugin: str) -> dict[str, Any]:
    """Read-only per-cell navmesh checklist for the CK-handoff (Faz 3 / W12 support tool).

    Walks every cell in the plugin and classifies each for navmesh status. The Mutagen-vs-CK
    boundary for navmesh was reclassified on 2026-06-21 (A-in-game PASS): an isolated INTERIOR
    cell's navmesh IS Mutagen-authorable and in-game-pathable (NAVM flattened cover-grid + a
    000FF1 NAVI override; an NPC walks on it, adversarial-proven). EXTERIOR/worldspace navmesh
    (the 23-mesh neighbour stitch) and combat-cover remain CK-gated.

    Per cell the verdict is:
      * interior + navmesh authored        -> OK (in-game-valid via the writer); WARN if no NAVI
        coverage (an authored navmesh without a NAVI MapInfo can't be pathed — re-author with
        navmesh:{...}, which now also writes the NAVI override).
      * interior + NO navmesh               -> WARN, agent-authorable (add navmesh:{floor,divisions}
        to the cell spec; NOT a CK task anymore).
      * exterior/worldspace cell            -> ERROR, CK-gated (generate navmesh + stitch in the CK;
        the writer never authors exterior NAVM/NAVI — neighbour-mesh corruption + crash risk).

    Returns a findings list + a CK checklist of only the cells that genuinely need the Creation
    Kit, so the human CK session is scoped. Read-only; authors nothing."""
    plugin_path = Path(plugin)
    if not plugin_path.is_absolute():
        plugin_path = (cfg.repo_root / plugin_path).resolve()
    if not plugin_path.exists():
        raise Fo4McpError(
            ErrorCode.PATH_NOT_FOUND, f"plugin not found: {plugin_path}", {"plugin": str(plugin_path)})

    cells = _cell_navmesh_list(cfg, manifest, plugin_path)
    findings: list[dict[str, Any]] = []
    ck_checklist: list[dict[str, Any]] = []
    for c in cells:
        interior = bool(c.get("interior"))
        nm = int(c.get("navmeshCount") or 0)
        has_navi = bool(c.get("hasNavi"))
        base = {"formKey": c.get("cell"), "editorId": c.get("editorId")}
        if not interior:
            findings.append({**base, "level": "error", "rule": "exterior_navmesh_ck_gated",
                "message": f"exterior cell (worldspace {c.get('worldspaceParent')}) — navmesh + "
                "neighbour stitch is CK-gated; the writer never authors exterior NAVM/NAVI"})
            ck_checklist.append({**base, "task": "generate + stitch exterior navmesh in the CK",
                "worldspaceParent": c.get("worldspaceParent")})
        elif nm == 0:
            findings.append({**base, "level": "warning", "rule": "interior_navmesh_missing",
                "message": "interior cell has no navmesh — agent-authorable (add "
                "navmesh:{floor,divisions} to the cell spec; NOT a CK task)"})
        elif not has_navi:
            findings.append({**base, "level": "warning", "rule": "navmesh_without_navi",
                "message": "interior navmesh authored but no NAVI MapInfo covers it — re-author "
                "with the current writer (navmesh:{...} now also writes the 000FF1 NAVI override) "
                "or the actor can't path on it"})
        else:
            findings.append({**base, "level": "ok", "rule": "interior_navmesh_ingame_valid",
                "message": "interior navmesh authored + NAVI coverage present (Mutagen-authored, "
                "in-game-pathable)"})

    error_count = sum(1 for f in findings if f["level"] == "error")
    warning_count = sum(1 for f in findings if f["level"] == "warning")
    verdict = ("ck-required" if error_count else
               "agent-authorable-gaps" if warning_count else
               "clean")
    return ok({
        "plugin":        str(plugin_path),
        "cell_count":    len(cells),
        "findings":      findings,
        "error_count":   error_count,
        "warning_count": warning_count,
        "ck_checklist":  ck_checklist,
        "verdict":       verdict,
    })


def _voice_handoff_list(
    cfg: Config, manifest: Manifest, plugin: Path
) -> list[dict[str, Any]]:
    """Run the mutagen-cli voice-handoff verb -> one entry per dialogue response LINE
    (quest-nested DIAL->INFO->line) with its subtitle, speaker, resolved voice type, and the
    canonical .fuz path. Passes the FO4 Data dir as --masters-dir so a vanilla speaker's voice
    type resolves to its folder name."""
    import json
    cli = _mutagen_cli_binary(cfg, manifest)
    if cli is None:
        raise Fo4McpError(
            ErrorCode.TOOL_BINARY_MISSING,
            "mutagen-cli not built (tools/mutagen-cli/) — required for voice handoff",
            {"tool": "mutagen-cli"})
    args = ["voice-handoff", "--plugin", str(plugin)]
    if cfg.fo4_install_dir is not None and (cfg.fo4_install_dir / "Data").is_dir():
        args += ["--masters-dir", str(cfg.fo4_install_dir / "Data")]
    result = run_tool(cli, args, timeout=cfg.subprocess_timeout, env_extra=_spriggit_env())
    if not result.stdout.strip():
        raise Fo4McpError(
            ErrorCode.SUBPROCESS_FAILED, "mutagen-cli voice-handoff failed",
            {"exit_code": result.exit_code, "stderr_tail": result.stderr[-500:]})
    try:
        return json.loads(result.stdout).get("lines", [])
    except json.JSONDecodeError:
        raise Fo4McpError(
            ErrorCode.SUBPROCESS_OUTPUT_UNPARSEABLE, "voice-handoff emitted no JSON",
            {"stdout_tail": result.stdout[-500:]})


def fo4_voice_handoff(
    cfg: Config, manifest: Manifest, plugin: str, audio_root: str | None = None
) -> dict[str, Any]:
    """Read-only voice/lip checklist for the human voice-acting handoff (Faz 3 / W9 support tool).

    Recording voice (.fuz) is an audio/human-gated step the agent cannot perform; this tool scopes
    it. It walks every dialogue response LINE in the plugin (quest-nested DIAL->INFO->line) and, for
    each, reports the subtitle text, the speaker, the resolved voice type, and the canonical on-disk
    path the .fuz must land at:

        Sound/Voice/<plugin>/<VoiceTypeEditorID>/<INFO-FormID-8hex>_<ResponseNumber>.fuz

    The .lip lip-sync is packed INSIDE the .fuz (FUZE container), so one .fuz per line is the whole
    deliverable. The path embeds the INFO FormID, so run this AFTER FormID-lock (W12). Per line:
      * .fuz present under audio_root          -> OK
      * voice type unresolved (no speaker / speaker not loadable) -> WARN (folder unknown; set the
        INFO speaker + give the NPC a VoiceType, and pass the FO4 install so it resolves)
      * .fuz missing                           -> WARN, needs recording (in the human/TTS step)

    audio_root defaults to the plugin's own directory (the loose-file layout a modder builds against).
    Returns a per-line findings list + a recording checklist of only the lines still missing a .fuz.
    Read-only; records nothing."""
    plugin_path = Path(plugin)
    if not plugin_path.is_absolute():
        plugin_path = (cfg.repo_root / plugin_path).resolve()
    if not plugin_path.exists():
        raise Fo4McpError(
            ErrorCode.PATH_NOT_FOUND, f"plugin not found: {plugin_path}",
            {"plugin": str(plugin_path)})
    root = Path(audio_root) if audio_root else plugin_path.parent
    if not root.is_absolute():
        root = (cfg.repo_root / root).resolve()

    lines = _voice_handoff_list(cfg, manifest, plugin_path)
    findings: list[dict[str, Any]] = []
    recording_checklist: list[dict[str, Any]] = []
    for ln in lines:
        fuz = ln.get("fuzPath") or ""
        base = {
            "info": ln.get("info"), "responseNumber": ln.get("responseNumber"),
            "text": ln.get("text"), "speaker": ln.get("speaker"),
            "voiceType": ln.get("voiceType"), "fuzPath": fuz,
        }
        if not ln.get("voiceTypeResolved"):
            findings.append({**base, "level": "warning", "rule": "voice_type_unresolved",
                "message": "voice-type folder unknown (no speaker, or speaker NPC/VoiceType not "
                "loadable) — set the INFO speaker + give the NPC a VoiceType; the .fuz folder "
                "can't be determined until then"})
            recording_checklist.append({**base, "task": "resolve voice type + record .fuz"})
            continue
        exists = (root / fuz).is_file()
        if exists:
            findings.append({**base, "level": "ok", "rule": "voice_line_present",
                "message": "recorded .fuz present"})
        else:
            findings.append({**base, "level": "warning", "rule": "voice_line_missing",
                "message": "no recorded .fuz — needs the human voice/TTS step "
                "(record line, FUZE-pack .lip+.xwm into the .fuz at this path)"})
            recording_checklist.append({**base, "task": "record + FUZE-pack .fuz"})

    line_count = len(lines)
    warning_count = sum(1 for f in findings if f["level"] == "warning")
    verdict = ("no-dialogue" if line_count == 0 else
               "voice-incomplete" if warning_count else
               "voice-complete")
    return ok({
        "plugin":              str(plugin_path),
        "audio_root":          str(root),
        "line_count":          line_count,
        "findings":            findings,
        "warning_count":       warning_count,
        "recording_checklist": recording_checklist,
        "verdict":             verdict,
    })


def fo4_release_preflight(cfg: Config, manifest: Manifest, plugin: str) -> dict[str, Any]:
    """Read-only ship-readiness preflight for a plugin (Faz 3 / W12 support tool).

    Composes the existing read-only advisors into ONE verdict so a release is checked in a single
    call before the (user-gated) CK finalize + BA2 pack + FOMOD steps. Each sub-check degrades to a
    warning if its backend is unavailable rather than hard-failing the whole preflight. Aggregates:
      * format/ESL    — fo4_check_esl_eligibility verdict (ESM-flag vs ESL-eligible vs needs-compaction)
      * navmesh       — fo4_navmesh_handoff roll-up (CK-required exterior cells vs agent gaps)
      * previs-impact — per-cell precombine/previs presence (new loose cells are fine; overrides
                        into precombined cells need a CK previs regen)
      * voice/lip     — fo4_voice_handoff roll-up (dialogue lines still needing a recorded .fuz)

    Returns sections + a flat findings list + an aggregate `verdict`:
      ship-blocked (an error: needs CK / compaction) > review (warnings) > ship-ready (clean).
    Read-only — performs no flag flip, no compaction, no pack. Those remain user-gated."""
    plugin_path = Path(plugin)
    if not plugin_path.is_absolute():
        plugin_path = (cfg.repo_root / plugin_path).resolve()
    if not plugin_path.exists():
        raise Fo4McpError(
            ErrorCode.PATH_NOT_FOUND, f"plugin not found: {plugin_path}", {"plugin": str(plugin_path)})

    findings: list[dict[str, Any]] = []
    sections: dict[str, Any] = {}

    # --- format / ESL eligibility ---
    try:
        elig = fo4_check_esl_eligibility(cfg, manifest, str(plugin_path))["data"]
        sections["eligibility"] = elig
        v = elig.get("verdict")
        if v == "esl-needs-compaction":
            findings.append({"level": "error", "rule": "esl_needs_compaction", "section": "format",
                "message": "new-record ObjectIDs exceed the 0xFFF ESL ceiling — compact FormIDs "
                "(user-gated) before ESL-flagging"})
        elif v == "esm-flag":
            findings.append({"level": "warning", "rule": "esm_flag_required", "section": "format",
                "message": "creates new cells/worldspaces -> must ship ESM-flagged (not ESL); "
                "confirm the master flag is set"})
    except Fo4McpError as e:
        findings.append({"level": "warning", "rule": "eligibility_unavailable", "section": "format",
            "message": f"ESL eligibility check unavailable: {e.message}"})

    # --- navmesh handoff roll-up ---
    try:
        nav = fo4_navmesh_handoff(cfg, manifest, str(plugin_path))["data"]
        sections["navmesh"] = nav
        if nav.get("error_count"):
            findings.append({"level": "error", "rule": "navmesh_ck_required", "section": "navmesh",
                "message": f"{nav['error_count']} exterior cell(s) need CK navmesh generation "
                "(see ck_checklist)"})
        if nav.get("warning_count"):
            findings.append({"level": "warning", "rule": "navmesh_gaps", "section": "navmesh",
                "message": f"{nav['warning_count']} interior cell(s) have navmesh gaps "
                "(agent-authorable — re-author with navmesh:{...})"})
    except Fo4McpError as e:
        findings.append({"level": "warning", "rule": "navmesh_unavailable", "section": "navmesh",
            "message": f"navmesh handoff check unavailable: {e.message}"})

    # --- previs impact (per cell) ---
    try:
        cells = _cell_navmesh_list(cfg, manifest, plugin_path)
        previs_hits = []
        for c in cells:
            try:
                info = _cell_info(cfg, manifest, plugin_path, str(c.get("cell")))
            except Fo4McpError:
                continue
            if info.get("hasPrecombines") or info.get("hasPrevis"):
                previs_hits.append({"formKey": c.get("cell"), "editorId": c.get("editorId"),
                    "hasPrecombines": bool(info.get("hasPrecombines")),
                    "hasPrevis": bool(info.get("hasPrevis"))})
        sections["previs"] = {"cells_with_previs": previs_hits, "cell_count": len(cells)}
        if previs_hits:
            findings.append({"level": "warning", "rule": "previs_present", "section": "previs",
                "message": f"{len(previs_hits)} cell(s) carry precombines/previs — if you added or "
                "moved refs there, regenerate previs in the CK (W12) or expect visual holes"})
    except Fo4McpError as e:
        findings.append({"level": "warning", "rule": "previs_unavailable", "section": "previs",
            "message": f"previs impact check unavailable: {e.message}"})

    # --- voice/lip handoff roll-up (dialogue lines needing a recorded .fuz) ---
    try:
        voice = fo4_voice_handoff(cfg, manifest, str(plugin_path))["data"]
        sections["voice"] = voice
        if voice.get("warning_count"):
            findings.append({"level": "warning", "rule": "voice_incomplete", "section": "voice",
                "message": f"{voice['warning_count']} dialogue line(s) need a recorded .fuz / a "
                "resolvable voice type (human voice/TTS step — see recording_checklist)"})
    except Fo4McpError as e:
        findings.append({"level": "warning", "rule": "voice_unavailable", "section": "voice",
            "message": f"voice handoff check unavailable: {e.message}"})

    error_count = sum(1 for f in findings if f["level"] == "error")
    warning_count = sum(1 for f in findings if f["level"] == "warning")
    verdict = ("ship-blocked" if error_count else
               "review" if warning_count else
               "ship-ready")
    return ok({
        "plugin":        str(plugin_path),
        "verdict":       verdict,
        "error_count":   error_count,
        "warning_count": warning_count,
        "findings":      findings,
        "sections":      sections,
    })


def fo4_place_into_cell(
    cfg: Config,
    manifest: Manifest,
    cell: str,
    output_plugin: str,
    *,
    placed_objects: list[dict[str, Any]] | None = None,
    placed_npcs: list[dict[str, Any]] | None = None,
    source_plugin: str | None = None,
    clear_existing: bool = False,
    acknowledge_previs: bool = False,
    confirm_overwrite: bool = False,
) -> dict[str, Any]:
    """Add placed references (REFR/ACHR) to an EXISTING cell as an override (Faz 3 / W5).

    Builds a `cellOverride` record and writes it via the create path. The writer DeepCopies the
    master cell (so its lighting/data carry forward — no black cell), ADDITIVELY appends the new
    refs (default), and places the override in the block hierarchy. Output is safety-gated
    (staging/fixtures; .bak on overwrite).

    SAFE DEFAULT (clear_existing=False): the deep-copied master refs are KEPT. clear_existing=True
    is destructive on a POPULATED cell — it wipes the master's own refs in the override (the Kerem
    RedRocketExt incident: 482 refs lost). Only opt in when overriding an empty/new cell.

    BLOCKING previs precondition: if the target cell has precombines/previs, this REFUSES (no
    write) unless acknowledge_previs=True — editing such a cell needs a CK previs regen (W12) or
    the refs may be invisible + the cell may show holes (see fo4_check_previs_safety).

    Args:
        cell:               target cell FormKey '<6hex>:<master>'
        output_plugin:      destination plugin path, .esp/.esm/.esl (safety-gated)
        placed_objects:     REFR refs [{base, position?, rotation?, scale?, editorId?, persistent?}]
        placed_npcs:        ACHR refs (same shape)
        source_plugin:      plugin holding the cell (default: derive master from the FormKey,
                            look in the FO4 install Data dir)
        clear_existing:     wipe the deep-copied master refs (default False -> additive, keep them;
                            True only for empty/new cells — destructive on populated cells)
        acknowledge_previs: proceed even if the cell is precombined/previs'd (refs may be unseen)
        confirm_overwrite:  required to overwrite an existing output plugin
    """
    if not placed_objects and not placed_npcs:
        raise Fo4McpError(
            ErrorCode.INVALID_ARGUMENT,
            "fo4_place_into_cell needs at least one placed_objects or placed_npcs entry", {})
    source = _resolve_source_plugin(cfg, cell, source_plugin)
    safety = fo4_check_previs_safety(cfg, manifest, cell, str(source))["data"]
    if not safety["safe"] and not acknowledge_previs:
        return ok({
            "wrote":         False,
            "blocked":       True,
            "reason":        "previs_unsafe",
            "cell":          safety["cell"],
            "previs_safety": safety,
            "message": (
                "target cell has precombines/previs; placing loose refs would break visuals "
                "until a CK previs regen (W12). Re-call with acknowledge_previs=true to proceed "
                "anyway (the refs exist on disk but may be invisible in-game until previs is "
                "regenerated)."),
        })
    rec: dict[str, Any] = {
        "type": "cellOverride", "cell": cell, "sourcePlugin": str(source),
        "clearExisting": clear_existing,
    }
    if placed_objects is not None:
        rec["placedObjects"] = placed_objects
    if placed_npcs is not None:
        rec["placedNpcs"] = placed_npcs
    result = fo4_create_record(
        cfg, manifest, {"records": [rec]}, output_plugin, confirm_overwrite=confirm_overwrite)
    data = result.get("data")
    if isinstance(data, dict):
        data["previs_safety"] = safety
    return result


def fo4_inspect_sm_tree(
    cfg: Config, manifest: Manifest, plugin: str, node: str | None = None
) -> dict[str, Any]:
    """Read-only Story Manager tree reader (Faz 3 / W6).

    Without `node`: lists the plugin's SM EVENT nodes (the auto-start anchor points) with
    editorId/formKey/event-type + childCount. With `node` (a FormKey or EditorID): that node +
    its direct children (branch/quest nodes whose Parent == it). Use it to pick the right Parent
    (and PreviousSibling) for a new SMQN — the SM tree isn't in the repo, so this walks it live
    from Fallout4.esm (or any plugin). A wrong Parent/sibling is the W6 silent-fail mode (clean
    load + Spriggit OK but the quest never auto-starts in-game). `plugin` may be a bare master
    name (resolved in the FO4 install Data dir) or a path."""
    import json
    cli = _mutagen_cli_binary(cfg, manifest)
    if cli is None:
        raise Fo4McpError(
            ErrorCode.TOOL_BINARY_MISSING,
            "mutagen-cli not built (tools/mutagen-cli/) — required for fo4_inspect_sm_tree",
            {"tool": "mutagen-cli"})
    pp = Path(plugin)
    if (not pp.is_absolute() and "/" not in plugin and "\\" not in plugin
            and cfg.fo4_install_dir is not None):
        cand = cfg.fo4_install_dir / "Data" / plugin
        if cand.exists():
            pp = cand
    if not pp.is_absolute():
        pp = (cfg.repo_root / pp).resolve()
    if not pp.exists():
        raise Fo4McpError(ErrorCode.INVALID_ARGUMENT, f"plugin not found: {pp}", {"plugin": plugin})
    cmd = ["sm-tree", "--plugin", str(pp)]
    if node:
        cmd += ["--record", node]
    result = run_tool(cli, cmd, timeout=cfg.subprocess_timeout, env_extra=_spriggit_env())
    if not result.stdout.strip():
        raise Fo4McpError(
            ErrorCode.SUBPROCESS_FAILED, "mutagen-cli sm-tree failed",
            {"exit_code": result.exit_code, "stderr_tail": result.stderr[-500:]})
    try:
        return ok(json.loads(result.stdout))
    except json.JSONDecodeError:
        raise Fo4McpError(
            ErrorCode.SUBPROCESS_OUTPUT_UNPARSEABLE, "sm-tree emitted no JSON",
            {"stdout_tail": result.stdout[-500:]})


# ---- Tool 3a-lint: NPC template / FaceGen-coverage lint (Faz 3 / W3f) --------

# TemplateActorType.Traits — the bit that governs trait/appearance inheritance.
_NPC_TRAITS_BIT = 1


def fo4_lint_npc_template(cfg: Config, manifest: Manifest, plugin_path: str) -> dict[str, Any]:
    """Lint a plugin's NPCs for template-coherence bugs + FaceGen-asset coverage.

    Read-only. Two checks, grounded in the W3a/W3f reflection probes:
      - orphan_template_flags (error): UseTemplateActors flags set but no DefaultTemplate
        -> the flags are inert (they only take effect with a template) = authoring bug.
      - facegen_needed (warning): the NPC carries its own face data (HeadParts/FaceMorphs/
        FaceTintingLayers) -> it needs baked FaceGen assets (CK/W10) shipped, or it renders
        with a dark face. A coverage list; each entry notes whether it inherits Traits from
        a template (DefaultTemplate + the Traits bit), which lowers the risk.

    NOTE: dark-face risk is NOT confirmable from the plugin alone (FaceGen .dds/.nif live in
    loose/BA2 assets). The W3f probe refuted the naive "Traits bit => empty own FaceGen" model
    (templated Remnants troopers still carry FaceMorphs), so this reports a bake-coverage list,
    not a dark-face verdict.
    """
    import json

    ppath = Path(plugin_path)
    if not ppath.is_absolute():
        ppath = (cfg.repo_root / ppath).resolve()
    if not ppath.exists():
        raise Fo4McpError(
            ErrorCode.PATH_NOT_FOUND, f"plugin not found: {ppath}", {"plugin_path": str(ppath)},
        )

    cli = _mutagen_cli_binary(cfg, manifest)
    if cli is None:
        raise Fo4McpError(
            ErrorCode.TOOL_BINARY_MISSING,
            "mutagen-cli not built (tools/mutagen-cli/) — required for fo4_lint_npc_template",
            {"tool": "mutagen-cli"},
        )

    result = run_tool(
        cli, ["lint-npc", "--plugin", str(ppath)],
        timeout=cfg.subprocess_timeout, env_extra=_spriggit_env(),
    )
    if not result.ok:
        raise Fo4McpError(
            ErrorCode.SUBPROCESS_FAILED, "mutagen-cli lint-npc failed",
            {"exit_code": result.exit_code, "stderr_tail": result.stderr[-1000:]},
        )
    try:
        npcs = json.loads(result.stdout).get("npcs", [])
    except json.JSONDecodeError:
        raise Fo4McpError(
            ErrorCode.SUBPROCESS_OUTPUT_UNPARSEABLE,
            "mutagen-cli lint-npc emitted no JSON", {"stdout_tail": result.stdout[-500:]},
        )

    findings: list[dict[str, Any]] = []
    for n in npcs:
        uta = int(n.get("useTemplateActors", 0))
        has_def = n.get("defaultTemplate") is not None
        hp, fm, tl = (int(n.get("headPartCount", 0)), int(n.get("faceMorphCount", 0)),
                      int(n.get("faceTintingLayerCount", 0)))
        own_face = hp > 0 or fm > 0 or tl > 0
        inherits_traits = has_def and (uta & _NPC_TRAITS_BIT) != 0
        base = {"editorId": n.get("editorId"), "formKey": n.get("formKey")}
        if uta != 0 and not has_def:
            findings.append({
                **base, "rule": "orphan_template_flags", "level": "error",
                "message": f"UseTemplateActors flags set ({uta}) but no DefaultTemplate — "
                           "flags are inert (they apply only with a template)",
            })
        if own_face:
            findings.append({
                **base, "rule": "facegen_needed", "level": "warning",
                "inheritsTraits": inherits_traits,
                "faceData": {"headParts": hp, "faceMorphs": fm, "faceTintingLayers": tl},
                "message": "carries own face data — needs baked FaceGen (CK/W10) shipped or "
                           "risks dark face" + ("; inherits Traits from a template (lower risk)"
                                                if inherits_traits else ""),
            })

    errors = sum(1 for f in findings if f["level"] == "error")
    warnings = sum(1 for f in findings if f["level"] == "warning")
    facegen = [f for f in findings if f["rule"] == "facegen_needed"]
    verdict = "bug" if errors else ("review" if warnings else "clean")
    return ok({
        "plugin":                        str(ppath),
        "npc_count":                     len(npcs),
        "finding_count":                 len(findings),
        "error_count":                   errors,
        "warning_count":                 warnings,
        "facegen_needed_count":          len(facegen),
        "facegen_inherits_traits_count": sum(1 for f in facegen if f.get("inheritsTraits")),
        "findings":                      findings,
        "verdict":                       verdict,
        "note": ("dark-face risk is not confirmable from the plugin alone (FaceGen assets are "
                 "external); facegen_needed is a W10 bake-coverage list, not a verdict"),
    })


# ---- Tool 3b: ESL eligibility check ------------------------------------------

# FE-space light-master capacity and the new-record ObjectID ceiling for ESL.
_ESL_MAX_NEW_RECORDS = 2048
_ESL_MAX_OBJECT_ID   = 0xFFF
# SPID-F4 (and several distributors) silently drop records below this ObjectID.
_SPID_MIN_OBJECT_ID  = 0x800
# MutagenObjectType substrings meaning "new cell/worldspace" -> forces ESM, never ESL.
_NEW_CELL_TYPE_HINTS = ("cell", "worldspace")


def _record_data_modkey(text: str) -> str | None:
    """Pull `ModKey` from a Spriggit RecordData.yaml body (top-level scan)."""
    for raw in text.splitlines():
        if raw[:1] not in (" ", "-", "\t"):
            key, _, val = raw.partition(":")
            if key.strip() == "ModKey":
                return val.strip() or None
    return None


def _esl_verdict(new_count: int, max_object_id: int, new_cell_count: int) -> tuple[str, list[str]]:
    """Pure ESL/ESM verdict from the scanned counts. `max_object_id` is an int
    (-1 if no new record had a parseable ObjectID). Returns (verdict, reasons)."""
    max_oid_hex = None if max_object_id < 0 else f"0x{max_object_id:X}"
    reasons: list[str] = []

    if new_cell_count > 0:
        return "esm-flag", [
            f"creates {new_cell_count} new cell/worldspace record(s) -> previs/"
            "precombine can't live in FE-space; ESM-flag, never ESL"
        ]
    if new_count == 0:
        return "no-new-records", ["no new records (override-only plugin); ESL flagging is moot"]
    if new_count <= _ESL_MAX_NEW_RECORDS and 0 <= max_object_id <= _ESL_MAX_OBJECT_ID:
        reasons.append(
            f"{new_count} new records (< {_ESL_MAX_NEW_RECORDS}) and max ObjectID "
            f"{max_oid_hex} <= 0xFFF"
        )
        if max_object_id < _SPID_MIN_OBJECT_ID:
            reasons.append(
                f"WARN: max ObjectID {max_oid_hex} < 0x800 -> SPID-F4 and distributors "
                "drop these records; author in 0x800-0xFFF if distributing via SPID"
            )
        return "esl-eligible", reasons
    if new_count <= _ESL_MAX_NEW_RECORDS and max_object_id > _ESL_MAX_OBJECT_ID:
        return "esl-needs-compaction", [
            f"{new_count} new records but max ObjectID {max_oid_hex} > 0xFFF -> needs "
            "FormID compaction (gated, irreversible) before ESL-flag"
        ]
    return "plain-esp", [
        f"{new_count} new records (>= {_ESL_MAX_NEW_RECORDS}) -> too many for ESL; "
        "ship as full ESP/ESM"
    ]


def _scan_serialized_records(
    out_dir: Path, header: Path, mod_key: str
) -> tuple[int, int, list[str], set[str]]:
    """Count new records in a Spriggit serialize tree. Returns
    (new_count, max_object_id, new_cell_types, referenced_masters).

    Spriggit emits one YAML per record in TWO layouts: a simple record is a flat
    `<Type>/<Name> - <FormID>_<ModKey>.yaml`, while a record with nested content
    (quests, cells, npcs...) is a FOLDER `<Type>/<rec>/RecordData.yaml`. Only the
    single top-level `out_dir/RecordData.yaml` (the mod header) is skipped — by
    PATH, never by name: skipping every file *named* RecordData.yaml silently
    drops every folder-style record (the exact complex types — QUST/CELL/NPC/PACK
    — this verdict cares about). Record type is the explicit MutagenObjectType
    field, else Spriggit's top-level type folder (Cells/Worldspaces/...), which is
    what _NEW_CELL_TYPE_HINTS matches.
    """
    new_count = 0
    max_object_id = -1
    new_cell_types: list[str] = []
    referenced_masters: set[str] = set()
    for f in sorted(out_dir.rglob("*.yaml")):
        if f == header:
            continue  # the mod header, not a record (skip by PATH, never by name)
        fields = _extract_record_fields(f.read_text(encoding="utf-8", errors="replace"))
        fk = fields["form_key"] or ""
        if ":" not in fk:
            continue
        id_part, _, fk_mod = fk.partition(":")
        fk_mod = fk_mod.strip()
        oid = _norm_formid(id_part)
        if fk_mod.lower() == mod_key.lower():
            new_count += 1
            if oid is not None:
                max_object_id = max(max_object_id, int(oid, 16))
            rtype = fields["record_type"] or ""
            if not rtype:
                parts = f.relative_to(out_dir).parts
                rtype = parts[0] if parts else ""
            if any(h in rtype.lower() for h in _NEW_CELL_TYPE_HINTS):
                new_cell_types.append(rtype)
        elif fk_mod:
            referenced_masters.add(fk_mod)
    return new_count, max_object_id, new_cell_types, referenced_masters


def fo4_check_esl_eligibility(cfg: Config, manifest: Manifest, plugin: str) -> dict[str, Any]:
    """Read-only ESL / ESM-flag eligibility report for a plugin.

    Serializes the plugin via Spriggit (process-boundary GPL isolation) and
    inspects its NEW records (FormKey ModKey == the plugin's own ModKey):
      * new-record count (< 2048 to ESL-flag),
      * max new-record ObjectID (<= 0xFFF for ESL; >= 0x800 to survive SPID-F4),
      * whether it creates new cells/worldspaces -> ESM-flag, never ESL (FE-space
        cells can't carry previs/precombine).

    Verdict is ADVISORY. Flag-writing and FormID compaction are user-gated
    (docs/V2-backlog.md #3, #14) and never performed here. `referenced_masters`
    is a lower bound (distinct ModKeys of overridden records only).
    """
    import tempfile

    binary = _spriggit_binary(cfg, manifest)

    plugin_path = Path(plugin)
    if not plugin_path.is_absolute():
        plugin_path = (cfg.repo_root / plugin_path).resolve()
    if not plugin_path.exists():
        raise Fo4McpError(
            ErrorCode.PATH_NOT_FOUND,
            f"plugin not found: {plugin_path}",
            {"plugin": str(plugin_path)},
        )

    version = _spriggit_version(manifest, None)

    with tempfile.TemporaryDirectory() as td:
        out_dir = Path(td) / "yaml"
        args = [
            "serialize",
            "-i", str(plugin_path),
            "-o", str(out_dir),
            "-g", _SPRIGGIT_GAME_RELEASE,
            "-p", _SPRIGGIT_PACKAGE,
            "-v", version,
        ]
        result = run_tool(binary, args, timeout=cfg.subprocess_timeout, env_extra=_spriggit_env())
        if not out_dir.exists():
            raise Fo4McpError(
                ErrorCode.SUBPROCESS_FAILED,
                "Spriggit serialize produced no output",
                {"exit_code": result.exit_code, "stderr_tail": result.stderr[-1000:]},
            )

        rd = out_dir / "RecordData.yaml"
        mod_key = _record_data_modkey(rd.read_text(encoding="utf-8", errors="replace")) if rd.exists() else None
        if not mod_key:
            mod_key = plugin_path.name

        new_count, max_object_id, new_cell_types, referenced_masters = (
            _scan_serialized_records(out_dir, rd, mod_key)
        )

    verdict, reasons = _esl_verdict(new_count, max_object_id, len(new_cell_types))
    max_oid_hex = None if max_object_id < 0 else f"0x{max_object_id:X}"

    return ok({
        "plugin":                       str(plugin_path),
        "mod_key":                      mod_key,
        "new_record_count":             new_count,
        "max_object_id":                max_oid_hex,
        "esl_object_id_ceiling":        "0xFFF",
        "spid_object_id_floor":         "0x800",
        "new_cell_or_worldspace_count": len(new_cell_types),
        "referenced_masters":           sorted(referenced_masters),
        "referenced_master_count":      len(referenced_masters),
        "verdict":                      verdict,
        "reasons":                      reasons,
    })


# ---- Tool 3d: engine-config linter -------------------------------------------

# Addictol bundles Buffout 4 NG + X-Cell + Baka MaxPapyrusOps + EscapeFreeze in
# ONE plugin. Running it alongside the standalone versions double-patches the
# engine (two MemoryManagers, two op-limit hooks) -> instability.
_ADDICTOL_SUPERSEDES = ("buffout4", "x-cell", "xcell", "bakamaxpapyrusops")

# (setting, required_flag, note): the setting is a no-op unless the flag is on.
# Derived from the real Addictol.toml (tools/addictol/.../Addictol.toml).
_ENGINE_DEP_RULES: tuple[tuple[str, str, str], ...] = (
    ("uScaleformPageSize", "bScaleformAllocator", "scaleform page size needs bScaleformAllocator"),
    ("uScaleformHeapSize",  "bScaleformAllocator", "scaleform heap size needs bScaleformAllocator"),
    ("nMaxPapyrusOpsPerFrame", "bBakaMaxPapyrusOps", "papyrus op limit needs bBakaMaxPapyrusOps"),
    ("nSleepTimer",  "bEscapeFreeze", "nSleepTimer needs bEscapeFreeze"),
    ("nMaxLockCount", "bEscapeFreeze", "nMaxLockCount needs bEscapeFreeze"),
    ("bUseNewRedistributable", "bMemoryManager", "bUseNewRedistributable needs bMemoryManager"),
    ("bInteriorNavCutMultiThreading", "bInteriorNavCut", "needs bInteriorNavCut"),
    ("bDbgFacegenOutput", "bFacegen", "needs bFacegen"),
)
# Settings that must be a multiple of 8 within 8..2048 (scaleform memory).
_ENGINE_SCALEFORM_KEYS = ("uScaleformPageSize", "uScaleformHeapSize")


def _flatten_toml(data: dict[str, Any]) -> dict[str, Any]:
    """Flatten one level of TOML sections into a flat key->value map. Keys in an
    engine config are unique across sections, so this is lossless here."""
    out: dict[str, Any] = {}
    for k, v in data.items():
        if isinstance(v, dict):
            out.update(v)
        else:
            out[k] = v
    return out


def _lint_engine_config(data: dict[str, Any]) -> list[dict[str, str]]:
    """Pure ruleset over a flattened engine-config map. Returns findings
    [{level, rule, message}]. No I/O — unit-testable."""
    flat = _flatten_toml(data)
    findings: list[dict[str, str]] = []

    for setting, flag, note in _ENGINE_DEP_RULES:
        if setting not in flat:
            continue
        sval = flat[setting]
        active = (sval is True) if isinstance(sval, bool) else (sval is not None)
        if active and flag in flat and flat[flag] is False:
            findings.append({
                "level": "warn", "rule": f"{setting}->{flag}",
                "message": f"{setting} is set but {flag}=false -> no effect ({note})",
            })

    for key in _ENGINE_SCALEFORM_KEYS:
        v = flat.get(key)
        if isinstance(v, int) and not isinstance(v, bool):
            if v % 8 != 0:
                findings.append({"level": "warn", "rule": key,
                                 "message": f"{key}={v} should be a multiple of 8"})
            if not (8 <= v <= 2048):
                findings.append({"level": "warn", "rule": key,
                                 "message": f"{key}={v} out of range 8..2048"})

    n = flat.get("nMaxStdIO")
    if isinstance(n, int) and not isinstance(n, bool) and n != -1 and n > 8192:
        findings.append({"level": "warn", "rule": "nMaxStdIO",
                         "message": f"nMaxStdIO={n} exceeds the 8192 max (use -1 for auto)"})
    return findings


def fo4_lint_engine_config(
    cfg: Config, config_path: str, *, plugins_dir: str | None = None
) -> dict[str, Any]:
    """Lint an Addictol/Buffout-style engine-config TOML for no-op settings,
    out-of-range scaleform values, and (if plugins_dir given) double-patching
    against standalone plugins Addictol supersedes.

    Read-only. Advisory neighbor to fo4_analyze_crash_log (FO4 sweep #A5).
    """
    import tomllib

    cpath = Path(config_path)
    if not cpath.is_absolute():
        cpath = (cfg.repo_root / cpath).resolve()
    if not cpath.exists():
        raise Fo4McpError(
            ErrorCode.PATH_NOT_FOUND, f"config not found: {cpath}", {"config_path": str(cpath)},
        )
    try:
        data = tomllib.loads(cpath.read_text(encoding="utf-8", errors="replace"))
    except tomllib.TOMLDecodeError as e:
        raise Fo4McpError(
            ErrorCode.SUBPROCESS_OUTPUT_UNPARSEABLE, f"invalid TOML: {e}", {"config_path": str(cpath)},
        )

    findings = _lint_engine_config(data)
    is_addictol = "addictol" in cpath.name.lower()
    double_patch: list[str] = []

    if plugins_dir:
        pdir = Path(plugins_dir)
        if not pdir.is_absolute():
            pdir = (cfg.repo_root / pdir).resolve()
        if pdir.exists() and is_addictol:
            for dll in pdir.glob("*.dll"):
                low = dll.name.lower().replace(" ", "")
                if any(s in low for s in _ADDICTOL_SUPERSEDES):
                    double_patch.append(dll.name)
                    findings.append({
                        "level": "error", "rule": "double-patch",
                        "message": f"{dll.name} present alongside Addictol -> double-patch "
                                   "(Addictol already bundles Buffout4/X-Cell/Baka); remove the standalone",
                    })

    errors = sum(1 for f in findings if f["level"] == "error")
    verdict = "conflict" if errors else ("warnings" if findings else "clean")
    return ok({
        "config_path":           str(cpath),
        "config_kind":           "addictol" if is_addictol else "generic-engine-toml",
        "finding_count":         len(findings),
        "error_count":           errors,
        "double_patch_plugins":  double_patch,
        "findings":              findings,
        "verdict":               verdict,
    })


# ---- Tool 3f: save backup ----------------------------------------------------

# FO4 save + F4SE co-save extensions (the player's Documents Saves folder).
_SAVE_EXTS = (".fos", ".f4se")


def fo4_backup_saves(
    cfg: Config, *, label: str | None = None, dest_dir: str | None = None
) -> dict[str, Any]:
    """Copy the player's FO4 saves to a timestamped archive under staging/.

    Read-only on the source (`Documents/My Games/Fallout4/Saves`). The safety
    net to run BEFORE any save-breaking op (FormID compaction, risky mod swaps)
    — user-requested (TASKS #U2). First concrete piece of the save layer; the
    save-EDIT side (ReSaver/Fallrim) is still research/plan.
    """
    from datetime import datetime
    import shutil

    if cfg.fo4_user_docs is None:
        raise Fo4McpError(
            ErrorCode.PATH_NOT_FOUND,
            "FO4 user docs not detected (set FO4_USER_DOCS); can't find Saves",
            {},
        )
    saves = cfg.fo4_user_docs / "Saves"
    if not saves.is_dir():
        raise Fo4McpError(
            ErrorCode.PATH_NOT_FOUND, f"Saves dir not found: {saves}", {"saves": str(saves)},
        )

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    name = f"{stamp}-{label}" if label else stamp
    base = Path(dest_dir) if dest_dir else (cfg.repo_root / "staging" / "save-archive")
    if not base.is_absolute():
        base = (cfg.repo_root / base).resolve()
    dest = base / name
    check_write(dest, cfg.repo_root)  # raises on DENY
    dest.mkdir(parents=True, exist_ok=True)

    copied: list[str] = []
    total = 0
    for f in sorted(saves.iterdir()):
        if f.is_file() and f.suffix.lower() in _SAVE_EXTS:
            shutil.copy2(f, dest / f.name)
            copied.append(f.name)
            total += f.stat().st_size

    return ok({
        "source":       str(saves),
        "archive_dir":  str(dest),
        "save_count":   sum(1 for n in copied if n.lower().endswith(".fos")),
        "cosave_count": sum(1 for n in copied if n.lower().endswith(".f4se")),
        "file_count":   len(copied),
        "total_bytes":  total,
        "files":        copied,
    })


# ---- Tool 3e: BA2 header version patch ---------------------------------------

_BA2_MAGIC = b"BTDX"
_BA2_VALID_VERSIONS = (1, 7, 8)  # v1 = OG, v7/v8 = next-gen


def _patch_ba2_version_bytes(data: bytes, target_version: int) -> tuple[bytes, int, str]:
    """Rewrite the BA2 header version field. Returns (patched, old_version, type).

    BA2 layout: magic 'BTDX' (4) | version uint32 (4) | type 'GNRL'/'DX10' (4) ...
    Verified against real archives (HUDFramework v1 GNRL, game NG v8 GNRL). The
    file body is unchanged; only the 4-byte version field is rewritten. Pure."""
    if data[0:4] != _BA2_MAGIC:
        raise ValueError(f"not a BA2 archive (magic={data[0:4]!r}, expected {_BA2_MAGIC!r})")
    old = struct.unpack_from("<I", data, 4)[0]
    btype = data[8:12].decode("ascii", "replace")
    patched = data[:4] + struct.pack("<I", target_version) + data[8:]
    return patched, old, btype


def fo4_ba2_version_patch(
    cfg: Config, ba2_path: str, output_path: str, *, target_version: int = 1
) -> dict[str, Any]:
    """Rewrite a BA2's header version (e.g. NG v7/v8 -> OG v1) for cross-compat.

    Pure-Python header rewrite — no external tool (FO4 sweep #A4 / V2 #10; the
    `fo4_pack_ba2` BSArchPro wrapper remains download-blocked). The file body is
    untouched. Output is safety-gated to staging/fixtures; an existing target is
    backed up to .bak. DX10 (texture) archives get a warning: a version flip
    alone may not satisfy OG texture loaders.
    """
    if target_version not in _BA2_VALID_VERSIONS:
        raise Fo4McpError(
            ErrorCode.INVALID_ARGUMENT,
            f"target_version must be one of {_BA2_VALID_VERSIONS}",
            {"target_version": target_version},
        )

    src = Path(ba2_path)
    if not src.is_absolute():
        src = (cfg.repo_root / src).resolve()
    if not src.exists():
        raise Fo4McpError(ErrorCode.PATH_NOT_FOUND, f"BA2 not found: {src}", {"ba2_path": str(src)})

    out = Path(output_path)
    if not out.is_absolute():
        out = (cfg.repo_root / out).resolve()
    check_write(out, cfg.repo_root)  # raises on DENY

    data = src.read_bytes()
    try:
        patched, old_version, btype = _patch_ba2_version_bytes(data, target_version)
    except ValueError as e:
        raise Fo4McpError(ErrorCode.INVALID_ARGUMENT, str(e), {"ba2_path": str(src)})

    warnings: list[str] = []
    if btype.upper().startswith("DX10") and target_version == 1 and old_version >= 7:
        warnings.append(
            "DX10 texture archive: a version-field flip alone may not be readable by "
            "OG/v1 texture loaders (next-gen texture chunks differ); a full repack via "
            "BSArchPro may be needed for textures"
        )
    if old_version == target_version:
        warnings.append(f"already version {target_version}; output is a copy")

    out.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    if out.exists():
        backup = out.with_suffix(out.suffix + ".bak")
        backup.write_bytes(out.read_bytes())
    out.write_bytes(patched)

    return ok({
        "source":         str(src),
        "output":         str(out),
        "source_version": old_version,
        "target_version": target_version,
        "archive_type":   btype,
        "backup_path":    str(backup) if backup else None,
        "bytes":          len(patched),
        "warnings":       warnings,
    })


# ---- Tool 3c: FOMOD installer generator --------------------------------------

# FOMOD ModuleConfig.xml enumerations (XFL/Mod Config 5.0 schema).
_FOMOD_PLUGIN_TYPES = {"Required", "Optional", "Recommended", "NotUsable", "CouldBeUsable"}
_FOMOD_GROUP_TYPES = {
    "SelectExactlyOne", "SelectAtMostOne", "SelectAtLeastOne", "SelectAll", "SelectAny",
}


def _fomod_append_files(parent: ET.Element, files: list[dict[str, Any]]) -> None:
    """Append <file>/<folder> children to `parent` from a list of
    {source, destination, [type=file|folder], [priority]} dicts."""
    for f in files or []:
        tag = "folder" if f.get("type") == "folder" else "file"
        el = ET.SubElement(parent, tag)
        el.set("source", str(f["source"]))
        el.set("destination", str(f.get("destination", "")))
        el.set("priority", str(f.get("priority", 0)))


def fo4_generate_fomod(cfg: Config, spec: dict[str, Any], output_dir: str) -> dict[str, Any]:
    """Generate a FOMOD installer (`fomod/info.xml` + `fomod/ModuleConfig.xml`).

    No mature CLI FOMOD generator exists (FO4 sweep, docs/V2-backlog.md #9); the
    format is plain XML, so we emit it deterministically from a spec. Output is
    safety-gated to staging/ or fixtures/. Validates option/group type enums and
    warns (rather than failing) on non-standard values.

    spec keys:
      name (required), author, version, website, description
      required_files: [{source, destination, [type=file|folder], [priority]}]
      install_steps: [{name, groups: [{name, type, plugins: [
          {name, description, [image], type, files:[{source,destination}]} ]}]}]
    """
    name = (spec.get("name") or "").strip()
    if not name:
        raise Fo4McpError(
            ErrorCode.INVALID_ARGUMENT, "spec.name is required",
            {"spec_keys": sorted(spec)},
        )

    out_path = Path(output_dir)
    if not out_path.is_absolute():
        out_path = (cfg.repo_root / out_path).resolve()
    disposition = check_write(out_path, cfg.repo_root)  # raises on DENY
    fomod_dir = out_path / "fomod"
    fomod_dir.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []

    # --- info.xml ---
    info = ET.Element("fomod")
    for tag, key in (
        ("Name", "name"), ("Author", "author"), ("Version", "version"),
        ("Website", "website"), ("Description", "description"),
    ):
        val = spec.get(key)
        if val:
            ET.SubElement(info, tag).text = str(val)
    info_tree = ET.ElementTree(info)
    ET.indent(info_tree, space="  ")
    info_path = fomod_dir / "info.xml"
    info_tree.write(info_path, encoding="utf-8", xml_declaration=True)

    # --- ModuleConfig.xml ---
    root = ET.Element("config")
    root.set("xmlns:xsi", "http://www.w3.org/2001/XMLSchema-instance")
    root.set("xsi:noNamespaceSchemaLocation", "http://qconsulting.ca/fo3/ModConfig5.0.xsd")
    ET.SubElement(root, "moduleName").text = name

    req = spec.get("required_files") or []
    if req:
        _fomod_append_files(ET.SubElement(root, "requiredInstallFiles"), req)

    steps = spec.get("install_steps") or []
    if steps:
        steps_el = ET.SubElement(root, "installSteps")
        steps_el.set("order", "Explicit")
        for step in steps:
            step_el = ET.SubElement(steps_el, "installStep")
            step_el.set("name", str(step.get("name", "Options")))
            groups_el = ET.SubElement(step_el, "optionalFileGroups")
            groups_el.set("order", "Explicit")
            for group in step.get("groups", []):
                g_el = ET.SubElement(groups_el, "group")
                g_el.set("name", str(group.get("name", "Group")))
                gtype = str(group.get("type", "SelectAny"))
                if gtype not in _FOMOD_GROUP_TYPES:
                    warnings.append(f"group '{group.get('name')}': non-standard type '{gtype}'")
                g_el.set("type", gtype)
                plugins_el = ET.SubElement(g_el, "plugins")
                plugins_el.set("order", "Explicit")
                for plugin in group.get("plugins", []):
                    p_el = ET.SubElement(plugins_el, "plugin")
                    p_el.set("name", str(plugin.get("name", "Option")))
                    ET.SubElement(p_el, "description").text = str(plugin.get("description", ""))
                    if plugin.get("image"):
                        ET.SubElement(p_el, "image").set("path", str(plugin["image"]))
                    files = plugin.get("files")
                    if files:
                        _fomod_append_files(ET.SubElement(p_el, "files"), files)
                    td = ET.SubElement(p_el, "typeDescriptor")
                    ptype = str(plugin.get("type", "Optional"))
                    if ptype not in _FOMOD_PLUGIN_TYPES:
                        warnings.append(f"plugin '{plugin.get('name')}': non-standard type '{ptype}'")
                    ET.SubElement(td, "type").set("name", ptype)

    mc_tree = ET.ElementTree(root)
    ET.indent(mc_tree, space="  ")
    mc_path = fomod_dir / "ModuleConfig.xml"
    mc_tree.write(mc_path, encoding="utf-8", xml_declaration=True)

    return ok({
        "ok":                  True,
        "output_dir":          str(out_path),
        "output_disposition":  disposition.value,
        "files_created": [
            str(info_path.relative_to(out_path)).replace("\\", "/"),
            str(mc_path.relative_to(out_path)).replace("\\", "/"),
        ],
        "module_name":         name,
        "install_step_count":  len(steps),
        "required_file_count": len(req),
        "warnings":            warnings,
    })


# ---- Tool 4: spriggit export -------------------------------------------------

# Spriggit serialization package defaults (Fallout 4 YAML backend).
_SPRIGGIT_PACKAGE = "Spriggit.Yaml.Fallout4"
_SPRIGGIT_GAME_RELEASE = "Fallout4"


def _spriggit_binary(cfg: Config, manifest: Manifest) -> Path:
    entry = _require_tool(manifest, "spriggit")
    binary = Path(entry.binary_path)
    if not binary.is_absolute():
        binary = (cfg.repo_root / binary).resolve()
    return binary


def _mutagen_cli_binary(cfg: Config, manifest: Manifest) -> Path | None:
    """Resolve the optional record-query CLI, or None if not built/present.

    Unlike _spriggit_binary this never raises: the binary is an opt-in perf
    backend for fo4_inspect_record (research/p0/mutagen-cli/), so absence just
    means "fall back to Spriggit serialize"."""
    entry = manifest.get("mutagen-cli")
    if entry is None or not entry.is_resolved:
        return None
    binary = Path(entry.binary_path)
    if not binary.is_absolute():
        binary = (cfg.repo_root / binary).resolve()
    return binary if binary.exists() else None


def _spriggit_version(manifest: Manifest, override: str | None) -> str:
    if override:
        return override
    entry = manifest.get("spriggit")
    return (entry.version if entry and entry.version else "0.40.1")


def _spriggit_env() -> dict[str, str]:
    """Ensure a net9-capable dotnet is discoverable by the Spriggit subprocess.

    Spriggit resolves its serialization engine via `dotnet tool install`, which
    needs the .NET 9 SDK on PATH (see research/p0/spriggit/2026-05-15-roundtrip).
    `~/.dotnet` is normally on PATH already, but we prepend it defensively so
    the tool works even when the server is launched from a bare environment."""
    import os
    dotnet_dir = Path(os.path.expanduser("~/.dotnet"))
    if dotnet_dir.exists():
        return {"PATH": f"{dotnet_dir}{os.pathsep}{os.environ.get('PATH', '')}"}
    return {}


def fo4_spriggit_export(
    cfg: Config,
    manifest: Manifest,
    plugin_path: str,
    output_dir: str,
    *,
    package_version: str | None = None,
) -> dict[str, Any]:
    """ESP/ESM/ESL -> Spriggit YAML tree (git-trackable text form).

    Read-only on the plugin (input may live anywhere readable, including the
    Steam Data folder). Output is gated: it must land in staging/ or fixtures/.
    Roundtrip is lossless on the YAML form (research/p0/spriggit/2026-05-15-
    roundtrip.md), so export is always safe to run.

    Args:
        plugin_path:     input plugin (read-only)
        output_dir:      destination dir for the YAML tree (safety-gated)
        package_version: Spriggit serialization package version (default: manifest)
    """
    binary = _spriggit_binary(cfg, manifest)

    plugin = Path(plugin_path)
    if not plugin.is_absolute():
        plugin = (cfg.repo_root / plugin).resolve()
    if not plugin.exists():
        raise Fo4McpError(
            ErrorCode.PATH_NOT_FOUND,
            f"plugin not found: {plugin}",
            {"plugin_path": str(plugin)},
        )

    out_path = Path(output_dir)
    if not out_path.is_absolute():
        out_path = (cfg.repo_root / out_path).resolve()
    disposition = check_write(out_path, cfg.repo_root)  # raises on DENY
    out_path.mkdir(parents=True, exist_ok=True)

    version = _spriggit_version(manifest, package_version)
    args = [
        "serialize",
        "-i", str(plugin),
        "-o", str(out_path),
        "-g", _SPRIGGIT_GAME_RELEASE,
        "-p", _SPRIGGIT_PACKAGE,
        "-v", version,
    ]
    result = run_tool(binary, args, timeout=cfg.subprocess_timeout, env_extra=_spriggit_env())
    files = sorted(str(p.relative_to(out_path)) for p in out_path.rglob("*") if p.is_file())

    return ok({
        "exit_code":          result.exit_code,
        "ok":                 result.ok and bool(files),
        "plugin":             str(plugin),
        "output_dir":         str(out_path),
        "output_disposition": disposition.value,
        "package":            _SPRIGGIT_PACKAGE,
        "spriggit_version":   version,
        "files_created":      files,
        "file_count":         len(files),
        "stdout_tail":        result.stdout[-1500:],
        "stderr_tail":        result.stderr[-1500:],
    })


# ---- Tool 4b: spriggit import ------------------------------------------------

def fo4_spriggit_import(
    cfg: Config,
    manifest: Manifest,
    source_dir: str,
    output_plugin: str,
    *,
    package_version: str | None = None,
    confirm_overwrite: bool = False,
) -> dict[str, Any]:
    """Spriggit YAML tree -> binary plugin (ESP/ESM/ESL).

    DIFF-GATED. The binary plugin is not byte-stable (only the YAML form is —
    see research/p0/spriggit/2026-05-15-roundtrip.md), and import writes a real
    plugin file, so overwriting an existing target is never silent:

      * target does not exist        -> deserialize, report created
      * target exists, no confirm    -> DO NOT WRITE. Serialize the existing
                                        target back to YAML, diff it against
                                        `source_dir`, and return the changed
                                        file list with `diff_required: true`.
      * target exists, confirm=True   -> back up existing to `<name>.bak`,
                                        then deserialize over it.

    Args:
        source_dir:        Spriggit YAML tree (must contain spriggit-meta.json)
        output_plugin:     destination plugin path (safety-gated)
        confirm_overwrite: required to overwrite an existing plugin
    """
    import os
    import shutil

    binary = _spriggit_binary(cfg, manifest)

    src = Path(source_dir)
    if not src.is_absolute():
        src = (cfg.repo_root / src).resolve()
    if not (src / "spriggit-meta.json").exists():
        raise Fo4McpError(
            ErrorCode.INVALID_ARGUMENT,
            f"source_dir is not a Spriggit tree (no spriggit-meta.json): {src}",
            {"source_dir": str(src)},
        )

    out_plugin = Path(output_plugin)
    if not out_plugin.is_absolute():
        out_plugin = (cfg.repo_root / out_plugin).resolve()
    disposition = check_write(out_plugin, cfg.repo_root)  # raises on DENY
    out_plugin.parent.mkdir(parents=True, exist_ok=True)

    version = _spriggit_version(manifest, package_version)
    env = _spriggit_env()

    def _deserialize(dest: Path) -> "ToolResult":
        dest.parent.mkdir(parents=True, exist_ok=True)
        args = [
            "deserialize",
            "-i", str(src),
            "-o", str(dest),
            "-p", _SPRIGGIT_PACKAGE,
            "-v", version,
        ]
        return run_tool(binary, args, timeout=cfg.subprocess_timeout, env_extra=env)

    # --- target exists + not confirmed: diff-gate, no write ---
    if out_plugin.exists() and not confirm_overwrite:
        existing_sha = _sha256_file(out_plugin)
        # Serialize the existing plugin to a temp YAML tree and diff vs source.
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            existing_yaml = Path(td) / "existing"
            ser_args = [
                "serialize",
                "-i", str(out_plugin),
                "-o", str(existing_yaml),
                "-g", _SPRIGGIT_GAME_RELEASE,
                "-p", _SPRIGGIT_PACKAGE,
                "-v", version,
            ]
            run_tool(binary, ser_args, timeout=cfg.subprocess_timeout, env_extra=env)
            changed = _diff_yaml_trees(existing_yaml, src)
        return ok({
            "ok":                 True,
            "diff_required":      True,
            "wrote":              False,
            "output_plugin":      str(out_plugin),
            "output_disposition": disposition.value,
            "existing_sha256":    existing_sha,
            "changed_files":      changed,
            "message":            (
                "target plugin exists; not overwritten. Review changed_files, "
                "then call again with confirm_overwrite=true to back up + write."
            ),
        })

    # --- write path (new target, or confirmed overwrite) ---
    backup_path: str | None = None
    if out_plugin.exists() and confirm_overwrite:
        backup = out_plugin.with_suffix(out_plugin.suffix + ".bak")
        shutil.copy2(out_plugin, backup)
        backup_path = str(backup)

    result = _deserialize(out_plugin)
    return ok({
        "exit_code":          result.exit_code,
        "ok":                 result.ok and out_plugin.exists(),
        "diff_required":      False,
        "wrote":              True,
        "source_dir":         str(src),
        "output_plugin":      str(out_plugin),
        "output_disposition": disposition.value,
        "backup_path":        backup_path,
        "package":            _SPRIGGIT_PACKAGE,
        "spriggit_version":   version,
        "stdout_tail":        result.stdout[-1500:],
        "stderr_tail":        result.stderr[-1500:],
    })


def _sha256_file(path: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _diff_yaml_trees(left: Path, right: Path) -> list[dict[str, str]]:
    """Compare two Spriggit YAML trees by relative path + content hash.

    Returns a list of {path, status} where status is added/removed/modified.
    'added' = present in `right` (the incoming source) but not `left`
    (the existing plugin); 'removed' = the reverse."""
    def _index(root: Path) -> dict[str, str]:
        out: dict[str, str] = {}
        if not root.exists():
            return out
        for p in root.rglob("*"):
            if p.is_file():
                out[str(p.relative_to(root)).replace("\\", "/")] = _sha256_file(p)
        return out

    li, ri = _index(left), _index(right)
    changed: list[dict[str, str]] = []
    for rel in sorted(set(li) | set(ri)):
        if rel not in li:
            changed.append({"path": rel, "status": "added"})
        elif rel not in ri:
            changed.append({"path": rel, "status": "removed"})
        elif li[rel] != ri[rel]:
            changed.append({"path": rel, "status": "modified"})
    return changed


# ---- Tool 5: papyrus build ---------------------------------------------------

_SCRIPTNAME_RE = re.compile(r"^\s*scriptname\s+(\S+)", re.IGNORECASE)


def _papyrus_import_root(psc: Path) -> str:
    """Import dir for a source .psc. Papyrus (Caprica/CK) rejects a script whose
    path-relative-to-an-import-dir namespace doesn't match its declared
    `Scriptname`. Fragment scripts are namespaced ("Fragments:Quests:QF_..."),
    so the import dir must be the NAMESPACE ROOT, not the file's own dir. Derive
    the namespace depth from the ':'-count in the declared Scriptname and walk up
    that many dirs; for a flat (un-namespaced) script this is just the file's own
    directory — preserving prior behaviour."""
    psc = psc.resolve()
    root = psc.parent
    try:
        text = psc.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return str(root)
    for line in text.splitlines():
        m = _SCRIPTNAME_RE.match(line)
        if m:
            for _ in range(m.group(1).count(":")):
                root = root.parent
            break
    return str(root)


def fo4_papyrus_build(
    cfg: Config,
    manifest: Manifest,
    source_paths: list[str],
    output_dir: str,
    *,
    import_paths: list[str] | None = None,
    flags_file: str | None = None,
    backend: Literal["caprica", "ck"] = "caprica",
) -> dict[str, Any]:
    """Compile Papyrus scripts. Backend default = caprica (Session 4 D2 decision).

    Args:
        source_paths: .psc files to compile (one or many)
        output_dir:   where to write .pex (must pass safety.check_write)
        import_paths: dirs of dependent .psc files; defaults to
                      `<tools_dir>/papyrus-source/Base` if extracted. Each
                      source file's namespace root (derived from its declared
                      Scriptname) is always added, so namespaced fragment
                      scripts ("Fragments:Quests:QF_...") compile out of the box.
        flags_file:   path to Institute_Papyrus_Flags.flg; defaults to the
                      copy under the Base import dir
        backend:      "caprica" or "ck". CK is deliberately NOT wired: the
                      Bethesda toolchain was validated working (2026-06-05,
                      once the 32-bit VC++ 2012 runtime was staged), but its
                      .pex is functionally identical to Caprica's — the diff is
                      cosmetic only (timestamps, temp-register names, an unused
                      flag-table). So CK adds no value over Caprica (MIT, no
                      proprietary EULA, no Steam-install dependency) and wiring
                      it would be speculative complexity. Passing backend="ck"
                      raises NotImplementedYetError by design. See
                      research/p0/ck-papyrus/2026-06-05-runtime-context.md.

    Returns:
        ok({...}) with compile results — exit code, list of produced .pex
        files, structured warnings/errors.
    """
    if backend == "ck":
        raise NotImplementedYetError(
            "fo4_papyrus_build(backend='ck')",
            "not wired by design: the CK PapyrusCompiler was validated working "
            "but produces bytecode functionally identical to Caprica (cosmetic "
            "diff only), so Caprica (MIT) stays the sole backend. Re-evaluate "
            "only if a real flag-table / bytecode difference ever matters. See "
            "research/p0/ck-papyrus/2026-06-05-runtime-context.md",
        )
    if backend != "caprica":
        raise Fo4McpError(
            ErrorCode.INVALID_ARGUMENT,
            f"unknown backend: {backend!r}",
            {"backend": backend},
        )

    entry = _require_tool(manifest, "caprica")
    binary = Path(entry.binary_path)
    if not binary.is_absolute():
        binary = (cfg.repo_root / binary).resolve()

    if not source_paths:
        raise Fo4McpError(
            ErrorCode.INVALID_ARGUMENT,
            "source_paths is empty",
            {"source_paths": source_paths},
        )

    # Output gate — never let the agent write outside the safe zones.
    out_path = Path(output_dir)
    if not out_path.is_absolute():
        out_path = (cfg.repo_root / out_path).resolve()
    disposition = check_write(out_path, cfg.repo_root)  # raises PathForbiddenError on DENY
    out_path.mkdir(parents=True, exist_ok=True)

    base_import = cfg.tools_dir / "papyrus-source" / "Base"
    if import_paths is None:
        import_paths = [str(base_import)] if base_import.exists() else []

    # Caprica wants every source file to live inside an import dir, and for
    # namespaced scripts (fragments: "Fragments:Quests:QF_...") that dir must be
    # the namespace ROOT or Caprica rejects the file ("namespace does not match
    # expected namespace ''"). _papyrus_import_root reads the declared Scriptname
    # to find it (falls back to the file's own dir for flat scripts).
    src_roots = {_papyrus_import_root(Path(p)) for p in source_paths}
    import_paths = list(dict.fromkeys([*import_paths, *src_roots]))

    if flags_file is None:
        candidate = base_import / "Institute_Papyrus_Flags.flg"
        flags_file = str(candidate) if candidate.exists() else None

    args: list[str] = ["--game", "fallout4", "--ignorecwd"]
    for ip in import_paths:
        args += ["-i", str(ip)]
    if flags_file:
        args += ["-f", flags_file]
    args += ["-o", str(out_path)]
    args += [str(p) for p in source_paths]

    result = run_tool(binary, args, timeout=cfg.subprocess_timeout)
    diagnostics = _parse_caprica_diagnostics(result.stdout + "\n" + result.stderr)
    # rglob + as_posix: namespaced fragments compile to a subdir
    # (Fragments/Quests/QF_*.pex), which a flat *.pex glob would miss.
    produced = sorted(p.relative_to(out_path).as_posix() for p in out_path.rglob("*.pex"))

    return ok({
        "backend":          backend,
        "exit_code":        result.exit_code,
        "ok":               result.ok and bool(produced),
        "output_dir":       str(out_path),
        "output_disposition": disposition.value,
        "produced":         produced,
        "diagnostics":      diagnostics,
        "imports_used":     import_paths,
        "flags_file":       flags_file,
        "stdout_tail":      result.stdout[-1500:],
        "stderr_tail":      result.stderr[-1500:],
    })


_CAPRICA_DIAG_RE = re.compile(
    r"^(?P<file>.+?)\s*\((?P<line>\d+),\s*(?P<col>\d+)(?::\d+)?\)\s*:\s*"
    r"(?P<severity>Fatal Error|Error|Warning):\s*(?P<msg>.+)$"
)


def _parse_caprica_diagnostics(combined_output: str) -> list[dict[str, Any]]:
    """Extract structured diagnostics from Caprica stdout+stderr."""
    out: list[dict[str, Any]] = []
    for line in combined_output.splitlines():
        m = _CAPRICA_DIAG_RE.match(line.strip())
        if m:
            out.append({
                "file":     m.group("file"),
                "line":     int(m.group("line")),
                "col":      int(m.group("col")),
                "severity": m.group("severity").lower().replace("fatal error", "fatal"),
                "msg":      m.group("msg").strip(),
            })
    return out


# ---- Tool 6: crash log analyze -----------------------------------------------

_CRASH_EXCEPTION_RE = re.compile(
    r'Unhandled exception\s+"(?P<type>[^"]+)"\s+at\s+(?P<addr>0x[0-9A-Fa-f]+)'
    r'(?:\s+(?P<module>[\w.\-]+)\+(?P<offset>[0-9A-Fa-f]+))?'
)
_CRASH_GENERATOR_RE = re.compile(r"^(?P<name>Buffout 4|Addictol)\s+v(?P<ver>[0-9][0-9.]*)", re.IGNORECASE)
_CRASH_GAMEVER_RE = re.compile(r"^Fallout 4\s+v(?P<ver>[0-9][0-9.]*)", re.IGNORECASE)
# Module names can contain spaces (e.g. "Workshop Framework.dll"); match the
# trailing +offset hex at end-of-line and let the module be everything before.
_CRASH_FRAME_RE = re.compile(
    r"^\s*\[(?P<frame>\d+)\]\s+0x[0-9A-Fa-f]+\s+(?P<module>.+?)\+(?P<offset>[0-9A-Fa-f]+)\s*$"
)
_CRASH_XSE_RE = re.compile(r"^\s*(?P<name>.+?\.dll)\s+v(?P<ver>[0-9][0-9.]*)", re.IGNORECASE)
_CRASH_PLUGIN_RE = re.compile(r"^\s*\[(?P<idx>[0-9A-Fa-f]{2}|FE:[0-9A-Fa-f]{3})\]\s+(?P<name>.+?)\s*$")

# ALL-CAPS section headers that terminate with a colon in Buffout/Addictol logs.
_CRASH_SECTION_RE = re.compile(r"^(?P<name>[A-Z][A-Z0-9 /]+):\s*$")


def _split_crash_sections(text: str) -> dict[str, list[str]]:
    """Split a crash log into {SECTION_NAME: [lines]} by ALL-CAPS headers.

    Lines before the first header land under the synthetic '_PREAMBLE' key
    (game/crash-generator banner + the exception line live there)."""
    sections: dict[str, list[str]] = {"_PREAMBLE": []}
    current = "_PREAMBLE"
    for raw in text.splitlines():
        m = _CRASH_SECTION_RE.match(raw)
        if m:
            current = m.group("name").strip()
            sections.setdefault(current, [])
            continue
        sections[current].append(raw)
    return sections


def parse_crash_log(text: str) -> dict[str, Any]:
    """Native parser for raw Buffout 4 / Addictol crash logs.

    This is the authoritative path: CLASSIC's native CLI is GUI-primary and
    does not expose a usable headless scan invocation (see
    research/p0/classic/2026-05-15-format-notes.md), so we parse the raw log
    the user always has rather than depending on CLASSIC's AUTOSCAN output.
    """
    sections = _split_crash_sections(text)
    warnings: list[str] = []

    crash_generator: dict[str, str] | None = None
    game_version: str | None = None
    exception: dict[str, Any] | None = None

    for line in sections.get("_PREAMBLE", []):
        s = line.strip()
        if game_version is None:
            mg = _CRASH_GAMEVER_RE.match(s)
            if mg:
                game_version = mg.group("ver")
                continue
        if crash_generator is None:
            mc = _CRASH_GENERATOR_RE.match(s)
            if mc:
                crash_generator = {"name": mc.group("name"), "version": mc.group("ver")}
                continue
        if exception is None:
            me = _CRASH_EXCEPTION_RE.search(s)
            if me:
                exception = {
                    "type":   me.group("type"),
                    "address": me.group("addr"),
                    "module": me.group("module"),
                    "offset": me.group("offset"),
                }

    # Probable call stack -> frames; non-engine modules are prime suspects.
    call_stack: list[dict[str, Any]] = []
    culprits: list[dict[str, Any]] = []
    for line in sections.get("PROBABLE CALL STACK", []):
        m = _CRASH_FRAME_RE.match(line)
        if m:
            frame = {
                "frame":  int(m.group("frame")),
                "module": m.group("module"),
                "offset": m.group("offset"),
            }
            call_stack.append(frame)
            if m.group("module").lower() != "fallout4.exe":
                culprits.append(frame)

    # XSE plugins.
    xse: list[dict[str, str]] = []
    for line in sections.get("XSE PLUGINS", []):
        m = _CRASH_XSE_RE.match(line)
        if m:
            xse.append({"name": m.group("name"), "version": m.group("ver")})

    # Plugin load order.
    plugins: list[dict[str, Any]] = []
    for line in sections.get("PLUGINS", []):
        m = _CRASH_PLUGIN_RE.match(line)
        if m:
            idx = m.group("idx")
            plugins.append({
                "load_index": idx,
                "name":       m.group("name").strip(),
                "light":      idx.upper().startswith("FE:"),
            })

    if exception is None:
        warnings.append("no 'Unhandled exception' line found — not a recognized crash log?")
    if not plugins:
        warnings.append("no PLUGINS section parsed")

    if culprits:
        verdict = f"probable culprit: {culprits[0]['module']} (call-stack frame {culprits[0]['frame']})"
    elif exception:
        verdict = f"crash in {exception.get('module') or 'unknown module'}; no third-party frame in call stack"
    else:
        verdict = "unable to determine culprit from this log"

    return {
        "crash_generator":   crash_generator,
        "game_version":      game_version,
        "exception":         exception,
        "probable_culprits": culprits,
        "call_stack_top":    call_stack[:8],
        "xse_plugins":       xse,
        "plugins":           plugins,
        "plugin_count":      len(plugins),
        "verdict":           verdict,
        "warnings":          warnings,
    }


def fo4_analyze_crash_log(cfg: Config, manifest: Manifest, crash_log_path: str) -> dict[str, Any]:
    """Parse a Buffout 4 / Addictol crash log into structured data.

    Strategy:
      1. Native parse of the raw crash log (authoritative — always available).
      2. CLASSIC is registered as an optional enricher but its native v9 CLI
         is GUI-primary with no usable headless scan entry point (probed
         Session 5), so we do not invoke it; `analyzer` reports "native".

    The native parser extracts: crash-generator + game version, the unhandled
    exception, probable-culprit modules from the call stack, XSE plugin
    versions, and the full plugin load order with ESL/light flags.
    """
    path = Path(crash_log_path)
    if not path.is_absolute():
        path = (cfg.repo_root / path).resolve()
    if not path.exists():
        raise Fo4McpError(
            ErrorCode.PATH_NOT_FOUND,
            f"crash log not found: {path}",
            {"crash_log_path": str(path)},
        )

    text = path.read_text(encoding="utf-8", errors="replace")
    parsed = parse_crash_log(text)
    parsed["crash_log"] = str(path)
    parsed["analyzer"] = "native"
    # CLASSIC presence is informational only; not invoked (GUI-primary CLI).
    classic = manifest.get("classic")
    parsed["classic_available"] = bool(classic and classic.is_resolved)
    return ok(parsed)


# ---- Helpers -----------------------------------------------------------------

def _require_tool(manifest: Manifest, slug: str):
    """Return the manifest entry for `slug`, raising if missing/unresolved."""
    entry = manifest.get(slug)
    if entry is None:
        raise ToolBinaryMissingError(slug, expected_path=None)
    if not entry.is_resolved:
        raise ToolBinaryMissingError(slug, expected_path=entry.binary_path)
    return entry
