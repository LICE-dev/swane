# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-
"""
Diffusion tensor fit and fractional anisotropy (FA) map.

Fits dipy's diffusion tensor model (``dipy.reconst.dti.TensorModel``) inside
a brain mask and writes the FA map derived from the fitted eigenvalues.
"""

import os
from os.path import abspath

import nibabel as nib
import numpy as np
from nipype.interfaces.base import (
    BaseInterface,
    BaseInterfaceInputSpec,
    TraitedSpec,
    File,
    isdefined,
)

OMP_THREADS_VAR = "OMP_NUM_THREADS"


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
class DipyTensorFitInputSpec(BaseInterfaceInputSpec):
    in_file = File(
        exists=True, mandatory=True, desc="the input 4D diffusion-weighted image"
    )
    bval = File(exists=True, mandatory=True, desc="the b-values file")
    bvec = File(exists=True, mandatory=True, desc="the b-vectors file")
    mask = File(exists=True, mandatory=True, desc="the brain mask restricting the fit")
    out_fa = File(desc="the output FA map")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class DipyTensorFitOutputSpec(TraitedSpec):
    fa = File(desc="the output FA map")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class DipyTensorFit(BaseInterface):
    """
    Fits a diffusion tensor model to a 4D DWI volume and writes its
    fractional anisotropy (FA) map.

    """

    input_spec = DipyTensorFitInputSpec
    output_spec = DipyTensorFitOutputSpec

    def _run_interface(self, runtime):
        from dipy.core.gradients import gradient_table
        from dipy.io.gradients import read_bvals_bvecs
        from dipy.reconst import dti

        out_fa = self._gen_outfilename()

        in_nii = nib.load(self.inputs.in_file)
        data = in_nii.get_fdata()
        mask_data = nib.load(self.inputs.mask).get_fdata().astype(bool)
        bvals, bvecs = read_bvals_bvecs(self.inputs.bval, self.inputs.bvec)
        gtab = gradient_table(bvals, bvecs=bvecs)

        previous_omp = os.environ.get(OMP_THREADS_VAR)
        os.environ[OMP_THREADS_VAR] = "1"
        try:
            tenfit = dti.TensorModel(gtab).fit(data, mask=mask_data)
            fa = tenfit.fa
        finally:
            if previous_omp is None:
                os.environ.pop(OMP_THREADS_VAR, None)
            else:
                os.environ[OMP_THREADS_VAR] = previous_omp

        nib.save(
            nib.Nifti1Image(fa.astype(np.float32), in_nii.affine, in_nii.header),
            out_fa,
        )

        return runtime

    def _gen_outfilename(self):
        out_fa = self.inputs.out_fa
        if not isdefined(out_fa) and isdefined(self.inputs.in_file):
            out_fa = "fa_" + os.path.basename(self.inputs.in_file)
        return abspath(out_fa)

    def _list_outputs(self):
        outputs = self.output_spec().get()
        outputs["fa"] = self._gen_outfilename()
        return outputs
