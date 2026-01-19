# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-

import traceback
from nipype.interfaces.base import isdefined
from nipype.pipeline.plugins.multiproc import MultiProcPlugin
from swane.nipype_pipeline.engine.WorkflowReport import WorkflowReport, WorkflowSignals
from swane import strings
import numpy as np
from logging import INFO
import logging
logger = logging.getLogger("nipype.workflow")
from nipype.pipeline.plugins.multiproc import indent
from nipype import MapNode
from traceback import format_exception
import sys
import gc
from copy import deepcopy
import nibabel as nib
import math
import os

class NipypeRamEstimator:
    """
    Base class for Nipype RAM estimators.

    Aggregates RAM contributions from inputs using user-defined multipliers.
    Returns both mem_gb and a debug string for reporting.
    """

    def __init__(
        self,
        input_multipliers=None,
        overhead_gb=0.3,
        min_gb=0.5,
        max_gb=8.0
    ):
        """
        Parameters
        ----------
        input_multipliers : dict
            Mapping input_name -> multiplier (user-defined unit)
        overhead_gb : float
            Fixed overhead added to the estimate (GB)
        min_gb : float
            Minimum RAM estimate
        max_gb : float
            Maximum RAM estimate
        """
        self.input_multipliers = input_multipliers or {}
        self.overhead_gb = overhead_gb
        self.min_gb = min_gb
        self.max_gb = max_gb

    @staticmethod
    def voxels(path):
        """Return number of spatial voxels (ignores time dimension)."""
        img = nib.load(path)
        shape = img.header.get_data_shape()
        return math.prod(shape[:3])

    @staticmethod
    def clamp(value, min_val=None, max_val=None):
        """Clamp a value between min_val and max_val."""
        if min_val is not None:
            value = max(min_val, value)
        if max_val is not None:
            value = min(max_val, value)
        return value

    def __call__(self, inputs):
        """
        Estimate RAM usage based on Nipype input traits.

        - File-like inputs contribute via voxel count
        - Numeric inputs contribute via their numeric value
        - Lists are supported for both files and numbers

        Returns
        -------
        mem_gb : float
            Estimated RAM in GB
        estimator_string : str
            Debug string for node report
        """
        total_gb = 0.0
        debug_lines = []

        traits = inputs.traits()

        for attr, multiplier in self.input_multipliers.items():
            if attr not in traits:
                debug_lines.append(f"{attr}: trait not found")
                continue

            val = getattr(inputs, attr, None)

            if not isdefined(val) or val is None:
                debug_lines.append(f"{attr}: undefined")
                continue

            # --------------------------------------------------
            # FILE-LIKE VALUES (string or list/tuple of strings)
            # --------------------------------------------------
            paths = None

            if isinstance(val, str):
                paths = [val]

            elif isinstance(val, (list, tuple)) and any(isinstance(v, str) for v in val):
                paths = [v for v in val if isinstance(v, str)]

            if paths is not None:
                vox_total = 0
                valid_files = 0

                for p in paths:
                    if not isinstance(p, str) or not os.path.exists(p):
                        continue
                    try:
                        vox_total += self.voxels(p)
                        valid_files += 1
                    except Exception:
                        # exists but not a readable image (e.g. txt)
                        continue

                if valid_files > 0:
                    contribution = vox_total * multiplier / (1024 ** 3)
                    total_gb += contribution

                    debug_lines.append(
                        f"{attr}: voxels={vox_total}, multiplier={multiplier}, "
                        f"contribution={contribution:.3f} GB"
                    )
                else:
                    debug_lines.append(f"{attr}: no readable image files")

                continue

            # --------------------------------------------------
            # NUMERIC VALUES (scalar or list/tuple of numbers)
            # --------------------------------------------------
            values = None

            if isinstance(val, (int, float)):
                values = [val]

            elif isinstance(val, (list, tuple)) and all(isinstance(v, (int, float)) for v in val):
                values = val

            if values is not None:
                contribution = sum(float(v) for v in values) * multiplier
                total_gb += contribution

                debug_lines.append(
                    f"{attr}: values={values}, multiplier={multiplier}, "
                    f"contribution={contribution:.3f} GB"
                )
                continue

            # --------------------------------------------------
            # UNSUPPORTED TYPE
            # --------------------------------------------------
            debug_lines.append(
                f"{attr}: unsupported value type ({type(val).__name__})"
            )

        # ------------------------------------------------------
        # OVERHEAD + CLAMP
        # ------------------------------------------------------
        mem_gb = total_gb + self.overhead_gb
        debug_lines.append(
            f"Overhead={self.overhead_gb} GB, total estimated RAM={mem_gb:.3f} GB"
        )

        mem_gb = self.clamp(mem_gb, self.min_gb, self.max_gb)
        debug_lines.append(f"Clamp={mem_gb:.3f} GB")

        estimator_string = " | ".join(debug_lines)
        return float(mem_gb), estimator_string


def update_node_mem_gb(node):
    """
    Update node._mem_gb using a NipypeRamEstimator instance.
    Stores the debug/estimation string in the node's result/report.
    """
    # Exit if the node has no ram_estimator attribute
    if not hasattr(node, "ram_estimator"):
        return

    # Exit if RAM has already been estimated for this node
    if getattr(node, "_ram_estimated", False):
        return

    estimator = node.ram_estimator

    # Ensure the estimator is an instance of NipypeRamEstimator
    if not isinstance(estimator, NipypeRamEstimator):
        if logger:
            logger.error(
                f"Node {node.name}: ram_estimator must be a NipypeRamEstimator instance "
                f"(got {type(estimator)!r}), skipping RAM estimation"
            )
        return

    try:
        # Populate input
        node._get_inputs()

        # Call the estimator: returns mem_gb and debug string
        mem_gb, estimator_string = estimator(node.inputs)

        # Assign estimated RAM to the node as a float
        node._mem_gb = float(mem_gb)
        node._ram_estimated = True
        node._ram_debug_str = estimator_string
        # TODO modificare nipype/engine/utils

    except Exception as e:
        if logger:
            logger.warning(
                f"RAM estimator failed for node {node.name}: {e}",
                exc_info=True
            )
        # Do not block the node if estimation fails
        return


# -*- DISCLAIMER: this class extends a Nipype class (nipype.pipeline.plugins.multiproc.MultiProcPlugin)  -*-
class MonitoredMultiProcPlugin(MultiProcPlugin):
    """
    Custom reimplementation of MultiProcPlugin to support UI signaling and GPU queue
    """

    def __init__(self, plugin_args=None):
        # This method implement support for queue signaling
        if "queue" in plugin_args:
            self.queue = plugin_args["queue"]

        super().__init__(plugin_args=plugin_args)

        # it's mandatory delete this argument to avoid plugin copy generated by MapNodes to raise exceptions
        plugin_args["queue"] = None

    def _prerun_check(self, graph):
        """Check if any node exceeds the available resources"""
        # This method implements signaling for insufficient resources error
        try:
            super(MonitoredMultiProcPlugin, self)._prerun_check(graph)
        except RuntimeError:
            self.queue.put(
                WorkflowReport(
                    signal_type=WorkflowSignals.WORKFLOW_INSUFFICIENT_RESOURCES
                )
            )
            raise RuntimeError("Insufficient resources available for job")

    def _report_crash(self, node, result=None):
        # This class implements signaling for generic node error

        crash_file = super(MonitoredMultiProcPlugin, self)._report_crash(node, result)
        try:
            info = None
            for line in result["traceback"]:
                if "out of memory" in line:
                    info = strings.subj_tab_wf_error_oom_gpu
                    break
                elif "Killed" in line:
                    info = strings.subj_tab_wf_error_oom
                    break
                elif "Terminated" in line:
                    info = strings.subj_tab_wf_error_terminated
                    break
            self.queue.put(
                WorkflowReport(
                    long_name=node.fullname,
                    signal_type=WorkflowSignals.NODE_ERROR,
                    info=info,
                    crash_file=crash_file,
                )
            )
        except:
            traceback.print_exc()

        return crash_file

    def _submit_job(self, node, updatehash=False):
        # This class implements signaling for generic node start
        if node.name[0] != "_":
            try:
                self.queue.put(
                    WorkflowReport(
                        long_name=node.fullname,
                        signal_type=WorkflowSignals.NODE_STARTED,
                    )
                )
            except:
                traceback.print_exc()

        # Force english language for every node with: export LC_ALL=en_US.UTF-8
        # This is needed to recognize the "Killed" message in case of Out Of Memory Killer error
        if hasattr(node.interface.inputs, "environ"):
            node.interface.inputs.environ["LC_ALL"] = "en_US.UTF-8"

        return super(MonitoredMultiProcPlugin, self)._submit_job(node, updatehash)

    def _submit_mapnode(self, jobid):
        # This class implements signaling for mapnode start
        try:
            self.queue.put(
                WorkflowReport(
                    long_name=self.procs[jobid].fullname,
                    signal_type=WorkflowSignals.NODE_STARTED,
                )
            )
        except:
            traceback.print_exc()
                
        ret = super(MonitoredMultiProcPlugin, self)._submit_mapnode(jobid)

        for sub_id, original_id in self.mapnodesubids.items():
            print(jobid, sub_id, original_id, self.procs[original_id].fullname, self.procs[sub_id].fullname)
        # we do this here to not subclass _submit_mapnode
        if hasattr(self.procs[jobid], "ram_estimator"):
            for sub_id, original_id in self.mapnodesubids.items():
                if original_id == jobid:
                    self.procs[sub_id].ram_estimator = self.procs[original_id].ram_estimator

        return ret

    def _task_finished_cb(self, jobid, cached=False):
        # Implements signaling for generic node completion
        if jobid not in self.mapnodesubids:
            try:
                self.queue.put(
                    WorkflowReport(
                        long_name=self.procs[jobid].fullname,
                        signal_type=WorkflowSignals.NODE_COMPLETED,
                    )
                )
            except:
                traceback.print_exc()

        return super(MonitoredMultiProcPlugin, self)._task_finished_cb(jobid, cached)


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
        free_memory_gb, free_processors, free_gpu_slots = self._check_resources(
            self.pending_tasks
        )

        stats = (
            len(self.pending_tasks),
            len(jobids),
            free_memory_gb,
            self.memory_gb,
            free_processors,
            self.processors,
            free_gpu_slots,
            self.n_gpu_procs,
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
                self.n_gpu_procs,
                tasks_list_msg,
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

            update_node_mem_gb(self.procs[jobid])

            # Check requirements of this job
            next_job_gb = min(self.procs[jobid].mem_gb, self.memory_gb)
            next_job_th = min(self.procs[jobid].n_procs, self.processors)
            next_job_gpu_th = min(self.procs[jobid].n_procs, self.n_gpu_procs)

            is_gpu_node = self.procs[jobid].is_gpu_node()

            # If node does not fit, skip at this moment
            if (
                    next_job_th > free_processors
                    or next_job_gb > free_memory_gb
                    or (is_gpu_node and next_job_gpu_th > free_gpu_slots)
            ):
                logger.debug(
                    "Cannot allocate job %d (%0.2fGB, %d threads, %d GPU slots).",
                    jobid,
                    next_job_gb,
                    next_job_th,
                    next_job_gpu_th,
                )
                continue

            free_memory_gb -= next_job_gb
            free_processors -= next_job_th
            if is_gpu_node:
                free_gpu_slots -= next_job_gpu_th
            logger.debug(
                "Allocating %s ID=%d (%0.2fGB, %d threads). Free: "
                "%0.2fGB, %d threads, %d GPU slots.",
                self.procs[jobid].fullname,
                jobid,
                next_job_gb,
                next_job_th,
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

            cached, updated = self.procs[jobid].is_cached()
            # updatehash and run_without_submitting are also run locally
            if (cached and updatehash and not updated) or self.procs[
                jobid
            ].run_without_submitting:
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
                    free_gpu_slots += next_job_gpu_th
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

