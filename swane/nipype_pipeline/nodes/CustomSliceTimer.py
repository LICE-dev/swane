# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-

import shutil
from nipype.interfaces.fsl import SliceTimer
from nipype import Node
from os.path import abspath
import os
from nipype.interfaces.base import (traits, TraitedSpec, BaseInterface, BaseInterfaceInputSpec, File)


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
class CustomSliceTimerInputSpec(BaseInterfaceInputSpec):
    in_file = File(exists=True, mandatory=True, desc='the input image')
    time_repetition = traits.Float(mandatory=True)
    slice_timing = traits.Enum(
        0,  # None
        1,  # Regular up
        2,  # Regular down
        3,  # intervealed
        usedefault=True)


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class CustomSliceTimerOutputSpec(TraitedSpec):
    slice_time_corrected_file = File(desc='the output image')


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class CustomSliceTimer(BaseInterface):
    """
    Applies a slice timing correction.

    """
    
    input_spec = CustomSliceTimerInputSpec
    output_spec = CustomSliceTimerOutputSpec

    def _run_interface(self, runtime):
        out_file = self._gen_outfilename()
        if self.inputs.slice_timing == 0:
            shutil.copy(self.inputs.in_file, out_file)
        else:
            fmri_timing_correction = Node(SliceTimer(), name="fMRI_timing_correction")
            fmri_timing_correction.inputs.time_repetition = self.inputs.time_repetition
            fmri_timing_correction.inputs.in_file = self.inputs.in_file
            fmri_timing_correction.inputs.out_file = out_file
            if self.inputs.slice_timing == 2:
                fmri_timing_correction.inputs.index_dir = True
            elif self.inputs.slice_timing == 3:
                fmri_timing_correction.inputs.interleaved = True
            fmri_timing_correction.run()

        return runtime

    def _gen_outfilename(self):
        out_file = os.path.basename(self.inputs.in_file)
        return abspath(out_file)

    def _list_outputs(self):
        outputs = self.output_spec().get()
        outputs['slice_time_corrected_file'] = self._gen_outfilename()
        return outputs
