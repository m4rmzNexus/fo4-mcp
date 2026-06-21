"""fo4_clean_save_changeforms — pure-Python Fallout 4 save (.fos) WRITE path.

GATED, destructive-class tool. Removes the orphaned ChangeForms left behind
when a plugin is uninstalled, then re-serializes a valid .fos. Backlog #16-A.

This module is a faithful extension of `save_inspect.py`'s read cursor into a
full BODY SPAN-WALKER plus a writer. No external binary, no Java, no GUI. The
FO4 save body is uncompressed (see save_inspect.py docstring + research/p0/
save-clean/2026-06-05-write-path.md), so the body is a flat little-endian
struct we can walk, edit, and re-emit byte-for-byte.

Field layout is derived directly from ReSaver source (Apache-2.0):

  ESS.java              body read ctor (170-515), linear write order (580-672),
                        getPluginFor (1095-1109), end-of-body assert (499-504)
  FileLocationTable.java  FLT on-disk field order + rebuild recipe (105-129)
  ChangeForm.java       on-disk layout + length-width-by-type-bits (48-138)
  GlobalData.java       u32 type + u32 size + size bytes (41-78)
  RefID.java            3-byte RefID: type bits (>>22 & 3) + 22-bit value

BODY LINEAR ORDER (what ESS.write emits, lines 580-672):
  u8   formVersion
  wstr gameVersion                       (FO4 only)
  PluginInfo  = u32 size, u8 fullCount, full wstr[],
                (if formVersion >= 68) u16 liteCount, lite wstr[]
  FLT         100 bytes (6 absolute offsets + 4 counts + 15 unused u32)
  GlobalDataTable1   (TABLE1COUNT blocks)
  GlobalDataTable2   (TABLE2COUNT blocks)
  ChangeForms        (changeFormCount entries)
  GlobalDataTable3   (TABLE3COUNT blocks; 1001 = Papyrus VM, left byte-identical)
  u32 formIDArrayCount + u32 formID[]
  u32 visitedWorldspaceCount + u32 worldspace[]
  UNKNOWN3           (trailing bytes, byte-preserved)

READ-vs-WRITE subtlety (spec §3): ESS *reads* the tables by seeking to the FLT
absolute offsets, but *writes* in the linear order above. Our walker reads in
linear order too (which is valid for genuine saves — the tables are physically
laid out in that order) and validates by reaching EOF exactly, mirroring
ESS.java's end-of-body assert (line 499-504). The writer re-emits in linear
order with a freshly rebuilt FLT.
"""

from __future__ import annotations

import json
import os
import struct
from pathlib import Path
from typing import Any

from .config import Config
from .errors import ErrorCode, Fo4McpError, ok
from .safety import check_write
from .save_inspect import FO4_MAGIC, _Cursor, _ESL_MIN_FORMVERSION
from .subprocess_wrap import run_tool

# RefID type codes (DATA >>> 22 & 0x3), per RefID.java getType().
_REFID_FORMIDX = 0
_REFID_DEFAULT = 1
_REFID_CREATED = 2
_REFID_INVALID = 3


# ---- Body span walker --------------------------------------------------------


class _SaveBody:
    """A fully-walked FO4 .fos body, with every block recorded as a byte span.

    `header` is the verbatim header+screenshot prefix (everything before the
    body). The body proper begins at `body_start`. Each table/array is held as
    raw on-disk bytes so a no-op re-serialize reproduces the file exactly.
    """

    def __init__(self, data: bytes) -> None:
        self.data = data

        if data[: len(FO4_MAGIC)] != FO4_MAGIC:
            raise ValueError(
                f"not a FO4 save (bad magic): {data[: len(FO4_MAGIC)]!r}"
            )

        c = _Cursor(data)
        # --- header block (magic .. screenshot) — preserved verbatim ---------
        c.take(len(FO4_MAGIC))
        c.u32()  # header_size
        c.u32()  # version
        c.u32()  # save_number
        c.wstring()  # player_name
        c.u32()  # player_level
        c.wstring()  # player_location
        c.wstring()  # game_date
        c.wstring()  # race
        c.u16()  # sex
        c.f32()  # cur_exp
        c.f32()  # lvlup_exp
        c.u64()  # filetime
        shot_w = c.u32()
        shot_h = c.u32()
        c.take(shot_w * shot_h * 4)  # screenshot (FO4 BYPP=4)

        self.body_start = c.pos
        self.header = data[: self.body_start]

        # --- body (uncompressed) --------------------------------------------
        self.form_version = c.u8()
        gv_start = c.pos
        self.game_version = c.wstring()
        self.game_version_bytes = data[gv_start : c.pos]

        plugin_start = c.pos
        c.u32()  # pluginInfoSize
        full_count = c.u8()
        self.full_plugins = [c.wstring() for _ in range(full_count)]
        self.has_lite = self.form_version >= _ESL_MIN_FORMVERSION
        self.lite_plugins: list[str] = []
        if self.has_lite:
            lite_count = c.u16()
            self.lite_plugins = [c.wstring() for _ in range(lite_count)]
        self.plugin_info_bytes = data[plugin_start : c.pos]

        # --- FLT (100 bytes) -------------------------------------------------
        flt_raw = c.take(100)
        flt = struct.unpack_from("<10I", flt_raw)
        (
            self._fid_count_offset,
            self._unknown3_offset,
            self._t1_offset,
            self._t2_offset,
            self._cf_offset,
            self._t3_offset,
            self.table1_count,
            self.table2_count,
            self.table3_count,
            self.change_form_count,
        ) = flt
        self.flt_unused = flt_raw[40:]  # 15 * u32 = 60 bytes, preserved verbatim

        # --- GlobalDataTable1 / 2 (opaque) ----------------------------------
        self.table1_bytes = self._take_globals(c, self.table1_count)
        self.table2_bytes = self._take_globals(c, self.table2_count)

        # --- ChangeForms -----------------------------------------------------
        self.change_forms: list[bytes] = []
        for _ in range(self.change_form_count):
            self.change_forms.append(self._take_changeform(c))

        # --- GlobalDataTable3 (opaque; 1001 Papyrus stays byte-identical) ----
        self.table3_bytes = self._take_globals(c, self.table3_count)

        # --- formID array ----------------------------------------------------
        fid_start = c.pos
        fid_count = c.u32()
        self.form_ids = [c.u32() for _ in range(fid_count)]
        self.form_id_array_bytes = data[fid_start : c.pos]

        # --- visited worldspace array ---------------------------------------
        ws_start = c.pos
        ws_count = c.u32()
        for _ in range(ws_count):
            c.u32()
        self.visited_worldspace_bytes = data[ws_start : c.pos]

        # --- UNKNOWN3 (trailing) --------------------------------------------
        self.unknown3 = data[c.pos :]

        # ACCEPTANCE: the walker must consume the body and reach EOF EXACTLY,
        # mirroring ESS.java's end-of-body assert (lines 499-504).
        consumed = c.pos + len(self.unknown3)
        if consumed != len(data):
            raise ValueError(
                f"walker did not reach EOF: consumed {consumed} of {len(data)} bytes"
            )

    @staticmethod
    def _take_globals(c: _Cursor, count: int) -> bytes:
        """Consume `count` GlobalData blocks (u32 type + u32 size + size bytes)
        and return their raw concatenated bytes."""
        start = c.pos
        for _ in range(count):
            c.u32()  # type
            block_size = c.u32()
            c.take(block_size)
        return c.data[start : c.pos]

    @staticmethod
    def _take_changeform(c: _Cursor) -> bytes:
        """Consume one ChangeForm and return its raw on-disk bytes.

        Layout (ChangeForm.java 48-138): RefID(3B) + changeFlags(u32) +
        type(u8) + version(u8) + length1 + length2 + rawData. The length1/
        length2 field WIDTH depends on the top 2 bits of the type byte
        (0->u8, 1->u16, 2->u32). rawData size on disk == length1 (the size of
        the bytes physically present); length2>0 only signals the body is
        individually zlib-compressed — we never decompress, just preserve.
        """
        start = c.pos
        c.take(3)  # RefID
        c.u32()  # changeFlags
        type_field = c.u8()
        c.u8()  # version
        width = type_field >> 6
        if width == 0:
            length1 = c.u8()
            c.u8()  # length2
        elif width == 1:
            length1 = c.u16()
            c.u16()  # length2
        elif width == 2:
            length1 = c.u32()
            c.u32()  # length2
        else:
            raise ValueError(f"invalid ChangeForm length-size bits: {width}")
        c.take(length1)  # rawData (size on disk = length1)
        return c.data[start : c.pos]

    # ---- writer -------------------------------------------------------------

    def serialize(self) -> bytes:
        """Re-emit the full file in ESS.write linear order with a rebuilt FLT.

        Header is byte-identical. With zero changeform removals this is a no-op
        re-serializer and MUST produce output identical to the input (the
        roundtrip oracle).
        """
        change_forms_bytes = b"".join(self.change_forms)

        # Rebuild the 100-byte FLT (FileLocationTable.rebuild, lines 105-129).
        # All 6 offsets are ABSOLUTE file offsets.
        t1_offset = (
            self.body_start
            + 1  # formVersion u8
            + len(self.game_version_bytes)
            + len(self.plugin_info_bytes)
            + 100  # FLT itself
        )
        t2_offset = t1_offset + len(self.table1_bytes)
        cf_offset = t2_offset + len(self.table2_bytes)
        t3_offset = cf_offset + len(change_forms_bytes)
        fid_count_offset = t3_offset + len(self.table3_bytes)
        unknown3_offset = (
            fid_count_offset
            + len(self.form_id_array_bytes)
            + len(self.visited_worldspace_bytes)
        )

        flt = struct.pack(
            "<10I",
            fid_count_offset,
            unknown3_offset,
            t1_offset,
            t2_offset,
            cf_offset,
            t3_offset,
            self.table1_count,
            self.table2_count,
            self.table3_count,
            len(self.change_forms),  # changeFormCount = live count
        ) + self.flt_unused

        out = bytearray()
        out += self.header
        out += struct.pack("<B", self.form_version)
        out += self.game_version_bytes
        out += self.plugin_info_bytes
        out += flt
        out += self.table1_bytes
        out += self.table2_bytes
        out += change_forms_bytes
        out += self.table3_bytes
        out += self.form_id_array_bytes
        out += self.visited_worldspace_bytes
        out += self.unknown3
        return bytes(out)


# ---- ChangeForm RefID -> plugin resolution -----------------------------------


def _changeform_refid(cf_bytes: bytes) -> int:
    """The 3-byte big-endian RefID DATA at the start of a ChangeForm.

    RefID.write emits DATA>>16, DATA>>8, DATA>>0 (big-endian 3 bytes).
    """
    return (cf_bytes[0] << 16) | (cf_bytes[1] << 8) | cf_bytes[2]


def _refid_plugin_index(refid_data: int, form_ids: list[int]) -> int | None:
    """Resolve a ChangeForm's RefID to a full-plugin load-order index, or the
    sentinel 0xFE for ESL/lite, or 0xFF for CREATED. Returns None if it does
    not resolve to a plugin we can name (zero / invalid / out-of-range FORMIDX).

    Per RefID.java + ESS.getPluginFor:
      type = (DATA >>> 22) & 0x3
      FORMIDX -> formIDs[(DATA & 0x3FFFFF) - 1] -> full formID -> high byte index
      CREATED -> 0xFF (created-in-this-save plugin)
      DEFAULT -> full plugin index 0
    """
    val = refid_data & 0x3FFFFF
    if val == 0:
        return None  # zero RefID
    rtype = (refid_data >> 22) & 0x3

    if rtype == _REFID_DEFAULT:
        return 0
    if rtype == _REFID_CREATED:
        return 0xFF
    if rtype == _REFID_FORMIDX:
        idx = val - 1
        if 0 <= idx < len(form_ids):
            return form_ids[idx] >> 24
        return None
    return None  # INVALID


# ---- The tool ----------------------------------------------------------------


def _resolve_plugin_indices(
    body: _SaveBody, plugins: list[str]
) -> tuple[set[int], list[str]]:
    """Map each named plugin to its load-order INDEX using the save's own
    plugin tables. Full plugins -> their position in the full list. ESL/lite
    plugins -> 0xFE with the subindex packed in. Returns (index_set, missing).

    For ESL plugins we encode the resolved index as 0xFE00 + subindex so it can
    be compared against a changeform's resolved (0xFE, subindex) without
    collision with a real full-plugin byte index.
    """
    indices: set[int] = set()
    missing: list[str] = []
    full_lc = [p.lower() for p in body.full_plugins]
    lite_lc = [p.lower() for p in body.lite_plugins]
    for name in plugins:
        nl = name.lower()
        if nl in full_lc:
            indices.add(full_lc.index(nl))
        elif nl in lite_lc:
            indices.add(0xFE00 + lite_lc.index(nl))
        else:
            missing.append(name)
    return indices, missing


def _changeform_target_index(cf_bytes: bytes, body: _SaveBody) -> int | None:
    """Resolve a ChangeForm to the same index space _resolve_plugin_indices
    uses: a full-plugin byte index (0..0xFD), 0xFE00+subindex for ESL, 0xFF for
    CREATED, or None if it does not map to a nameable plugin."""
    refid = _changeform_refid(cf_bytes)
    idx = _refid_plugin_index(refid, body.form_ids)
    if idx is None:
        return None
    if idx == 0xFE:
        # ESL: recover the full formID to get the subindex.
        val = refid & 0x3FFFFF
        rtype = (refid >> 22) & 0x3
        if rtype != _REFID_FORMIDX:
            return None
        form_id = body.form_ids[val - 1]
        subindex = (form_id & 0xFFFFFF) >> 12
        return 0xFE00 + subindex
    return idx


def fo4_clean_save_changeforms(
    cfg: Config,
    save_path: str,
    output_path: str,
    *,
    plugins: list[str],
    confirm: bool = False,
) -> dict[str, Any]:
    """Remove ChangeForms belonging to named (uninstalled) plugins and write a
    cleaned .fos. Pure-Python; destructive-class so gated by `confirm`.

    GATES return a clear ok-style refusal envelope (not an exception):
      * `plugins` must be a non-empty list — we NEVER auto-pick which plugins.
      * `confirm` must be True — writing a save is destructive.

    The output is safety-gated to staging/fixtures (check_write runs FIRST, so a
    forbidden path fails closed BEFORE any file existence check). An existing
    output is backed up to .bak. The source is read-only.
    """
    if not plugins:
        return {
            "refused": True,
            "reason": "plugins must be a non-empty list; this tool never "
            "auto-picks which plugins to clean — name the uninstalled plugin(s)",
        }
    if not confirm:
        return {
            "refused": True,
            "reason": "writing a save is destructive; pass confirm=True after "
            "backing up (run fo4_backup_saves first)",
        }

    out = Path(output_path)
    if not out.is_absolute():
        out = (cfg.repo_root / out).resolve()
    check_write(out, cfg.repo_root)  # raises PathForbiddenError on DENY — fail closed FIRST

    src = Path(save_path)
    if not src.is_absolute():
        src = (cfg.repo_root / src).resolve()
    if not src.exists():
        raise Fo4McpError(
            ErrorCode.PATH_NOT_FOUND, f"save not found: {src}", {"save_path": str(src)}
        )

    data = src.read_bytes()
    try:
        body = _SaveBody(data)
    except ValueError as e:
        raise Fo4McpError(
            ErrorCode.INVALID_ARGUMENT, str(e), {"save_path": str(src)}
        )

    target_indices, missing = _resolve_plugin_indices(body, plugins)
    if missing:
        return {
            "refused": True,
            "reason": f"plugin(s) not present in this save: {missing}",
            "present_full_plugins": body.full_plugins,
            "present_lite_plugins": body.lite_plugins,
        }

    survivors: list[bytes] = []
    removed = 0
    for cf in body.change_forms:
        idx = _changeform_target_index(cf, body)
        if idx is not None and idx in target_indices:
            removed += 1
        else:
            survivors.append(cf)
    body.change_forms = survivors

    out.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    if out.exists():
        backup = out.with_suffix(out.suffix + ".bak")
        backup.write_bytes(out.read_bytes())

    cleaned = body.serialize()
    out.write_bytes(cleaned)

    warning = (
        "ChangeForm removal is damage control, not a clean uninstall; verify the "
        "save loads in-game. Papyrus VM (block 1001) is left untouched — orphaned "
        "script instances are handled by a separate tool."
    )

    return ok({
        "save_path": str(src),
        "output_path": str(out),
        "removed_count": removed,
        "removed_plugins": list(plugins),
        "kept_changeform_count": len(survivors),
        "bak_path": str(backup) if backup else None,
        "warning": warning,
    })


# ---- Papyrus-VM cleaning via the ReSaver (Apache-2.0) Java shim (#16-B) -------


def _resolve_papyrus_shim(cfg: Config) -> dict[str, str] | None:
    """Resolve the headless ReSaver shim toolchain, or None if not built.

    Needs three things under the (gitignored) tools/ tree: a JDK java.exe, the
    compiled CleanShim.jar, and the ReSaver.jar + its lib/ deps. Absence is not
    an error — the whole Papyrus layer is an optional, download-gated backend.
    """
    java = next((cfg.tools_dir / "jdk").glob("*/bin/java.exe"), None)
    shim = cfg.tools_dir / "resaver-shim" / "CleanShim.jar"
    resaver = cfg.tools_dir / "resaver" / "target" / "ReSaver.jar"
    lib = cfg.tools_dir / "resaver" / "target" / "lib"
    if java is None or not shim.exists() or not resaver.exists():
        return None
    # Classpath: shim + ReSaver + every dep jar (lib wildcard, Java-expanded).
    classpath = os.pathsep.join([str(shim), str(resaver), f"{lib}/*"])
    return {"java": str(java), "classpath": classpath}


def fo4_clean_save_papyrus(
    cfg: Config,
    save_path: str,
    output_path: str,
    *,
    mode: str,
    confirm: bool = False,
    accept_unattached_risk: bool = False,
) -> dict[str, Any]:
    """Remove orphaned Papyrus-VM elements from a .fos and write a cleaned save,
    by driving ReSaver's (Apache-2.0) battle-tested engine headlessly. #16-B.

    The Papyrus VM (save GlobalData block 1001) is a deeply cross-referenced
    graph; we do NOT reimplement it in Python (that is what fo4_clean_save_
    changeforms does for the flat change-form list). Instead a ~90-line Java
    shim calls ESS.readESS -> Papyrus.remove*{Undefined,Unattached} ->
    ESS.writeESS, then re-reads its own output as a corruption oracle.

    mode:
      "undefined"  — remove elements whose defining script/plugin is gone
                     (the safer class; the usual post-uninstall cleanup).
      "unattached" — remove script instances with no attached reference.
                     WARNING: unattached instances are ENGINE-NORMAL in FO4, so
                     removing them can corrupt an otherwise-good save. Requires
                     accept_unattached_risk=True on top of confirm.

    Gated like the rest of the save layer: confirm=True, output safety-gated to
    staging/fixtures (check_write runs FIRST), source read-only. ReSaver writes
    its own timestamped .bak if the output already exists. Run fo4_backup_saves
    first. Returns a refusal envelope (not an exception) when the shim toolchain
    is not built (JDK + CleanShim.jar download-gated).
    """
    if mode not in ("undefined", "unattached"):
        return {"refused": True, "reason": "mode must be 'undefined' or 'unattached'"}
    if mode == "unattached" and not accept_unattached_risk:
        return {
            "refused": True,
            "reason": "unattached instances are engine-NORMAL in FO4; removing "
            "them can corrupt a good save. Pass accept_unattached_risk=True only "
            "if you understand this and have a backup.",
        }
    if not confirm:
        return {
            "refused": True,
            "reason": "writing a save is destructive; pass confirm=True after "
            "backing up (run fo4_backup_saves first)",
        }

    out = Path(output_path)
    if not out.is_absolute():
        out = (cfg.repo_root / out).resolve()
    check_write(out, cfg.repo_root)  # raises PathForbiddenError on DENY — fail closed FIRST

    src = Path(save_path)
    if not src.is_absolute():
        src = (cfg.repo_root / src).resolve()
    if not src.exists():
        raise Fo4McpError(
            ErrorCode.PATH_NOT_FOUND, f"save not found: {src}", {"save_path": str(src)}
        )

    shim = _resolve_papyrus_shim(cfg)
    if shim is None:
        return {
            "refused": True,
            "reason": "ReSaver shim toolchain not built. Needs a JDK under "
            "tools/jdk/, tools/resaver-shim/CleanShim.jar, and tools/resaver/ "
            "(ReSaver.jar + lib). See research/p0/save-clean/2026-06-05-write-path.md.",
        }

    out.parent.mkdir(parents=True, exist_ok=True)
    result = run_tool(
        shim["java"],
        ["-cp", shim["classpath"], "fo4mcp.CleanShim",
         "--in", str(src), "--out", str(out), "--op", mode],
        timeout=max(cfg.subprocess_timeout, 600),
    )
    if result.exit_code != 0 or not result.stdout.strip():
        raise Fo4McpError(
            ErrorCode.SUBPROCESS_FAILED,
            "ReSaver shim failed to clean the save",
            {"exit_code": result.exit_code, "stderr_tail": result.stderr[-1500:]},
        )

    report = json.loads(result.stdout.strip().splitlines()[-1])
    warning = (
        "Papyrus-VM cleaning is damage control, not a clean uninstall; load the "
        "save in-game to verify. "
        + ("UNATTACHED removal is risky in FO4 (engine-normal instances) — double-"
           "check the save still works." if mode == "unattached" else
           "")
    ).strip()

    return ok({
        "save_path":     str(src),
        "output_path":   str(out),
        "mode":          mode,
        "removed_count": report.get("removed_count"),
        "reread_ok":     report.get("reread_ok"),
        "before":        report.get("before"),
        "after":         report.get("after"),
        "backend":       "resaver-shim",
        "warning":       warning,
    })


def reserialize_save(data: bytes) -> bytes:
    """No-op re-serializer used by the roundtrip oracle: walk the body and
    re-emit with zero removals. MUST be byte-identical to the input for a
    genuine .fos. Raises ValueError if the walker fails to reach EOF."""
    return _SaveBody(data).serialize()
