# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-
"""
Particle Filtering Tractography (PFT) in diffusion space.

Seeds are placed in the **white-matter PVE mask only**: whole-brain seeding was
measured at a 7 GB peak and roughly 5x the runtime (spec Measurements), so the
tractography seeds from the WM channel of the tissue classifier's partial-volume
estimates and nowhere else. The Continuous Map Criterion
(:class:`dipy.tracking.stopping_criterion.CmcStoppingCriterion`) is built from
the three PVE maps and drives both stopping and PFT's reinitialisation of
implausible streamlines.

Tracking runs in diffusion space (no DWI interpolation); the resulting
streamlines are moved to reference space with
:func:`dipy.tracking.streamline.transform_streamlines` and the diffusion ->
reference affine already produced by the registration -- there is no FSL ``.mat``.
The tractogram is written as a memory-mappable ``.trx`` rather than accumulated
as a Python list.

The tracker's SH input is consumed in the descoteaux07 legacy basis, matching
the basis ``DipyCsdFit`` writes.
"""

import os
from os.path import abspath, basename

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

# BLAS/OpenMP thread-count environment variables, pinned like the ITK variable
# in AntsN4BiasFieldCorrection so numpy's OpenBLAS backend and the tracker's
# OpenMP pool do not multithread invisibly to nipype's resource accounting.
OMP_THREADS_VAR = "OMP_NUM_THREADS"
OPENBLAS_THREADS_VAR = "OPENBLAS_NUM_THREADS"

# A voxel is a seed site when white matter is the dominant tissue there. This
# keeps seeds out of CSF and cortex, where they would only produce streamlines
# to prune (spec Measurements).
WM_PVE_SEED_THRESHOLD = 0.5


def wm_seed_mask(pve_wm, threshold=WM_PVE_SEED_THRESHOLD):
    """Boolean seed mask of WM-dominant voxels from the WM PVE map."""
    return np.asarray(pve_wm) >= threshold


def generate_wm_seeds(pve_wm, affine, density):
    """World-space seed positions placed evenly inside the WM PVE mask.

    Wraps :func:`dipy.tracking.utils.seeds_from_mask` over
    :func:`wm_seed_mask`, so seeding is restricted to white matter.
    """
    from dipy.tracking.utils import seeds_from_mask

    mask = wm_seed_mask(pve_wm)
    return seeds_from_mask(mask, affine, density=int(density))


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
class DipyTrackingInputSpec(BaseInterfaceInputSpec):
    shm_coeff = File(
        exists=True,
        mandatory=True,
        desc="fODF spherical-harmonic coefficients in diffusion space "
        "(descoteaux07 legacy basis)",
    )
    pve_wm = File(
        exists=True,
        mandatory=True,
        desc="white-matter partial volume estimate (diffusion space) -- the "
        "seed mask and the CMC WM channel",
    )
    pve_gm = File(
        exists=True,
        mandatory=True,
        desc="gray-matter partial volume estimate (diffusion space)",
    )
    pve_csf = File(
        exists=True,
        mandatory=True,
        desc="CSF partial volume estimate (diffusion space)",
    )
    reference = File(
        exists=True,
        mandatory=True,
        desc="reference-space image anchoring the output tractogram's grid",
    )
    affine_diff2ref = File(
        exists=True,
        mandatory=True,
        desc="text file with the 4x4 diffusion->reference affine "
        "(np.loadtxt-readable) used to move streamlines to reference space",
    )
    seed_density = traits.Range(
        low=1,
        high=10,
        value=2,
        usedefault=True,
        desc="seeds per voxel dimension inside the WM mask (2 -> 8 seeds/voxel)",
    )
    max_angle = traits.Range(
        low=1.0,
        high=90.0,
        value=20.0,
        usedefault=True,
        desc="maximum angle (degrees) between consecutive tracking steps",
    )
    step_size = traits.Range(
        low=0.05,
        high=2.0,
        value=0.2,
        usedefault=True,
        desc="tracking step size in mm",
    )
    random_seed = traits.Int(
        1,
        usedefault=True,
        desc="RNG seed; a value > 0 fixes the trajectory per seed coordinate",
    )
    num_threads = traits.Int(
        nohash=True, desc="OpenMP/BLAS thread count and tracker nbr_threads"
    )
    out_file = File(desc="the output tractogram (.trx, reference space)")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class DipyTrackingOutputSpec(TraitedSpec):
    tractogram = File(desc="the output tractogram (.trx, reference space)")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class DipyTracking(BaseInterface):
    """
    Particle filtering tractography seeded from the WM PVE mask, with a
    continuous-map stopping criterion built from the three PVE maps. Streamlines
    are tracked in diffusion space and written to reference space as ``.trx``.

    """

    input_spec = DipyTrackingInputSpec
    output_spec = DipyTrackingOutputSpec

    def _run_interface(self, runtime):
        from dipy.tracking.stopping_criterion import CmcStoppingCriterion
        from dipy.tracking.tracker import pft_tracking
        from dipy.tracking.streamline import Streamlines, transform_streamlines
        from dipy.io.stateful_tractogram import StatefulTractogram, Space
        from dipy.io.streamline import save_tractogram

        out_file = self._gen_outfilename()

        num_threads = (
            int(self.inputs.num_threads) if isdefined(self.inputs.num_threads) else 1
        )

        shm_nii = nib.load(self.inputs.shm_coeff)
        sh_data = shm_nii.get_fdata()
        diff_affine = shm_nii.affine
        # average voxel size drives the CMC step-length normalisation
        average_voxel_size = float(np.mean(shm_nii.header.get_zooms()[:3]))

        pve_wm = nib.load(self.inputs.pve_wm).get_fdata()
        pve_gm = nib.load(self.inputs.pve_gm).get_fdata()
        pve_csf = nib.load(self.inputs.pve_csf).get_fdata()

        seed_density = int(self.inputs.seed_density)
        max_angle = float(self.inputs.max_angle)
        step_size = float(self.inputs.step_size)
        random_seed = int(self.inputs.random_seed)

        # Pin the process-level thread environment to the declared count (both
        # the tracker's OpenMP pool and any BLAS call), saving/restoring like
        # the ITK variable in AntsN4BiasFieldCorrection.
        previous = {
            var: os.environ.get(var) for var in (OMP_THREADS_VAR, OPENBLAS_THREADS_VAR)
        }
        for var in (OMP_THREADS_VAR, OPENBLAS_THREADS_VAR):
            os.environ[var] = str(num_threads)
        try:
            seeds = generate_wm_seeds(pve_wm, diff_affine, seed_density)
            criterion = CmcStoppingCriterion.from_pve(
                pve_wm,
                pve_gm,
                pve_csf,
                step_size=step_size,
                average_voxel_size=average_voxel_size,
            )
            tracking = pft_tracking(
                seeds,
                criterion,
                diff_affine,
                sh=sh_data,
                max_angle=max_angle,
                step_size=step_size,
                random_seed=random_seed,
                nbr_threads=num_threads,
                return_all=False,
            )
            # Streamlines() is dipy's contiguous ArraySequence, not a Python
            # list of arrays: the tractogram is materialised memory-efficiently.
            streamlines = Streamlines(tracking)
        finally:
            for var, value in previous.items():
                if value is None:
                    os.environ.pop(var, None)
                else:
                    os.environ[var] = value

        # Move streamlines from diffusion to reference space with the affine
        # already produced by the diffusion->reference registration.
        diff2ref = np.loadtxt(self.inputs.affine_diff2ref).reshape(4, 4)
        streamlines_ref = transform_streamlines(streamlines, diff2ref)

        reference_img = nib.load(self.inputs.reference)
        sft = StatefulTractogram(streamlines_ref, reference_img, Space.RASMM)
        # bbox validity is not required here: streamlines may leave the reference
        # grid, and the tractogram is consumed by SLR/RecoBundles in world space.
        save_tractogram(sft, out_file, bbox_valid_check=False)

        return runtime

    def _gen_outfilename(self):
        out_file = self.inputs.out_file
        if not isdefined(out_file) and isdefined(self.inputs.shm_coeff):
            base = basename(self.inputs.shm_coeff)
            for ext in (".nii.gz", ".nii"):
                if base.endswith(ext):
                    base = base[: -len(ext)]
                    break
            out_file = "tractogram_" + base + ".trx"
        return abspath(out_file)

    def _list_outputs(self):
        outputs = self.output_spec().get()
        outputs["tractogram"] = self._gen_outfilename()
        return outputs
