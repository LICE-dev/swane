# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-

from nipype.interfaces.fsl import (BinaryMaths, ImageStats, ApplyMask)
from os.path import abspath
import os
from nipype.interfaces.base import (BaseInterface, BaseInterfaceInputSpec, TraitedSpec, File, isdefined)


# NODO PER CALCOLARE Z SCORE DA ROI
# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
class ZscoreInputSpec(BaseInterfaceInputSpec):
    in_file = File(exists=True, mandatory=True, desc='the input image')
    ROI_file = File(exists=True, mandatory=True, desc='the input image')
    out_file = File(desc='the output image')


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class ZscoreOutputSpec(TraitedSpec):
    out_file = File(exists=True, desc='the output image')


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class Zscore(BaseInterface):
    """
    Calculates the z-score index of an image compared with a ROI.

    """
    
    input_spec = ZscoreInputSpec
    output_spec = ZscoreOutputSpec

    def _run_interface(self, runtime):
        self.inputs.out_file = self._gen_outfilename()

        mask = ApplyMask()
        mask.inputs.in_file = self.inputs.in_file
        mask.inputs.mask_file = self.inputs.ROI_file
        mask.inputs.out_file = abspath("mask_" + os.path.basename(self.inputs.in_file))
        res_mask = mask.run()

        mean = ImageStats()
        mean.inputs.in_file = res_mask.outputs.out_file
        mean.inputs.op_string = "-M"
        mean_res = mean.run()

        sd = ImageStats()
        sd.inputs.in_file = res_mask.outputs.out_file
        sd.inputs.op_string = "-S"
        sd_res = sd.run()

        sub = BinaryMaths()
        sub.inputs.in_file = self.inputs.in_file
        sub.inputs.operation = "sub"
        sub.inputs.operand_value = mean_res.outputs.out_stat
        sub_res = sub.run()

        div = BinaryMaths()
        div.inputs.in_file = sub_res.outputs.out_file
        div.inputs.operation = "div"
        div.inputs.operand_value = sd_res.outputs.out_stat
        div.inputs.out_file = self.inputs.out_file
        div.run()

        return runtime

    def _gen_outfilename(self):
        out_file = self.inputs.out_file
        if not isdefined(out_file) and isdefined(self.inputs.in_file):
            out_file = "zscore_" + os.path.basename(self.inputs.in_file)
        return abspath(out_file)

    def _list_outputs(self):
        outputs = self.output_spec().get()
        outputs['out_file'] = self._gen_outfilename()
        return outputs
