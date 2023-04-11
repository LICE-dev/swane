from PySide6.QtCore import Signal, QObject, QRunnable
import os
from swane.nipype_pipeline.MainWorkflow import MainWorkflow


class WorkflowGeneratorSignaler(QObject):
    workflow = Signal(object)


class WorkflowGeneratorWorker(QRunnable):
    WF_DIR_SUFFIX = "_nipype"

    def __init__(self, pt_folder):
        super(WorkflowGeneratorWorker, self).__init__()
        self.signal = WorkflowGeneratorSignaler()
        self.pt_folder = pt_folder
        self.workflow = None

    def run(self):
        self.workflow = MainWorkflow(name=os.path.basename(self.pt_folder) + WorkflowGeneratorWorker.WF_DIR_SUFFIX,
                                     base_dir=self.pt_folder)
        self.signal.workflow.emit(self.workflow)
