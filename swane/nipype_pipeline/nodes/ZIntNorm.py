# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-
import nibabel as nib
import numpy as np
from os.path import abspath
import os
from nipype.interfaces.base import (
    traits,
    BaseInterface,
    BaseInterfaceInputSpec,
    TraitedSpec,
    File,
    isdefined,
)


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
class ZIntNormInputSpec(BaseInterfaceInputSpec):
    in_file = File(
        exists=True,
        mandatory=True,
        desc="the input image"
    )
    out_file = File(desc="the output normalized image")
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
class ZIntNormOutputSpec(TraitedSpec):
    out_file = File(desc="the output unbiased image")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class ZIntNorm(BaseInterface):
    """
    Apply Z score internal normalization

    """

    input_spec = ZIntNormInputSpec
    output_spec = ZIntNormOutputSpec

    def _run_interface(self, runtime):
        self.inputs.out_file = self._gen_outfilename()

        # --- LOAD IMAGE ---
        img_nii = nib.load(self.inputs.in_file)
        img = img_nii.get_fdata(dtype=np.float32)

        # --- MASK LOGIC ---
        if isdefined(self.inputs.mask_file):
            mask = nib.load(self.inputs.mask_file).get_fdata() > 0
        else:
            mask = img > 0

        # --- Z-SCORE NORMALIZATION ---
        vals = img[mask]

        mean = vals.mean()
        std = vals.std()

        if std == 0:
            raise RuntimeError("Standard deviation is zero")

        img_norm = np.zeros_like(img, dtype=np.float32)
        img_norm[mask] = (img - mean) / std

        # --- SAVE ---
        hdr = img_nii.header.copy()
        hdr.set_data_dtype(np.float32)
        out_nii = nib.Nifti1Image(img_norm, img_nii.affine, hdr)
        nib.save(out_nii, self.inputs.out_file)

        return runtime

    def _gen_outfilename(self):
        out_file = self.inputs.out_file
        if not isdefined(out_file) and isdefined(self.inputs.in_file):
            out_file = "normalized_" + os.path.basename(self.inputs.in_file)
        return abspath(out_file)

    def _list_outputs(self):
        outputs = self.output_spec().get()
        outputs["out_file"] = self._gen_outfilename()
        return outputs
