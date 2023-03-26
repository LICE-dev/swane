# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-

import shutil
from nipype.pipeline.engine import Workflow
from nipype.interfaces.dcm2nii import Dcm2niix, Dcm2niixInputSpec
from nipype.interfaces.base import InputMultiObject
from nipype.interfaces.fsl import (SwapDimensions, BinaryMaths, UnaryMaths, ImageStats, ProbTrackX2, BEDPOSTX5,
                                   Threshold, ApplyMask, DilateImage, Cluster, SliceTimer, ImageMaths)
from nipype.interfaces.fsl.dti import BEDPOSTX5InputSpec, ProbTrackX2InputSpec
from nipype import Node
from nipype.interfaces.utility import IdentityInterface
from nipype.interfaces.freesurfer import Label2Vol
from os.path import abspath
import os
import glob
import math
from nipype.interfaces.fsl.maths import KernelInput
from nipype.interfaces.fsl.base import FSLCommand, FSLCommandInputSpec
from nipype.interfaces.base import (traits, BaseInterface, BaseInterfaceInputSpec,
                                    TraitedSpec, CommandLineInputSpec, CommandLine,
                                    InputMultiPath, File, Directory, Bunch,
                                    isdefined)
from nipype.interfaces.io import DataSink


# -*- DISCLAIMER: this class extends a Nipype class (nipype.pipeline.engine.Workflow)  -*-
class CustomWorkflow(Workflow):
    def get_node_array(self):
        """List names of all nodes in a workflow"""
        from networkx import topological_sort

        outlist = {}
        for node in topological_sort(self._graph):
            if isinstance(node, Workflow):
                outlist[node.name] = node.get_node_array()
            elif not isinstance(node.interface, IdentityInterface):
                outlist[node.name] = {}
        return outlist

    def sink_result(self, save_path, result_node, result_name, sub_folder, regexp_substitutions=None):

        if isinstance(result_node, str):
            result_node = self.get_node(result_node)

        data_sink = Node(DataSink(), name='SaveResults_' + result_node.name + "_" + result_name.replace(".", "_"))
        data_sink.inputs.base_directory = save_path

        if regexp_substitutions is not None:
            data_sink.inputs.regexp_substitutions = regexp_substitutions

        self.connect(result_node, result_name, data_sink, sub_folder)
