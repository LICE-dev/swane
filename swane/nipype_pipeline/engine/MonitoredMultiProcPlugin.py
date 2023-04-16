# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-

from nipype.pipeline.plugins.multiproc import MultiProcPlugin
import traceback


# -*- DISCLAIMER: this class extends a Nipype class (nipype.pipeline.plugins.multiproc.MultiProcPlugin)  -*-
class MonitoredMultiProcPlugin(MultiProcPlugin):

    NODE_STARTED = "start"
    NODE_COMPLETED = "end"
    NODE_ERROR = "exception"
    WORKFLOW_INSUFFICIENT_RESOURCES = "insufficientresources"

    def __init__(self,  plugin_args=None):
        print(plugin_args)
        if "queue" in plugin_args:
            self.queue = plugin_args["queue"]
        super(MonitoredMultiProcPlugin, self).__init__(plugin_args=plugin_args)

        # it's mandatory delete this argument to avoid plugin copy generated by MapNodes to raise exceptions
        plugin_args["queue"] = None

    def _report_crash(self, node, result=None):
        # This class implements signaling for generic node error
        try:
            self.queue.put(node.fullname + "." + MonitoredMultiProcPlugin.NODE_ERROR)
        except:
            traceback.print_exc()
        return super(MonitoredMultiProcPlugin, self)._report_crash(node, result)

    def _submit_job(self, node, updatehash=False):
        # This class implements signaling for generic node start
        if node.name[0] != "_":
            try:
                self.queue.put(node.fullname + "." + MonitoredMultiProcPlugin.NODE_STARTED)
            except:
                traceback.print_exc()
        return super(MonitoredMultiProcPlugin, self)._submit_job(node, updatehash)

    def _submit_mapnode(self, jobid):
        # This class implements signaling for mapnode start
        try:
            self.queue.put(self.procs[jobid].fullname + "." + MonitoredMultiProcPlugin.NODE_STARTED)
        except:
            traceback.print_exc()
        return super(MonitoredMultiProcPlugin, self)._submit_mapnode(jobid)

    def _task_finished_cb(self, jobid, cached=False):
        # This class implements signaling for generic node completion
        if jobid not in self.mapnodesubids:
            try:
                self.queue.put(self.procs[jobid].fullname + "." + MonitoredMultiProcPlugin.NODE_COMPLETED)
            except:
                traceback.print_exc()
        return super(MonitoredMultiProcPlugin, self)._task_finished_cb(jobid, cached)

    def _prerun_check(self, graph):
        # This class implements signaling for insufficient resources error
        try:
            return super(MonitoredMultiProcPlugin, self)._prerun_check(graph)
        except RuntimeError:
            self.queue.put(MonitoredMultiProcPlugin.WORKFLOW_INSUFFICIENT_RESOURCES)
            raise RuntimeError("Insufficient resources available for job")
