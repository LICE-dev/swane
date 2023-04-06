# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-

from nipype.pipeline.engine import Workflow
from nipype import Node, logging
from nipype.interfaces.utility import IdentityInterface
from nipype.interfaces.io import DataSink
from swane.nipype_pipeline.engine.NodeListEntry import NodeListEntry
from swane import strings

logger = logging.getLogger("nipype.workflow")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.pipeline.engine.Workflow)  -*-
class CustomWorkflow(Workflow):
    """
    Custom implementation of Workflow class with utility funcs.

    """
    
    @staticmethod
    def format_node_name(node):
        """
        Returns the explicit name of a Node.

        """
        
        default_node_name = None
        if hasattr(node, "interface") and type(node.interface).__name__ in strings.node_names:
            default_node_name = strings.node_names[type(node.interface).__name__]
        if hasattr(node, "long_name"):
            formatted_name = node.long_name
            if "%s" in node.long_name and default_node_name is not None:
                formatted_name = node.long_name % default_node_name
        elif default_node_name is not None:
            formatted_name = default_node_name
        else:
            formatted_name = node.name

        formatted_name = formatted_name[0].upper() + formatted_name[1:]
        return formatted_name

    def get_node_array(self):
        """
        Returns a List of NodeListEntry objects for the Nodes in a Workflow.
        
        """
        
        from networkx import topological_sort

        outlist = {}
        for node in topological_sort(self._graph):
            if hasattr(node, "interface") and isinstance(node.interface, IdentityInterface):
                continue

            outlist[node.name] = NodeListEntry()
            outlist[node.name].long_name = self.format_node_name(node)
            if isinstance(node, Workflow):
                outlist[node.name].node_list = node.get_node_array()
        return outlist

    def sink_result(self, save_path, result_node, result_name, sub_folder, regexp_substitutions=None):
        """
        Creates a sink_result Node to save the output files of a Workflow.
        
        """
        
        if isinstance(result_node, str):
            result_node = self.get_node(result_node)

        data_sink = Node(DataSink(), name='SaveResults_' + result_node.name + "_" + result_name.replace(".", "_"))
        data_sink.long_name = "%s: " + result_name
        data_sink.inputs.base_directory = save_path

        if regexp_substitutions is not None:
            data_sink.inputs.regexp_substitutions = regexp_substitutions

        self.connect(result_node, result_name, data_sink, sub_folder)

    def _get_dot(
            self, prefix=None, hierarchy=None, colored=False, simple_form=True, level=0
    ):
        """
        Custom implementation of _get_dot Nipype func to support the long_name Node attribute.
        
        """
        
        import networkx as nx

        if prefix is None:
            prefix = "  "
        if hierarchy is None:
            hierarchy = []
        colorset = [
            "#FFFFC8",  # Y
            "#0000FF",
            "#B4B4FF",
            "#E6E6FF",  # B
            "#FF0000",
            "#FFB4B4",
            "#FFE6E6",  # R
            "#00A300",
            "#B4FFB4",
            "#E6FFE6",  # G
            "#0000FF",
            "#B4B4FF",
        ]  # loop B
        if level > len(colorset) - 2:
            level = 3  # Loop back to blue

        dotlist = ['%slabel="%s";' % (prefix, self.name)]
        for node in nx.topological_sort(self._graph):
            fullname = ".".join(hierarchy + [node.fullname])
            nodename = fullname.replace(".", "_")
            if not isinstance(node, Workflow):
                node_class_name = self.format_node_name(node)
                if hasattr(node, "iterables") and node.iterables:
                    dotlist.append(
                        (
                            '%s[label="%s", shape=box3d,'
                            "style=filled, color=black, colorscheme"
                            "=greys7 fillcolor=2];"
                        )
                        % (nodename, node_class_name)
                    )
                else:
                    if colored:
                        dotlist.append(
                            ('%s[label="%s", style=filled,' ' fillcolor="%s"];')
                            % (nodename, node_class_name, colorset[level])
                        )
                    else:
                        dotlist.append(
                            ('%s[label="%s"];') % (nodename, node_class_name)
                        )

        for node in nx.topological_sort(self._graph):
            if isinstance(node, Workflow):
                fullname = ".".join(hierarchy + [node.fullname])
                nodename = fullname.replace(".", "_")
                dotlist.append("subgraph cluster_%s {" % nodename)
                if colored:
                    dotlist.append(
                        prefix + prefix + 'edge [color="%s"];' % (colorset[level + 1])
                    )
                    dotlist.append(prefix + prefix + "style=filled;")
                    dotlist.append(
                        prefix + prefix + 'fillcolor="%s";' % (colorset[level + 2])
                    )
                dotlist.append(
                    node._get_dot(
                        prefix=prefix + prefix,
                        hierarchy=hierarchy + [self.name],
                        colored=colored,
                        simple_form=simple_form,
                        level=level + 3,
                    )
                )
                dotlist.append("}")
            else:
                for subnode in self._graph.successors(node):
                    if node._hierarchy != subnode._hierarchy:
                        continue
                    if not isinstance(subnode, Workflow):
                        nodefullname = ".".join(hierarchy + [node.fullname])
                        subnodefullname = ".".join(hierarchy + [subnode.fullname])
                        nodename = nodefullname.replace(".", "_")
                        subnodename = subnodefullname.replace(".", "_")
                        for _ in self._graph.get_edge_data(node, subnode)["connect"]:
                            dotlist.append("%s -> %s;" % (nodename, subnodename))
                        logger.debug("connection: %s", dotlist[-1])
        # add between workflow connections
        for u, v, d in self._graph.edges(data=True):
            uname = ".".join(hierarchy + [u.fullname])
            vname = ".".join(hierarchy + [v.fullname])
            for src, dest in d["connect"]:
                uname1 = uname
                vname1 = vname
                if isinstance(src, tuple):
                    srcname = src[0]
                else:
                    srcname = src
                if "." in srcname:
                    uname1 += "." + ".".join(srcname.split(".")[:-1])
                if "." in dest and "@" not in dest:
                    if not isinstance(v, Workflow):
                        if "datasink" not in str(v._interface.__class__).lower():
                            vname1 += "." + ".".join(dest.split(".")[:-1])
                    else:
                        vname1 += "." + ".".join(dest.split(".")[:-1])
                if uname1.split(".")[:-1] != vname1.split(".")[:-1]:
                    dotlist.append(
                        "%s -> %s;"
                        % (uname1.replace(".", "_"), vname1.replace(".", "_"))
                    )
                    logger.debug("cross connection: %s", dotlist[-1])
        return ("\n" + prefix).join(dotlist)