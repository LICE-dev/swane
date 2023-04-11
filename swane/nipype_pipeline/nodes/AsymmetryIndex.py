# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-

from nipype.interfaces.fsl import BinaryMaths

from os.path import abspath
import os

from nipype.interfaces.base import (BaseInterface, BaseInterfaceInputSpec, TraitedSpec, File, isdefined)


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
class AsymmetryIndexInputSpec(BaseInterfaceInputSpec):
    
    in_file = File(exists=True, mandatory=True, desc='the input image')
    swapped_file = File(exists=True, mandatory=True, desc='the swapped input image')
    out_file = File(desc='the output image')


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class AsymmetryIndexOutputSpec(TraitedSpec):
    out_file = File(desc='the output image')


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class AsymmetryIndex(BaseInterface):
    """
    Generate Asymmetry Index Map from an image and its RL swapped as subtraction/sum.

    """
    
    input_spec = AsymmetryIndexInputSpec
    output_spec = AsymmetryIndexOutputSpec

    def _run_interface(self, runtime):
        self.inputs.out_file = self._gen_outfilename()

        add = BinaryMaths()
        add.inputs.in_file = self.inputs.in_file
        add.inputs.operand_file = self.inputs.swapped_file
        add.inputs.operation = "add"
        add.inputs.out_file = abspath("add_" + os.path.basename(self.inputs.in_file))
        add_res = add.run()

        sub = BinaryMaths()
        sub.inputs.in_file = self.inputs.in_file
        sub.inputs.operand_file = self.inputs.swapped_file
        sub.inputs.operation = "sub"
        sub.inputs.out_file = abspath("sub_" + os.path.basename(self.inputs.in_file))
        sub_res = sub.run()

        div = BinaryMaths()
        div.inputs.in_file = sub_res.outputs.out_file
        div.inputs.operand_file = add_res.outputs.out_file
        div.inputs.operation = "div"
        div.inputs.out_file = self.inputs.out_file
        div.run()

        return runtime

    def _gen_outfilename(self):
        out_file = self.inputs.out_file
        if not isdefined(out_file) and isdefined(self.inputs.in_file):
            out_file = "Aindex_" + os.path.basename(self.inputs.in_file)
        return abspath(out_file)

    def _list_outputs(self):
        outputs = self.output_spec().get()
        outputs['out_file'] = self._gen_outfilename()
        return outputs
