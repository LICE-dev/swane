"""Unit tests for
:class:`swane.nipype_pipeline.nodes.DwiCrop.DwiCrop`.

C1 (spec section "C1 -- crop the 4D DWI upfront, with median_otsu"): the 4D DWI
is cropped to the brain bounding box immediately after orientation, so every
upstream node (denoise -> motion -> bias -> tensor -> CSD) works on the brain
sub-box instead of paying for the empty margin in time and RAM.

The load-bearing contracts:

* the crop is **generous and lossless w.r.t. the brain** -- a too-large crop is
  correct, a too-small crop (cutting brain) is an unrecoverable defect;
* the brain mask is built from the **mean across all volumes** (the motion
  envelope, since this runs before motion correction), not a single volume;
* **world coordinates are preserved end to end** -- the cropped affine follows
  the project's :func:`shift_affine_for_crop` convention, so a voxel of brain
  maps to exactly the same world point before and after the crop. This is what
  keeps streamlines, registration matrices and the reference-space transform
  unaffected downstream;
* a **crop is not a mask** -- the original voxel data is subselected, never
  multiplied by the mask, so nothing downstream depends on a tight boundary;
* bvals/bvecs are invariant to a spatial crop and are not an input to this node.
"""

import os

import numpy as np
import nibabel as nib

from swane.nipype_pipeline.nodes.DwiCrop import (
    DwiCrop,
    crop_4d_median_otsu,
    CROP_PAD_VOXELS,
    OMP_THREADS_VAR,
    OPENBLAS_THREADS_VAR,
)

# shift_affine_for_crop is the project's world-coordinate convention and the
# source of truth for the affine shift; DwiCrop re-exports it for the crop.
from swane.nipype_pipeline.nodes.DipyTracking import (
    shift_affine_for_crop,
    foreground_bbox_slices,
)


# --------------------------------------------------------------------------- #
# A synthetic 4D DWI: a solid "brain" blob surrounded by wide empty margins.
# Margins are wide (>= 14 voxels each side) so that even the node's generous
# default crop still shrinks every axis. All volumes carry the brain, so the
# mean-over-volumes mask covers it.
# --------------------------------------------------------------------------- #
_BRAIN = (slice(20, 44), slice(22, 46), slice(14, 34))
_BRAIN_CORNER = (20, 22, 14)  # the min corner of the brain block


def _brain_4d(motion_shift=0):
    """A 4D brain blob. With ``motion_shift`` > 0 the brain is displaced by one
    voxel in +x in half of the volumes, so the per-volume brain positions differ
    and only a multi-volume (envelope) mask can cover them all."""
    data = np.zeros((64, 64, 48, 6), dtype=np.float32)
    data[_BRAIN[0], _BRAIN[1], _BRAIN[2], :] = 100.0
    if motion_shift:
        data[:, :, :, 3:] = 0.0
        sx = slice(_BRAIN[0].start + motion_shift, _BRAIN[0].stop + motion_shift)
        data[sx, _BRAIN[1], _BRAIN[2], 3:] = 100.0
    affine = np.diag([2.0, 2.0, 2.5, 1.0])
    affine[:3, 3] = [-64.0, -64.0, -60.0]
    return data, affine


class TestCropFunction:
    def test_crop_preserves_brain_and_world_coordinates(self):
        data, affine = _brain_4d()
        cropped, cropped_affine = crop_4d_median_otsu(data, affine, pad=4)

        # (a) the crop is generous: no brain voxel is lost. Background is 0, so a
        # crop that clipped brain would drop the total intensity.
        assert cropped[..., 0].sum() >= data[..., 0].sum() - 1e-3
        # it is a real crop -- strictly smaller than the FOV on every axis.
        for axis in range(3):
            assert cropped.shape[axis] < data.shape[axis]
        # the 4th dimension (volumes) is untouched.
        assert cropped.shape[3] == data.shape[3]

        # (b) world coordinates are preserved: the original brain corner lands on
        # the same world point through the cropped affine. Its cropped voxel index
        # is recovered from the shifted affine (no dependency on the crop offset
        # being returned).
        cx, cy, cz = _BRAIN_CORNER
        orig_corner_world = affine @ np.array([cx, cy, cz, 1.0])
        vox_in_crop = np.linalg.inv(cropped_affine) @ orig_corner_world
        # the recovered index is a non-negative integer inside the cropped grid
        assert np.allclose(vox_in_crop[:3], np.round(vox_in_crop[:3]), atol=1e-6)
        idx = np.round(vox_in_crop[:3]).astype(int)
        assert np.all(idx >= 0)
        assert np.all(idx < np.array(cropped.shape[:3]))
        # and mapping that cropped voxel back to world reproduces the point
        back = cropped_affine @ np.array([idx[0], idx[1], idx[2], 1.0])
        assert np.allclose(back, orig_corner_world, atol=1e-6)
        # the cropped voxel is brain (intensity preserved, not masked to 0)
        assert cropped[idx[0], idx[1], idx[2], 0] == 100.0

    def test_crop_covers_the_motion_envelope_across_volumes(self):
        # The brain sits at x in [20,44) in the first volumes and is shifted to
        # [23,47) in the rest (simulated inter-volume motion). The crop must
        # contain BOTH positions -- the whole envelope -- because it runs before
        # motion correction. A single-volume mask would miss one position.
        shift = 3
        data, affine = _brain_4d(motion_shift=shift)
        cropped, cropped_affine = crop_4d_median_otsu(data, affine, pad=4)
        # the shifted brain's far corner must fall inside the crop
        cx, cy, cz = _BRAIN_CORNER
        far_x = _BRAIN[0].stop - 1 + shift  # last brain voxel of the shifted vols
        for corner in ([cx, cy, cz], [far_x, cy, cz]):
            world = affine @ np.array(corner + [1.0])
            idx = np.round(np.linalg.inv(cropped_affine) @ world)[:3].astype(int)
            assert np.all((idx >= 0) & (idx < np.array(cropped.shape[:3]))), corner
        # and no brain intensity was lost from any volume
        assert cropped.sum() >= data.sum() - 1e-3

    def test_crop_is_not_a_mask_data_is_subselected_not_multiplied(self):
        # A voxel that median_otsu would exclude from the *mask* but that falls
        # inside the generous crop box must keep its original intensity: the node
        # crops, it does not apply the mask.
        data, affine = _brain_4d()
        # put a lone bright voxel just outside the brain but within pad range
        cx, cy, cz = _BRAIN_CORNER
        data[cx - 1, cy, cz, :] = 55.0
        cropped, cropped_affine = crop_4d_median_otsu(data, affine, pad=4)
        world = affine @ np.array([cx - 1, cy, cz, 1.0])
        idx = np.round(np.linalg.inv(cropped_affine) @ world)[:3].astype(int)
        assert np.all((idx >= 0) & (idx < np.array(cropped.shape[:3])))
        assert cropped[idx[0], idx[1], idx[2], 0] == 55.0

    def test_bbox_convention_matches_median_otsu_own_crop(self):
        # autocrop is deprecated in dipy 1.11+ (removed 1.13) and median_otsu
        # returns no affine, so the project computes the crop itself. Prove the
        # project's foreground bbox (pad=0) coincides with dipy's own autocrop
        # bounding box, i.e. the crop convention is dipy's, not a divergent one.
        from dipy.segment.mask import median_otsu, bounding_box

        data, affine = _brain_4d()
        mean_volume = data.mean(axis=-1)
        _, mask = median_otsu(mean_volume, median_radius=4, numpass=4, dilate=2)
        mins, maxs = bounding_box(mask)
        dipy_slices = tuple(slice(int(a), int(b)) for a, b in zip(mins, maxs))
        project_slices = foreground_bbox_slices((mask,), data.shape[:3], pad=0)
        assert project_slices == dipy_slices


class TestNode:
    def _write_input(self, make_nifti):
        data, affine = _brain_4d()
        in_file = make_nifti("dwi.nii.gz", data=data, affine=affine)
        return in_file, data, affine

    def test_node_writes_cropped_4d_preserving_world_coordinates(
        self, workspace, make_nifti
    ):
        in_file, data, affine = self._write_input(make_nifti)

        node = DwiCrop()
        node.inputs.in_file = in_file
        node.inputs.out_file = "crop_dwi.nii.gz"
        node.run()

        out = node._list_outputs()["out_file"]
        assert os.path.exists(out)
        cropped_nii = nib.load(out)

        # strictly smaller volume, same number of gradient volumes
        for axis in range(3):
            assert cropped_nii.shape[axis] < data.shape[axis]
        assert cropped_nii.shape[3] == data.shape[3]

        # world coordinates of the brain corner survive the crop
        cx, cy, cz = _BRAIN_CORNER
        orig_corner_world = affine @ np.array([cx, cy, cz, 1.0])
        vox = np.round(np.linalg.inv(cropped_nii.affine) @ orig_corner_world)[
            :3
        ].astype(int)
        assert np.all((vox >= 0) & (vox < np.array(cropped_nii.shape[:3])))
        back = cropped_nii.affine @ np.array([vox[0], vox[1], vox[2], 1.0])
        assert np.allclose(back, orig_corner_world, atol=1e-4)
        # every brain voxel survived (generous crop)
        cropped_data = np.asarray(cropped_nii.dataobj)
        assert cropped_data[..., 0].sum() >= data[..., 0].sum() - 1e-1

    def test_node_pins_blas_threads_and_restores_environment(
        self, workspace, make_nifti, monkeypatch
    ):
        monkeypatch.delenv(OMP_THREADS_VAR, raising=False)
        monkeypatch.delenv(OPENBLAS_THREADS_VAR, raising=False)
        in_file, _, _ = self._write_input(make_nifti)

        node = DwiCrop()
        node.inputs.in_file = in_file
        node.inputs.num_threads = 2
        node.inputs.out_file = "crop_dwi.nii.gz"
        node.run()

        # the pin is scoped to the run and restored afterwards
        assert OMP_THREADS_VAR not in os.environ
        assert OPENBLAS_THREADS_VAR not in os.environ
