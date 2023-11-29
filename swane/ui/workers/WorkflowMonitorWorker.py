from PySide6.QtCore import Signal, QObject, QRunnable
from swane.nipype_pipeline.engine.WorkflowReport import WorkflowReport


class LogReceiverSignal(QObject):
    log_msg = Signal(WorkflowReport)


class WorkflowMonitorWorker(QRunnable):
    """
    Create a thread waiting for nipype workflow reports using a multiprocessing queue.
    """

    def __init__(self, queue):
        super(WorkflowMonitorWorker, self).__init__()
        self.signal = LogReceiverSignal()
        self.queue = queue

    def run(self):
        while True:
            # get a unit of work
            wf_report = self.queue.get()
            # report
            self.signal.log_msg.emit(wf_report)
            # check for stop
            if wf_report.signal_type == WorkflowReport.WORKFLOW_STOP:
                break
