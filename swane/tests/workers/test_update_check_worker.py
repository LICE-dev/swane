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
    captured = {}
    worker = UpdateCheckWorker()
    worker.signal.last_available.connect(emitted.append)

    def fake_run(cmd, stdout, stderr):
        captured["cmd"] = cmd
        captured["stderr"] = stderr
        return type("P", (), {"stdout": b"swane (9999.9.9)\n"})

    monkeypatch.setattr(subprocess, "run", fake_run)
    worker.run()

    assert emitted == ["9999.9.9"]
    # stderr is silenced cross-platform via DEVNULL, not the POSIX-only 2>/dev/null
    assert captured["stderr"] is subprocess.DEVNULL
    # argv list without a shell: interpreter paths with spaces are not split
    assert isinstance(captured["cmd"], list)
    assert captured["cmd"][1:] == ["-m", "pip", "index", "versions", "swane"]


def test_run_silent_when_up_to_date(monkeypatch):
    emitted = []
    worker = UpdateCheckWorker()
    worker.signal.last_available.connect(emitted.append)

    def fake_run(cmd, stdout, stderr):
        return type("P", (), {"stdout": b"swane (0.0.1)\n"})

    monkeypatch.setattr(subprocess, "run", fake_run)
    worker.run()

    assert emitted == []


def test_run_parses_crlf_output(monkeypatch):
    emitted = []
    worker = UpdateCheckWorker()
    worker.signal.last_available.connect(emitted.append)

    def fake_run(cmd, stdout, stderr):
        return type(
            "P", (), {"stdout": b"WARNING: x\r\nswane (9999.9.9)\r\n  Available\r\n"}
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    worker.run()

    assert emitted == ["9999.9.9"]
