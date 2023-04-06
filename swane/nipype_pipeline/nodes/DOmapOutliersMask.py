# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-

import shutil
from nipype.interfaces.fsl import (BinaryMaths, UnaryMaths, ImageStats, Threshold)
from os.path import abspath
import math
from nipype.interfaces.base import (BaseInterface, BaseInterfaceInputSpec, TraitedSpec, File, isdefined)


# nodo per rimozione outliers nel DOmap
# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
class DOmapOutliersMaskInputSpec(BaseInterfaceInputSpec):
    in_file = File(exists=True, mandatory=True, desc='the input image')
    mask_file = File(exists=True, mandatory=True, desc='the original mask image')
    out_file = File(desc='the output mask name')


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class DOmapOutliersMaskOutputSpec(TraitedSpec):
    out_file = File(exists=True, desc='the output image')


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class DOmapOutliersMask(BaseInterface):
    """
    Creates a mask that can be used to remove the outliers in DOmap workflow.

    """
    
    input_spec = DOmapOutliersMaskInputSpec
    output_spec = DOmapOutliersMaskOutputSpec

    def _run_interface(self, runtime):
        self.inputs.out_file = self._gen_outfilename()

        mean = ImageStats()
        mean.inputs.in_file = self.inputs.in_file
        mean.inputs.op_string = "-M"
        mean_res = mean.run()

        mean_value = math.trunc(mean_res.outputs.out_stat)

        if mean_value <= 100:
            threshold = mean_value + 1
            thr = Threshold()
            thr.inputs.in_file = self.inputs.in_file
            thr.inputs.thresh = threshold
            thr_res = thr.run()

            bin_math = UnaryMaths()
            bin_math.inputs.in_file = thr_res.outputs.out_file
            bin_math.inputs.operation = "bin"
            bin_res = bin_math.run()

            sub = BinaryMaths()
            sub.inputs.in_file = self.inputs.mask_file
            sub.inputs.operation = "sub"
            sub.inputs.operand_file = bin_res.outputs.out_file
            sub.inputs.out_file = self.inputs.out_file
            sub.run()
        else:
            shutil.copy(self.inputs.mask_file, self.inputs.out_file)

        return runtime

    def _gen_outfilename(self):
        out_file = self.inputs.out_file
        if not isdefined(out_file):
            out_file = "brain_cortex_mas_refined.nii.gz"
        return abspath(out_file)

    def _list_outputs(self):
        outputs = self.output_spec().get()
        outputs['out_file'] = self._gen_outfilename()
        return outputs
