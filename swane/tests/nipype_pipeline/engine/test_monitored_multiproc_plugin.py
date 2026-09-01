"""Unit tests for the insufficient-resources signaling in
:class:`~swane.nipype_pipeline.engine.MonitoredMultiProcPlugin.MonitoredMultiProcPlugin`.

``_prerun_check()`` is nipype's own pre-flight gate: before a workflow
starts, it compares every node's declared ``mem_gb`` / ``n_procs`` / GPU need
against the plugin's budget and raises ``RuntimeError`` if any single node's
requirement can never be satisfied (not "the queue is full right now", but
"this can never be scheduled with this budget"). ``MonitoredMultiProcPlugin``
wraps that check to also put a ``WORKFLOW_INSUFFICIENT_RESOURCES`` report on
the signaling queue before re-raising -- that is what lets SWANe's UI (and
the pre-release sweep, see ``tests/prerelease/runner.py``) surface the
failure to the user instead of it disappearing into a stack trace inside the
workflow subprocess.

These tests drive ``_prerun_check`` directly against a minimal fake
graph/node, for all three budgets (CPU threads, RAM, GPU slots), without
spinning up nipype's real process pools or building an actual workflow.
"""

from concurrent.futures import Future
from concurrent.futures.process import BrokenProcessPool
from multiprocessing import Queue
from types import SimpleNamespace

import pytest

# nipype's MultiProcPlugin (the base class under test) imports the Unix-only
# ``pwd`` module transitively (via its sge plugin), so it cannot be imported on
# Windows — where MonitoredMultiProcPlugin falls back to ``object`` and cannot be
# constructed. Skip the whole module with a clear reason there: workflow
# execution (and this plugin) only runs on Linux/macOS.
try:
    from nipype.pipeline.plugins.multiproc import (
        MultiProcPlugin as _RealMultiProcPlugin,
    )  # noqa: F401
except Exception as _exc:  # pragma: no cover - platform dependent
    pytest.skip(
        "nipype MultiProcPlugin unavailable in this environment (%s)" % _exc,
        allow_module_level=True,
    )

from swane.nipype_pipeline.engine.MonitoredMultiProcPlugin import (
    MonitoredMultiProcPlugin,
)
from swane.nipype_pipeline.engine.WorkflowReport import WorkflowSignals


class _FakeNode:
    """Stands in for a nipype ``Node``: only what ``_prerun_check`` reads."""

    def __init__(self, mem_gb=0.1, n_procs=1, gpu=False):
        self.mem_gb = mem_gb
        self.n_procs = n_procs
        self._gpu = gpu

    def is_gpu_node(self):
        return self._gpu


class _FakeGraph:
    """Stands in for the networkx graph ``_prerun_check`` iterates."""

    def __init__(self, nodes):
        self._nodes = nodes

    def nodes(self):
        return self._nodes


@pytest.fixture
def make_plugin():
    """Build a :class:`MonitoredMultiProcPlugin` with a small, explicit budget.

    Yields a ``(plugin, queue)`` pair and shuts the plugin's process pool
    down afterwards -- ``MultiProcPlugin.__init__`` allocates a real
    ``ProcessPoolExecutor``, which must be released or it leaks workers
    across the test session.
    """
    created = []

    def _make(**budget):
        queue = Queue()
        plugin_args = {"n_procs": 4, "memory_gb": 8.0, "n_gpu_procs": 1}
        plugin_args.update(budget)
        plugin_args["queue"] = queue
        plugin = MonitoredMultiProcPlugin(plugin_args=plugin_args)
        created.append(plugin)
        return plugin, queue

    yield _make

    for plugin in created:
        plugin.pool.shutdown(wait=False, cancel_futures=True)


class TestPrerunCheckSignalsInsufficientResources:
    """Each budget (RAM, CPU threads, GPU slots) is checked independently."""

    def test_ram_over_budget_raises_and_signals(self, make_plugin):
        plugin, queue = make_plugin(memory_gb=1.0)
        graph = _FakeGraph([_FakeNode(mem_gb=2.0)])

        with pytest.raises(RuntimeError):
            plugin._prerun_check(graph)

        report = queue.get(timeout=5)
        assert report.signal_type == WorkflowSignals.WORKFLOW_INSUFFICIENT_RESOURCES

    def test_cores_over_budget_raises_and_signals(self, make_plugin):
        plugin, queue = make_plugin(n_procs=1)
        graph = _FakeGraph([_FakeNode(n_procs=4)])

        with pytest.raises(RuntimeError):
            plugin._prerun_check(graph)

        report = queue.get(timeout=5)
        assert report.signal_type == WorkflowSignals.WORKFLOW_INSUFFICIENT_RESOURCES

    def test_gpu_over_budget_raises_and_signals(self, make_plugin):
        plugin, queue = make_plugin(n_gpu_procs=0)
        graph = _FakeGraph([_FakeNode(n_procs=1, gpu=True)])

        with pytest.raises(RuntimeError):
            plugin._prerun_check(graph)

        report = queue.get(timeout=5)
        assert report.signal_type == WorkflowSignals.WORKFLOW_INSUFFICIENT_RESOURCES

    def test_within_every_budget_does_not_raise_or_signal(self, make_plugin):
        plugin, queue = make_plugin()
        graph = _FakeGraph([_FakeNode(mem_gb=1.0, n_procs=2, gpu=False)])

        plugin._prerun_check(graph)  # must not raise

        assert queue.empty()

    def test_gpu_node_within_budget_does_not_raise(self, make_plugin):
        """A GPU node that fits the GPU slot budget must not be flagged."""
        plugin, queue = make_plugin(n_gpu_procs=1)
        graph = _FakeGraph([_FakeNode(n_procs=1, gpu=True)])

        plugin._prerun_check(graph)  # must not raise

        assert queue.empty()


def _register_task(plugin, taskid, node_name):
    """Wire one in-flight task into the plugin's bookkeeping, as _submit_job does."""
    future = Future()
    plugin._task_obj[taskid] = future
    plugin._task_nodes[taskid] = node_name
    plugin._future_taskids[future] = taskid
    return future


def test_broken_process_pool_callback_feeds_every_in_flight_task(make_plugin):
    """A native worker crash must become observable outside the callback.

    ``Future.result()`` raises in Nipype's done-callback. Without SWANe's
    interception, concurrent.futures only logs that exception and Nipype keeps
    polling forever. Because the pool marks *all* in-flight futures broken at
    once and there is no way to tell which node actually crashed, every pending
    task must receive a terminal result -- otherwise the tasks whose own
    callback cannot resolve a task id keep Nipype waiting for a result that can
    never appear.
    """
    plugin, queue = make_plugin()

    futures = {
        taskid: _register_task(plugin, taskid, name)
        for taskid, name in (
            (17, "prerelease_wf.ref_bias_correction"),
            (18, "prerelease_wf.innocent_neighbour"),
            (19, "prerelease_wf.another_neighbour"),
        )
    }
    # A single worker dies by signal; concurrent.futures then marks the whole
    # pool broken, so any of the three callbacks may fire first.
    crasher = futures[18]
    crasher.set_exception(BrokenProcessPool("worker terminated abruptly"))

    plugin._async_callback(crasher)

    for taskid in (17, 18, 19):
        result = plugin._taskresult[taskid]
        assert result["taskid"] == taskid
        assert result["traceback"]
        # No sentinel flag: each result must flow through the normal crash path
        # so its NODE_ERROR carries the crash file and the real node name.
        assert "_swane_node_error_reported" not in result

    # The callback itself does not emit NODE_ERROR (Nipype's poll loop does,
    # via _report_crash) and no longer force-stops the workflow process.
    assert queue.empty()


def test_broken_process_pool_reports_each_in_flight_node_via_report_crash(
    make_plugin, monkeypatch
):
    """The fed results route through _report_crash, tagging the broken-pool reason.

    This is the emission path a real run takes: the poll loop reads each
    terminal result and calls :meth:`_report_crash`. Here we drive that method
    directly with the fed result to assert the NODE_ERROR names the node and
    carries both the broken-pool ``info`` and the crash file Nipype wrote for
    the abrupt failure.
    """
    # The parent _report_crash writes a real crash file from a full nipype Node;
    # stub the writer so the test can use a lightweight node and still assert the
    # crash file path is threaded onto the NODE_ERROR.
    import nipype.pipeline.plugins.base as nipype_base

    monkeypatch.setattr(
        nipype_base, "report_crash", lambda node, traceback=None: "ref_crash.txt"
    )

    plugin, queue = make_plugin()
    node_name = "prerelease_wf.ref_bias_correction"
    future = _register_task(plugin, 17, node_name)
    future.set_exception(BrokenProcessPool("worker terminated abruptly"))

    plugin._async_callback(future)

    node = SimpleNamespace(fullname=node_name)
    crash_file = plugin._report_crash(node, result=plugin._taskresult[17])

    assert crash_file == "ref_crash.txt"
    report = queue.get(timeout=5)
    assert report.signal_type == WorkflowSignals.NODE_ERROR
    assert report.node_name == node_name
    assert "terminated abruptly" in report.info
    assert report.crash_file == "ref_crash.txt"


def test_broken_pool_on_submit_without_in_flight_tasks_still_reports_failure(
    make_plugin,
):
    """A pool already dead at submit time has no in-flight task to carry the failure.

    With nothing to route through _report_crash, a standalone NODE_ERROR must be
    emitted so the pass is recorded as failed instead of silently passing.
    """
    plugin, queue = make_plugin()

    plugin._handle_broken_pool(
        BrokenProcessPool("pool already dead"),
        unsubmitted_node="prerelease_wf.ref_bias_correction",
    )

    report = queue.get(timeout=5)
    assert report.signal_type == WorkflowSignals.NODE_ERROR
    assert report.node_name == "prerelease_wf.ref_bias_correction"
    assert "terminated abruptly" in report.info
