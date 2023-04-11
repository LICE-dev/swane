from PySide6.QtCore import Signal, QObject, QRunnable


class LogReceiverSignal(QObject):
    log_msg = Signal(str)


class WorkflowMonitorWorker(QRunnable):
    STOP = "stopstring"

    def __init__(self, queue, parent=None):
        super(WorkflowMonitorWorker, self).__init__(parent)
        self.signal = LogReceiverSignal()
        self.queue = queue

    def run(self):
        while True:
            # get a unit of work
            item = self.queue.get()
            # report
            self.signal.log_msg.emit(item)
            # check for stop
            if item == WorkflowMonitorWorker.STOP:
                break
