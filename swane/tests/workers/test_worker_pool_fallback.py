"""``start_worker`` without a Qt binding runs the worker synchronously."""

import pytest

from swane.workers import worker_pool


@pytest.fixture
def headless(monkeypatch):
    monkeypatch.setattr(worker_pool, "QT_AVAILABLE", False)


def test_start_worker_runs_the_worker_synchronously(headless):
    ran = []

    class Worker:
        def run(self):
            ran.append(True)

    worker_pool.start_worker(Worker())
    assert ran == [True]


def test_start_worker_propagates_run_errors(headless):
    class Worker:
        def run(self):
            raise RuntimeError("synthetic run failure")

    with pytest.raises(RuntimeError, match="synthetic run failure"):
        worker_pool.start_worker(Worker())
