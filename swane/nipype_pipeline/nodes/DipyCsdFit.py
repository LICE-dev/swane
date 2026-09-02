# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-
"""
Constrained spherical deconvolution (CSD) fibre-orientation fit.

Estimates a single-shell single-tissue response with dipy's
``auto_response_ssst`` and fits a :class:`ConstrainedSphericalDeconvModel`,
writing the fODF spherical-harmonic coefficients (``shm_coeff``) that the
tracking node consumes.

The SH order is chosen adaptively from the angular sampling: fitting more
coefficients than the number of gradient directions supports over-fits the
fODF, so ``sh_order_max`` follows the spec's direction -> lmax table
(:func:`sh_order_for_directions`), and the direction count is the number of
non-b0 volumes (:func:`n_directions_from_gtab`), never the total volume count.

Parallelism is by worker process (``peaks_from_model(num_processes=...)``);
each worker's BLAS is pinned to a single thread so the node's real footprint
matches the core count it declares to nipype.
"""

import os
from os.path import abspath

import numpy as np
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


def sh_order_for_directions(n_dirs):
    """Adaptive spherical-harmonic order for ``n_dirs`` gradient directions.

    Follows the spec section 5 table -- lmax needs ``(lmax+1)(lmax+2)/2``
    coefficients, so the order never exceeds what the angular sampling can
    support:

    ======================  ====
    directions              lmax
    ======================  ====
    >= 45                   8
    >= 28                   6
    >= 15                   4
    >= 6                    2
    ======================  ====

    Below the lowest tier the lmax=2 floor is returned rather than raising;
    SWANe supports acquisitions down to 15 directions, so this only guards
    degenerate inputs.
    """
    if n_dirs >= 45:
        return 8
    if n_dirs >= 28:
        return 6
    if n_dirs >= 15:
        return 4
    return 2


def n_directions_from_gtab(gtab):
    """Number of non-b0 gradient directions in ``gtab``.

    This is the count that drives :func:`sh_order_for_directions`; it is
    deliberately the number of diffusion-weighted volumes
    (``~gtab.b0s_mask``), not the total volume count, so extra b0 volumes
    never inflate the fitted SH order.
    """
    return int(np.count_nonzero(~gtab.b0s_mask))


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
class DipyCsdFitInputSpec(BaseInterfaceInputSpec):
    in_file = File(
        exists=True, mandatory=True, desc="the input 4D diffusion-weighted image"
    )
    bval = File(exists=True, mandatory=True, desc="the b-values file")
    bvec = File(exists=True, mandatory=True, desc="the b-vectors file")
    mask = File(exists=True, mandatory=True, desc="the brain mask restricting the fit")
    num_threads = traits.Int(
        nohash=True, desc="number of worker processes / BLAS-pinned cores"
    )
    out_file = File(desc="the output fODF SH-coefficient image")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class DipyCsdFitOutputSpec(TraitedSpec):
    shm_coeff = File(desc="the fODF spherical-harmonic coefficients")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class DipyCsdFit(BaseInterface):
    """
    Fits a constrained spherical deconvolution model to a 4D DWI volume and
    writes the fODF spherical-harmonic coefficients, with an SH order chosen
    adaptively from the number of gradient directions.

    """

    input_spec = DipyCsdFitInputSpec
    output_spec = DipyCsdFitOutputSpec

    def _run_interface(self, runtime):
        from dipy.core.gradients import gradient_table
        from dipy.io.gradients import read_bvals_bvecs
        from dipy.data import default_sphere
        import dipy.reconst.csdeconv as csd
        import dipy.direction as direction

        out_file = self._gen_outfilename()

        in_nii = nib.load(self.inputs.in_file)
        data = in_nii.get_fdata()
        mask_data = nib.load(self.inputs.mask).get_fdata().astype(bool)
        bvals, bvecs = read_bvals_bvecs(self.inputs.bval, self.inputs.bvec)
        gtab = gradient_table(bvals, bvecs=bvecs)

        sh_order = sh_order_for_directions(n_directions_from_gtab(gtab))

        # Parallelism is by process (num_processes); each worker inherits the
        # environment, so pinning BLAS to a single thread here keeps the node's
        # real footprint at the declared core count instead of num_procs * BLAS.
        num_procs = (
            int(self.inputs.num_threads) if isdefined(self.inputs.num_threads) else 1
        )
        previous = {
            OMP_THREADS_VAR: os.environ.get(OMP_THREADS_VAR),
            OPENBLAS_THREADS_VAR: os.environ.get(OPENBLAS_THREADS_VAR),
        }
        os.environ[OMP_THREADS_VAR] = "1"
        os.environ[OPENBLAS_THREADS_VAR] = "1"
        try:
            response, _ = csd.auto_response_ssst(gtab, data, fa_thr=0.7)
            model = csd.ConstrainedSphericalDeconvModel(
                gtab, response, sh_order_max=sh_order
            )
            peaks = direction.peaks_from_model(
                model,
                data,
                default_sphere,
                relative_peak_threshold=0.5,
                min_separation_angle=25,
                mask=mask_data,
                sh_order_max=sh_order,
                return_sh=True,
                parallel=num_procs > 1,
                num_processes=num_procs,
            )
        finally:
            for var, value in previous.items():
                if value is None:
                    os.environ.pop(var, None)
                else:
                    os.environ[var] = value

        nib.save(
            nib.Nifti1Image(
                peaks.shm_coeff.astype(np.float32), in_nii.affine, in_nii.header
            ),
            out_file,
        )

        return runtime

    def _gen_outfilename(self):
        out_file = self.inputs.out_file
        if not isdefined(out_file) and isdefined(self.inputs.in_file):
            out_file = "shm_coeff_" + os.path.basename(self.inputs.in_file)
        return abspath(out_file)

    def _list_outputs(self):
        outputs = self.output_spec().get()
        outputs["shm_coeff"] = self._gen_outfilename()
        return outputs
