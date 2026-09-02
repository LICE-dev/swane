# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-
"""
B1 bias field correction of a 4D diffusion-weighted image.

The N4 bias field (Tustison 2010, via the antspyx library) is estimated
**once**, on the mean b0, and that single multiplicative field is divided out
of every DWI volume. Estimating a field per volume, or correcting only the b0,
would introduce a volume-dependent intensity bias into the tensor/CSD fit; the
field is a property of the receive coil and the subject's anatomy, not of the
diffusion weighting, so one estimate applies to all volumes.

The b0 volumes are located from the b-values (``bval`` at or below
``B0_MAX_BVAL``). Only antspyx's N4 estimator is borrowed here; the rest is
plain nibabel/numpy so the estimate and the broadcast division stay index
aligned with the input.
"""

import os
from os.path import abspath

import nibabel as nib
import numpy as np
from nipype.interfaces.base import (
    traits,
    BaseInterface,
    BaseInterfaceInputSpec,
    TraitedSpec,
    File,
    isdefined,
)

# antspyx is imported lazily inside _run_interface, as in AntsN4BiasFieldCorrection.

OMP_THREADS_VAR = "OMP_NUM_THREADS"
OPENBLAS_THREADS_VAR = "OPENBLAS_NUM_THREADS"
ITK_THREADS_VAR = "ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS"

# b-values at or below this threshold are treated as b0 (non-diffusion-weighted).
B0_MAX_BVAL = 50.0


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
class DwiBiasCorrectionInputSpec(BaseInterfaceInputSpec):
    in_file = File(
        exists=True, mandatory=True, desc="the input 4D diffusion-weighted image"
    )
    bval = File(
        exists=True, mandatory=True, desc="the b-values file (used to locate the b0s)"
    )
    num_threads = traits.Int(
        nohash=True, desc="number of OpenMP/OpenBLAS/ITK threads to use"
    )
    out_file = File(desc="the output 4D bias-corrected image")
    bias_field = File(desc="the estimated N4 bias field")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class DwiBiasCorrectionOutputSpec(TraitedSpec):
    out_file = File(desc="the output 4D bias-corrected image")
    bias_field = File(desc="the estimated N4 bias field")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class DwiBiasCorrection(BaseInterface):
    """
    Corrects the B1 bias field of a 4D DWI by estimating a single N4 field on
    the mean b0 and dividing every volume by that same field.

    """

    input_spec = DwiBiasCorrectionInputSpec
    output_spec = DwiBiasCorrectionOutputSpec

    def _run_interface(self, runtime):
        import ants

        out_file = self._gen_outfilename()
        field_file = self._gen_fieldfilename()

        in_nii = nib.load(self.inputs.in_file)
        data = in_nii.get_fdata(dtype=np.float32)
        if data.ndim != 4:
            raise RuntimeError(
                "DwiBiasCorrection expects a 4D DWI, got shape %s" % (data.shape,)
            )

        bvals = np.atleast_1d(np.loadtxt(self.inputs.bval).astype(float).ravel())
        if bvals.shape[0] != data.shape[3]:
            raise RuntimeError(
                "bval count (%d) does not match the number of DWI volumes (%d)"
                % (bvals.shape[0], data.shape[3])
            )

        b0_mask = bvals <= B0_MAX_BVAL
        if not np.any(b0_mask):
            raise RuntimeError(
                "no b0 volume found (all b-values above %g); cannot estimate the "
                "bias field" % B0_MAX_BVAL
            )

        # Mean b0 image: the single input to the one N4 estimation.
        mean_b0 = data[..., b0_mask].mean(axis=3)

        # antspyx wants the physical voxel spacing to place its spline mesh; the
        # division below is index-aligned, so only the spatial spacing matters.
        zooms = in_nii.header.get_zooms()[:3]
        mean_b0_img = ants.from_numpy(
            mean_b0.astype(np.float32), spacing=tuple(float(z) for z in zooms)
        )

        previous = {
            var: os.environ.get(var)
            for var in (OMP_THREADS_VAR, OPENBLAS_THREADS_VAR, ITK_THREADS_VAR)
        }
        if isdefined(self.inputs.num_threads):
            for var in (OMP_THREADS_VAR, OPENBLAS_THREADS_VAR, ITK_THREADS_VAR):
                os.environ[var] = str(self.inputs.num_threads)
        try:
            # Estimate the bias field once, on the mean b0.
            bias_img = ants.n4_bias_field_correction(
                mean_b0_img, return_bias_field=True
            )
        finally:
            for var, value in previous.items():
                if value is None:
                    os.environ.pop(var, None)
                else:
                    os.environ[var] = value

        field = np.asarray(bias_img.numpy(), dtype=np.float32)

        # Divide every volume by that single field. The field is strictly
        # positive where N4 is defined; guard the rest to avoid dividing by zero
        # (background voxels stay unchanged).
        safe_field = np.where(field > 0, field, 1.0).astype(np.float32)
        corrected = (data / safe_field[..., np.newaxis]).astype(np.float32)

        nib.save(nib.Nifti1Image(corrected, in_nii.affine, in_nii.header), out_file)
        nib.save(nib.Nifti1Image(field, in_nii.affine), field_file)

        return runtime

    def _gen_outfilename(self):
        out_file = self.inputs.out_file
        if not isdefined(out_file) and isdefined(self.inputs.in_file):
            out_file = "unbiased_" + os.path.basename(self.inputs.in_file)
        return abspath(out_file)

    def _gen_fieldfilename(self):
        field_file = self.inputs.bias_field
        if not isdefined(field_file) and isdefined(self.inputs.in_file):
            field_file = "biasfield_" + os.path.basename(self.inputs.in_file)
        return abspath(field_file)

    def _list_outputs(self):
        outputs = self.output_spec().get()
        outputs["out_file"] = self._gen_outfilename()
        outputs["bias_field"] = self._gen_fieldfilename()
        return outputs
