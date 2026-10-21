"""Tests for the headless fallbacks of :mod:`swane.utils.qt_compat`.

The fallback classes only exist in the module when PySide6 is missing, so each
test executes a private copy of the module with PySide6 made unimportable. This
exercises the fallback on every host, whether or not Qt is installed, and leaves
the real ``swane.utils.qt_compat`` untouched.
"""

import importlib.util
import subprocess
import sys
import types

import pytest

from swane.utils import qt_compat as real_qt_compat


@pytest.fixture
def fallback(monkeypatch):
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


def _signaler(fallback):
    class Signaler(fallback.QObject):
        first = fallback.Signal(int)
        second = fallback.Signal()

    return Signaler


def test_signal_slots_are_not_shared_between_instances(fallback):
    Signaler = _signaler(fallback)
    one, other = Signaler(), Signaler()
    received = []
    one.first.connect(received.append)

    other.first.emit(1)
    assert received == []

    one.first.emit(2)
    assert received == [2]


def test_signals_of_one_instance_are_independent(fallback):
    signaler = _signaler(fallback)()
    received = []
    signaler.first.connect(lambda *args: received.append("first"))

    signaler.second.emit()
    assert received == []

    signaler.first.emit(1)
    assert received == ["first"]


def test_signal_is_the_same_object_on_every_access(fallback):
    signaler = _signaler(fallback)()
    assert signaler.first is signaler.first
    assert isinstance(type(signaler).first, fallback.Signal)


def test_emit_passes_arguments_to_slots_in_connection_order(fallback):
    signaler = _signaler(fallback)()
    calls = []
    signaler.first.connect(lambda value: calls.append(("a", value)))
    signaler.first.connect(lambda value: calls.append(("b", value)))

    signaler.first.emit(5)
    assert calls == [("a", 5), ("b", 5)]


def test_emit_runs_every_slot_then_raises_the_first_error(fallback):
    signaler = _signaler(fallback)()
    calls = []

    def failing_first(value):
        calls.append("failing_first")
        raise AssertionError("first failure")

    def failing_second(value):
        calls.append("failing_second")
        raise ValueError("second failure")

    signaler.first.connect(failing_first)
    signaler.first.connect(failing_second)
    signaler.first.connect(lambda value: calls.append("last"))

    with pytest.raises(AssertionError, match="first failure"):
        signaler.first.emit(1)
    assert calls == ["failing_first", "failing_second", "last"]


def test_thread_pool_fallback_propagates_run_errors(fallback):
    class Runnable:
        def run(self):
            raise RuntimeError("synthetic run failure")

    with pytest.raises(RuntimeError, match="synthetic run failure"):
        fallback.QThreadPool.globalInstance().start(Runnable())


def test_thread_pool_fallback_runs_the_runnable_synchronously(fallback):
    ran = []

    class Runnable:
        def run(self):
            ran.append(True)

    fallback.QThreadPool.globalInstance().start(Runnable())
    assert ran == [True]
