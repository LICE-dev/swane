"""Workers reach Qt only through :mod:`swane.utils.qt_compat`.

Importing PySide6 directly bypasses the headless fallback, so a worker module
could not even be imported where qt_compat falls back (PySide6 missing, or
crashing under pytest) while every other worker imports.
"""

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

import swane.workers
from swane.tests.helpers.qt_fallback import load_qt_compat_fallback

WORKERS_DIR = Path(swane.workers.__file__).parent


def _top_level_pyside6_imports(path):
    """Names of the PySide6 modules imported unconditionally by ``path``."""
    found = []
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Import):
            found += [a.name for a in node.names if a.name.split(".")[0] == "PySide6"]
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[0] == "PySide6":
                found.append(node.module)
    return found


@pytest.mark.parametrize(
    "worker", sorted(WORKERS_DIR.glob("*.py")), ids=lambda path: path.name
)
def test_worker_modules_do_not_import_pyside6_directly(worker):
    # Imports guarded by ``if QT_AVAILABLE`` (worker_pool) are not top level
    assert _top_level_pyside6_imports(worker) == []


def test_workflow_generate_worker_imports_under_the_fallback(monkeypatch):
    fallback = load_qt_compat_fallback(monkeypatch)
    monkeypatch.setitem(sys.modules, "swane.utils.qt_compat", fallback)

    # A private copy: the cached swane.workers module keeps the real Qt classes
    path = WORKERS_DIR / "WorkflowGenerateWorker.py"
    spec = importlib.util.spec_from_file_location("worker_under_fallback", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert issubclass(module.WorkflowGenerateWorker, fallback.QRunnable)
    received = []
    signals = module.WorkerSignals()
    signals.progress_msg.connect(received.append)
    signals.progress_msg.emit("loading")
    assert received == ["loading"]
