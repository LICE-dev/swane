"""Unit tests for :mod:`swane.utils.last_pid_is_running`."""

import os

import swane.utils.last_pid_is_running as mod
from swane.utils.last_pid_is_running import last_pid_is_running


def test_invalid_pid_values():
    assert last_pid_is_running("not-a-number") is False
    assert last_pid_is_running(-1) is False
    assert last_pid_is_running(0) is False


def test_current_process_is_not_a_duplicate():
    assert last_pid_is_running(os.getpid(), 123.0) is False


class _FakeProcess:
    def __init__(self, pid):
        self.pid = pid

    def is_running(self):
        return True

    def status(self):
        return "running"

    def create_time(self):
        return 1000.0


def test_matching_creation_time_is_running(monkeypatch):
    monkeypatch.setattr(mod.psutil, "Process", _FakeProcess)
    other_pid = os.getpid() + 1
    assert last_pid_is_running(other_pid, 1000.0) is True
    # a different creation time means the PID was reused
    assert last_pid_is_running(other_pid, 5000.0) is False
