"""Unit tests for
:class:`swane.nipype_pipeline.nodes.DipyTracking.DipyTracking`.

The load-bearing behaviours (spec sections 5 and Measurements):

* seeds come from the **white-matter PVE mask only** -- whole-brain seeding was
  measured at 7 GB / 5x runtime, so any seed landing in CSF or cortex is a
  regression;
* the tractogram is written as a memory-mappable ``.trx`` that loads and is
  non-empty;
* two runs at an equal ``random_seed`` give identical trajectories even if the
  file bytes differ (streamline order may vary between threads);
* the BLAS/OpenMP thread count is pinned to the declared ``num_threads`` and the
  tracker's ``nbr_threads`` follows it.
"""

import os

import numpy as np
import nibabel as nib
import pytest

from swane.nipype_pipeline.nodes.DipyTracking import (
    DipyTracking,
    wm_seed_mask,
    generate_wm_seeds,
    foreground_bbox_slices,
    shift_affine_for_crop,
    WM_PVE_SEED_THRESHOLD,
    BBOX_PAD_VOXELS,
    MIN_LEN_MM,
    MAX_LEN_MM,
    OMP_THREADS_VAR,
    OPENBLAS_THREADS_VAR,
)


# --------------------------------------------------------------------------- #
# Synthetic fixture: a single coherent WM slab along z, CSF everywhere else,
# GM caps at the slab ends. The fODF points along z, so probabilistic_tracking
# produces real streamlines from the WM seeds. The slab is long enough (36 mm at
# 1 mm isotropic) that valid streamlines clear the MIN_LEN_MM=10 filter, so the
# tractogram is non-empty and the length-bound contract is exercisable.
# --------------------------------------------------------------------------- #
_SHAPE = (12, 12, 40)
_WM_X = slice(4, 8)
_WM_Y = slice(4, 8)
_WM_Z = slice(2, 38)
_GM_CAPS = (0, 1, 38, 39)


def _pve_maps():
    wm = np.zeros(_SHAPE, dtype=np.float32)
    gm = np.zeros(_SHAPE, dtype=np.float32)
    csf = np.ones(_SHAPE, dtype=np.float32)
    wm[_WM_X, _WM_Y, _WM_Z] = 1.0
    csf[_WM_X, _WM_Y, _WM_Z] = 0.0
    for z_cap in _GM_CAPS:
        gm[_WM_X, _WM_Y, z_cap] = 1.0
        csf[_WM_X, _WM_Y, z_cap] = 0.0
    return wm, gm, csf


def _sh_field(sh_order=8):
    """SH coefficients of a sharp fODF along +z, in the descoteaux07 legacy
    basis the tracker consumes by default."""
    from dipy.data import default_sphere
    from dipy.reconst.shm import sf_to_sh

    sphere = default_sphere
    lobe = np.abs(sphere.vertices @ np.array([0.0, 0.0, 1.0])) ** 16
    sf = np.empty(_SHAPE + (len(sphere.vertices),), dtype=np.float32)
    sf[...] = lobe
    return sf_to_sh(
        sf, sphere, sh_order_max=sh_order, basis_type="descoteaux07", legacy=True
    )


@pytest.fixture
def tracking_inputs(make_nifti, tmp_path):
    """Write shm_coeff, the three PVE maps, the reference image and the
    diffusion->reference affine, returning a dict of paths."""
    affine = np.eye(4)
    wm, gm, csf = _pve_maps()

    shm = make_nifti("shm.nii.gz", data=_sh_field(), affine=affine)
    pve_wm = make_nifti("pve_wm.nii.gz", data=wm, affine=affine)
    pve_gm = make_nifti("pve_gm.nii.gz", data=gm, affine=affine)
    pve_csf = make_nifti("pve_csf.nii.gz", data=csf, affine=affine)
    # A reference image on its own grid; identity here keeps the test coords
    # readable. Its only job is to anchor the output tractogram's space.
    reference = make_nifti(
        "reference.nii.gz", data=np.zeros(_SHAPE, dtype=np.float32), affine=affine
    )
    diff2ref = tmp_path / "diff2ref.txt"
    np.savetxt(diff2ref, np.eye(4))

    return {
        "shm_coeff": shm,
        "pve_wm": pve_wm,
        "pve_gm": pve_gm,
        "pve_csf": pve_csf,
        "reference": reference,
        "affine_diff2ref": str(diff2ref),
    }


def _configure(node, inputs, **overrides):
    node.inputs.shm_coeff = inputs["shm_coeff"]
    node.inputs.pve_wm = inputs["pve_wm"]
    node.inputs.pve_gm = inputs["pve_gm"]
    node.inputs.pve_csf = inputs["pve_csf"]
    node.inputs.reference = inputs["reference"]
    node.inputs.affine_diff2ref = inputs["affine_diff2ref"]
    for key, value in overrides.items():
        setattr(node.inputs, key, value)
    return node


# --------------------------------------------------------------------------- #
# Brain bounding-box crop before tracking (spec section 2 "crop").
#
# The committed node passed the full FOV SH volume to probabilistic_tracking:
# 256x256x52x15 float64 = 4.15 GB just for that array on subj1, of which >50% is
# background zeros. That full-FOV footprint (~7 GB tree peak) is what busts the
# 8 GB target and hard-froze the measurement box. Cropping SH + PVE to the brain
# bounding box (and shifting the affine so world coordinates are preserved) halves
# the voxel count at zero scientific cost: background carries no fODF, no WM seed
# and no tissue for the CMC criterion.
# --------------------------------------------------------------------------- #
class TestBrainBboxCrop:
    def test_bbox_slices_tighten_to_foreground_with_pad(self):
        # A 20x20x20 volume whose only signal is an inner 6x6x6 block.
        mask = np.zeros((20, 20, 20), dtype=np.float32)
        mask[7:13, 7:13, 7:13] = 1.0
        slices = foreground_bbox_slices((mask,), mask.shape, pad=BBOX_PAD_VOXELS)
        # foreground spans [7,13); with pad=2 the box is [5,15) on every axis.
        assert slices == (slice(5, 15), slice(5, 15), slice(5, 15))
        # and it is strictly smaller than the full FOV -> real memory saving
        for axis, sl in enumerate(slices):
            assert sl.stop - sl.start < mask.shape[axis]

    def test_bbox_slices_union_multiple_masks(self):
        a = np.zeros((10, 10, 10), dtype=np.float32)
        b = np.zeros((10, 10, 10), dtype=np.float32)
        a[1, 1, 1] = 1.0
        b[6, 6, 6] = 1.0
        slices = foreground_bbox_slices((a, b), a.shape, pad=0)
        assert slices == (slice(1, 7), slice(1, 7), slice(1, 7))

    def test_bbox_slices_clip_to_volume_bounds(self):
        mask = np.zeros((8, 8, 8), dtype=np.float32)
        mask[0, 0, 0] = 1.0
        mask[7, 7, 7] = 1.0
        # a generous pad must not run off either end of the array
        slices = foreground_bbox_slices((mask,), mask.shape, pad=5)
        assert slices == (slice(0, 8), slice(0, 8), slice(0, 8))

    def test_bbox_slices_no_foreground_keeps_full_fov(self):
        mask = np.zeros((6, 6, 6), dtype=np.float32)
        slices = foreground_bbox_slices((mask,), mask.shape, pad=2)
        assert slices == (slice(0, 6), slice(0, 6), slice(0, 6))

    def test_shift_affine_preserves_world_coordinates(self):
        # A non-trivial affine (anisotropic voxels + an offset origin).
        affine = np.array(
            [
                [0.9, 0.0, 0.0, -10.0],
                [0.0, 0.9, 0.0, -20.0],
                [0.0, 0.0, 2.5, -30.0],
                [0.0, 0.0, 0.0, 1.0],
            ]
        )
        slices = (slice(5, 15), slice(6, 16), slice(2, 40))
        shifted = shift_affine_for_crop(affine, slices)
        # the cropped-space voxel (0,0,0) must land on the same world point as the
        # original-space voxel (5,6,2)
        lo = np.array([5, 6, 2])
        world_from_original = affine[:3, :3] @ lo + affine[:3, 3]
        world_from_cropped = shifted[:3, 3]
        assert np.allclose(world_from_cropped, world_from_original)
        # the linear part (voxel sizes / orientation) is untouched
        assert np.allclose(shifted[:3, :3], affine[:3, :3])

    def test_node_crops_sh_before_tracking(
        self, workspace, make_nifti, tmp_path, monkeypatch
    ):
        # Embed the tight fixture content inside a larger volume with a genuine
        # zero-background border (all PVE and SH zero there), so the crop has
        # something to remove -- unlike the base fixture, whose CSF fills the FOV.
        pad = 4
        wm0, gm0, csf0 = _pve_maps()
        sh0 = _sh_field()

        def _embed(arr):
            if arr.ndim == 4:
                out = np.zeros(
                    (
                        arr.shape[0] + 2 * pad,
                        arr.shape[1] + 2 * pad,
                        arr.shape[2] + 2 * pad,
                        arr.shape[3],
                    ),
                    dtype=arr.dtype,
                )
                out[pad:-pad, pad:-pad, pad:-pad, :] = arr
            else:
                out = np.zeros(tuple(d + 2 * pad for d in arr.shape), dtype=arr.dtype)
                out[pad:-pad, pad:-pad, pad:-pad] = arr
            return out

        affine = np.eye(4)
        padded = {
            "shm_coeff": make_nifti("psh.nii.gz", data=_embed(sh0), affine=affine),
            "pve_wm": make_nifti("pwm.nii.gz", data=_embed(wm0), affine=affine),
            "pve_gm": make_nifti("pgm.nii.gz", data=_embed(gm0), affine=affine),
            "pve_csf": make_nifti("pcsf.nii.gz", data=_embed(csf0), affine=affine),
            "reference": make_nifti(
                "pref.nii.gz",
                data=np.zeros(_embed(csf0).shape, dtype=np.float32),
                affine=affine,
            ),
            "affine_diff2ref": str(tmp_path / "id.txt"),
        }
        np.savetxt(padded["affine_diff2ref"], np.eye(4))
        full_shape = _embed(csf0).shape[:3]

        seen = {}

        def _capture(seed_positions, sc, affine_in, **kwargs):
            seen["sh_spatial"] = tuple(np.asarray(kwargs["sh"]).shape[:3])
            seen["affine"] = np.array(affine_in)
            return [np.array([[6.0, 6.0, 6.0], [6.0, 6.0, 7.0]])]

        import dipy.tracking.tracker as tracker

        monkeypatch.setattr(tracker, "probabilistic_tracking", _capture)

        node = _configure(DipyTracking(), padded, seed_density=1)
        node.run()

        # the SH handed to the tracker is cropped strictly smaller than the FOV
        for axis in range(3):
            assert seen["sh_spatial"][axis] < full_shape[axis]
        # and the affine was shifted off identity by the crop offset
        assert not np.allclose(seen["affine"], np.eye(4))

    def test_crop_is_invariant_to_background_padding(
        self, workspace, make_nifti, tracking_inputs
    ):
        """The crop must be scientifically a no-op: the same brain content placed
        in two different zero-background FOVs (with the affine offset so its world
        coordinates are unchanged) must yield identical streamlines, because the
        crop recovers the same tracking problem in the same world frame from both.
        Without the crop the tracker would see two different-sized grids and their
        boundary behaviour would diverge."""
        from dipy.io.streamline import load_tractogram

        def _canonical(streamlines):
            return sorted(tuple(np.round(s.ravel(), 2)) for s in streamlines)

        wm0, gm0, csf0 = _pve_maps()
        sh0 = _sh_field()

        def _padded_inputs(pad, prefix):
            def _embed(arr):
                shape = tuple(d + 2 * pad for d in arr.shape[:3])
                out = np.zeros(shape + arr.shape[3:], dtype=arr.dtype)
                out[pad:-pad, pad:-pad, pad:-pad] = arr
                return out

            affine = np.eye(4)
            affine[:3, 3] = -pad  # inner block (pad,pad,pad) -> world (0,0,0)
            return {
                "shm_coeff": make_nifti(
                    prefix + "sh.nii.gz", data=_embed(sh0), affine=affine
                ),
                "pve_wm": make_nifti(
                    prefix + "wm.nii.gz", data=_embed(wm0), affine=affine
                ),
                "pve_gm": make_nifti(
                    prefix + "gm.nii.gz", data=_embed(gm0), affine=affine
                ),
                "pve_csf": make_nifti(
                    prefix + "csf.nii.gz", data=_embed(csf0), affine=affine
                ),
                "reference": tracking_inputs["reference"],
                "affine_diff2ref": tracking_inputs["affine_diff2ref"],
            }

        results = []
        for pad, prefix, out in ((4, "a", "pa.trx"), (8, "b", "pb.trx")):
            node = _configure(
                DipyTracking(),
                _padded_inputs(pad, prefix),
                seed_density=1,
                random_seed=1,
                out_file=out,
            )
            node.run()
            sft = load_tractogram(
                node._list_outputs()["tractogram"], "same", bbox_valid_check=False
            )
            results.append(_canonical(sft.streamlines))

        assert len(results[0]) > 0
        assert results[0] == results[1]


# --------------------------------------------------------------------------- #
# Trait defaults / ranges -- the same knobs surfaced as the Task 2 preferences,
# and they must stay in sync (spec section 2 gating table).
# --------------------------------------------------------------------------- #
class TestTrackingTraitContract:
    def test_defaults_match_preferences(self):
        node = DipyTracking()
        assert node.inputs.seed_density == 2
        assert node.inputs.max_angle == 20.0
        assert node.inputs.step_size == 0.2

    def test_ranges_match_preferences(self):
        node = DipyTracking()
        for value in (0, 11):
            with pytest.raises(Exception):
                node.inputs.seed_density = value
        for value in (0.9, 91.0):
            with pytest.raises(Exception):
                node.inputs.max_angle = value
        for value in (0.049, 2.1):
            with pytest.raises(Exception):
                node.inputs.step_size = value


# --------------------------------------------------------------------------- #
# Seeding is restricted to the WM PVE mask.
# --------------------------------------------------------------------------- #
class TestWmSeeding:
    def test_mask_is_wm_dominant_voxels_only(self):
        wm, gm, csf = _pve_maps()
        mask = wm_seed_mask(wm)
        # every masked voxel is WM-dominant, nothing in CSF or cortex caps
        assert mask.sum() > 0
        assert np.all(wm[mask] >= WM_PVE_SEED_THRESHOLD)
        assert not mask[csf > 0.5].any()
        assert not mask[gm > 0.5].any()

    def test_seeds_fall_inside_the_wm_region(self):
        wm, _, _ = _pve_maps()
        affine = np.eye(4)
        seeds = generate_wm_seeds(wm, affine, density=2)
        assert len(seeds) > 0
        # map each world seed back to its nearest voxel and assert it is WM
        inv = np.linalg.inv(affine)
        for seed in seeds:
            vox = np.round(inv[:3, :3] @ seed + inv[:3, 3]).astype(int)
            assert wm[tuple(vox)] >= WM_PVE_SEED_THRESHOLD


# --------------------------------------------------------------------------- #
# The tractogram is a non-empty, loadable .trx in reference space.
# --------------------------------------------------------------------------- #
class TestTractogramOutput:
    def test_trx_is_written_loadable_and_non_empty(self, workspace, tracking_inputs):
        from dipy.io.streamline import load_tractogram

        node = _configure(DipyTracking(), tracking_inputs, seed_density=1)
        node.run()

        out = node._list_outputs()["tractogram"]
        assert out.endswith(".trx")
        assert os.path.exists(out)

        sft = load_tractogram(out, "same", bbox_valid_check=False)
        assert len(sft.streamlines) > 0

    def test_streamlines_are_moved_to_reference_space(
        self, workspace, tracking_inputs, tmp_path
    ):
        from dipy.io.streamline import load_tractogram

        # A pure translation diffusion->reference must shift every coordinate.
        shift = np.eye(4)
        shift[:3, 3] = [100.0, 0.0, 0.0]
        shifted = tmp_path / "diff2ref_shift.txt"
        np.savetxt(shifted, shift)

        node = _configure(
            DipyTracking(),
            tracking_inputs,
            seed_density=1,
            affine_diff2ref=str(shifted),
        )
        node.run()

        sft = load_tractogram(
            node._list_outputs()["tractogram"], "same", bbox_valid_check=False
        )
        # all x coordinates are pushed past the original 12-voxel grid extent
        xs = np.concatenate([s[:, 0] for s in sft.streamlines])
        assert xs.min() > 50.0


# --------------------------------------------------------------------------- #
# Streamline-order reproducibility at a fixed random_seed.
# --------------------------------------------------------------------------- #
class TestReproducibility:
    @staticmethod
    def _canonical(streamlines):
        return sorted(tuple(np.round(s.ravel(), 3)) for s in streamlines)

    def test_equal_random_seed_gives_identical_trajectories(
        self, workspace, tracking_inputs
    ):
        from dipy.io.streamline import load_tractogram

        results = []
        for name in ("run_a.trx", "run_b.trx"):
            node = _configure(
                DipyTracking(),
                tracking_inputs,
                seed_density=1,
                random_seed=1,
                num_threads=2,  # exercise the multi-threaded order variance
                out_file=name,
            )
            node.run()
            sft = load_tractogram(
                node._list_outputs()["tractogram"], "same", bbox_valid_check=False
            )
            results.append(self._canonical(sft.streamlines))

        assert results[0] == results[1]


# --------------------------------------------------------------------------- #
# The literature-based length bounds (spec section 5) are enforced by the
# tracker: no valid streamline is shorter than MIN_LEN_MM or longer than
# MAX_LEN_MM. They ship as module constants (not traits) so the graph and the
# golden matrix snapshots do not change.
# --------------------------------------------------------------------------- #
class TestLengthBounds:
    def test_length_constants_are_the_literature_values(self):
        assert MIN_LEN_MM == 10.0
        assert MAX_LEN_MM == 250.0

    def test_output_streamlines_respect_the_length_bounds(
        self, workspace, tracking_inputs
    ):
        from dipy.io.streamline import load_tractogram
        from dipy.tracking.utils import length

        node = _configure(DipyTracking(), tracking_inputs, seed_density=2)
        node.run()

        sft = load_tractogram(
            node._list_outputs()["tractogram"], "same", bbox_valid_check=False
        )
        assert len(sft.streamlines) > 0
        lengths = np.array(list(length(sft.streamlines)))
        # a small numerical tolerance: dipy measures the polyline length, which
        # can dip a hair below the requested bound at the discretised step.
        assert lengths.min() >= MIN_LEN_MM - 1.0
        assert lengths.max() <= MAX_LEN_MM


# --------------------------------------------------------------------------- #
# Thread pinning: OMP/OPENBLAS pinned to num_threads, nbr_threads follows it,
# and the length bounds are wired to probabilistic_tracking.
# --------------------------------------------------------------------------- #
class TestThreadPinning:
    def test_omp_pinned_and_nbr_threads_follows_num_threads(
        self, workspace, tracking_inputs, monkeypatch
    ):
        monkeypatch.delenv(OMP_THREADS_VAR, raising=False)
        monkeypatch.delenv(OPENBLAS_THREADS_VAR, raising=False)

        seen = {}

        def _fake_tracking(seed_positions, sc, affine, **kwargs):
            seen["omp"] = os.environ.get(OMP_THREADS_VAR)
            seen["openblas"] = os.environ.get(OPENBLAS_THREADS_VAR)
            seen["nbr_threads"] = kwargs.get("nbr_threads")
            seen["min_len"] = kwargs.get("min_len")
            seen["max_len"] = kwargs.get("max_len")
            # return a single short streamline so the node can finish
            return [np.array([[1.0, 1.0, 1.0], [1.0, 1.0, 2.0]])]

        # the node imports probabilistic_tracking lazily; patch the dipy source
        import dipy.tracking.tracker as tracker

        monkeypatch.setattr(tracker, "probabilistic_tracking", _fake_tracking)

        node = _configure(
            DipyTracking(), tracking_inputs, num_threads=3, seed_density=1
        )
        node.run()

        assert seen["omp"] == "3"
        assert seen["openblas"] == "3"
        assert seen["nbr_threads"] == 3
        assert seen["min_len"] == MIN_LEN_MM
        assert seen["max_len"] == MAX_LEN_MM
        assert OMP_THREADS_VAR not in os.environ
        assert OPENBLAS_THREADS_VAR not in os.environ
