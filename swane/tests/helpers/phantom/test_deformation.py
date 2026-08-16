"""Properties the phantom deformation must keep — fast, no FreeSurfer needed.

These pin the field itself (pure numpy), independently of building an anatomy:
it must be deterministic, small, smooth, diffeomorphic, and it must rotate
direction vectors by a proper rotation. If any of these break, the phantom is
no longer a trustworthy non-linear-registration target.
"""

import numpy as np

from swane.tests.helpers.phantom.deformation import (
    DEFORMATION,
    _displacement_jacobian,
    _rotate_directions,
    displacement,
)


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
