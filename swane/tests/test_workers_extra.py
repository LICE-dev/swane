import multiprocessing
import time

from swane.workers.UpdateCheckWorker import UpdateCheckWorker
from swane.workers.WorkflowMonitorWorker import WorkflowMonitorWorker
from swane.nipype_pipeline.engine.WorkflowReport import WorkflowReport, WorkflowSignals


def test_is_newer_version():
    # a very new version should be detected as newer
    assert UpdateCheckWorker.is_newer_version('9.9.9') is True
    # an older version should not
    assert UpdateCheckWorker.is_newer_version('0.0.1') is False
    # malformed input should return False
    assert UpdateCheckWorker.is_newer_version('not-a-version') is False


def test_workflow_monitor_emits_and_stops():
    q = multiprocessing.Queue()
    # prepare two reports: a generic and a stop
    r1 = WorkflowReport(signal_type=WorkflowSignals.NODE_STARTED, long_name='x.WORKFLOW.node')
    r2 = WorkflowReport(signal_type=WorkflowSignals.WORKFLOW_STOP)
    q.put(r1)
    q.put(r2)

    worker = WorkflowMonitorWorker(q)

    emitted = []

    # monkeypatch the emit to capture calls
    def fake_emit(report):
        emitted.append(report)

    worker.signal.log_msg.emit = fake_emit

    # run will process the queue and return after stop
    worker.run()

    assert len(emitted) == 2
    assert emitted[0].signal_type == WorkflowSignals.NODE_STARTED
    assert emitted[1].signal_type == WorkflowSignals.WORKFLOW_STOP
