"""Tests for the DWI signal model — whole-WM anisotropy and direction count.

These pin the v9 behaviour: 15 directions (lmax-4 floor) and an anisotropic
tensor across every WM voxel that has a fibre direction, not just the CST.
"""

import numpy as np
import pytest

from swane.tests.helpers.phantom.tissue import TissueClass, TissueModel


def _tiny_tissue_with_wm_background():
    """A minimal tissue model with CST corridor + WM background directions.

    A 20^3 grid where WM fills the inner 4-16 cube.  A thin CST corridor
    runs along z through the centre; the rest of WM is background.  The
    ``cst_dir`` field carries a unit direction everywhere in WM:

    - CST corridor: direction is (0, 0, 1)  (superior)
    - WM background: direction is (1, 0, 0) (right)

    This lets the test distinguish corridor from background anisotropy.
    """
    shape = (20, 20, 20)
    labels = np.full(shape, TissueClass.AIR, dtype=np.int16)
    labels[4:16, 4:16, 4:16] = TissueClass.WM

    precentral = np.zeros(shape, dtype=bool)
    cst = np.zeros(shape, dtype=bool)
    cst[9:11, 9:11, 4:16] = True  # thin corridor

    wm = labels == TissueClass.WM
    cst_dir = np.zeros(shape + (3,), dtype=np.float32)
    cst_dir[cst] = [0.0, 0.0, 1.0]  # superior
    bg = wm & ~cst
    cst_dir[bg] = [1.0, 0.0, 0.0]  # right

    affine = np.eye(4) * 3.0  # 3 mm isotropic
    affine[3, 3] = 1.0
    affine[:3, 3] = -30.0  # centre near origin

    return TissueModel(
        labels=labels,
        affine=affine,
        zooms=(3.0, 3.0, 3.0),
        precentral=precentral,
        cst=cst,
        cst_dir=cst_dir,
    )


def _dwi_spec():
    """A bare DWI SequenceSpec for testing."""
    from swane.tests.helpers.phantom.sequences import SequenceSpec

    return SequenceSpec(
        name="test_dwi",
        modality="MR",
        lut={TissueClass.WM: 800, TissueClass.AIR: 0},
        in_plane_mm=3.0,
        slice_mm=3.0,
        noise_sigma=0.0,
        bias_amp=0.0,
    )


def _render(tissue, n_directions=15, b_value=1000.0):
    """Render a DWI with the given direction count."""
    from swane.tests.helpers.phantom.dataset import _dwi_scheme
    from swane.tests.helpers.phantom.sequences import render_dwi

    bvals, bvecs = _dwi_scheme(n_directions, b_value)
    return render_dwi(tissue, _dwi_spec(), bvals, bvecs, seed=42)


class TestRenderDwiVolumeCount:
    """The DWI must have 15 gradient directions + the b0(s)."""

    def test_15_directions_produce_16_volumes(self):
        tissue = _tiny_tissue_with_wm_background()
        data, affine, bvals, bvecs = _render(tissue, n_directions=15)
        # 1 b0 + 15 gradient = 16 volumes total
        assert data.shape[-1] == 16
        assert len(bvals) == 16
        assert (bvals[0] == 0.0) and np.all(bvals[1:] > 0)


class TestRenderDwiAnisotropySignConvention:
    """The signal model attenuates most along the fibre direction.

    S = S0 * exp(-b * gT D g).  With d_par >> d_perp, a gradient parallel
    to the fibre gives maximum attenuation (lowest signal).  This is the
    standard DWI convention and must be preserved.
    """

    def test_cst_corridor_attenuation_matches_fibre_direction(self):
        """In the CST corridor (fibre direction [0,0,1]), a gradient along z
        must produce lower signal than a gradient along x or y."""
        tissue = _tiny_tissue_with_wm_background()
        data, _, bvals, bvecs = _render(tissue, n_directions=15)

        # CST corridor voxels in the output grid — the tissue grid IS the
        # output grid for this test (same 3 mm isotropic).
        cst_mask = tissue.cst

        # Find a gradient direction closest to z and one closest to x.
        dw_idx = np.where(bvals > 0)[0]
        dw_bvecs = bvecs[dw_idx]
        z_proj = np.abs(dw_bvecs[:, 2])
        x_proj = np.abs(dw_bvecs[:, 0])
        i_z = dw_idx[np.argmax(z_proj)]  # most along fibre
        i_x = dw_idx[np.argmax(x_proj)]  # most perpendicular

        # Mean signal in the corridor for each direction.
        s_z = data[cst_mask, i_z].astype(float).mean()
        s_x = data[cst_mask, i_x].astype(float).mean()

        # Along fibre => more attenuation => lower signal.
        assert s_z < s_x, (
            f"CST anisotropy sign wrong: signal along fibre ({s_z:.1f}) "
            f"should be < signal perpendicular ({s_x:.1f})"
        )


class TestRenderDwiBackgroundWmAnisotropy:
    """Background WM must be anisotropic in v9 (was isotropic before)."""

    def test_background_wm_is_anisotropic(self):
        """Background WM voxels (fibre direction [1,0,0]) must show direction-
        dependent attenuation, not the isotropic fallback."""
        tissue = _tiny_tissue_with_wm_background()
        data, _, bvals, bvecs = _render(tissue, n_directions=15)

        bg_mask = (tissue.labels == TissueClass.WM) & ~tissue.cst

        # Find a gradient closest to x (background fibre) and one closest to z.
        dw_idx = np.where(bvals > 0)[0]
        dw_bvecs = bvecs[dw_idx]
        x_proj = np.abs(dw_bvecs[:, 0])
        z_proj = np.abs(dw_bvecs[:, 2])
        i_x = dw_idx[np.argmax(x_proj)]  # along bg fibre
        i_z = dw_idx[np.argmax(z_proj)]  # perpendicular to bg fibre

        s_x = data[bg_mask, i_x].astype(float).mean()
        s_z = data[bg_mask, i_z].astype(float).mean()

        # Background fibre is [1,0,0] so gradient along x => maximum
        # attenuation => lower signal.
        assert s_x < s_z, (
            f"Background WM should be anisotropic: signal along fibre ({s_x:.1f}) "
            f"should be < signal perpendicular ({s_z:.1f}). "
            f"If equal, the background is still isotropic (pre-v9 behaviour)."
        )

    def test_background_wm_not_isotropic(self):
        """A stronger form: the ratio of signals in two perpendicular directions
        within background WM must differ by a meaningful amount (not ~1.0)."""
        tissue = _tiny_tissue_with_wm_background()
        data, _, bvals, bvecs = _render(tissue, n_directions=15)

        bg_mask = (tissue.labels == TissueClass.WM) & ~tissue.cst

        dw_idx = np.where(bvals > 0)[0]
        dw_bvecs = bvecs[dw_idx]
        x_proj = np.abs(dw_bvecs[:, 0])
        z_proj = np.abs(dw_bvecs[:, 2])
        i_x = dw_idx[np.argmax(x_proj)]
        i_z = dw_idx[np.argmax(z_proj)]

        s_x = data[bg_mask, i_x].astype(float).mean()
        s_z = data[bg_mask, i_z].astype(float).mean()

        ratio = s_z / max(s_x, 1e-9)
        # With d_par=1.7e-3, d_perp=0.3e-3, b=1000: the ratio should be
        # clearly > 1.0 (expected ~1.4+).
        assert ratio > 1.1, (
            f"Background WM signal ratio (perp/par) = {ratio:.3f}, "
            f"expected > 1.1 for meaningful anisotropy."
        )


class TestGeneratorVersionAndDirections:
    """GENERATOR_VERSION and dwi_directions must match v9."""

    def test_generator_version_is_9(self):
        from swane.tests.helpers.phantom.dataset import GENERATOR_VERSION

        assert GENERATOR_VERSION == "9"

    def test_default_dwi_directions_is_15(self):
        from swane.tests.helpers.phantom.dataset import PhantomProfile

        assert PhantomProfile().dwi_directions == 15

    def test_sh_order_for_15_directions_is_4(self):
        from swane.nipype_pipeline.nodes.DipyCsdFit import sh_order_for_directions

        assert sh_order_for_directions(15) == 4
