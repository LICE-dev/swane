# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-

from nipype.interfaces.fsl.preprocess import SliceTimer, SliceTimerInputSpec
from nipype.interfaces.base import traits
from swane.config.config_enums import SliceTiming


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.fsl.preprocess.SliceTimerInputSpec)  -*-
class CustomSliceTimerInputSpec(SliceTimerInputSpec):
    # UNKNOWN is excluded here: it is handled by skipping this node's
    # construction at the workflow level, so accepting it on the trait would
    # let it silently slip through as a plain "regular up" run instead.
    slice_timing = traits.Enum(
        *(v for v in SliceTiming if v != SliceTiming.UNKNOWN), usedefault=True
    )


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.fsl.preprocess.SliceTimer)  -*-
class CustomSliceTimer(SliceTimer):
    """
    Applies a slice timing correction.

    Callers must not build this node when the slice timing is unknown: that
    case is skipped at the workflow level, so this node always runs the
    underlying slicetimer command when it is executed.

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
