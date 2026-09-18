# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-

from nipype.interfaces.fsl.utils import ImageMaths, ImageMathsInputSpec
from nipype.interfaces.base import traits


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.fsl.utils.ImageMathsInputSpec)  -*-
class ThrROIInputSpec(ImageMathsInputSpec):
    seg_val_min = traits.Float(
        mandatory=True, desc="the min value of interested segmentation"
    )
    seg_val_max = traits.Float(
        mandatory=True, desc="the max value of interested segmentation"
    )


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.fsl.utils.ImageMaths)  -*-
class ThrROI(ImageMaths):
    """
    Extracts a binary ROI from a segmentation using a min and a max value.

    """

    input_spec = ThrROIInputSpec

    def _parse_inputs(self, skip=None):
        """
        Custom implementation of _parse_inputs func to build the threshold op_string.

        """

        self.inputs.op_string = "-thr %.10f -uthr %.10f -bin" % (
            self.inputs.seg_val_min,
            self.inputs.seg_val_max,
        )

        return super(ThrROI, self)._parse_inputs(skip)
