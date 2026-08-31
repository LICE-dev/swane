"""
Tests for SWANe's Nipype monkeypatches: the Resource Monitor ``.proc`` files
must be written into the configured ``crashdump_dir`` (the log folder), and the
mechanism must keep working with the ``spawn`` start method.
"""

import multiprocessing as mp
import os

import pytest
from nipype.interfaces.fsl.epi import Eddy, EddyInputSpec
from nipype.utils.profiler import ResourceMonitor

import swane.patches.nipype_patches as npx
from swane.tests.patches import spawn_helpers


@pytest.fixture(autouse=True)
def _reset_proc_dir():
    """Keep the module-level proc_dir from leaking between tests."""
    previous = npx.proc_dir
    npx.proc_dir = None
    yield
    npx.proc_dir = previous


def _close(rm):
    # ResourceMonitor opens its logfile in __init__; close it so tmp dirs can be
    # removed cleanly on all platforms.
    rm._logfile.close()


def test_resource_monitor_redirects_proc_into_proc_dir(tmp_path):
    npx.apply_patches()
    npx.proc_dir = str(tmp_path)

    rm = ResourceMonitor(os.getpid(), freq=0.2)
    try:
        assert os.path.realpath(os.path.dirname(rm.fname)) == os.path.realpath(
            str(tmp_path)
        )
        assert os.path.basename(rm.fname).startswith(".proc-")
        assert os.path.exists(rm.fname)
    finally:
        _close(rm)


def test_resource_monitor_falls_back_to_cwd_without_proc_dir(tmp_path, monkeypatch):
    npx.apply_patches()
    npx.proc_dir = None
    monkeypatch.chdir(tmp_path)

    rm = ResourceMonitor(os.getpid(), freq=0.2)
    try:
        # Original Nipype behaviour: default name resolved against the CWD.
        assert os.path.realpath(os.path.dirname(rm.fname)) == os.path.realpath(
            str(tmp_path)
        )
    finally:
        _close(rm)


def test_swane_run_node_sets_proc_dir_from_node_config(monkeypatch):
    captured = {}

    def fake_orig(node, updatehash, taskid):
        captured["proc_dir"] = npx.proc_dir
        captured["args"] = (node, updatehash, taskid)
        return "SENTINEL"

    monkeypatch.setattr(npx, "_orig_run_node", fake_orig)

    class Node:
        config = {"execution": {"crashdump_dir": "/some/log/dir"}}

    node = Node()
    out = npx.swane_run_node(node, True, 7)

    assert out == "SENTINEL"
    assert captured["proc_dir"] == "/some/log/dir"
    assert captured["args"] == (node, True, 7)


def test_swane_run_node_resets_proc_dir_when_config_missing(monkeypatch):
    npx.proc_dir = "/stale/dir"

    def fake_orig(node, updatehash, taskid):
        return npx.proc_dir

    monkeypatch.setattr(npx, "_orig_run_node", fake_orig)

    class Node:
        config = {}  # no execution/crashdump_dir

    assert npx.swane_run_node(Node(), False, 1) is None


def test_apply_patches_is_idempotent():
    npx.apply_patches()
    first_resource_monitor = ResourceMonitor.__init__
    first_get_hashval = EddyInputSpec.get_hashval
    npx.apply_patches()
    assert ResourceMonitor.__init__ is first_resource_monitor
    assert EddyInputSpec.get_hashval is first_get_hashval


def test_eddy_thread_argument_does_not_change_hash():
    eddy = Eddy()
    eddy.inputs.args = "--nthr=2"
    hashed_inputs, two_thread_hash = eddy.inputs.get_hashval()

    assert "args" not in dict(hashed_inputs)

    eddy.inputs.args = "--nthr=8"
    _, eight_thread_hash = eddy.inputs.get_hashval()
    assert eight_thread_hash == two_thread_hash


def test_other_eddy_arguments_still_change_hash():
    eddy = Eddy()
    eddy.inputs.args = "--repol"
    hashed_inputs, repol_hash = eddy.inputs.get_hashval()

    assert dict(hashed_inputs)["args"] == "--repol"

    eddy.inputs.args = "--fep"
    _, fep_hash = eddy.inputs.get_hashval()
    assert fep_hash != repol_hash


@pytest.mark.parametrize(
    "start_method",
    [method for method in ("fork", "spawn") if method in mp.get_all_start_methods()],
)
def test_eddy_hash_patch_survives_process_start(start_method):
    context = mp.get_context(start_method)
    queue = context.Queue()
    process = context.Process(target=spawn_helpers.eddy_hash_worker, args=(queue,))
    try:
        process.start()
        process.join(30)

        assert process.exitcode == 0
        result = queue.get(timeout=5)
        assert not result["args_in_hash"]
        assert result["same_hash"]
    finally:
        if process.is_alive():
            process.terminate()
            process.join(5)
        queue.close()
        queue.join_thread()


def test_swane_run_node_enables_resource_monitor_from_node_config(monkeypatch):
    """
    Under spawn the worker's global config loses the parent's runtime
    ``enable_resource_monitor()``; swane_run_node must re-enable it from the
    pickled ``node.config`` so nodes create a real ResourceMonitor.
    """
    from nipype import config as nipype_config

    calls = {"enabled": 0}
    monkeypatch.setattr(npx, "_orig_run_node", lambda *a, **k: None)
    monkeypatch.setattr(
        nipype_config,
        "enable_resource_monitor",
        lambda: calls.__setitem__("enabled", calls["enabled"] + 1),
    )

    class Node:
        config = {
            "execution": {"crashdump_dir": "/log"},
            "monitoring": {"enabled": "true"},
        }

    npx.swane_run_node(Node(), False, 1)
    assert calls["enabled"] == 1

    # When monitoring is off, we must NOT enable it.
    class OffNode:
        config = {"monitoring": {"enabled": "false"}}

    npx.swane_run_node(OffNode(), False, 1)
    assert calls["enabled"] == 1


def test_spawn_worker_writes_proc_into_crashdump_dir(tmp_path):
    """
    End-to-end check with the ``spawn`` start method: a fresh interpreter must
    import the patch (via unpickling ``swane_run_node``), *enable* the resource
    monitor from node.config and drop the ``.proc`` file into ``crashdump_dir``.
    This goes through the real Nipype ``config.resource_monitor`` gate.
    """
    ctx = mp.get_context("spawn")
    crashdump = tmp_path / "log"
    crashdump.mkdir()

    queue = ctx.Queue()
    proc = ctx.Process(target=spawn_helpers.spawn_worker, args=(str(crashdump), queue))
    proc.start()
    proc.join(60)

    assert proc.exitcode == 0
    result = queue.get(timeout=5)
    # The gate must be open in the fresh spawn interpreter...
    assert result["resource_monitor"] is True
    # ...and the .proc file must land in crashdump_dir (not None -> not the Mock).
    fname = result["fname"]
    assert fname is not None
    assert os.path.realpath(os.path.dirname(fname)) == os.path.realpath(str(crashdump))
    assert os.path.basename(fname).startswith(".proc-")
