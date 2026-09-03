# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-
"""
Probabilistic tractography with a continuous-map criterion, in diffusion space.

The tracker is
:func:`dipy.tracking.tracker.probabilistic_tracking` (it samples the fODF rather
than following its maximum). It replaced particle-filtering tractography
(``pft_tracking``), which was unusable on the 8 GB / 4-core target: ``pft_tracking``
runs single-core (its OpenMP pool does not engage on the ``sh=`` path) and its
dense full-FOV PMF precompute (X x Y x Z x 362 x 8 bytes = 9.19 GB on subj1)
alone busts the memory budget. ``probabilistic_tracking`` keeps the *same*
:class:`dipy.tracking.stopping_criterion.CmcStoppingCriterion`, so tracking stays
probabilistic and anatomically constrained; only PFT's particle-filtering reinit
is lost (spec section 5, "Accepted risk").

Seeds are placed in the **white-matter PVE mask only**: whole-brain seeding was
measured at a 7 GB peak and roughly 5x the runtime (spec Measurements), so the
tractography seeds from the WM channel of the tissue classifier's partial-volume
estimates and nowhere else. The Continuous Map Criterion is built from the three
PVE maps and drives streamline stopping.

Streamline length is bounded to the literature range ``MIN_LEN_MM`` .. ``MAX_LEN_MM``;
these are module constants rather than traits so the workflow graph and the golden
matrix snapshots do not change.

The SH and PVE volumes are cropped to the brain bounding box before tracking
(``BBOX_PAD_VOXELS``, :func:`foreground_bbox_slices`, :func:`shift_affine_for_crop`).
The full FOV is dominated by background -- on subj1 the brain fills <50% of
256x256x52, so the uncropped SH volume alone is 4.15 GB in float64 and passing it
whole to ``probabilistic_tracking`` peaks around 7 GB, over the 8 GB target (spec
section 2, "crop"). Background voxels carry no fODF, no WM seed and no tissue for
the CMC criterion, so the crop halves the voxel count at zero scientific cost: the
affine is shifted by the crop offset, so tracking still runs in the original
diffusion world frame and the streamlines are unchanged.

Tracking runs in diffusion space (no DWI interpolation); each streamline is
moved to reference space with the diffusion -> reference affine already produced
by the registration -- there is no FSL ``.mat``. Rather than materialise the
whole tractogram (a >6 GB save spike at ``seed_density=2``, spec Measurements),
the tracker's generator is streamed straight into a memory-mappable ``.trx`` via
:meth:`trx.trx_file_memmap.TrxFile.from_lazy_tractogram`, so the peak RSS stays
flat regardless of streamline count.

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

# Streamline length bounds in mm (spec section 5, user's literature-based
# choice). Kept as module constants, not traits/preferences, so the workflow
# graph and the golden matrix snapshots do not change. These override dipy's
# permissive defaults (min_len=2, max_len=500).
MIN_LEN_MM = 10.0
MAX_LEN_MM = 250.0

# Streamlines are streamed to the .trx in chunks of this many so the peak RSS
# stays flat regardless of how many the tracker produces (spec Measurements).
# The dipy/trx default is 10000.
TRX_CHUNK_SIZE = 10000

# The SH + PVE volumes are cropped to the brain bounding box (plus this padding,
# in voxels) before tracking. The full FOV is dominated by background: on subj1
# the brain fills <50% of 256x256x52, so the uncropped SH volume alone is
# 256x256x52x15 float64 = 4.15 GB, and passing it whole to probabilistic_tracking
# peaks around 7 GB -- over the 8 GB target (spec section 2, "crop"). Background
# voxels carry no fODF, no WM seed and no tissue for the CMC criterion, so the
# crop is a pure memory optimisation with no effect on the streamlines: the affine
# is shifted by the crop offset (see shift_affine_for_crop) so tracking still runs
# in the original diffusion world frame.
BBOX_PAD_VOXELS = 2


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


def foreground_bbox_slices(masks, shape, pad=BBOX_PAD_VOXELS):
    """Slices tightening ``shape`` to the union foreground of ``masks`` + ``pad``.

    ``masks`` is an iterable of 3D arrays sharing ``shape[:3]``; a voxel is
    foreground where any of them is non-zero. The returned per-axis slices span
    the foreground bounding box grown by ``pad`` voxels and clipped to the volume
    bounds. If nothing is foreground the full FOV is returned unchanged (a safe
    no-op crop).
    """
    foreground = np.zeros(tuple(shape[:3]), dtype=bool)
    for mask in masks:
        foreground |= np.asarray(mask) != 0

    if not foreground.any():
        return tuple(slice(0, int(shape[axis])) for axis in range(3))

    where = np.where(foreground)
    slices = []
    for axis in range(3):
        lo = max(int(where[axis].min()) - pad, 0)
        hi = min(int(where[axis].max()) + 1 + pad, int(shape[axis]))
        slices.append(slice(lo, hi))
    return tuple(slices)


def shift_affine_for_crop(affine, slices):
    """Affine for a cropped volume that preserves world coordinates.

    Cropping moves the voxel origin to ``(slices[0].start, slices[1].start,
    slices[2].start)``; shifting the translation by that offset makes the
    cropped-space voxel ``(0, 0, 0)`` map to the same world point it did before
    the crop, so seeds and streamlines stay in the original diffusion frame.
    """
    lo = np.array([sl.start for sl in slices], dtype=float)
    shifted = np.array(affine, dtype=float)
    shifted[:3, 3] = affine[:3, :3] @ lo + affine[:3, 3]
    return shifted


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
    Probabilistic tractography seeded from the WM PVE mask, with a continuous-map
    stopping criterion built from the three PVE maps. Streamlines are tracked in
    diffusion space and written to reference space as ``.trx``.

    """

    input_spec = DipyTrackingInputSpec
    output_spec = DipyTrackingOutputSpec

    def _run_interface(self, runtime):
        from dipy.tracking.stopping_criterion import CmcStoppingCriterion
        from dipy.tracking.tracker import probabilistic_tracking
        from nibabel.affines import apply_affine
        from nibabel.streamlines import LazyTractogram
        from trx.trx_file_memmap import TrxFile, save as trx_save

        out_file = self._gen_outfilename()

        num_threads = (
            int(self.inputs.num_threads) if isdefined(self.inputs.num_threads) else 1
        )

        shm_nii = nib.load(self.inputs.shm_coeff)
        # Load via dataobj as float32 rather than get_fdata (float64): the full FOV
        # SH volume is 256x256x52x15 = 4.15 GB in float64 on subj1, half that in
        # float32, and dipy upcasts to float64 only the cropped array below.
        sh_data = np.asarray(shm_nii.dataobj, dtype=np.float32)
        diff_affine = shm_nii.affine
        # average voxel size drives the CMC step-length normalisation (crop-invariant)
        average_voxel_size = float(np.mean(shm_nii.header.get_zooms()[:3]))

        pve_wm = np.asarray(nib.load(self.inputs.pve_wm).dataobj, dtype=np.float32)
        pve_gm = np.asarray(nib.load(self.inputs.pve_gm).dataobj, dtype=np.float32)
        pve_csf = np.asarray(nib.load(self.inputs.pve_csf).dataobj, dtype=np.float32)

        # Crop SH + PVE to the brain bounding box so tracking never carries the
        # background (>50% of the FOV on subj1) in RAM. Foreground is any voxel
        # with fODF signal or any tissue; the affine is shifted so the cropped
        # volume tracks in the original diffusion world frame (BBOX_PAD_VOXELS,
        # foreground_bbox_slices, shift_affine_for_crop -- spec section 2 "crop").
        sh_signal = np.any(sh_data != 0, axis=-1)
        crop = foreground_bbox_slices(
            (sh_signal, pve_wm, pve_gm, pve_csf), sh_data.shape[:3]
        )
        sh_data = np.ascontiguousarray(sh_data[crop])
        pve_wm = np.ascontiguousarray(pve_wm[crop])
        pve_gm = np.ascontiguousarray(pve_gm[crop])
        pve_csf = np.ascontiguousarray(pve_csf[crop])
        track_affine = shift_affine_for_crop(diff_affine, crop)

        seed_density = int(self.inputs.seed_density)
        max_angle = float(self.inputs.max_angle)
        step_size = float(self.inputs.step_size)
        random_seed = int(self.inputs.random_seed)

        # The diffusion->reference affine already produced by the registration;
        # streamlines are moved to reference space one at a time in the streaming
        # generator below, so no full set is ever transformed in place.
        diff2ref = np.loadtxt(self.inputs.affine_diff2ref).reshape(4, 4)
        reference_img = nib.load(self.inputs.reference)

        def streamlines_ref():
            # probabilistic_tracking yields streamlines in diffusion space; move
            # each to reference space (apply_affine == transform_streamlines for
            # one streamline) and hand it straight to the .trx writer, so the
            # full set is never held in RAM (density=2 accumulates ~600k
            # streamlines -> a >6 GB save spike on the materialise-then-save
            # path; streaming keeps the peak flat, spec Measurements).
            for streamline in probabilistic_tracking(
                seeds,
                criterion,
                track_affine,
                sh=sh_data,
                min_len=MIN_LEN_MM,
                max_len=MAX_LEN_MM,
                max_angle=max_angle,
                step_size=step_size,
                random_seed=random_seed,
                nbr_threads=num_threads,
                return_all=False,
            ):
                yield apply_affine(diff2ref, np.asarray(streamline, dtype=np.float32))

        # Pin the process-level thread environment to the declared count (both
        # the tracker's OpenMP pool and any BLAS call), saving/restoring like the
        # ITK variable in AntsN4BiasFieldCorrection. The generator only runs when
        # from_lazy_tractogram consumes it, so the pin must wrap that call.
        previous = {
            var: os.environ.get(var) for var in (OMP_THREADS_VAR, OPENBLAS_THREADS_VAR)
        }
        for var in (OMP_THREADS_VAR, OPENBLAS_THREADS_VAR):
            os.environ[var] = str(num_threads)
        try:
            seeds = generate_wm_seeds(pve_wm, track_affine, seed_density)
            criterion = CmcStoppingCriterion.from_pve(
                pve_wm,
                pve_gm,
                pve_csf,
                step_size=step_size,
                average_voxel_size=average_voxel_size,
            )
            # The generator already yields reference-space (RASMM) coordinates,
            # so affine_to_rasmm is the identity; reference_img anchors the
            # tractogram's grid (affine + dimensions) exactly as a
            # StatefulTractogram(..., Space.RASMM) would.
            lazy = LazyTractogram(
                streamlines=streamlines_ref, affine_to_rasmm=np.eye(4)
            )
            trx = TrxFile.from_lazy_tractogram(
                lazy, reference_img, chunk_size=TRX_CHUNK_SIZE
            )
        finally:
            for var, value in previous.items():
                if value is None:
                    os.environ.pop(var, None)
                else:
                    os.environ[var] = value

        trx_save(trx, out_file)

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
