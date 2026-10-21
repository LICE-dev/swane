"""Tests for the headless fallbacks of :mod:`swane.utils.qt_compat`.

Each test runs a private copy of the module with PySide6 made unimportable (see
:func:`swane.tests.helpers.qt_fallback.load_qt_compat_fallback`).
"""

import pytest

from swane.tests.helpers.qt_fallback import load_qt_compat_fallback


@pytest.fixture
def fallback(monkeypatch):
    return load_qt_compat_fallback(monkeypatch)


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
