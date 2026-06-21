"""fo4_inspect_save — pure-Python Fallout 4 save (.fos) parser.

READ-ONLY tool. Parses a FO4 savegame and returns a structured summary.
No external binary, no Java, no GUI — a small struct-cursor over the file
bytes. Never writes anything.

WHY pure-Python: ReSaver (the canonical GUI tool) is Java-only and Java
isn't installed here. The FO4 save header AND body are uncompressed, so a
faithful re-implementation of ReSaver's read path is the clean autonomous
route. Field layout below is derived directly from ReSaver source:

  tools/resaver/.../ess/Header.java  — header field order + types
  tools/resaver/.../ess/ESS.java     — body order, compression handling
  tools/resaver/.../ess/PluginInfo.java + Plugin.java — plugin tables
  tools/resaver/.../mf/BufferUtil.java — wstring (u16 len-prefixed) decode

KEY FORMAT FACTS (FO4-specific, verified against the above):

  * Fallout 4 saves are NOT compressed. Header.java sets `compression`
    only for SKYRIM_SE (line ~122: `compression = GAME == SKYRIM_SE
    ? CompressionType.read(input) : null`), and ESS.supportsCompression()
    returns false for FALLOUT4. The body therefore follows the screenshot
    bytes directly — there is no compressionType field in the FO4 header.
    (The original task spec assumed a header compression u16; that applies
    to Skyrim SE, not FO4. We still surface a `compression_type` field for
    a uniform shape — always "none" for genuine FO4 saves.)

  * All multi-byte integers are little-endian (ESS.java orders the buffer
    LITTLE_ENDIAN).

  * wstring = u16 length prefix + that many raw bytes (BufferUtil
    getWStringRaw). Player name / location / etc. decode UTF-8 in ReSaver
    (Plugin uses UTF_8; readSizedString uses UTF_8). We decode latin-1 /
    utf-8 tolerantly with errors="replace" so a malformed byte never
    crashes a read-only inspection.

HEADER LAYOUT (offsets are relative to file start; *=variable):
   0   magic            12 bytes  ascii "FO4_SAVEGAME"
  12   headerSize       u32       (size of the header block below, < 256)
  16   version          u32       (FO4: >= 11)
  20   saveNumber       u32
  24   playerName       wstring
   *   playerLevel      u32
   *   playerLocation   wstring
   *   gameDate         wstring
   *   playerRaceEditorId wstring
   *   playerSex        u16       (0 = male, 1 = female)
   *   playerCurExp     f32
   *   playerLvlUpExp   f32
   *   filetime         u64       (Windows FILETIME, 100ns since 1601)
   *   shotWidth        u32
   *   shotHeight       u32
  --- end of the `headerSize`-counted block ---
   *   screenshot       shotWidth * shotHeight * 4 bytes  (FO4 BYPP=4, RGBA)

BODY LAYOUT (immediately after screenshot; uncompressed for FO4):
   *   formVersion      u8        (FO4: >= 60)
   *   gameVersion      wstring   (e.g. "1.10.163.0")
   *   pluginInfoSize   u32
   *   numberOfFull     u8
   *   fullPlugins      numberOfFull * wstring
   --- if formVersion >= 68 (ESL support): ---
   *   numberOfLite     u16
   *   litePlugins      numberOfLite * wstring

(Everything after the plugin tables — file location table, change forms,
Papyrus — is out of scope for this summary tool.)

VERIFIED against a real AE save (Autosave1, runtime 1.11.169.0):
header version=15, headerSize=103, formVersion=69 (>=68 so an ESL table is
present), gameVersion="1.11.169.0", 7 full + 9 lite plugins — all decode
correctly with the offsets above. Note an early-game autosave can have an
EMPTY playerName (u16 length 0); callers must not assume it is non-empty.
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Any

from .config import Config
from .errors import ErrorCode, Fo4McpError, ok

FO4_MAGIC = b"FO4_SAVEGAME"
# formVersion threshold at/above which an ESL (lite) plugin table follows
# the full plugin table. From ESS.supportsESL(): FALLOUT4 => FORMVERSION >= 68.
_ESL_MIN_FORMVERSION = 68

_COMPRESSION_NAMES = {0: "none", 1: "zlib", 2: "lz4"}


class _Cursor:
    """Minimal little-endian struct reader over a bytes buffer.

    Raises ValueError on any out-of-bounds read so the caller can map it to
    a structured error instead of an IndexError / struct.error.
    """

    def __init__(self, data: bytes) -> None:
        self.data = data
        self.pos = 0

    def _need(self, n: int) -> None:
        if self.pos + n > len(self.data):
            raise ValueError(
                f"truncated save: need {n} bytes at offset {self.pos}, "
                f"only {len(self.data) - self.pos} remain"
            )

    def take(self, n: int) -> bytes:
        self._need(n)
        chunk = self.data[self.pos : self.pos + n]
        self.pos += n
        return chunk

    def u8(self) -> int:
        return self.take(1)[0]

    def u16(self) -> int:
        return struct.unpack_from("<H", self.take(2))[0]

    def u32(self) -> int:
        return struct.unpack_from("<I", self.take(4))[0]

    def u64(self) -> int:
        return struct.unpack_from("<Q", self.take(8))[0]

    def f32(self) -> float:
        return struct.unpack_from("<f", self.take(4))[0]

    def wstring(self) -> str:
        """u16 length-prefixed string. Decoded tolerantly (read-only tool)."""
        length = self.u16()
        raw = self.take(length)
        # ReSaver decodes plugin/header strings as UTF-8; fall back gracefully
        # so a non-UTF8 byte in a filename never aborts an inspection.
        return raw.decode("utf-8", errors="replace")


def _parse_fos_header(data: bytes) -> dict[str, Any]:
    """Parse a FO4 .fos save from raw bytes into a summary dict.

    Pure function — no I/O. Always returns the uncompressed header summary.
    For FO4 the body is uncompressed, so we also parse formVersion,
    gameVersion and the full + ESL plugin tables.

    Raises ValueError on bad magic or truncation.
    """
    if data[: len(FO4_MAGIC)] != FO4_MAGIC:
        raise ValueError(
            f"not a FO4 save (bad magic): "
            f"{data[: len(FO4_MAGIC)]!r} != {FO4_MAGIC!r}"
        )

    c = _Cursor(data)
    c.take(len(FO4_MAGIC))  # magic

    header_size = c.u32()
    version = c.u32()
    save_number = c.u32()
    player_name = c.wstring()
    player_level = c.u32()
    player_location = c.wstring()
    game_date = c.wstring()
    race = c.wstring()
    sex = c.u16()
    cur_exp = c.f32()
    lvlup_exp = c.f32()
    filetime = c.u64()
    shot_w = c.u32()
    shot_h = c.u32()

    notes: list[str] = []

    # FO4 BYPP = 4 (RGBA). Skip the screenshot block to reach the body.
    screenshot_len = shot_w * shot_h * 4
    c.take(screenshot_len)

    # FO4 saves are uncompressed (no header compression field — see module
    # docstring). We surface a uniform "compression_type" anyway.
    compression_code = 0
    compression_type = _COMPRESSION_NAMES[compression_code]

    result: dict[str, Any] = {
        "magic_ok": True,
        "save_version": version,
        "save_number": save_number,
        "player_name": player_name,
        "player_level": player_level,
        "player_location": player_location,
        "game_date": game_date,
        "race": race,
        "sex": sex,
        "screenshot": {"width": shot_w, "height": shot_h},
        "filetime": filetime,
        "compression_type": compression_type,
        "header_size": header_size,
        "current_exp": cur_exp,
        "levelup_exp": lvlup_exp,
        "form_version": None,
        "game_version": None,
        "plugin_count": None,
        "plugins": None,
        "light_plugin_count": None,
        "light_plugins": None,
        "notes": notes,
    }

    # ---- Body (uncompressed for FO4) -------------------------------------
    form_version = c.u8()
    game_version = c.wstring()
    result["form_version"] = form_version
    result["game_version"] = game_version

    c.u32()  # pluginInfoSize (size prefix; not needed for sequential read)
    full_count = c.u8()
    plugins = [c.wstring() for _ in range(full_count)]
    result["plugin_count"] = full_count
    result["plugins"] = plugins

    if form_version >= _ESL_MIN_FORMVERSION:
        lite_count = c.u16()
        light_plugins = [c.wstring() for _ in range(lite_count)]
        result["light_plugin_count"] = lite_count
        result["light_plugins"] = light_plugins
    else:
        notes.append(
            f"form_version {form_version} < {_ESL_MIN_FORMVERSION}: "
            "no ESL/light plugin table in this save"
        )

    return result


def fo4_inspect_save(cfg: Config, save_path: str) -> dict[str, Any]:
    """Parse a Fallout 4 .fos save and return a structured summary.

    READ-ONLY. Resolves `save_path` relative to cfg.repo_root if not absolute
    (saves are usually absolute under Documents/My Games/Fallout4/Saves). The
    .f4se co-save is a separate format and is rejected with a hint.
    """
    p = Path(save_path)
    if not p.is_absolute():
        p = (cfg.repo_root / p).resolve()

    if not p.exists():
        raise Fo4McpError(
            ErrorCode.PATH_NOT_FOUND,
            f"save not found: {p}",
            {"save_path": str(p)},
        )
    if not p.is_file():
        raise Fo4McpError(
            ErrorCode.PATH_NOT_FOUND,
            f"not a file: {p}",
            {"save_path": str(p)},
        )
    if p.suffix.lower() == ".f4se":
        raise Fo4McpError(
            ErrorCode.INVALID_ARGUMENT,
            ".f4se is an F4SE co-save (companion to a .fos), not a savegame "
            "itself; pass the matching .fos file instead",
            {"save_path": str(p)},
        )

    data = p.read_bytes()
    try:
        summary = _parse_fos_header(data)
    except ValueError as e:
        raise Fo4McpError(
            ErrorCode.INVALID_ARGUMENT,
            f"not a FO4 save (bad magic): {e}"
            if data[: len(FO4_MAGIC)] != FO4_MAGIC
            else str(e),
            {"save_path": str(p)},
        )

    summary["save_path"] = str(p)
    return ok(summary)
