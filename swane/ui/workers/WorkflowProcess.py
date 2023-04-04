from nipype import logging, config
from logging import Formatter
import os
import traceback
from multiprocessing import Process, Event
from threading import Thread
from swane.ui.workers.WorkflowMonitorWorker import WorkflowMonitorWorker
from nipype.external.cloghandler import ConcurrentRotatingFileHandler
from nipype.pipeline.plugins.multiproc import MultiProcPlugin


class WorkflowProcess(Process):
    NODE_STARTED = "start"
    NODE_COMPLETED = "end"
    NODE_ERROR = "exception"

    LOG_CHANNELS = [
        "nipype.workflow",
        "nipype.utils",
        "nipype.filemanip",
        "nipype.interface",
    ]

    def __init__(self, pt_name, workflow, queue):
        super(WorkflowProcess, self).__init__()
        self.stop_event = Event()
        self.workflow = workflow
        self.queue = queue
        self.pt_name = pt_name

    @staticmethod
    def remove_handlers(handler):
        for channel in WorkflowProcess.LOG_CHANNELS:
            logging.getLogger(channel).removeHandler(handler)

    @staticmethod
    def add_handlers(handler):
        for channel in WorkflowProcess.LOG_CHANNELS:
            logging.getLogger(channel).addHandler(handler)

    def workflow_run_worker(self):
        plugin_args = {
            'mp_context': 'fork',
            'status_callback': self.callback_function
        }
        if self.workflow.max_cpu > 0:
            plugin_args['n_procs'] = self.workflow.max_cpu
        try:
            self.workflow.run(plugin=MultiProcPlugin(plugin_args=plugin_args))
        except:
            traceback.print_exc()
        self.stop_event.set()

    def callback_function(self, node, signal):
        try:
            self.queue.put(node.fullname + "." + signal)
        except:
            pass

    @staticmethod
    def kill_with_subprocess():
        import psutil
        try:
            this_process = psutil.Process(os.getpid())
            children = this_process.children(recursive=True)

            for child_process in children:
                try:
                    child_process.kill()
                except psutil.NoSuchProcess:
                    continue
            this_process.kill()
        except psutil.NoSuchProcess:
            return

    def run(self):
        # gestione del file di log nella cartella del paziente
        log_dir = os.path.join(self.workflow.base_dir, "log/")
        if not os.path.exists(log_dir):
            os.mkdir(log_dir)

        self.workflow.config["execution"]["crashdump_dir"] = log_dir
        log_filename = os.path.join(log_dir, "pypeline.log")
        file_handler = ConcurrentRotatingFileHandler(
            log_filename,
            maxBytes=int(config.get("logging", "log_size")),
            backupCount=int(config.get("logging", "log_rotate")),
        )
        formatter = Formatter(fmt=logging.fmt, datefmt=logging.datefmt)
        file_handler.setFormatter(formatter)
        WorkflowProcess.add_handlers(file_handler)

        # avvio il wf in un subhread
        workflow_run_work = Thread(target=self.workflow_run_worker)
        workflow_run_work.start()

        # l'evento può essere settato dal wf_run_worker (se il wf finisce spontaneamente) o dall'esterno per terminare il processo
        self.stop_event.wait()

        # rimuovo gli handler di filelog e aggiornamento gui
        WorkflowProcess.remove_handlers(file_handler)

        # chiudo la queue del subprocess
        self.queue.put(WorkflowMonitorWorker.STOP)
        self.queue.close()

        # se il thread è alive vuol dire che devo killare su richiesta della GUI
        if workflow_run_work.is_alive():
            WorkflowProcess.kill_with_subprocess()
