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


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
class AsymmetryIndexInputSpec(BaseInterfaceInputSpec):

    in_file = File(exists=True, mandatory=True, desc="the input image")
    swapped_file = File(exists=True, mandatory=True, desc="the swapped input image")
    out_file = File(desc="the output image")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class AsymmetryIndexOutputSpec(TraitedSpec):
    out_file = File(desc="the output image")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class AsymmetryIndex(BaseInterface):
    """
    Generate Asymmetry Index Map from an image and its RL swapped as (in - swapped) / (in + swapped).

    """

    input_spec = AsymmetryIndexInputSpec
    output_spec = AsymmetryIndexOutputSpec

    def _run_interface(self, runtime):
        out_file = self._gen_outfilename()

        in_nii = nib.load(self.inputs.in_file)
        in_data = in_nii.get_fdata(dtype=np.float32)
        swapped_data = nib.load(self.inputs.swapped_file).get_fdata(dtype=np.float32)

        num = in_data - swapped_data
        den = in_data + swapped_data

        # asymmetry index; division by zero yields 0
        ai = np.zeros_like(in_data, dtype=np.float32)
        np.divide(num, den, out=ai, where=(den != 0))

        # preserve exactly the input image space; set_data_dtype clears any
        # residual scaling so values are not re-scaled on write
        hdr = in_nii.header.copy()
        hdr.set_data_dtype(np.float32)
        nib.save(nib.Nifti1Image(ai, in_nii.affine, hdr), out_file)

        return runtime

    def _gen_outfilename(self):
        out_file = self.inputs.out_file
        if not isdefined(out_file) and isdefined(self.inputs.in_file):
            out_file = "Aindex_" + os.path.basename(self.inputs.in_file)
        return abspath(out_file)

    def _list_outputs(self):
        outputs = self.output_spec().get()
        outputs["out_file"] = self._gen_outfilename()
        return outputs
