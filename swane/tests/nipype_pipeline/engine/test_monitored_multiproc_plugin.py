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
from multiprocessing import Event, Queue

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


def test_broken_process_pool_callback_reports_node_and_wakes_workflow(make_plugin):
    """A native worker crash must become observable outside the callback.

    ``Future.result()`` raises in Nipype's done-callback. Without SWANe's
    interception, concurrent.futures only logs that exception and Nipype keeps
    polling forever.
    """
    plugin, queue = make_plugin()
    workflow_stop_event = Event()
    plugin.workflow_stop_event = workflow_stop_event

    taskid = 17
    node_name = "prerelease_wf.ref_bias_correction"
    future = Future()
    plugin._task_obj[taskid] = future
    plugin._task_nodes[taskid] = node_name
    plugin._future_taskids[future] = taskid
    future.set_exception(BrokenProcessPool("worker terminated abruptly"))

    plugin._async_callback(future)

    report = queue.get(timeout=5)
    assert report.signal_type == WorkflowSignals.NODE_ERROR
    assert report.node_name == node_name
    assert "terminated abruptly" in report.info
    assert workflow_stop_event.wait(timeout=5)
    assert plugin._taskresult[taskid]["taskid"] == taskid
    assert plugin._taskresult[taskid]["traceback"]
