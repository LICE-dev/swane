# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-

from nipype.interfaces.fsl import (UnaryMaths, Threshold)
from os.path import abspath
import os
from nipype.interfaces.base import (traits, BaseInterface, BaseInterfaceInputSpec, TraitedSpec, File, isdefined)


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
class ThrROIInputSpec(BaseInterfaceInputSpec):
    in_file = File(exists=True, mandatory=True, desc='the input image')
    seg_val_min = traits.Float(mandatory=True, desc='the min value of interested segmentation')
    seg_val_max = traits.Float(mandatory=True, desc='the max value of interested segmentation')
    out_file = File(desc='the output image')


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class ThrROIOutputSpec(TraitedSpec):
    out_file = File(desc='the output image')


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class ThrROI(BaseInterface):
    """
    Extracts a binary ROI from a segmentation using a min and a max value.

    """
    
    input_spec = ThrROIInputSpec
    output_spec = ThrROIOutputSpec

    def _run_interface(self, runtime):
        self.inputs.out_file = self._gen_outfilename()

        below = Threshold()
        below.inputs.in_file = self.inputs.in_file
        below.inputs.direction = "below"
        below.inputs.thresh = self.inputs.seg_val_min
        below.inputs.out_file = abspath("below_" + os.path.basename(self.inputs.in_file))
        below_res = below.run()

        above = Threshold()
        above.inputs.in_file = below_res.outputs.out_file
        above.inputs.direction = "above"
        above.inputs.thresh = self.inputs.seg_val_max
        above.inputs.out_file = abspath("above_" + os.path.basename(self.inputs.in_file))
        above_res = above.run()

        bin = UnaryMaths()
        bin.inputs.in_file = above_res.outputs.out_file
        bin.inputs.operation = "bin"
        bin.inputs.out_file = self.inputs.out_file
        bin.run()

        # todo semplificare il nodo subclassando ImageMaths, esempio sotto
        # calc_roi = ImageMaths()
        # calc_roi.inputs.in_file = self.inputs.in_file
        # calc_roi.inputs.op_string = "-thr %f -uthr %f -bin" % (self.inputs.seg_val_min, self.inputs.seg_val_max)
        # calc_roi.inputs.out_file = self.inputs.out_file
        # calc_roi.run()

        return runtime

    def _gen_outfilename(self):
        out_file = self.inputs.out_file
        if not isdefined(out_file) and isdefined(self.inputs.in_file):
            out_file = "ROI_" + str(self.inputs.seg_val_min) + "_" + str(
                self.inputs.seg_val_min) + "_" + os.path.basename(self.inputs.in_file)
        return abspath(out_file)

    def _list_outputs(self):
        outputs = self.output_spec().get()
        outputs['out_file'] = self._gen_outfilename()
        return outputs
