"""ck_run unit tests — direct coverage of the MO2-VFS CK launcher internals.

Previously run_ck_via_mo2 was exercised only INDIRECTLY (previs tests replace it
with a fake), so its real logic — ini parse, @ByteArray base_directory unwrap,
CreationKit custom-exec lookup, overwrite before/after diff, bounded proc poll,
and the ALWAYS-restore-ini finally — had zero direct tests. These do, with NO live
CK: ShellExecuteW / _proc_running / _kill are monkeypatched and every binary is a
b"MZ" stub on tmp_path. Also covers the substring->exact-field _proc_running fix.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import fo4_mcp.ck_run as ck_run
from fo4_mcp.ck_run import (
    _ck_entry_index,
    _proc_running,
    _read_base_directory,
    run_ck_via_mo2,
)
from fo4_mcp.config import Config
from fo4_mcp.errors import ErrorCode, Fo4McpError, ToolBinaryMissingError


# ---------------- fixtures / builders ----------------

def _cfg(tmp_path: Path, *, mo2: Path | None, install: Path | None) -> Config:
    return Config(
        repo_root=tmp_path, fo4_install_dir=install, fo4_user_docs=None,
        fo4_localappdata=None, mo2_instance_dir=mo2, tools_dir=tmp_path / "tools",
        log_level="INFO", subprocess_timeout=120,
    )


_INI_HEAD = "[General]\ngameName=Fallout 4\n"


def _ck_entry(idx: int = 1) -> str:
    return (
        f"[customExecutables]\n"
        f"{idx}\\title=CreationKit\n"
        f"{idx}\\binary=C:/MO2/ModOrganizer.exe\n"
        f"{idx}\\arguments=\n"
    )


def _make_mo2(tmp_path: Path, *, base_dir: Path | None = None,
              ini_body: str | None = None) -> tuple[Path, Path]:
    """Write a synthetic MO2 instance + a fake FO4 install with CreationKit.exe.

    Returns (mo2_dir, install_dir). base_dir defaults to mo2_dir/data so the
    overwrite diff has a real (empty) dir to scan.
    """
    mo2 = tmp_path / "mo2"
    mo2.mkdir(exist_ok=True)
    (mo2 / "ModOrganizer.exe").write_bytes(b"MZ")
    if base_dir is None:
        base_dir = mo2 / "data"
        base_dir.mkdir(exist_ok=True)
    if ini_body is None:
        ini_body = _INI_HEAD + f"base_directory={base_dir.as_posix()}\n" + _ck_entry(1)
    (mo2 / "ModOrganizer.ini").write_text(ini_body, encoding="utf-8")

    install = tmp_path / "Fallout 4"
    install.mkdir(exist_ok=True)
    (install / "CreationKit.exe").write_bytes(b"MZ")
    return mo2, install


# ---------------- _read_base_directory (pure file read) ----------------

def test_read_base_directory_plain(tmp_path):
    base = tmp_path / "portable-fo4-agentic"
    base.mkdir()
    ini = tmp_path / "ModOrganizer.ini"
    ini.write_text(f"base_directory={base.as_posix()}\n", encoding="utf-8")
    assert _read_base_directory(ini, tmp_path) == base


def test_read_base_directory_bytearray_unwrapped(tmp_path):
    base = tmp_path / "wrapped"
    base.mkdir()
    ini = tmp_path / "ModOrganizer.ini"
    ini.write_text(f"base_directory=@ByteArray({base.as_posix()})\n", encoding="utf-8")
    assert _read_base_directory(ini, tmp_path) == base


def test_read_base_directory_nonexistent_falls_back(tmp_path):
    ini = tmp_path / "ModOrganizer.ini"
    ini.write_text("base_directory=C:/nope/does/not/exist\n", encoding="utf-8")
    assert _read_base_directory(ini, tmp_path) == tmp_path


def test_read_base_directory_missing_line_falls_back(tmp_path):
    ini = tmp_path / "ModOrganizer.ini"
    ini.write_text("[General]\ngameName=Fallout 4\n", encoding="utf-8")
    assert _read_base_directory(ini, tmp_path) == tmp_path


def test_read_base_directory_case_insensitive(tmp_path):
    base = tmp_path / "casey"
    base.mkdir()
    ini = tmp_path / "ModOrganizer.ini"
    ini.write_text(f"Base_Directory={base.as_posix()}\n", encoding="utf-8")
    assert _read_base_directory(ini, tmp_path) == base


# ---------------- _ck_entry_index (pure) ----------------

def test_ck_entry_index_simple():
    lines = _ck_entry(1).splitlines()
    assert _ck_entry_index(lines) == 1


def test_ck_entry_index_multiple_execs():
    lines = (
        "1\\title=FO4Edit\n"
        "2\\title=F4SE\n"
        "3\\title=CreationKit\n"
    ).splitlines()
    assert _ck_entry_index(lines) == 3


def test_ck_entry_index_absent():
    lines = "1\\title=FO4Edit\n2\\title=F4SE\n".splitlines()
    assert _ck_entry_index(lines) is None


# ---------------- run_ck_via_mo2: missing-prereq guards ----------------

def test_run_ck_no_mo2_raises(tmp_path):
    _mo2, install = _make_mo2(tmp_path)
    with pytest.raises(Fo4McpError) as ei:
        run_ck_via_mo2(_cfg(tmp_path, mo2=None, install=install), ["-GenerateSEQ:M.esp"])
    assert ei.value.code == ErrorCode.ENV_FO4_NOT_DETECTED


def test_run_ck_missing_mo2_exe_raises(tmp_path):
    mo2 = tmp_path / "mo2"
    mo2.mkdir()  # no ModOrganizer.exe
    install = tmp_path / "Fallout 4"
    install.mkdir()
    (install / "CreationKit.exe").write_bytes(b"MZ")
    with pytest.raises(ToolBinaryMissingError):
        run_ck_via_mo2(_cfg(tmp_path, mo2=mo2, install=install), ["-GenerateSEQ:M.esp"])


def test_run_ck_missing_ini_raises(tmp_path):
    mo2 = tmp_path / "mo2"
    mo2.mkdir()
    (mo2 / "ModOrganizer.exe").write_bytes(b"MZ")  # no .ini
    install = tmp_path / "Fallout 4"
    install.mkdir()
    (install / "CreationKit.exe").write_bytes(b"MZ")
    with pytest.raises(ToolBinaryMissingError):
        run_ck_via_mo2(_cfg(tmp_path, mo2=mo2, install=install), ["-GenerateSEQ:M.esp"])


def test_run_ck_missing_ck_binary_raises(tmp_path):
    mo2, _install = _make_mo2(tmp_path)
    install = tmp_path / "install-no-ck"
    install.mkdir()  # no CreationKit.exe
    with pytest.raises(ToolBinaryMissingError):
        run_ck_via_mo2(_cfg(tmp_path, mo2=mo2, install=install), ["-GenerateSEQ:M.esp"])


def test_run_ck_no_creationkit_entry_raises(tmp_path):
    base = tmp_path / "data"
    base.mkdir()
    body = _INI_HEAD + f"base_directory={base.as_posix()}\n1\\title=F4SE\n"
    mo2, install = _make_mo2(tmp_path, base_dir=base, ini_body=body)
    with pytest.raises(Fo4McpError) as ei:
        run_ck_via_mo2(_cfg(tmp_path, mo2=mo2, install=install), ["-GenerateSEQ:M.esp"])
    assert ei.value.code == ErrorCode.INVALID_ARGUMENT


# ---------------- run_ck_via_mo2: runtime-monkeypatched paths ----------------

def _patch_clock(monkeypatch, ticks):
    """Deterministic time.monotonic (consumes `ticks`) + no-op sleep."""
    seq = iter(ticks)
    last = {"v": ticks[-1]}

    def _mono():
        try:
            last["v"] = next(seq)
        except StopIteration:
            pass
        return last["v"]

    monkeypatch.setattr(ck_run.time, "monotonic", _mono)
    monkeypatch.setattr(ck_run.time, "sleep", lambda *_a, **_k: None)


def _proc_seq(monkeypatch, values):
    """_proc_running returns successive `values`, repeating the last forever."""
    seq = iter(values)
    last = {"v": values[-1]}

    def _running(_name):
        try:
            last["v"] = next(seq)
        except StopIteration:
            pass
        return last["v"]

    monkeypatch.setattr(ck_run, "_proc_running", _running)


def _record_kills(monkeypatch):
    killed: list[str] = []
    monkeypatch.setattr(ck_run, "_kill", lambda name: killed.append(name))
    return killed


def _fake_shellexecute(monkeypatch, callback=None, rc=42):
    """Monkeypatch ShellExecuteW; optional callback() fires at launch time."""
    import ctypes

    def _se(*_a, **_k):
        if callback:
            callback()
        return rc

    monkeypatch.setattr(ctypes.windll.shell32, "ShellExecuteW", _se)


def test_run_ck_happy_path_writes_arguments_and_restores_ini(tmp_path, monkeypatch):
    base = tmp_path / "data"
    base.mkdir()
    mo2, install = _make_mo2(tmp_path, base_dir=base)
    ini = mo2 / "ModOrganizer.ini"
    original = ini.read_text(encoding="utf-8")

    captured = {}

    def _at_launch():
        # at launch time the ini holds the rewritten N\arguments line
        for line in ini.read_text(encoding="utf-8").splitlines():
            if line.startswith("1\\arguments="):
                captured["args"] = line.split("=", 1)[1]
        # bak must exist while the body runs
        captured["bak_exists"] = (mo2 / "ModOrganizer.ini.ckrunbak").exists()

    _patch_clock(monkeypatch, [0, 1, 2, 3, 4])
    _proc_seq(monkeypatch, [True, False])   # seen running -> gone == clean finish
    killed = _record_kills(monkeypatch)
    _fake_shellexecute(monkeypatch, callback=_at_launch)

    r = run_ck_via_mo2(_cfg(tmp_path, mo2=mo2, install=install),
                       ["-GenerateSEQ:M.esp", "extra"], poll=1)
    assert r["launched"] is True
    assert r["exited"] is True
    assert r["timed_out"] is False
    assert captured["args"] == "-GenerateSEQ:M.esp extra"
    assert captured["bak_exists"] is True
    # ini restored from bak, bak removed
    assert ini.read_text(encoding="utf-8") == original
    assert not (mo2 / "ModOrganizer.ini.ckrunbak").exists()
    assert "ModOrganizer.exe" in killed   # MO2 always killed at the end


def test_run_ck_overwrite_diff_lists_only_new_files(tmp_path, monkeypatch):
    base = tmp_path / "data"
    overwrite = base / "overwrite"
    overwrite.mkdir(parents=True)
    (overwrite / "preexisting.txt").write_text("old")
    mo2, install = _make_mo2(tmp_path, base_dir=base)

    def _create_output():
        (overwrite / "M.seq").write_text("new")

    _patch_clock(monkeypatch, [0, 1, 2, 3])
    _proc_seq(monkeypatch, [True, False])
    _record_kills(monkeypatch)
    _fake_shellexecute(monkeypatch, callback=_create_output)

    r = run_ck_via_mo2(_cfg(tmp_path, mo2=mo2, install=install), ["-GenerateSEQ:M.esp"], poll=1)
    assert r["overwrite_new"] == ["M.seq"]   # only the NEW file, not preexisting.txt


def test_run_ck_expected_outputs_and_ckpe_errors(tmp_path, monkeypatch):
    base = tmp_path / "data"
    overwrite = base / "overwrite"
    overwrite.mkdir(parents=True)
    mo2, install = _make_mo2(tmp_path, base_dir=base)
    ckpe = install / "ckpe.log"

    def _produce():
        (overwrite / "CombinedObjects.esp").write_text("x")
        ckpe.write_text("INFO loading\nERROR: something broke\nINFO done\n")

    _patch_clock(monkeypatch, [0, 1, 2, 3])
    _proc_seq(monkeypatch, [True, False])
    _record_kills(monkeypatch)
    _fake_shellexecute(monkeypatch, callback=_produce)

    r = run_ck_via_mo2(_cfg(tmp_path, mo2=mo2, install=install),
                       ["-GeneratePrecombined:M.esp"], poll=1,
                       expected_outputs=["CombinedObjects.esp", "Geometry.csg"])
    assert r["missing_outputs"] == ["Geometry.csg"]   # one present, one missing
    assert any("ERROR" in e for e in r["ckpe_errors"])
    assert r["artifacts_ok"] is False                 # missing + error


def test_run_ck_never_appeared_fast_op(tmp_path, monkeypatch):
    base = tmp_path / "data"
    base.mkdir()
    mo2, install = _make_mo2(tmp_path, base_dir=base)

    # started=0, appear_grace=180. Drive monotonic past 180 so the never-appeared
    # branch (time.monotonic() > appear_grace) breaks the loop. deadline=600.
    _patch_clock(monkeypatch, [0, 100, 200, 200])
    _proc_seq(monkeypatch, [False])           # never running
    killed = _record_kills(monkeypatch)
    _fake_shellexecute(monkeypatch)

    r = run_ck_via_mo2(_cfg(tmp_path, mo2=mo2, install=install), ["-GenerateSEQ:M.esp"], poll=1)
    assert r["exited"] is True
    assert r["timed_out"] is False
    assert "CreationKit.exe" not in killed     # never hung, no CK kill needed


def test_run_ck_hung_is_killed_and_timed_out(tmp_path, monkeypatch):
    base = tmp_path / "data"
    base.mkdir()
    mo2, install = _make_mo2(tmp_path, base_dir=base)

    # monotonic crosses deadline (600) so the while-loop exits with CK still running.
    _patch_clock(monkeypatch, [0, 100, 700, 700])
    _proc_seq(monkeypatch, [True])             # always running == hung
    killed = _record_kills(monkeypatch)
    _fake_shellexecute(monkeypatch)

    r = run_ck_via_mo2(_cfg(tmp_path, mo2=mo2, install=install), ["-GenerateSEQ:M.esp"], poll=1)
    assert r["timed_out"] is True
    assert r["exited"] is False
    assert "CreationKit.exe" in killed
    assert "ModOrganizer.exe" in killed


def test_run_ck_restores_ini_on_exception(tmp_path, monkeypatch):
    base = tmp_path / "data"
    base.mkdir()
    mo2, install = _make_mo2(tmp_path, base_dir=base)
    ini = mo2 / "ModOrganizer.ini"
    original = ini.read_text(encoding="utf-8")

    _patch_clock(monkeypatch, [0, 1, 2])
    _proc_seq(monkeypatch, [False])
    _record_kills(monkeypatch)
    _fake_shellexecute(monkeypatch, rc=0)   # rc<=32 -> run_ck_via_mo2 raises SUBPROCESS_FAILED

    with pytest.raises(Fo4McpError) as ei:
        run_ck_via_mo2(_cfg(tmp_path, mo2=mo2, install=install), ["-GenerateSEQ:M.esp"], poll=1)
    assert ei.value.code == ErrorCode.SUBPROCESS_FAILED
    # finally restored the ini from bak AND removed the bak
    assert ini.read_text(encoding="utf-8") == original
    assert not (mo2 / "ModOrganizer.ini.ckrunbak").exists()


# ---------------- _proc_running: exact-field match (substring fix) ----------------

def test_proc_running_exact_match_no_substring_false_positive(monkeypatch):
    """A CSV row whose image merely EMBEDS the target name must NOT match; an
    exact field-0 row must. The old `name in out` substring form would false-+."""
    import subprocess as _sp

    embed_csv = '"not-creationkit.exe","123","Console","1","30,000 K"\r\n'
    exact_csv = '"CreationKit.exe","456","Console","1","800,000 K"\r\n'

    class _Done:
        def __init__(self, out):
            self.stdout = out

    monkeypatch.setattr(_sp, "run", lambda *a, **k: _Done(embed_csv))
    assert "creationkit.exe" in embed_csv.lower()   # the substring trap the old code hit
    assert _proc_running("CreationKit.exe") is False

    monkeypatch.setattr(_sp, "run", lambda *a, **k: _Done(exact_csv))
    assert _proc_running("CreationKit.exe") is True


def test_proc_running_no_tasks_is_false(monkeypatch):
    import subprocess as _sp

    class _Done:
        stdout = "INFO: No tasks are running which match the specified criteria.\r\n"

    monkeypatch.setattr(_sp, "run", lambda *a, **k: _Done())
    assert _proc_running("CreationKit.exe") is False
