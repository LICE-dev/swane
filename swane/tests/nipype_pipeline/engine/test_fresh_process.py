"""End-to-end tests for the ``fresh_process`` interface flag honoured by
:class:`~swane.nipype_pipeline.engine.MonitoredMultiProcPlugin.MonitoredMultiProcPlugin`.

ITK, OpenMP and TensorFlow read their thread counts once per process and cache
them, so a node that needs its own thread cap must not run in a reused pool
worker. An interface declaring ``fresh_process = True`` is therefore run by the
plugin in a brand-new process of the pool's start method, one per node (and
per MapNode subnode); every other node keeps sharing the regular pool.

These tests run small real workflows (no external tools) and identify the
process each node ran in by its PID, for every start method this platform
offers.
"""

import errno
import multiprocessing as mp
import os
from concurrent.futures import ProcessPoolExecutor
from queue import Queue

import pytest
from nipype import MapNode, Node, Workflow
from nipype.interfaces.base import (
    BaseInterface,
    BaseInterfaceInputSpec,
    TraitedSpec,
    traits,
)

import swane.nipype_pipeline.engine.MonitoredMultiProcPlugin as plugin_module
from swane.nipype_pipeline.engine.MonitoredMultiProcPlugin import (
    MonitoredMultiProcPlugin,
)
from swane.nipype_pipeline.engine.WorkflowReport import WorkflowSignals

START_METHODS = mp.get_all_start_methods()


class _PidInputSpec(BaseInterfaceInputSpec):
    tag = traits.Int(0, usedefault=True, desc="distinguishes otherwise equal nodes")


class _PidOutputSpec(TraitedSpec):
    pid = traits.Int(desc="PID of the process that ran the node")


class PooledPid(BaseInterface):
    """Reports the PID of the process that ran it."""

    input_spec = _PidInputSpec
    output_spec = _PidOutputSpec

    def _run_interface(self, runtime):
        self._pid = os.getpid()
        return runtime

    def _list_outputs(self):
        outputs = self._outputs().get()
        outputs["pid"] = self._pid
        return outputs


class FreshPid(PooledPid):
    fresh_process = True


class FreshCrash(PooledPid):
    """Kills its own process, as a native crash or the OOM killer would."""

    fresh_process = True

    def _run_interface(self, runtime):
        os._exit(1)


def _plugin(start_method, n_procs, queue):
    return MonitoredMultiProcPlugin(
        plugin_args={
            "n_procs": n_procs,
            "memory_gb": 1.0,
            "n_gpu_procs": 0,
            "mp_context": start_method,
            "queue": queue,
        }
    )


def _workflow(tmp_path, name):
    workflow = Workflow(name=name, base_dir=str(tmp_path))
    workflow.config["execution"]["poll_sleep_duration"] = "0.05"
    # keep crashes inside tmp_path
    workflow.config["execution"]["crashdump_dir"] = str(tmp_path)
    return workflow


def _pids(graph):
    """Map node name -> list of PIDs (one per subnode for a MapNode)."""
    pids = {}
    for node in graph.nodes():
        pid = node.result.outputs.pid
        pids.setdefault(node.name, []).extend(pid if isinstance(pid, list) else [pid])
    return pids


def _zero(_):
    return 0


def _chain(workflow, nodes):
    """Run ``nodes`` one after another: each waits on the previous one's PID."""
    for upstream, downstream in zip(nodes, nodes[1:]):
        workflow.connect(upstream, ("pid", _zero), downstream, "tag")


@pytest.mark.parametrize("start_method", START_METHODS)
def test_fresh_process_nodes_never_share_a_process(tmp_path, start_method):
    workflow = _workflow(tmp_path, "fresh_pids")
    pooled = [Node(PooledPid(), name="pooled_%d" % i) for i in range(3)]
    fresh = [Node(FreshPid(), name="fresh_%d" % i) for i in range(3)]
    # Alternate pooled and fresh nodes in one chain, so a fresh node always
    # runs right after a pooled one and could reuse its idle worker.
    _chain(workflow, [n for pair in zip(pooled, fresh) for n in pair])

    queue = Queue()
    graph = workflow.run(plugin=_plugin(start_method, 1, queue))
    pids = _pids(graph)

    pooled_pids = {pids["pooled_%d" % i][0] for i in range(3)}
    fresh_pids = [pids["fresh_%d" % i][0] for i in range(3)]
    # one pool worker (n_procs=1) ran every pooled node...
    assert len(pooled_pids) == 1
    # ...while each fresh node got a process of its own, never the pool worker
    # nor the scheduler's own process
    assert len(set(fresh_pids)) == 3
    assert not set(fresh_pids) & pooled_pids
    assert os.getpid() not in fresh_pids


@pytest.mark.parametrize("start_method", START_METHODS)
def test_mapnode_subnodes_each_get_a_fresh_process(tmp_path, start_method):
    """The flag lives on the interface, so subnodes nipype creates inherit it."""
    workflow = _workflow(tmp_path, "fresh_mapnode")
    mapped = MapNode(FreshPid(), iterfield=["tag"], name="mapped")
    mapped.inputs.tag = [1, 2, 3]
    workflow.add_nodes([mapped])

    graph = workflow.run(plugin=_plugin(start_method, 1, Queue()))

    subnode_pids = _pids(graph)["mapped"]
    assert len(subnode_pids) == 3
    assert len(set(subnode_pids)) == 3
    assert os.getpid() not in subnode_pids


@pytest.mark.parametrize("start_method", START_METHODS)
def test_crashed_fresh_process_fails_only_its_own_node(tmp_path, start_method):
    """A fresh process dying by signal must not break the shared pool.

    The regular pool fails *every* in-flight task when one of its workers dies,
    because it cannot tell which one crashed. A fresh process runs exactly one
    node, so only that node may fail: the pooled nodes running at the same
    time and those submitted afterwards must still complete.
    """
    workflow = _workflow(tmp_path, "fresh_crash")
    crash = Node(FreshCrash(), name="crash")
    neighbour = Node(PooledPid(), name="neighbour")
    after = Node(PooledPid(), name="after")
    workflow.add_nodes([crash, neighbour])
    _chain(workflow, [neighbour, after])

    queue = Queue()
    plugin = _plugin(start_method, 2, queue)
    with pytest.raises(RuntimeError):
        workflow.run(plugin=plugin)

    assert not plugin._broken_pool_reported
    reports = []
    while not queue.empty():
        reports.append(queue.get_nowait())
    errors = [
        r.node_name for r in reports if r.signal_type == WorkflowSignals.NODE_ERROR
    ]
    completed = {
        r.node_name for r in reports if r.signal_type == WorkflowSignals.NODE_COMPLETED
    }
    assert errors == ["fresh_crash.crash"]
    assert {"fresh_crash.neighbour", "fresh_crash.after"} <= completed


@pytest.mark.parametrize("start_method", START_METHODS)
def test_no_fresh_process_outlives_the_run(tmp_path, start_method):
    import psutil

    workflow = _workflow(tmp_path, "fresh_cleanup")
    workflow.add_nodes([Node(FreshPid(), name="fresh_%d" % i) for i in range(2)])

    graph = workflow.run(plugin=_plugin(start_method, 2, Queue()))

    for pids in _pids(graph).values():
        for pid in pids:
            # joined, not just signalled: a zombie would still exist
            assert not psutil.pid_exists(pid), "fresh process %d outlived the run" % pid


@pytest.mark.parametrize("start_method", START_METHODS)
def test_crashed_fresh_subnode_is_reported_on_its_mapnode(tmp_path, start_method):
    """A subnode is named ``_<mapnode><i>`` with no hierarchy: its crash must
    reach the GUI under its MapNode's name, the row the GUI knows."""
    workflow = _workflow(tmp_path, "fresh_map_crash")
    mapped = MapNode(FreshCrash(), iterfield=["tag"], name="mapped")
    mapped.inputs.tag = [1, 2]
    workflow.add_nodes([mapped])

    queue = Queue()
    with pytest.raises(RuntimeError):
        workflow.run(plugin=_plugin(start_method, 1, queue))

    errors = set()
    while not queue.empty():
        report = queue.get_nowait()
        if report.signal_type == WorkflowSignals.NODE_ERROR:
            errors.add(report.node_name)
    assert errors == {"fresh_map_crash.mapped"}


class _UnforkableSubmitPool(ProcessPoolExecutor):
    """A fresh pool whose process cannot be forked, as under strict memory
    overcommit or a process limit."""

    shutdowns = []

    def submit(self, *args, **kwargs):
        raise OSError(errno.ENOMEM, "Cannot allocate memory")

    def shutdown(self, *args, **kwargs):
        type(self).shutdowns.append(self)
        return super().shutdown(*args, **kwargs)


class _UncreatablePool:
    def __init__(self, *args, **kwargs):
        raise OSError(errno.EAGAIN, "Resource temporarily unavailable")


@pytest.mark.parametrize("failing_pool", [_UnforkableSubmitPool, _UncreatablePool])
def test_fresh_process_that_cannot_start_fails_only_its_node(
    tmp_path, monkeypatch, failing_pool
):
    """A fresh process that cannot be started is a failure of that node, not of
    the run: the pooled nodes running and queued must still complete."""
    # only the plugin's fresh pools: nipype's shared pool stays a real one
    monkeypatch.setattr(plugin_module, "ProcessPoolExecutor", failing_pool)
    _UnforkableSubmitPool.shutdowns = []
    workflow = _workflow(tmp_path, "fresh_unstartable")
    fresh = Node(FreshPid(), name="fresh")
    pooled = [Node(PooledPid(), name="pooled_%d" % i) for i in range(3)]
    workflow.add_nodes([fresh])
    _chain(workflow, pooled)

    queue = Queue()
    plugin = _plugin("fork" if "fork" in START_METHODS else None, 2, queue)
    # nipype's "Workflow did not execute cleanly", not the OSError
    with pytest.raises(RuntimeError):
        workflow.run(plugin=plugin)

    reports = []
    while not queue.empty():
        reports.append(queue.get_nowait())
    errors = [r for r in reports if r.signal_type == WorkflowSignals.NODE_ERROR]
    completed = {
        r.node_name for r in reports if r.signal_type == WorkflowSignals.NODE_COMPLETED
    }
    assert [r.node_name for r in errors] == ["fresh_unstartable.fresh"]
    assert errors[0].crash_file and os.path.isfile(errors[0].crash_file)
    assert {"fresh_unstartable.pooled_%d" % i for i in range(3)} <= completed
    assert not plugin._fresh_pools
    if failing_pool is _UnforkableSubmitPool:
        # the half-made pool is released, not leaked
        assert len(_UnforkableSubmitPool.shutdowns) == 1
