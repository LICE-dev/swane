# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-

from nipype import logging as nipype_log, config
import os
import traceback
from multiprocessing import Process, Event
from threading import Thread
from swane.nipype_pipeline.engine.WorkflowReport import WorkflowReport, WorkflowSignals
from nipype.external.cloghandler import ConcurrentRotatingFileHandler
from swane.nipype_pipeline.engine.MonitoredMultiProcPlugin import MonitoredMultiProcPlugin
import logging as orig_log
from swane.nipype_pipeline.MainWorkflow import MainWorkflow
from multiprocessing import Queue


LOG_DIR_NAME = "log"


class WorkflowProcess(Process):
    LOG_CHANNELS = [
        "nipype.workflow",
        "nipype.utils",
        "nipype.filemanip",
        "nipype.interface",
    ]

    def __init__(self, subject_name: str, workflow: MainWorkflow, queue: Queue):
        """
            A Process that execute a subject workflow in a thread, manage executor settings and signaling with gui.
            A process is needed to iterate and kill its subprocess if user wants to stop a workflow, a thread would not
            allow that.

        Parameters
        ----------
        subject_name: str
            The subject name
        workflow: MainWorkflow
            The workflow already generated and populated
        queue: Queue
            The subprocess queue for signal handling

        """
        super(WorkflowProcess, self).__init__()
        self.stop_event: Event = Event()
        self.workflow: MainWorkflow = workflow
        self.queue: Queue = queue
        self.subject_name: str = subject_name

    @staticmethod
    def remove_handlers(handler):
        """
            Remove the specified handler from nipype logger channels
        """

        for channel in WorkflowProcess.LOG_CHANNELS:
            nipype_log.getLogger(channel).removeHandler(handler)

    @staticmethod
    def add_handlers(handler):
        """
            Add the specified handler to nipype logger channels
        """
        for channel in WorkflowProcess.LOG_CHANNELS:
            nipype_log.getLogger(channel).addHandler(handler)

    def workflow_run_worker(self):
        """
            Thread that run the workflow
        """

        plugin_args = {
            'mp_context': 'fork',
            'queue': self.queue,
            'status_callback': swane_log_nodes_cb,
        }
        if self.workflow.max_cpu > 0:
            plugin_args['n_procs'] = self.workflow.max_cpu
        if self.workflow.max_gpu > 0:
            plugin_args['n_gpu_proc'] = self.workflow.max_gpu

        try:
            # this is useful to generate resource monitor files in subject directory
            os.chdir(self.workflow.base_dir)

            self.workflow.run(plugin=MonitoredMultiProcPlugin(plugin_args=plugin_args))

        except:
            traceback.print_exc()

        # TODO implement nipype.utils.draw_gantt_chart.generate_gantt_chart but maybe it's bugged

        # This event signal the workflow end. When called here is a finished run
        self.stop_event.set()

    @staticmethod
    def kill_with_subprocess():
        """
            Loop all subprocess of current process and kill them, then kill the parent process.
            MUST BE CALLED FROM THE WORKFLOW PROCESS ITSELF OR WILL KILL THE MAIN APPLICATION!
        """
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
        """
            The Process main code
        """
        # log folder management
        log_dir = os.path.join(self.workflow.base_dir, LOG_DIR_NAME)
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

        # enable resource monitor if required
        if self.workflow.is_resource_monitor:
            config.enable_resource_monitor()
            resource_log_filename = os.path.join(log_dir, 'resource_monitor.log')
            callback_logger = orig_log.getLogger('callback')
            callback_logger.setLevel(orig_log.DEBUG)
            resource_log_handler = orig_log.FileHandler(resource_log_filename)
            callback_logger.addHandler(resource_log_handler)

        # start workflow subthread
        workflow_run_work = Thread(target=self.workflow_run_worker)
        workflow_run_work.start()

        # Wait for stop_event. It can be set from the workflow subthread (if workflow is executed till end) or from
        # the GUI to stop the execution
        self.stop_event.wait()

        # Handler removal
        WorkflowProcess.remove_handlers(file_handler)
        if self.workflow.is_resource_monitor:
            callback_logger.removeHandler(resource_log_handler)

        # Signal workflow_stop to GUI and close queue
        self.queue.put(WorkflowReport(signal_type=WorkflowSignals.WORKFLOW_STOP))
        self.queue.close()

        # If the thread is alive at this point the stop_event was set from GUI, so the user asked to kill the process
        if workflow_run_work.is_alive():
            WorkflowProcess.kill_with_subprocess()


# Log node stats function
def swane_log_nodes_cb(node, status):
    """Function to record node run statistics to a log file as json
    dictionaries

    Parameters
    ----------
    node : nipype.pipeline.engine.Node
        the node being logged
    status : string
        acceptable values are 'start', 'end'; otherwise it is
        considered and error

    Returns
    -------
    None
        this function does not return any values, it logs the node
        status info to the callback logger
    """

    if status != "end":
        return

    # Import packages
    import logging
    import json

    status_dict = {
        "name": node.name,
        "id": node._id,
        "start": getattr(node.result.runtime, "startTime", None),
        "finish": getattr(node.result.runtime, "endTime", None),
        "duration": getattr(node.result.runtime, "duration", None),
        "runtime_threads": getattr(node.result.runtime, "cpu_percent", "N/A"),
        "runtime_memory_gb": getattr(node.result.runtime, "mem_peak_gb", "N/A"),
        "estimated_memory_gb": node.mem_gb,
        "num_threads": node.n_procs,
    }

    if status_dict["start"] is None or status_dict["finish"] is None:
        status_dict["error"] = True

    # Dump string to log
    logging.getLogger("callback").debug(json.dumps(status_dict))
