import logging
import multiprocessing as mp
import os
import sys
from multiprocessing import Queue

import pytest

from swane.utils.mp_start_method import START_METHOD_ENV_VAR, worker_pool_start_method
from swane.workers.WorkflowProcess import WorkflowProcess, swane_log_nodes_cb
import types


class DummyWorkflow:
    def __init__(self):
        self.base_dir = os.getcwd()
        self.memory_gb = 1
        self.max_cpu = 0
        self.max_gpu = 0
        self.is_resource_monitor = False

    def run(self, plugin=None):
        return

    def _get_all_nodes(self):
        return []


def test_add_and_remove_handlers(monkeypatch):
    # create dummy handler object with required methods
    class DummyHandler:
        pass

    # Must be the SAME instance for both calls: logging.Logger.removeHandler()
    # is a silent no-op if the given object isn't in the handler list, so two
    # separate instances would leave the "added" one attached to the real
    # nipype.workflow/utils/filemanip/interface loggers for the rest of the
    # test session -- and it has no .level, so any later record logged
    # through those channels crashes with AttributeError.
    handler = DummyHandler()
    WorkflowProcess.add_handlers(handler)
    WorkflowProcess.remove_handlers(handler)

    for channel in WorkflowProcess.LOG_CHANNELS:
        assert handler not in logging.getLogger(channel).handlers


def test_workflow_run_worker_gpu_budget_reaches_the_plugin(monkeypatch, tmp_path):
    """``max_gpu`` must reach nipype's plugin as ``n_gpu_procs`` (with the
    trailing 's'): that is the key ``MultiProcPlugin.__init__`` actually
    reads (``self.plugin_args.get('n_gpu_procs', self.n_gpus_visible)``).
    A key typo here does not raise -- nipype just silently falls back to the
    system's visible GPU count instead of the user's configured limit -- so
    only asserting on the dict passed to the plugin constructor catches it.
    """
    captured = {}

    class FakePlugin:
        def __init__(self, plugin_args=None):
            captured.update(plugin_args or {})

    monkeypatch.setattr(
        "swane.nipype_pipeline.engine.MonitoredMultiProcPlugin.MonitoredMultiProcPlugin",
        FakePlugin,
    )

    workflow = DummyWorkflow()
    workflow.base_dir = str(tmp_path)
    workflow.max_cpu = 3
    workflow.max_gpu = 2
    workflow.memory_gb = 5

    wp = WorkflowProcess("subj", workflow, Queue())
    wp.workflow_run_worker()

    assert captured.get("n_gpu_procs") == 2
    assert captured.get("n_procs") == 3
    assert captured.get("memory_gb") == 5
    assert captured.get("mp_context") == worker_pool_start_method()


def test_antspynet_preload_failure_does_not_stop_the_workflow(monkeypatch, tmp_path):
    """The weights pre-fetch runs before the plugin; if it fails the workflow
    still runs and the node that needs the weights reports its own error."""
    from subprocess import CalledProcessError
    from swane.utils import antspynet_weights

    order = []

    class FakePlugin:
        def __init__(self, plugin_args=None):
            order.append("plugin")

    def failing_preload(names):
        order.append(("preload", list(names)))
        raise CalledProcessError(1, "child", stderr="offline")

    monkeypatch.setattr(
        "swane.nipype_pipeline.engine.MonitoredMultiProcPlugin.MonitoredMultiProcPlugin",
        FakePlugin,
    )
    monkeypatch.setattr(
        antspynet_weights, "workflow_modalities", lambda workflow: ["t1"]
    )
    monkeypatch.setattr(antspynet_weights, "preload_weights", failing_preload)

    workflow = DummyWorkflow()
    workflow.base_dir = str(tmp_path)
    prev_cwd = os.getcwd()
    try:
        WorkflowProcess("subj", workflow, Queue()).workflow_run_worker()
    finally:
        os.chdir(prev_cwd)

    assert order == [("preload", ["brainExtractionRobustT1"]), "plugin"]


def test_workflow_without_antspynet_nodes_skips_the_preload(monkeypatch):
    from swane.utils import antspynet_weights

    # Record rather than raise: preload_antspynet_weights swallows exceptions.
    calls = []
    monkeypatch.setattr(antspynet_weights, "preload_weights", calls.append)
    WorkflowProcess("subj", DummyWorkflow(), Queue()).preload_antspynet_weights()
    assert calls == [], "no antspynet node: nothing to pre-fetch"


#: Module registered in ``sys.modules`` by the test process only at run time:
#: a ``fork`` worker inherits it, a fresh (``spawn``/``forkserver``) one does not.
_PARENT_ONLY_SENTINEL = "_swane_start_method_check_sentinel"


def _record_worker_parent(out_dir):
    """Function node body: record which process started this worker and
    whether it inherited the test process's memory."""
    import os
    import sys

    ppid = os.getppid()
    inherited = "_swane_start_method_check_sentinel" in sys.modules
    with open(os.path.join(out_dir, "ppid.txt"), "w") as handle:
        handle.write(str(ppid))
    with open(os.path.join(out_dir, "inherited.txt"), "w") as handle:
        handle.write(str(int(inherited)))
    return ppid


@pytest.mark.parametrize(
    "start_method",
    [m for m in ("fork", "forkserver", "spawn") if m in mp.get_all_start_methods()],
)
def test_real_worker_pool_uses_the_selected_start_method(
    monkeypatch, tmp_path, start_method
):
    """
    Run a real one-node workflow through WorkflowProcess and the monitored
    MultiProc plugin. Under ``fork`` the worker is a child of this process;
    under ``forkserver`` it is a child of the fork server, never of this
    (Qt-holding, on macOS) process -- which is what keeps macOS workers clear
    of the frameworks that are not fork-safe. Under ``spawn`` (Windows' only
    start method) the worker is again a child of this process, but a fresh
    interpreter that must re-import swane, and with it the ``pwd`` stub, before
    unpickling the node runner: it does not inherit a module this process
    registered at run time.
    """
    from nipype import Node, Workflow
    from nipype.interfaces.utility import Function

    monkeypatch.setenv(START_METHOD_ENV_VAR, start_method)
    monkeypatch.setitem(
        sys.modules, _PARENT_ONLY_SENTINEL, types.ModuleType(_PARENT_ONLY_SENTINEL)
    )

    workflow = Workflow(name="start_method_check", base_dir=str(tmp_path))
    node = Node(
        Function(
            input_names=["out_dir"],
            output_names=["ppid"],
            function=_record_worker_parent,
        ),
        name="record_parent",
    )
    node.inputs.out_dir = str(tmp_path)
    workflow.add_nodes([node])
    workflow.max_cpu = 1
    workflow.max_gpu = 0
    workflow.memory_gb = 1.0
    workflow.config["execution"]["poll_sleep_duration"] = "0.1"

    queue = Queue()
    prev_cwd = os.getcwd()
    try:
        WorkflowProcess("subj", workflow, queue).workflow_run_worker()
    finally:
        os.chdir(prev_cwd)
        queue.close()
        queue.cancel_join_thread()

    ppid_file = tmp_path / "ppid.txt"
    assert ppid_file.exists(), "the node did not run in a worker"
    worker_parent = int(ppid_file.read_text())
    inherited = (tmp_path / "inherited.txt").read_text() == "1"
    if start_method == "fork":
        assert worker_parent == os.getpid()
        assert inherited, "a fork worker must inherit the test process memory"
    elif start_method == "forkserver":
        assert worker_parent != os.getpid()
        assert not inherited
    else:  # spawn: a fresh interpreter launched directly by this process
        assert worker_parent == os.getpid()
        assert not inherited, "a spawn worker must start from a fresh interpreter"


def test_run_advertises_monitoring_on_workflow_config(monkeypatch, tmp_path):
    """
    Regression: enabling the resource monitor must set ``monitoring.enabled`` on
    the workflow's OWN config, not only on the global nipype config.

    ``config.enable_resource_monitor()`` flips only the global config, which a
    ``spawn`` worker does not inherit. If the flag is not mirrored onto
    ``workflow.config``, the workflow-creation snapshot ("false") wins nipype's
    ``run()`` merge and every ``node.config`` reaches the (spawn) worker with
    monitoring disabled -- so no ``.proc`` file is ever produced. See
    ``swane_run_node`` for the worker-side half of the fix.
    """
    from nipype import config as nipype_config

    class FakePlugin:
        def __init__(self, plugin_args=None):
            pass

    monkeypatch.setattr(
        "swane.nipype_pipeline.engine.MonitoredMultiProcPlugin.MonitoredMultiProcPlugin",
        FakePlugin,
    )

    workflow = DummyWorkflow()
    workflow.base_dir = str(tmp_path)
    workflow.is_resource_monitor = True
    workflow.freesurfer = None
    workflow.config = {"execution": {}}

    prev_monitor = nipype_config.resource_monitor
    prev_cwd = os.getcwd()
    try:
        WorkflowProcess("subj", workflow, Queue()).run()
    finally:
        nipype_config.resource_monitor = prev_monitor
        os.chdir(prev_cwd)

    assert workflow.config["monitoring"]["enabled"] == "true"
    assert workflow.config["execution"]["crashdump_dir"] == os.path.join(
        str(tmp_path), "log"
    )


def test_swane_log_nodes_cb_creates_dict(monkeypatch):
    class Node:
        def __init__(self):
            self.name = "n"
            self._id = "id"

            class R:
                startTime = None
                endTime = None
                duration = None

            self.result = types.SimpleNamespace(
                runtime=types.SimpleNamespace(
                    startTime=None, endTime=None, duration=None
                )
            )
            self.mem_gb = 1
            self.n_procs = 1

    # call the callback with status not 'end' and 'end'
    swane_log_nodes_cb(Node(), "start")
    swane_log_nodes_cb(Node(), "end")


def test_workflow_run_worker_crash_sets_exitcode(monkeypatch, tmp_path):
    import pytest

    class CrashingWorkflow(DummyWorkflow):
        def run(self, plugin=None):
            raise ValueError("Intentional crash")

    workflow = CrashingWorkflow()
    workflow.base_dir = str(tmp_path)
    workflow.freesurfer = None
    workflow.config = {"execution": {}}

    wp = WorkflowProcess("subj", workflow, Queue())

    with pytest.raises(SystemExit) as exc:
        wp.run()
    assert exc.value.code == 1
    assert getattr(wp, "run_raised", False) is True
