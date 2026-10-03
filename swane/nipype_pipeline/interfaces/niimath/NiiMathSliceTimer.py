# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-

from nipype.interfaces.fsl.utils import ImageMathsInputSpec
from nipype.interfaces.base import traits
from swane.nipype_pipeline.interfaces.niimath.maths import ImageMaths
from swane.config.config_enums import SliceTiming


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.fsl.utils.ImageMathsInputSpec)  -*-
class NiiMathSliceTimerInputSpec(ImageMathsInputSpec):
    time_repetition = traits.Float(
        mandatory=True, desc="Repetition time of the series, in seconds"
    )
    # UNKNOWN is excluded here, as in CustomSliceTimer: that case is handled by
    # skipping this node's construction at the workflow level.
    slice_timing = traits.Enum(
        *(v for v in SliceTiming if v != SliceTiming.UNKNOWN), usedefault=True
    )


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.fsl.ImageMaths)  -*-
class NiiMathSliceTimer(ImageMaths):
    """
    Slice timing correction executed through the niimath binary (-stc).

    The per-slice acquisition times are derived from the slice timing mode,
    the repetition time and the number of slices along the third voxel axis,
    with the same conventions as FSL slicetimer's defaults: "Regular up"
    acquires slice k at k*TR/n, "Regular down" reverses the slice order and
    "Interleaved" acquires the even voxel indices first (0, 2, 4, ...), then the
    odd ones. Every slice is shifted to the middle of the TR (-tzero TR/2).

    Callers must not build this node when the slice timing is unknown.

    """

    input_spec = NiiMathSliceTimerInputSpec

    @staticmethod
    def slice_times(n_slices: int, tr: float, slice_timing: SliceTiming) -> list:
        """
        Returns the acquisition time, in seconds, of each slice along the
        third voxel axis.

        Parameters
        ----------
        n_slices : int
            The number of slices along the third voxel axis.
        tr : float
            The repetition time, in seconds.
        slice_timing : SliceTiming
            The slice acquisition order.

        Returns
        -------
        list of float
            The acquisition time of slice k at index k.

        """
        if slice_timing == SliceTiming.UP:
            order = list(range(n_slices))
        elif slice_timing == SliceTiming.DOWN:
            order = list(range(n_slices - 1, -1, -1))
        elif slice_timing == SliceTiming.INTERLEAVED:
            order = list(range(0, n_slices, 2)) + list(range(1, n_slices, 2))
        else:
            raise ValueError("Unsupported slice timing: %s" % slice_timing)

        times = [0.0] * n_slices
        for position, slice_index in enumerate(order):
            times[slice_index] = position * tr / n_slices
        return times

    def _parse_inputs(self, skip=None):
        from nibabel import load

        n_slices = load(self.inputs.in_file).shape[2]
        tr = self.inputs.time_repetition
        times = self.slice_times(n_slices, tr, self.inputs.slice_timing)
        self.inputs.op_string = "-stc --slicetiming %s -tzero %.6f" % (
            ",".join("%.6f" % t for t in times),
            tr / 2,
        )

        return super()._parse_inputs(skip)
