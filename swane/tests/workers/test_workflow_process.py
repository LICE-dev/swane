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

    # ensure no exception when adding/removing
    WorkflowProcess.add_handlers(DummyHandler())
    WorkflowProcess.remove_handlers(DummyHandler())


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
