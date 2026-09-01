"""Regression tests for prerelease process failure and work-dir ownership."""

import json
import os
import queue
import signal
import socket
import sys
import time
import types
from types import SimpleNamespace

import pytest

from swane.nipype_pipeline.engine.WorkflowReport import WorkflowReport, WorkflowSignals
from swane.tests.prerelease import runner


def _pass_item(name="crashing_pass"):
    return SimpleNamespace(
        name=name,
        skipped=False,
        skip_reason="",
        inputs=[],
        values={},
        downgrades=[],
    )


class _ImmediateQueue:
    """Minimal queue whose empty read does not add a one-second test delay."""

    def __init__(self):
        self.items = []

    def put(self, item):
        self.items.append(item)

    def get(self, timeout=None):
        if not self.items:
            raise queue.Empty
        return self.items.pop(0)


class _FakeEvent:
    def set(self):
        return None


def test_process_death_without_workflow_stop_is_not_completed(monkeypatch, tmp_path):
    """A truncated pass stays red even after one node reported completion."""

    class DeadWorkflowProcess:
        def __init__(self, subject_name, workflow, signal_queue):
            self.signal_queue = signal_queue
            self.stop_event = _FakeEvent()
            self.exitcode = -11

        def start(self):
            self.signal_queue.put(
                WorkflowReport(
                    WorkflowSignals.NODE_STARTED,
                    "prerelease_wf.finished_before_crash",
                )
            )
            self.signal_queue.put(
                WorkflowReport(
                    WorkflowSignals.NODE_COMPLETED,
                    "prerelease_wf.finished_before_crash",
                )
            )

        def is_alive(self):
            return False

        def join(self, timeout=None):
            return None

        def terminate(self):
            return None

    fake_main_workflow = types.ModuleType("swane.nipype_pipeline.MainWorkflow")
    fake_main_workflow.MainWorkflow = lambda **kwargs: object()
    fake_workflow_process = types.ModuleType("swane.workers.WorkflowProcess")
    fake_workflow_process.WorkflowProcess = DeadWorkflowProcess
    monkeypatch.setitem(
        sys.modules, "swane.nipype_pipeline.MainWorkflow", fake_main_workflow
    )
    monkeypatch.setitem(
        sys.modules, "swane.workers.WorkflowProcess", fake_workflow_process
    )
    monkeypatch.setattr(runner, "Queue", _ImmediateQueue)
    monkeypatch.setattr(runner, "DependencyManager", lambda: object())
    monkeypatch.setattr(
        runner,
        "prepare_subject",
        lambda *args, **kwargs: (str(tmp_path), None, None, None),
    )

    result = runner.run_pass(
        _pass_item(),
        exam=object(),
        work_dir=str(tmp_path),
        cores=1,
        ram_gb=1.0,
        timeout_seconds=30,
    )

    assert result.nodes_completed == 1
    assert result.status == "error"
    assert "without WORKFLOW_STOP" in result.reason
    assert "-11" in result.reason


def test_work_dir_lock_rejects_a_second_owner(tmp_path):
    first = runner.PrereleaseWorkDirLock(str(tmp_path))

    with first:
        with pytest.raises(runner.PrereleaseAlreadyRunningError, match="already using"):
            runner.run_sweep(
                [], exam=object(), work_dir=str(tmp_path), cores=1, ram_gb=1.0
            )

    assert not (tmp_path / runner.LOCK_FILE).exists()


def test_work_dir_lock_retries_when_lock_vanishes_mid_acquire(tmp_path, monkeypatch):
    """A lock released in the _try_create/_read_owner window is retried, not failed.

    If the previous owner releases the lock just after this contender's
    ``_try_create()`` loses the race but before it reads the owner record, the
    file is gone. That must be read as "the slot is free now, retry", not as
    "the lock exists but is corrupt" -- otherwise a benign completion overlap
    fails a legitimate new sweep.
    """
    lock = runner.PrereleaseWorkDirLock(str(tmp_path))

    real_try_create = lock._try_create
    calls = {"n": 0}

    def flaky_try_create():
        calls["n"] += 1
        if calls["n"] == 1:
            # Lose the race as if another owner held the lock; that owner then
            # releases it, so no lock file exists when _read_owner() looks.
            return False
        return real_try_create()

    monkeypatch.setattr(lock, "_try_create", flaky_try_create)

    with lock:
        assert (tmp_path / runner.LOCK_FILE).exists()

    assert calls["n"] == 2
    assert not (tmp_path / runner.LOCK_FILE).exists()


def test_work_dir_lock_replaces_a_stale_pid(tmp_path):
    lock_path = tmp_path / runner.LOCK_FILE
    lock_path.write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "process_create_time": 0,
                "hostname": socket.gethostname(),
                "acquired_at": 0,
                "token": "stale-owner",
            }
        ),
        encoding="utf-8",
    )

    with runner.PrereleaseWorkDirLock(str(tmp_path)) as lock:
        owner = json.loads(lock_path.read_text(encoding="utf-8"))
        assert owner["token"] == lock.owner["token"]
        assert owner["token"] != "stale-owner"

    assert not lock_path.exists()


def _segfault_worker():
    """Terminate only the ProcessPool worker with the native crash signal."""
    os.kill(os.getpid(), signal.SIGSEGV)


@pytest.mark.skipif(os.name == "nt", reason="Nipype MultiProc requires POSIX")
def test_sigsegv_worker_fails_run_pass_without_waiting_for_timeout(
    monkeypatch, tmp_path
):
    """Exercise the real WorkflowProcess -> MultiProc callback failure path."""
    from nipype import Node, Workflow
    from nipype.interfaces.utility import Function

    subject_dir = tmp_path / "subject"
    subject_dir.mkdir()

    def build_crashing_workflow(name, base_dir, **kwargs):
        workflow = Workflow(name=name, base_dir=base_dir)
        crash_node = Node(
            Function(
                input_names=[],
                output_names=["unused"],
                function=_segfault_worker,
            ),
            name="ref_bias_correction",
        )
        workflow.add_nodes([crash_node])
        workflow.max_cpu = 1
        workflow.max_gpu = 0
        workflow.memory_gb = 1.0
        workflow.is_resource_monitor = False
        workflow.freesurfer = None
        workflow.config["execution"]["poll_sleep_duration"] = "0.1"
        return workflow

    fake_main_workflow = types.ModuleType("swane.nipype_pipeline.MainWorkflow")
    fake_main_workflow.MainWorkflow = build_crashing_workflow
    monkeypatch.setitem(
        sys.modules, "swane.nipype_pipeline.MainWorkflow", fake_main_workflow
    )
    monkeypatch.setattr(runner, "DependencyManager", lambda: object())
    monkeypatch.setattr(
        runner,
        "prepare_subject",
        lambda *args, **kwargs: (str(subject_dir), None, None, None),
    )

    started = time.monotonic()
    result = runner.run_pass(
        _pass_item("segfault_pass"),
        exam=object(),
        work_dir=str(tmp_path),
        cores=1,
        ram_gb=1.0,
        timeout_seconds=30,
    )
    elapsed = time.monotonic() - started

    assert elapsed < 10
    assert result.status == "failed"
    assert result.node_errors
    assert "ref_bias_correction" in result.reason
    assert "timed out" not in result.reason
