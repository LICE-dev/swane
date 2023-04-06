# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-

import shutil
from nipype.interfaces.fsl import SwapDimensions
from os.path import abspath
import os
from nipype.interfaces.base import (BaseInterface, BaseInterfaceInputSpec, TraitedSpec, File, isdefined)
from swane.nipype_pipeline.nodes.Orient import Orient


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
class ForceOrientInputSpec(BaseInterfaceInputSpec):
    in_file = File(exists=True, mandatory=True, desc='the input image')
    out_file = File(desc='the output image')


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class ForceOrientOutputSpec(TraitedSpec):
    out_file = File(desc='the output image')


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class ForceOrient(BaseInterface):
    """
    Converts an image in radiological convention and in RL PA IS orientation.

    """
    
    input_spec = ForceOrientInputSpec
    output_spec = ForceOrientOutputSpec

    def _run_interface(self, runtime):
        self.inputs.out_file = self._gen_outfilename()
        shutil.copy(self.inputs.in_file, self.inputs.out_file)
        get_orient = Orient(in_file=self.inputs.out_file)
        get_orient.inputs.get_orient = True
        res = get_orient.run()
        if res.outputs.orient == "NEUROLOGICAL":
            swap_nr = SwapDimensions()
            swap_nr.inputs.in_file = self.inputs.out_file
            swap_nr.inputs.out_file = self.inputs.out_file
            swap_nr.inputs.new_dims = ("-x", "y", "z")
            swap_nr.run()
            swap_orient = Orient(in_file=self.inputs.out_file)
            swap_orient.inputs.swap_orient = True
            swap_orient.run()
        swap_dim = SwapDimensions()
        swap_dim.inputs.in_file = self.inputs.out_file
        swap_dim.inputs.out_file = self.inputs.out_file
        swap_dim.inputs.new_dims = ("RL", "PA", "IS")
        swap_dim.run()

        return runtime

    def _gen_outfilename(self):
        out_file = self.inputs.out_file
        if not isdefined(out_file) and isdefined(self.inputs.in_file):
            out_file = os.path.basename(self.inputs.in_file)
        return abspath(out_file)

    def _list_outputs(self):
        outputs = self.output_spec().get()
        outputs['out_file'] = self._gen_outfilename()
        return outputs
