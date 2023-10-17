from nipype import logging as nipype_log, config
import os
import traceback
from multiprocessing import Process, Event
from threading import Thread
from swane.ui.workers.WorkflowMonitorWorker import WorkflowMonitorWorker
from nipype.external.cloghandler import ConcurrentRotatingFileHandler
from swane.nipype_pipeline.engine.MonitoredMultiProcPlugin import MonitoredMultiProcPlugin
import logging as orig_log
from nipype.utils.profiler import log_nodes_cb


class WorkflowProcess(Process):
    # NODE_STARTED = "start"
    # NODE_COMPLETED = "end"
    # NODE_ERROR = "exception"

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
            nipype_log.getLogger(channel).removeHandler(handler)

    @staticmethod
    def add_handlers(handler):
        for channel in WorkflowProcess.LOG_CHANNELS:
            nipype_log.getLogger(channel).addHandler(handler)

    def workflow_run_worker(self):
        plugin_args = {
            'mp_context': 'fork',
            'queue': self.queue,
            'status_callback': log_nodes_cb
        }
        if self.workflow.max_cpu > 0:
            plugin_args['n_procs'] = self.workflow.max_cpu
        try:
            self.workflow.run(plugin=MonitoredMultiProcPlugin(plugin_args=plugin_args))
        except:
            traceback.print_exc()

        # TODO implement nipype.utils.draw_gantt_chart.generate_gantt_chart but maybe it's bugged

        self.stop_event.set()

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
        self.workflow.config['execution']['crashfile_format'] = 'txt'
        log_filename = os.path.join(log_dir, "pypeline.log")
        file_handler = ConcurrentRotatingFileHandler(
            log_filename,
            maxBytes=int(config.get("logging", "log_size")),
            backupCount=int(config.get("logging", "log_rotate")),
        )
        formatter = orig_log.Formatter(fmt=nipype_log.fmt, datefmt=nipype_log.datefmt)
        file_handler.setFormatter(formatter)
        WorkflowProcess.add_handlers(file_handler)

        # enable resource log
        config.enable_resource_monitor()
        resource_log_filename = os.path.join(log_dir, 'resource_monitor.log')
        logger = orig_log.getLogger('callback')
        logger.setLevel(orig_log.DEBUG)
        handler = orig_log.FileHandler(resource_log_filename)
        logger.addHandler(handler)

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
