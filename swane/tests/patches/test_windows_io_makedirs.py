"""Windows shim for the folder race in Nipype's ``DataSink``.

``nipype.interfaces.io`` creates a sink folder with ``os.makedirs`` after an
``os.path.exists`` check and tolerates the ``OSError`` only when its
``strerror`` contains ``"File exists"``. Sibling ``SaveResults_*`` nodes that
share a results folder race on that check; Windows reports ``"Cannot create a
file when that file already exists"`` (WinError 183) and the losing node fails.

Windows is simulated without touching the global ``os.name``: only
``windows_compat.is_windows`` answers True, and the race is reproduced by
making the sink folder look absent to ``os.path.exists`` while ``os.makedirs``
fails on it with the Windows message.
"""

import os

import pytest
from nipype.interfaces import io as nipype_io
from nipype.interfaces.io import DataSink

import swane.patches.nipype_patches as npx
from swane.patches import windows_compat

posix_only = pytest.mark.skipif(
    os.name == "nt", reason="the shim is installed at import on Windows"
)

_REAL_MAKEDIRS = os.makedirs
_REAL_EXISTS = os.path.exists
_WINDOWS_MESSAGE = "Cannot create a file when that file already exists"


@pytest.fixture
def lost_race(monkeypatch, tmp_path):
    """A results folder another sink has just created: ``exists`` still says
    no, ``makedirs`` fails on it with the Windows message."""
    results = tmp_path / "results"
    results.mkdir()

    stale = [True]

    def stale_exists(path):
        # Lie once, for the sink's own pre-check: the window of the real race.
        if stale[0] and os.path.normcase(os.path.abspath(path)) == os.path.normcase(
            str(results)
        ):
            stale[0] = False
            return False
        return _REAL_EXISTS(path)

    def windows_makedirs(name, mode=0o777, exist_ok=False):
        if os.path.isdir(name) and not exist_ok:
            raise FileExistsError(183, _WINDOWS_MESSAGE, name)
        return _REAL_MAKEDIRS(name, mode, exist_ok)

    monkeypatch.setattr(os.path, "exists", stale_exists)
    monkeypatch.setattr(os, "makedirs", windows_makedirs)
    source = tmp_path / "in.txt"
    source.write_text("x")
    return results, source


def _sink(results, source):
    sink = DataSink()
    sink.inputs.base_directory = str(results)
    setattr(sink.inputs, "@file", str(source))
    return sink


@pytest.fixture
def simulated_windows(monkeypatch):
    monkeypatch.setattr(windows_compat, "is_windows", lambda: True)
    monkeypatch.setattr(nipype_io, "os", nipype_io.os)
    assert npx.install_windows_io_makedirs() is True


def test_stock_datasink_fails_on_the_windows_message(monkeypatch, lost_race):
    """Root cause: the stock sink only tolerates the POSIX message."""
    monkeypatch.setattr(nipype_io, "os", os)
    with pytest.raises(FileExistsError, match=_WINDOWS_MESSAGE):
        _sink(*lost_race).run()


def test_patched_datasink_survives_the_race(simulated_windows, lost_race):
    results, source = lost_race
    copied = _sink(results, source).run().outputs.out_file
    copied = copied if isinstance(copied, list) else [copied]
    assert len(copied) == 1
    assert os.path.commonpath([copied[0], str(results)]) == str(results)
    with open(copied[0]) as handle:
        assert handle.read() == "x"


def test_tolerant_makedirs_accepts_an_existing_directory(tmp_path):
    windows_compat.tolerant_makedirs(str(tmp_path))
    nested = tmp_path / "a" / "b"
    windows_compat.tolerant_makedirs(str(nested))
    assert nested.is_dir()


def test_tolerant_makedirs_still_rejects_an_existing_file(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("")
    with pytest.raises(FileExistsError):
        windows_compat.tolerant_makedirs(str(blocker))


def test_windows_os_delegates_everything_else():
    assert windows_compat.WINDOWS_OS.path is os.path
    assert windows_compat.WINDOWS_OS.sep == os.sep
    assert windows_compat.WINDOWS_OS.makedirs is windows_compat.tolerant_makedirs


@posix_only
def test_io_untouched_off_windows(monkeypatch):
    monkeypatch.setattr(windows_compat, "is_windows", lambda: False)
    assert npx.install_windows_io_makedirs() is False
    assert nipype_io.os is os
