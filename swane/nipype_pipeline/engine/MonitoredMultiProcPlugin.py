# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-

import sys
import traceback
from nipype.pipeline.plugins.multiproc import MultiProcPlugin
from swane.nipype_pipeline.engine.WorkflowReport import WorkflowReport, WorkflowSignals
import gc
from copy import deepcopy
from nipype.pipeline.plugins.multiproc import logger, indent
from nipype.pipeline.engine import MapNode
from traceback import format_exception
import numpy as np
from logging import INFO
from swane import strings


# -*- DISCLAIMER: this class extends a Nipype class (nipype.pipeline.plugins.multiproc.MultiProcPlugin)  -*-
class MonitoredMultiProcPlugin(MultiProcPlugin):
    """
    Custom reimplementation of MultiProcPlugin to support UI signaling and GPU queue
    """

    def __init__(self,  plugin_args=None):

        # self.task_list = {}
        if "queue" in plugin_args:
            self.queue = plugin_args["queue"]

        # GPU found on syste
        self.n_gpus_visible = MonitoredMultiProcPlugin.gpu_count()
        # proc per GPU set by user
        self.n_gpu_proc = plugin_args.get('n_gpu_proc', 1)

        # total no. of processes allowed on all gpus
        if self.n_gpu_proc > self.n_gpus_visible:
            logger.info(
                'Total number of GPUs proc requested (%d) exceeds the available number of GPUs (%d) on the system. Using requested GPU slots at your own risk!' % (
                self.n_gpu_proc, self.n_gpus_visible))

        super().__init__(plugin_args=plugin_args)

        # it's mandatory delete this argument to avoid plugin copy generated by MapNodes to raise exceptions
        plugin_args["queue"] = None

    def _prerun_check(self, graph):
        """Check if any node exceeds the available resources"""
        # This class implements signaling for insufficient resources error
        try:
            super(MonitoredMultiProcPlugin, self)._prerun_check(graph)
            tasks_gpu_th = []

            for node in graph.nodes():
                if MonitoredMultiProcPlugin.is_gpu_node(node):
                    tasks_gpu_th.append(node.n_procs)

            if np.any(np.array(tasks_gpu_th) > self.n_gpu_proc):
                logger.warning(
                    'Nodes demand more GPU than allowed (%d).',
                    self.n_gpu_proc)
                if self.raise_insufficient:
                    raise RuntimeError('Insufficient GPU resources available for job')
        except RuntimeError:
            self.queue.put(WorkflowReport(signal_type=WorkflowSignals.WORKFLOW_INSUFFICIENT_RESOURCES))
            raise RuntimeError("Insufficient resources available for job")

    def _check_resources(self, running_tasks):
        free_memory_gb, free_processors = super()._check_resources(running_tasks)
        free_gpu_slots = self.n_gpu_proc
        for _, jobid in running_tasks:
            if MonitoredMultiProcPlugin.is_gpu_node(self.procs[jobid]):
                free_gpu_slots -= min(self.procs[jobid].n_procs, free_gpu_slots)
        return free_memory_gb, free_processors, free_gpu_slots

    def _send_procs_to_workers(self, updatehash=False, graph=None):
        """
        Sends jobs to workers when system resources are available.
        """

        # Check to see if a job is available (jobs with all dependencies run)
        # See https://github.com/nipy/nipype/pull/2200#discussion_r141605722
        # See also https://github.com/nipy/nipype/issues/2372
        jobids = np.flatnonzero(
            ~self.proc_done & (self.depidx.sum(axis=0) == 0).__array__()
        )

        # Check available resources by summing all threads and memory used
        free_memory_gb, free_processors, free_gpu_slots = self._check_resources(self.pending_tasks)

        stats = (
            len(self.pending_tasks),
            len(jobids),
            free_memory_gb,
            self.memory_gb,
            free_processors,
            self.processors,
            free_gpu_slots,
            self.n_gpu_proc
        )
        if self._stats != stats:
            tasks_list_msg = ""

            if logger.level <= INFO:
                running_tasks = [
                    "  * %s" % self.procs[jobid].fullname
                    for _, jobid in self.pending_tasks
                ]
                if running_tasks:
                    tasks_list_msg = "\nCurrently running:\n"
                    tasks_list_msg += "\n".join(running_tasks)
                    tasks_list_msg = indent(tasks_list_msg, " " * 21)
            logger.info(
                "[MultiProc] Running %d tasks, and %d jobs ready. Free "
                "memory (GB): %0.2f/%0.2f, Free processors: %d/%d, Free GPU slot:%d/%d.%s",
                len(self.pending_tasks),
                len(jobids),
                free_memory_gb,
                self.memory_gb,
                free_processors,
                self.processors,
                free_gpu_slots,
                self.n_gpu_proc,
                tasks_list_msg
            )
            self._stats = stats

        if free_memory_gb < 0.01 or free_processors == 0:
            logger.debug("No resources available")
            return

        if len(jobids) + len(self.pending_tasks) == 0:
            logger.debug(
                "No tasks are being run, and no jobs can "
                "be submitted to the queue. Potential deadlock"
            )
            return

        jobids = self._sort_jobs(jobids, scheduler=self.plugin_args.get("scheduler"))

        # Run garbage collector before potentially submitting jobs
        gc.collect()

        # Submit jobs
        for jobid in jobids:
            # First expand mapnodes
            if isinstance(self.procs[jobid], MapNode):
                try:
                    num_subnodes = self.procs[jobid].num_subnodes()
                except Exception:
                    traceback = format_exception(*sys.exc_info())
                    self._clean_queue(
                        jobid, graph, result={"result": None, "traceback": traceback}
                    )
                    self.proc_pending[jobid] = False
                    continue
                if num_subnodes > 1:
                    submit = self._submit_mapnode(jobid)
                    if not submit:
                        continue

            # Check requirements of this job
            next_job_gb = min(self.procs[jobid].mem_gb, self.memory_gb)
            next_job_th = min(self.procs[jobid].n_procs, self.processors)
            next_job_gpu_th = min(self.procs[jobid].n_procs, self.n_gpu_proc)

            is_gpu_node = MonitoredMultiProcPlugin.is_gpu_node(self.procs[jobid])

            # If node does not fit, skip at this moment
            if (next_job_th > free_processors or next_job_gb > free_memory_gb
                    or (is_gpu_node and next_job_gpu_th > free_gpu_slots)):
                logger.debug(
                    "Cannot allocate job %d (%0.2fGB, %d threads, %d GPU slots).",
                    jobid,
                    next_job_gb,
                    next_job_th,
                    next_job_gpu_th
                )
                continue

            free_memory_gb -= next_job_gb
            free_processors -= next_job_th
            if is_gpu_node:
                free_gpu_slots -= next_job_gpu_th

            logger.debug(
                "Allocating %s ID=%d (%0.2fGB, %d threads, %d GPU slots). Free: "
                "%0.2fGB, %d threads, %d GPU slots.",
                self.procs[jobid].fullname,
                jobid,
                next_job_gb,
                next_job_th,
                next_job_gpu_th,
                free_memory_gb,
                free_processors,
                free_gpu_slots,
            )

            # change job status in appropriate queues
            self.proc_done[jobid] = True
            self.proc_pending[jobid] = True

            # If cached and up-to-date just retrieve it, don't run
            if self._local_hash_check(jobid, graph):
                continue

            # updatehash and run_without_submitting are also run locally
            if updatehash or self.procs[jobid].run_without_submitting:
                logger.debug("Running node %s on master thread", self.procs[jobid])
                try:
                    self.procs[jobid].run(updatehash=updatehash)
                except Exception:
                    traceback = format_exception(*sys.exc_info())
                    self._clean_queue(
                        jobid, graph, result={"result": None, "traceback": traceback}
                    )

                # Release resources
                self._task_finished_cb(jobid)
                self._remove_node_dirs()
                free_memory_gb += next_job_gb
                free_processors += next_job_th
                if is_gpu_node:
                    free_gpu_slots -= next_job_gpu_th
                # Display stats next loop
                self._stats = None

                # Clean up any debris from running node in main process
                gc.collect()
                continue

            # Task should be submitted to workers
            # Send job to task manager and add to pending tasks
            if self._status_callback:
                self._status_callback(self.procs[jobid], "start")
            tid = self._submit_job(deepcopy(self.procs[jobid]), updatehash=updatehash)
            if tid is None:
                self.proc_done[jobid] = False
                self.proc_pending[jobid] = False
            else:
                self.pending_tasks.insert(0, (tid, jobid))
            # Display stats next loop
            self._stats = None

    def _report_crash(self, node, result=None):
        # This class implements signaling for generic node error
        try:
            # TODO: implements signaling in case of OOM strings.pttab_wf_error_oom
            info = None
            for line in result['traceback']:
                if "out of memory" in line:
                    info = strings.pttab_wf_error_oom_gpu
                    break
                elif "Killed" in line:
                    info = strings.pttab_wf_error_oom
                    break
                elif "Terminated" in line:
                    info = strings.pttab_wf_error_terminated
                    break
            self.queue.put(WorkflowReport(long_name=node.fullname, signal_type=WorkflowSignals.NODE_ERROR, info=info))
        except:
            traceback.print_exc()

        return super(MonitoredMultiProcPlugin, self)._report_crash(node, result)

    def _submit_job(self, node, updatehash=False):
        # This class implements signaling for generic node start
        if node.name[0] != "_":
            try:
                self.queue.put(WorkflowReport(long_name=node.fullname, signal_type=WorkflowSignals.NODE_STARTED))
            except:
                traceback.print_exc()

        # Force english language for every node with: export LC_ALL=en_US.UTF-8
        # This is needed to recognize the "Killed" message in case of Out Of Memory Killer error
        if hasattr(node.interface.inputs, "environ"):
            node.interface.inputs.environ['LC_ALL'] = "en_US.UTF-8"

        return super(MonitoredMultiProcPlugin, self)._submit_job(node, updatehash)

    def _submit_mapnode(self, jobid):
        # This class implements signaling for mapnode start
        try:
            self.queue.put(WorkflowReport(long_name=self.procs[jobid].fullname, signal_type=WorkflowSignals.NODE_STARTED))
        except:
            traceback.print_exc()
        return super(MonitoredMultiProcPlugin, self)._submit_mapnode(jobid)

    def _task_finished_cb(self, jobid, cached=False):
        # Implements signaling for generic node completion
        if jobid not in self.mapnodesubids:
            try:
                self.queue.put(WorkflowReport(long_name=self.procs[jobid].fullname, signal_type=WorkflowSignals.NODE_COMPLETED))
            except:
                traceback.print_exc()
        return super(MonitoredMultiProcPlugin, self)._task_finished_cb(jobid, cached)

    @staticmethod
    def gpu_count():
        n_gpus = 1
        try:
            import GPUtil
            return len(GPUtil.getGPUs())
        except ImportError:
            return n_gpus

    @staticmethod
    def is_gpu_node(node):
        return ((hasattr(node.interface.inputs, 'use_cuda') and node.interface.inputs.use_cuda)
                or (hasattr(node.interface.inputs, 'use_gpu') and node.interface.inputs.use_gpu))
