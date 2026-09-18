"""Properties the phantom deformation must keep — fast, no FreeSurfer needed.

These pin the field itself (pure numpy), independently of building an anatomy:
it must be deterministic, small, smooth, diffeomorphic, and it must rotate
direction vectors by a proper rotation. If any of these break, the phantom is
no longer a trustworthy non-linear-registration target.
"""

import os

import numpy as np
import pytest

from swane.tests.helpers.phantom.deformation import (
    DEFORMATION,
    _displacement_jacobian,
    _rotate_directions,
    deform_anatomy,
    displacement,
)
from swane.tests.helpers.phantom.tissue import TissueClass, _wm_background_field


def _has_fsaverage() -> bool:
    home = os.environ.get("FREESURFER_HOME")
    if not home:
        return False
    return os.path.isdir(os.path.join(home, "subjects", "fsaverage", "mri"))


def _adjacent_mean_cosine(field, mask):
    """Mean |cos| between the direction vectors of face-adjacent ``mask`` voxels.

    Sign-insensitive: a principal diffusion direction has no polarity, so an
    exact anti-parallel neighbour is as coherent as a parallel one. A random
    field averages ~0; a smooth one approaches 1.
    """
    cosines = []
    for axis in range(3):
        a = np.take(field, np.arange(field.shape[axis] - 1), axis=axis)
        b = np.take(field, np.arange(1, field.shape[axis]), axis=axis)
        ma = np.take(mask, np.arange(mask.shape[axis] - 1), axis=axis)
        mb = np.take(mask, np.arange(1, mask.shape[axis]), axis=axis)
        both = ma & mb
        if not both.any():
            continue
        dot = np.abs((a * b).sum(axis=-1))[both]
        cosines.append(dot)
    if not cosines:
        return 1.0
    return float(np.concatenate(cosines).mean())


def _grid(n=25, extent=100.0):
    g = np.linspace(-extent, extent, n)
    x, y, z = np.meshgrid(g, g, g, indexing="ij")
    return np.stack([x, y, z], axis=-1)


def test_displacement_is_deterministic():
    pts = _grid()
    assert np.array_equal(displacement(pts), displacement(pts))


def test_displacement_amplitude_is_small():
    """A few millimetres: enough to matter, small enough to stay realistic."""
    mag = np.linalg.norm(displacement(_grid()), axis=-1)
    assert mag.max() < 8.0, "peak displacement %.2f mm is too large" % mag.max()
    assert mag.mean() > 0.5, "displacement is negligible (mean %.2f mm)" % mag.mean()


def test_deformation_is_diffeomorphic_over_the_head():
    """det(I + J_D) > 0 everywhere means the warp folds nothing."""
    jac = _displacement_jacobian(_grid(), DEFORMATION)
    det = np.linalg.det(np.eye(3) + jac)
    assert det.min() > 0.0, (
        "deformation is not diffeomorphic (min det %.3f)" % det.min()
    )


def test_rotation_returns_unit_vectors_for_unit_input():
    pts = _grid(n=8).reshape(-1, 3)
    weight = np.ones(len(pts))
    vecs = np.tile(np.array([0.0, 0.0, 1.0]), (len(pts), 1))
    rotated = _rotate_directions(vecs, pts, weight, DEFORMATION)
    norms = np.linalg.norm(rotated, axis=-1)
    # The polar factor is a proper rotation, so it preserves length.
    assert np.allclose(norms, 1.0, atol=1e-6)


def test_zero_weight_leaves_directions_unchanged():
    """Where the taper weight is zero (outside the head) there is no rotation."""
    pts = _grid(n=6).reshape(-1, 3)
    weight = np.zeros(len(pts))
    vecs = np.tile(np.array([1.0, 0.0, 0.0]), (len(pts), 1))
    rotated = _rotate_directions(vecs, pts, weight, DEFORMATION)
    assert np.allclose(rotated, vecs, atol=1e-9)


# --- WM background direction field ---------------------------------------


def _wm_blob(shape=(40, 40, 40)):
    """A smooth solid WM blob and a voxel->RAS affine centred on the origin."""
    cx = (np.asarray(shape) - 1) / 2.0
    ii, jj, kk = np.indices(shape)
    r = np.sqrt((ii - cx[0]) ** 2 + (jj - cx[1]) ** 2 + (kk - cx[2]) ** 2)
    wm = r < 0.4 * min(shape)
    affine = np.eye(4)
    affine[:3, 3] = -cx
    return wm, affine, (1.0, 1.0, 1.0)


def test_background_field_is_unit_and_zero_outside_wm():
    wm, affine, zooms = _wm_blob()
    field = _wm_background_field(wm, affine, zooms)
    assert field.shape == wm.shape + (3,)
    norms = np.linalg.norm(field, axis=-1)
    # Unit inside WM, exactly zero outside it.
    assert np.allclose(norms[wm], 1.0, atol=1e-5)
    assert np.all(norms[~wm] == 0.0)


def test_background_field_covers_nearly_all_wm():
    """The registration structure is worthless with holes: fill nearly all WM."""
    wm, affine, zooms = _wm_blob()
    field = _wm_background_field(wm, affine, zooms)
    covered = (np.linalg.norm(field, axis=-1) > 1e-6) & wm
    assert covered.sum() >= 0.99 * wm.sum()


def test_background_field_is_spatially_coherent_not_noise():
    """Neighbouring background voxels must point the same way (anti-noise gate).

    A gradient-of-smoothed-distance field is low-frequency, so adjacent voxels
    align tightly; random directions would average ~0. The 0.9 bar (< ~26 deg
    between neighbours) is far above what any noise field could reach, yet easily
    met by a smooth field.
    """
    wm, affine, zooms = _wm_blob()
    field = _wm_background_field(wm, affine, zooms)
    assert _adjacent_mean_cosine(field, wm) > 0.9


# --- deform_anatomy over the whole fibre field ---------------------------


def _synthetic_fiber_anatomy():
    """A WM block with an embedded corridor and a unit direction over all of it.

    ``fiber_support`` is the whole WM block; a smaller ``cst`` corridor sits
    inside it. Used to prove ``deform_anatomy`` keeps the field over the whole
    support, not only the CST (the pre-v9 behaviour).
    """
    shape = (30, 30, 30)
    labels = np.full(shape, TissueClass.AIR, dtype=np.int16)
    labels[6:24, 6:24, 6:24] = TissueClass.WM
    wm = labels == TissueClass.WM
    cst = np.zeros(shape, dtype=bool)
    cst[14:16, 14:16, 6:24] = True  # a thin corridor through the block
    field = np.zeros(shape + (3,), dtype=np.float32)
    field[wm] = np.array([0.0, 0.0, 1.0], dtype=np.float32)  # unit, superior
    affine = np.eye(4)
    affine[:3, 3] = -np.array([14.5, 14.5, 14.5])
    masks = {"cst": cst, "fiber_support": wm}
    return labels, masks, field, affine, (1.0, 1.0, 1.0)


def test_deform_preserves_field_over_whole_support_not_just_cst():
    """After the warp the field must survive across the whole fibre support.

    Pre-v9 ``deform_anatomy`` re-masked the field to the CST corridor only, which
    would erase the AF/OR corridors and the WM background. It must now re-mask to
    the full ``fiber_support``.
    """
    labels, masks, field, affine, zooms = _synthetic_fiber_anatomy()
    _, warped_masks, warped_dir = deform_anatomy(labels, masks, field, affine, zooms)
    support = warped_masks["fiber_support"]
    norms = np.linalg.norm(warped_dir, axis=-1)
    # Field survives across the warped support (not collapsed to the corridor).
    covered = (norms > 1e-6) & support
    assert covered.sum() >= 0.95 * support.sum()
    # Unit-norm on the support, zero outside it.
    assert np.allclose(norms[support], 1.0, atol=1e-4)
    assert np.all(norms[~support] == 0.0)


@pytest.mark.heavy
@pytest.mark.skipif(
    not _has_fsaverage(),
    reason="needs $FREESURFER_HOME/subjects/fsaverage to build the phantom",
)
def test_built_model_field_spans_whole_wm_and_is_coherent():
    """A freshly built phantom carries a direction across (nearly) all of WM.

    This is the whole point of the WM background field: the pre-v9 model had a
    direction only inside the CST, so a whole-brain SLR had nothing to register.
    """
    from swane.tests.helpers.phantom.tissue import build_tissue_model

    model = build_tissue_model()
    wm = model.labels == TissueClass.WM
    norms = np.linalg.norm(model.cst_dir, axis=-1)
    covered = (norms > 1e-6) & wm
    assert covered.sum() >= 0.95 * wm.sum(), "only %.1f%% of WM carries a direction" % (
        100 * covered.sum() / wm.sum()
    )
    # Unit-norm wherever the field is present.
    present = norms > 1e-6
    assert np.allclose(norms[present], 1.0, atol=1e-4)
    # Zero in unambiguous non-fibre tissue.
    for cls in (TissueClass.AIR, TissueClass.CORTICAL_GM, TissueClass.CSF_VENTRICLE):
        assert np.all(norms[model.labels == cls] == 0.0), cls
    # The background stays spatially coherent through the deformation.
    assert _adjacent_mean_cosine(model.cst_dir, covered) > 0.9
