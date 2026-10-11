"""Tests for :mod:`swane.utils.main_workflow_preload`."""

import logging
import os
import subprocess
import sys
import textwrap
import threading
import pytest

from swane.utils import main_workflow_preload as preload

REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)


@pytest.fixture(autouse=True)
def _fresh_preload_state(monkeypatch):
    monkeypatch.setattr(preload, "_preload_thread", None)


class TestStartMainWorkflowPreload:

    def test_imports_on_a_background_daemon_thread(self, monkeypatch):
        calls = []
        release = threading.Event()

        def fake_import(name):
            calls.append((name, threading.current_thread()))
            release.wait(5)

        monkeypatch.setattr(preload.importlib, "import_module", fake_import)

        thread = preload.start_main_workflow_preload("swane._preload_test_dummy")
        # A second request while the first is still running reuses its thread
        assert preload.start_main_workflow_preload("swane._preload_test_dummy") is (
            thread
        )
        release.set()
        thread.join(5)

        assert not thread.is_alive()
        assert thread.daemon
        assert len(calls) == 1
        name, import_thread = calls[0]
        assert name == "swane._preload_test_dummy"
        assert import_thread is thread
        assert import_thread is not threading.main_thread()

    def test_already_imported_module_is_not_preloaded(self, monkeypatch):
        monkeypatch.setattr(
            preload.importlib,
            "import_module",
            lambda name: pytest.fail("unexpected import of " + name),
        )
        assert preload.start_main_workflow_preload("swane") is None

    def test_import_failure_is_logged_not_raised(self, monkeypatch, caplog):
        hook_calls = []
        monkeypatch.setattr(threading, "excepthook", hook_calls.append)

        with caplog.at_level(logging.WARNING, logger=preload.__name__):
            thread = preload.start_main_workflow_preload(
                "swane._missing_module_for_preload_test"
            )
            thread.join(5)

        assert not thread.is_alive()
        assert hook_calls == []
        assert any(
            "swane._missing_module_for_preload_test" in record.getMessage()
            and record.exc_info is not None
            for record in caplog.records
        )


# Runs in a fresh interpreter so MainWorkflow is not already imported by other
# tests. The repository-root conftest is executed first, as pytest does, to
# install the Windows pwd stub before swane/nipype are imported.
_RESULT_DIR_SCRIPT = textwrap.dedent("""
    import os, runpy, sys
    from types import SimpleNamespace

    runpy.run_path(os.path.join(sys.argv[1], "conftest.py"))

    from swane.utils import main_workflow_preload as preload
    from swane.utils.Subject import Subject

    assert preload.MAIN_WORKFLOW_MODULE not in sys.modules
    if sys.argv[2] == "preload":
        preload.start_main_workflow_preload().join(120)
        assert preload.MAIN_WORKFLOW_MODULE in sys.modules
    elif sys.argv[2] == "failed_preload":
        real_import_module = preload.importlib.import_module

        def failing_import(name):
            raise ImportError("simulated preload failure")

        preload.importlib.import_module = failing_import
        preload.start_main_workflow_preload().join(120)
        preload.importlib.import_module = real_import_module
        assert preload.MAIN_WORKFLOW_MODULE not in sys.modules

    class RecordingFinder:
        found = []

        def find_spec(self, name, path=None, target=None):
            self.found.append(name)
            return None

    sys.meta_path.insert(0, RecordingFinder())
    result_dir = Subject.result_dir(SimpleNamespace(folder="subject_folder"))
    from swane.nipype_pipeline.MainWorkflow import MainWorkflow

    assert result_dir == os.path.join("subject_folder", MainWorkflow.Result_DIR)
    print(preload.MAIN_WORKFLOW_MODULE in RecordingFinder.found)
    """)


@pytest.mark.parametrize(
    "mode, expect_import",
    [("preload", False), ("lazy", True), ("failed_preload", True)],
)
def test_result_dir_import_after_preload(mode, expect_import):
    """After the preload, result_dir finds MainWorkflow without importing it.

    The "lazy" control proves the finder does see the import when no preload
    ran, so the "preload" case cannot pass vacuously. "failed_preload" checks
    that a failed preload leaves result_dir on its lazy import fallback.
    """
    completed = subprocess.run(
        [sys.executable, "-c", _RESULT_DIR_SCRIPT, REPO_ROOT, mode],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip().splitlines()[-1] == str(expect_import)
