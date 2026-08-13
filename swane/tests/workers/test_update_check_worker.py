"""Unit tests for :class:`swane.workers.UpdateCheckWorker`."""

import subprocess

from swane.workers.UpdateCheckWorker import UpdateCheckWorker


def test_is_newer_version():
    assert UpdateCheckWorker.is_newer_version("9999.0.0") is True
    assert UpdateCheckWorker.is_newer_version("0.0.1") is False
    # malformed input must not raise
    assert UpdateCheckWorker.is_newer_version("not-a-version") is False


def test_run_emits_when_newer_available(monkeypatch):
    emitted = []
    worker = UpdateCheckWorker()
    worker.signal.last_available.connect(emitted.append)

    def fake_run(cmd, shell, stdout):
        return type("P", (), {"stdout": b"swane (9999.9.9)\n"})

    monkeypatch.setattr(subprocess, "run", fake_run)
    worker.run()

    assert emitted == ["9999.9.9"]


def test_run_silent_when_up_to_date(monkeypatch):
    emitted = []
    worker = UpdateCheckWorker()
    worker.signal.last_available.connect(emitted.append)

    def fake_run(cmd, shell, stdout):
        return type("P", (), {"stdout": b"swane (0.0.1)\n"})

    monkeypatch.setattr(subprocess, "run", fake_run)
    worker.run()

    assert emitted == []
