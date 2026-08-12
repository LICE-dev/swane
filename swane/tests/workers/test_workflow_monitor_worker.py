"""Unit tests for :class:`swane.workers.WorkflowMonitorWorker`."""

import queue

from swane.workers.WorkflowMonitorWorker import WorkflowMonitorWorker
from swane.nipype_pipeline.engine.WorkflowReport import (
    WorkflowReport,
    WorkflowSignals,
)


def test_monitor_emits_every_report_and_stops():
    # A pre-filled queue ending with WORKFLOW_STOP lets run() drain
    # synchronously in the current thread, so a direct signal connection
    # delivers every report without an event loop.
    q = queue.Queue()
    q.put(WorkflowReport(WorkflowSignals.NODE_STARTED, "wf.WORKFLOW.node"))
    q.put(WorkflowReport(WorkflowSignals.WORKFLOW_STOP))

    worker = WorkflowMonitorWorker(q)
    emitted = []
    worker.signal.log_msg.connect(emitted.append)

    worker.run()

    assert len(emitted) == 2
    assert emitted[0].signal_type == WorkflowSignals.NODE_STARTED
    assert emitted[-1].signal_type == WorkflowSignals.WORKFLOW_STOP
