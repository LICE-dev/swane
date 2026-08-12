import threading
from multiprocessing import Queue
from swane.workers.WorkflowMonitorWorker import WorkflowMonitorWorker
from swane.nipype_pipeline.engine.WorkflowReport import WorkflowReport, WorkflowSignals


def test_workflow_monitor_receives_and_emits(monkeypatch):
    q = Queue()
    w = WorkflowMonitorWorker(q)
    emitted = []
    # replace the signal emitter with a lambda to capture
    w.signal.log_msg.connect(lambda report: emitted.append(report))

    # run the worker in a separate thread
    t = threading.Thread(target=w.run, daemon=True)
    t.start()

    # put a start report and then a stop report
    q.put(WorkflowReport(WorkflowSignals.NODE_STARTED, 'a.b.node'))
    q.put(WorkflowReport(WorkflowSignals.WORKFLOW_STOP))

    t.join(timeout=2)
    assert len(emitted) >= 1
