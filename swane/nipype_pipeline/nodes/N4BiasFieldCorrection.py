# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-
import SimpleITK as sitk
from os.path import abspath
import os

from bokeh.core.property.primitive import Bool
from nipype.interfaces.base import (
    traits,
    BaseInterface,
    BaseInterfaceInputSpec,
    TraitedSpec,
    File,
    isdefined,
)


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
class N4BiasFieldCorrectionInputSpec(BaseInterfaceInputSpec):
    in_file = File(
        exists=True,
        mandatory=True,
        desc="the input image"
    )
    out_file = File(desc="the output unbiased image")
    skull_stripped = traits.Bool(
        False,
        usedefault=True,
        desc="Set to True if the input image is already skull stripped"
    )
    mask_file = File(
        exists=True,
        desc="the mask image"
    )


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class N4BiasFieldCorrectionOutputSpec(TraitedSpec):
    out_file = File(desc="the output unbiased image")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class N4BiasFieldCorrection(BaseInterface):
    """
    If FOV exceeds 250mm, crop the borders.

    """

    input_spec = N4BiasFieldCorrectionInputSpec
    output_spec = N4BiasFieldCorrectionOutputSpec

    def _run_interface(self, runtime):
        self.inputs.out_file = self._gen_outfilename()

        # load image as float, as requested by N4
        img = sitk.ReadImage(self.inputs.in_file, sitk.sitkFloat32)

        # --- MASK LOGIC ---
        if isdefined(self.inputs.mask_file):
            # If a mask is provided, use it
            mask = sitk.ReadImage(self.inputs.mask_file, sitk.sitkUInt8)
        elif self.inputs.skull_stripped:
            # Otherwise, if the input sequence is skull stripped, assume brain for every non 0 voxel
            mask = sitk.Cast(img > 0, sitk.sitkUInt8)
        else:
            # In other cases use automatic thresholding
            mask = sitk.OtsuThreshold(img, 0, 1, 200)

        # --- N4 ---
        corrector = sitk.N4BiasFieldCorrectionImageFilter()
        corrected = corrector.Execute(img, mask)

        # save output
        sitk.WriteImage(corrected, self.inputs.out_file)

        return runtime

    def _gen_outfilename(self):
        out_file = self.inputs.out_file
        if not isdefined(out_file) and isdefined(self.inputs.in_file):
            out_file = "unbiased_" + os.path.basename(self.inputs.in_file)
        return abspath(out_file)

    def _list_outputs(self):
        outputs = self.output_spec().get()
        outputs["out_file"] = self._gen_outfilename()
        return outputs
