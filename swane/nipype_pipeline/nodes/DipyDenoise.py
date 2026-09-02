# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-
"""
Non-local means denoising of a 4D diffusion-weighted image.

Estimates the per-volume noise level with dipy's ``estimate_sigma`` and
denoises with ``nlmeans`` (Coupe 2008). This is the only denoiser offered on
the dipy tractography engine; see the dipy + RecoBundles design (section 2)
for why MP-PCA is not.
"""

import os
from os.path import abspath

import nibabel as nib
from nipype.interfaces.base import (
    traits,
    BaseInterface,
    BaseInterfaceInputSpec,
    TraitedSpec,
    File,
    isdefined,
)

OMP_THREADS_VAR = "OMP_NUM_THREADS"
OPENBLAS_THREADS_VAR = "OPENBLAS_NUM_THREADS"


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
class DipyDenoiseInputSpec(BaseInterfaceInputSpec):
    in_file = File(
        exists=True, mandatory=True, desc="the input 4D diffusion-weighted image"
    )
    bval = File(exists=True, mandatory=True, desc="the b-values file")
    bvec = File(exists=True, mandatory=True, desc="the b-vectors file")
    num_threads = traits.Int(
        nohash=True, desc="number of OpenMP/OpenBLAS threads to use"
    )
    out_file = File(desc="the output denoised image")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class DipyDenoiseOutputSpec(TraitedSpec):
    out_file = File(desc="the output denoised image")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class DipyDenoise(BaseInterface):
    """
    Denoises a 4D DWI volume with dipy's non-local means filter, using a
    noise level estimated from the data itself.

    """

    input_spec = DipyDenoiseInputSpec
    output_spec = DipyDenoiseOutputSpec

    def _run_interface(self, runtime):
        from dipy.denoise import nlmeans, noise_estimate

        out_file = self._gen_outfilename()

        in_nii = nib.load(self.inputs.in_file)
        data = in_nii.get_fdata()

        # bval/bvec carry no information nlmeans/estimate_sigma need; they are
        # accepted so this node's inputs line up with the other DWI
        # preprocessing nodes it is wired next to.
        previous_omp = os.environ.get(OMP_THREADS_VAR)
        previous_openblas = os.environ.get(OPENBLAS_THREADS_VAR)
        if isdefined(self.inputs.num_threads):
            os.environ[OMP_THREADS_VAR] = str(self.inputs.num_threads)
            os.environ[OPENBLAS_THREADS_VAR] = str(self.inputs.num_threads)
        try:
            sigma = noise_estimate.estimate_sigma(data)
            denoised = nlmeans.nlmeans(
                data,
                sigma,
                num_threads=(
                    self.inputs.num_threads
                    if isdefined(self.inputs.num_threads)
                    else None
                ),
            )
        finally:
            for var, previous in (
                (OMP_THREADS_VAR, previous_omp),
                (OPENBLAS_THREADS_VAR, previous_openblas),
            ):
                if previous is None:
                    os.environ.pop(var, None)
                else:
                    os.environ[var] = previous

        nib.save(nib.Nifti1Image(denoised, in_nii.affine, in_nii.header), out_file)

        return runtime

    def _gen_outfilename(self):
        out_file = self.inputs.out_file
        if not isdefined(out_file) and isdefined(self.inputs.in_file):
            out_file = "denoised_" + os.path.basename(self.inputs.in_file)
        return abspath(out_file)

    def _list_outputs(self):
        outputs = self.output_spec().get()
        outputs["out_file"] = self._gen_outfilename()
        return outputs
