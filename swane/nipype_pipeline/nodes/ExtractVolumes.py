# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-
"""
Extraction of volumes along the time axis of a 4D NIfTI.

``extract_volumes`` slices the image with ``nibabel``'s slicer, which keeps
header, affine, data type and scaling untouched. A single extracted volume is
returned as a 3D image.
"""

from os.path import abspath
import os
import nibabel as nib
from nipype.interfaces.base import (
    traits,
    BaseInterface,
    BaseInterfaceInputSpec,
    TraitedSpec,
    File,
    isdefined,
)


def extract_volumes(in_nii, start_volume, num_volumes):
    """
    Extract ``num_volumes`` volumes starting at ``start_volume`` from the time
    axis of a 4D image. A single volume is returned as 3D.

    """

    if num_volumes == 1:
        return in_nii.slicer[..., start_volume]
    return in_nii.slicer[..., start_volume : start_volume + num_volumes]


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
class ExtractVolumesInputSpec(BaseInterfaceInputSpec):
    in_file = File(exists=True, mandatory=True, desc="the input 4D image")
    start_volume = traits.Int(
        0, usedefault=True, desc="index of the first volume to extract"
    )
    num_volumes = traits.Int(
        1, usedefault=True, desc="number of volumes to extract"
    )
    out_file = File(desc="the output image")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class ExtractVolumesOutputSpec(TraitedSpec):
    out_file = File(desc="the output image")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class ExtractVolumes(BaseInterface):
    """
    Extracts a range of volumes from the time axis of a 4d NIFTI file.

    """

    input_spec = ExtractVolumesInputSpec
    output_spec = ExtractVolumesOutputSpec

    def _run_interface(self, runtime):
        out_file = self._gen_outfilename()

        in_nii = nib.load(self.inputs.in_file)
        nib.save(
            extract_volumes(
                in_nii, self.inputs.start_volume, self.inputs.num_volumes
            ),
            out_file,
        )

        return runtime

    def _gen_outfilename(self):
        out_file = self.inputs.out_file
        if not isdefined(out_file) and isdefined(self.inputs.in_file):
            out_file = "roi_" + os.path.basename(self.inputs.in_file)
        return abspath(out_file)

    def _list_outputs(self):
        outputs = self.output_spec().get()
        outputs["out_file"] = self._gen_outfilename()
        return outputs
