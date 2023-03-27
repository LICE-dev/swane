# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-

from nipype.pipeline.engine import Workflow
from nipype import Node
from nipype.interfaces.utility import IdentityInterface
from nipype.interfaces.io import DataSink
from swane.nipype_pipeline.engine.NodeListEntry import NodeListEntry


# -*- DISCLAIMER: this class extends a Nipype class (nipype.pipeline.engine.Workflow)  -*-
class CustomWorkflow(Workflow):
    def get_node_array(self):
        """List names of all nodes in a workflow"""
        from networkx import topological_sort

        outlist = {}
        for node in topological_sort(self._graph):
            if hasattr(node, "interface") and isinstance(node.interface, IdentityInterface):
                continue

            outlist[node.name] = NodeListEntry()
            if hasattr(node, "long_name"):
                outlist[node.name].long_name = node.long_name
            else:
                outlist[node.name].long_name = node.name
            if isinstance(node, Workflow):
                outlist[node.name].node_list = node.get_node_array()
        return outlist

    def sink_result(self, save_path, result_node, result_name, sub_folder, regexp_substitutions=None):

        if isinstance(result_node, str):
            result_node = self.get_node(result_node)

        data_sink = Node(DataSink(), name='SaveResults_' + result_node.name + "_" + result_name.replace(".", "_"))
        data_sink.inputs.base_directory = save_path

        if regexp_substitutions is not None:
            data_sink.inputs.regexp_substitutions = regexp_substitutions

        self.connect(result_node, result_name, data_sink, sub_folder)
