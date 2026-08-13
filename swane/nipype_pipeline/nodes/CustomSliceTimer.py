# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-

import shutil
from nipype.interfaces.fsl.preprocess import SliceTimer, SliceTimerInputSpec
from nipype.interfaces.base import traits
from swane.config.config_enums import SliceTiming


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.fsl.preprocess.SliceTimerInputSpec)  -*-
class CustomSliceTimerInputSpec(SliceTimerInputSpec):
    slice_timing = traits.Enum(SliceTiming, usedefault=True)


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.fsl.preprocess.SliceTimer)  -*-
class CustomSliceTimer(SliceTimer):
    """
    Applies a slice timing correction, or a plain copy when timing is unknown.

    """

    input_spec = CustomSliceTimerInputSpec

    def _parse_inputs(self, skip=None):
        """
        Custom implementation of _parse_inputs func to map the slice timing
        mode onto the slicetimer command flags.

        """

        if self.inputs.slice_timing == SliceTiming.DOWN:
            self.inputs.index_dir = True
        elif self.inputs.slice_timing == SliceTiming.INTERLEAVED:
            self.inputs.interleaved = True

        return super()._parse_inputs(skip)

    def _run_interface(self, runtime, correct_return_codes=(0,)):
        if self.inputs.slice_timing == SliceTiming.UNKNOWN:
            # no correction needed: just copy the input to the expected output
            out_file = self._list_outputs()["slice_time_corrected_file"]
            shutil.copy(self.inputs.in_file, out_file)
            return runtime

        return super()._run_interface(
            runtime, correct_return_codes=correct_return_codes
        )
