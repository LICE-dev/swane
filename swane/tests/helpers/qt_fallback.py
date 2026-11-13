"""Load a private copy of :mod:`swane.utils.qt_compat` in its headless fallback mode.

The fallback classes only exist when PySide6 is missing, so the copy is executed
with PySide6 made unimportable. This exercises the fallback on every host,
whether or not Qt is installed, and leaves the real module untouched.
"""

import importlib.util
import subprocess
import sys
import types

from swane.utils import qt_compat as real_qt_compat


def load_qt_compat_fallback(monkeypatch):
    """Return a fresh ``qt_compat`` module that runs on its headless fallbacks.

    Everything it patches (``subprocess.run``, the PySide6 entries of
    ``sys.modules``) is restored by ``monkeypatch`` at test teardown.
    """
    # The pytest-only subprocess probe is irrelevant here: PySide6 is blocked below
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: types.SimpleNamespace(returncode=0)
    )
    # Qt may already be imported: block the submodule the module asks for too
    monkeypatch.setitem(sys.modules, "PySide6", None)
    monkeypatch.setitem(sys.modules, "PySide6.QtCore", None)
    spec = importlib.util.spec_from_file_location(
        "qt_compat_fallback_under_test", real_qt_compat.__file__
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.QT_AVAILABLE is False
    return module
