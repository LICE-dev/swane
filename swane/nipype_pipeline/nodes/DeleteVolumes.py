# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-

from nipype.interfaces.fsl.utils import (
    ExtractROI,
    ExtractROIInputSpec,
    ExtractROIOutputSpec,
)
from nipype.interfaces.base import traits


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.fsl.utils.ExtractROIInputSpec)  -*-
class DeleteVolumesInputSpec(ExtractROIInputSpec):
    nvols = traits.Int(mandatory=True, desc="original file volumes")
    del_start_vols = traits.Int(mandatory=True, desc="volumes to delete from start")
    del_end_vols = traits.Int(mandatory=True, desc="volumes to delete from end")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.fsl.utils.ExtractROIOutputSpec)  -*-
class DeleteVolumesOutputSpec(ExtractROIOutputSpec):
    nvols = traits.Int(desc="new number of volumes")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.fsl.utils.ExtractROI)  -*-
class DeleteVolumes(ExtractROI):
    """
    Removes specified num. of volumes from start and end of a 4d NIFTI file.

    """

    input_spec = DeleteVolumesInputSpec
    output_spec = DeleteVolumesOutputSpec

    def _parse_inputs(self, skip=None):
        """
        Custom implementation of _parse_inputs func to derive the ROI from the
        requested start/end trimming.

        """

        self.inputs.t_min = self.inputs.del_start_vols
        self.inputs.t_size = (
            self.inputs.nvols - self.inputs.del_start_vols - self.inputs.del_end_vols
        )

        return super()._parse_inputs(skip)

    def _list_outputs(self):
        outputs = super()._list_outputs()
        outputs["nvols"] = (
            self.inputs.nvols - self.inputs.del_start_vols - self.inputs.del_end_vols
        )
        return outputs
