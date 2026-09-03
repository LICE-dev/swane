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
    WM_PVE_SEED_THRESHOLD,
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
