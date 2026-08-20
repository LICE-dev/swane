# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-

import nibabel as nib
import numpy as np
from os.path import abspath
import os
from nipype.interfaces.base import (
    BaseInterface,
    BaseInterfaceInputSpec,
    TraitedSpec,
    File,
    isdefined,
)


# NODE TO CALCULATE Z-SCORE FROM ROI
# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
class ZscoreInputSpec(BaseInterfaceInputSpec):
    in_file = File(exists=True, mandatory=True, desc="the input image")
    ROI_file = File(exists=True, mandatory=True, desc="the ROI mask image")
    out_file = File(desc="the output image")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class ZscoreOutputSpec(TraitedSpec):
    out_file = File(exists=True, desc="the output image")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class Zscore(BaseInterface):
    """
    Calculates the z-score index of an image compared with a ROI.

    """

    input_spec = ZscoreInputSpec
    output_spec = ZscoreOutputSpec

    def _run_interface(self, runtime):
        out_file = self._gen_outfilename()

        in_nii = nib.load(self.inputs.in_file)
        in_data = in_nii.get_fdata(dtype=np.float32)
        roi = nib.load(self.inputs.ROI_file).get_fdata() > 0

        # use only the non-zero voxels inside the ROI; the standard deviation
        # is the sample one (ddof=1)
        roi_vals = in_data[roi & (in_data != 0)]
        mean = roi_vals.mean()
        std = roi_vals.std(ddof=1)

        if std == 0:
            raise RuntimeError("Standard deviation inside the ROI is zero")

        zscore = ((in_data - mean) / std).astype(np.float32)

        # preserve exactly the input image space; set_data_dtype clears any
        # residual scaling so values are not re-scaled on write
        hdr = in_nii.header.copy()
        hdr.set_data_dtype(np.float32)
        nib.save(nib.Nifti1Image(zscore, in_nii.affine, hdr), out_file)

        return runtime

    def _gen_outfilename(self):
        out_file = self.inputs.out_file
        if not isdefined(out_file) and isdefined(self.inputs.in_file):
            out_file = "zscore_" + os.path.basename(self.inputs.in_file)
        return abspath(out_file)

    def _list_outputs(self):
        outputs = self.output_spec().get()
        outputs["out_file"] = self._gen_outfilename()
        return outputs
