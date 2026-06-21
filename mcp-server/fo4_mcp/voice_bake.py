"""fo4_bake_voice_assets — bake silent-subtitled voice (.fuz) assets headlessly (Faz 3 / W9).

The roadmap's W9 MVP is a fully-playable SUBTITLED quest with SILENT placeholder voice: every
dialogue line ships a real `.fuz` so the engine advances dialogue + shows the subtitle, with a
closed mouth (silent ≠ lip-synced speech — do NOT imply real lipsync). This is mechanical and
needs no microphone / GPU / human, so it is agent-automatable:

    silence WAV (pure-Python `wave`) --> LipGenerator.exe <16k.wav> "<text>"  -> <name>.lip
    silence WAV (44.1k)              --> xWMAEncode.exe <44k.wav> <name>.xwm   -> <name>.xwm
    FUZE pack (pure-Python)          : b"FUZE" + ver(1) + lipSize + lip + xwm -> .fuz

The per-line work-list (INFO FormID, response number, subtitle text, resolved voice-type, and the
canonical `.fuz` path) comes from the `voice-handoff` mutagen-cli verb (see tools._voice_handoff_list)
— this baker consumes that checklist and materializes the silent `.fuz` at each path:

    <out_root>/Sound/Voice/<plugin>/<VoiceTypeEditorID>/<INFO-FormID-8hex>_<respNum>.fuz

The `.fuz` filename embeds the INFO FormID, so bake AFTER FormID-lock (fo4_compact_formids). Real
voice acting / TTS replaces the silent track later (human/optional) but is NOT required to ship.

Toolchain: tools/ckpe/Tools/LipGen/LipGenerator/{LipGenerator.exe,xWMAEncode.exe,FonixData.cdf}
(verified present). LipGenerator needs FonixData.cdf in its CWD, so it is run with cwd=that folder.
Output is gated to the repo (staging/) via check_write; never the game folder.
"""

from __future__ import annotations

import struct
import wave
from pathlib import Path
from typing import Any

from .config import Config
from .errors import ErrorCode, Fo4McpError, ok
from .manifest import Manifest
from .safety import check_write

# LipGenerator wants 16-bit PCM mono at 8000 or 16000 Hz for phoneme analysis; the shipped audio
# track is conventionally 44100 Hz 16-bit PCM. Silent = all-zero samples.
_LIP_RATE = 16000
_XWM_RATE = 44100


def _lipgen_dir(cfg: Config) -> Path:
    return cfg.repo_root / "tools" / "ckpe" / "Tools" / "LipGen" / "LipGenerator"


def _write_silence(path: Path, seconds: float, rate: int) -> None:
    """Write a mono 16-bit PCM WAV of pure silence (zero samples)."""
    frames = max(1, int(seconds * rate))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)          # 16-bit
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * frames)


def _fuze_pack(lip: bytes, xwm: bytes) -> bytes:
    """Pack a .lip + .xwm into the FUZE container (magic 'FUZE', ver=1, lipSize, lip, xwm)."""
    return b"FUZE" + struct.pack("<I", 1) + struct.pack("<I", len(lip)) + lip + xwm


def _duration_for(text: str | None) -> float:
    """Subtitle display duration heuristic: ~2.3 words/sec reading speed, clamped 1.5..30s."""
    words = len((text or "").split())
    return min(30.0, max(1.5, words / 2.3))


def fo4_bake_voice_assets(
    cfg: Config,
    manifest: Manifest,
    plugin: str,
    *,
    out_root: str | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Bake one silent `.fuz` per dialogue line so the quest is fully playable subtitled (W9 MVP).

    Args:
        plugin:   path to the authored plugin (its dialogue lines are read via voice-handoff).
        out_root: writable root the Sound/Voice tree is written under (default: the plugin's dir).
                  Gated to the repo (staging/) — never the game folder.
        dry_run:  default True — resolve the toolchain + per-line plan and return it WITHOUT
                  invoking LipGenerator/xWMAEncode or writing any .fuz. Set False to actually bake.

    Returns ok({...}) with the per-line plan/results, a baked count, and any skipped lines
    (voice-type unresolved -> can't determine the folder; bake after setting the speaker's voice).
    """
    from .subprocess_wrap import run_tool
    from .tools import _voice_handoff_list, _mutagen_cli_binary

    plugin_path = Path(plugin)
    if not plugin_path.is_absolute():
        plugin_path = (cfg.repo_root / plugin_path).resolve()
    if not plugin_path.exists():
        raise Fo4McpError(
            ErrorCode.PATH_NOT_FOUND, f"plugin not found: {plugin_path}", {"plugin": str(plugin_path)})

    root = Path(out_root) if out_root else plugin_path.parent
    if not root.is_absolute():
        root = (cfg.repo_root / root).resolve()
    # fail-closed: the whole Sound/Voice tree must land inside the repo (staging/), not the game dir
    check_write(root, cfg.repo_root)

    lip_dir = _lipgen_dir(cfg)
    lipgen = lip_dir / "LipGenerator.exe"
    xwmaenc = lip_dir / "xWMAEncode.exe"
    fonix = lip_dir / "FonixData.cdf"
    if not (lipgen.exists() and xwmaenc.exists() and fonix.exists()):
        raise Fo4McpError(
            ErrorCode.TOOL_BINARY_MISSING,
            "voice toolchain missing under tools/ckpe/Tools/LipGen/LipGenerator/ "
            "(need LipGenerator.exe + xWMAEncode.exe + FonixData.cdf)",
            {"lipgen": str(lipgen)})
    if _mutagen_cli_binary(cfg, manifest) is None:
        raise Fo4McpError(
            ErrorCode.TOOL_BINARY_MISSING,
            "mutagen-cli not built (tools/mutagen-cli/) — required to read dialogue lines",
            {"tool": "mutagen-cli"})

    lines = _voice_handoff_list(cfg, manifest, plugin_path)
    planned: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    baked = 0

    import tempfile
    for ln in lines:
        fuz_rel = ln.get("fuzPath") or ""
        entry = {
            "info": ln.get("info"), "responseNumber": ln.get("responseNumber"),
            "voiceType": ln.get("voiceType"), "fuzPath": fuz_rel,
            "duration": round(_duration_for(ln.get("text")), 2),
        }
        if not ln.get("voiceTypeResolved"):
            skipped.append({**entry, "reason": "voice_type_unresolved"})
            continue
        dest = root / fuz_rel
        entry["dest"] = str(dest)
        if dry_run:
            planned.append(entry)
            continue

        # ---- actually bake this line's silent .fuz ----
        dur = _duration_for(ln.get("text"))
        text = (ln.get("text") or "...").replace('"', "'")
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            wav16 = tdp / "lip16k.wav"
            wav44 = tdp / "audio44k.wav"
            _write_silence(wav16, dur, _LIP_RATE)
            _write_silence(wav44, dur, _XWM_RATE)
            # LipGenerator writes <wav-basename>.lip next to the input; run with cwd=lip_dir so
            # FonixData.cdf resolves. Pass an absolute wav path + the transcript string.
            lg = run_tool(lipgen, [str(wav16), text], timeout=cfg.subprocess_timeout, cwd=lip_dir)
            lip_out = wav16.with_suffix(".lip")
            lip_bytes = lip_out.read_bytes() if lip_out.exists() else b""
            # xWMAEncode the 44.1k silence
            xwm_out = tdp / "audio.xwm"
            xe = run_tool(xwmaenc, [str(wav44), str(xwm_out)], timeout=cfg.subprocess_timeout)
            if not xwm_out.exists():
                skipped.append({**entry, "reason": "xwmaencode_failed",
                                "stderr_tail": xe.stderr[-300:]})
                continue
            fuz = _fuze_pack(lip_bytes, xwm_out.read_bytes())
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(fuz)
            baked += 1
            planned.append({**entry, "lipBytes": len(lip_bytes), "fuzBytes": len(fuz),
                            "lipOk": lip_out.exists(), "magic": fuz[:4].decode("latin-1")})

    return ok({
        "plugin":       str(plugin_path),
        "out_root":     str(root),
        "mode":         "silent",
        "dry_run":      dry_run,
        "line_count":   len(lines),
        "baked_count":  baked,
        "planned":      planned,
        "skipped":      skipped,
        "note": ("silent placeholder voice — closed mouth, NOT lip-synced speech; the quest is "
                 "fully playable subtitled. Replace with real recorded/TTS audio later (optional). "
                 "Bake AFTER fo4_compact_formids (the .fuz name embeds the INFO FormID)."),
    })
