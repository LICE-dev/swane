import logging
import os
from multiprocessing import Queue
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
