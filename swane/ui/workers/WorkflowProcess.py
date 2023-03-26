from nipype import logging, config
from logging import Formatter
import os
import traceback
from multiprocessing import Process, Event
from threading import Thread
from swane.ui.workers.WorkflowMonitorWorker import WorkflowMonitorWorker
from nipype.external.cloghandler import ConcurrentRotatingFileHandler
from swane.nipype_pipeline.engine.MonitoredMultiProcPlugin import MonitoredMultiProcPlugin


class WorkflowProcess(Process):

    LOG_CHANNELS = [
        "nipype.workflow",
        "nipype.utils",
        "nipype.filemanip",
        "nipype.interface",
    ]

    def __init__(self, pt_name, wf, queue):
        super(WorkflowProcess, self).__init__()
        self.stop_event = Event()
        self.wf = wf
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

    @staticmethod
    def workflow_run_worker(workflow, stop_event, queue):
        plugin_args = {
            'mp_context': 'fork',
            'queue': queue,
        }
        if workflow.max_cpu > 0:
            plugin_args['n_procs'] = workflow.max_cpu
        try:
            workflow.run(plugin=MonitoredMultiProcPlugin(plugin_args=plugin_args))
        except:
            traceback.print_exc()
        stop_event.set()

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
        log_dir = os.path.join(self.wf.base_dir, "log/")
        if not os.path.exists(log_dir):
            os.mkdir(log_dir)

        self.wf.config["execution"]["crashdump_dir"] = log_dir
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
        workflow_run_work = Thread(target=WorkflowProcess.workflow_run_worker, args=(self.wf, self.stop_event, self.queue))
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
