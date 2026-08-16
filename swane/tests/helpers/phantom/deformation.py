"""A fixed, smooth, low-frequency deformation of the phantom anatomy.

Every phantom series is rendered from the *same* anatomy and then displaced by
its own small **rigid** pose (see ``sequences._resample``). That exercises the
linear registration between series, but leaves nothing for the non-linear step:
once the rigid part is solved the images match exactly, so FNIRT / SynthMorph
have no work to do, and the subject-to-atlas warp is never really tested.

This module warps the shared anatomy **once**, before any per-series pose, by a
deterministic smooth displacement field. Applied before the rigid pose and
identical across series, it keeps the inter-series relationship rigid — what a
real scanner produces — while making the *subject* differ non-linearly from the
atlas (MNI / the symmetric template SWANe registers to). The field is generated
by us from a handful of fixed low-frequency components, so it is known exactly
and can serve as ground truth for the recovered warp.

Nothing here reads or derives from FSL, its atlases, or the XTRACT data: the
displacement is a closed-form sum of sinusoids over world coordinates.

The forward map is ``phi(x) = x + D(x)`` (a subject point ``x`` moves to
``phi(x)``). To render the deformed subject on a fixed grid we pull: the value
at world point ``w`` is taken from the source location ``phi^-1(w) ~= w - D(w)``
(exact to first order, which is all a few-millimetre field needs).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class DeformationSpec:
    """Parameters of the smooth displacement field, in RAS millimetres.

    ``components`` is a tuple of ``(amp_xyz, wavelength_xyz, phase_xyz)`` triples.
    Each contributes ``amp * sin(2*pi*x/wavelength + phase)`` per axis, summed.
    The wavelengths are long (60-130 mm) so the field is smooth and, at these
    amplitudes, diffeomorphic (the Jacobian stays positive-definite). Fixed on
    purpose: the same field every run means reproducible ground truth.
    """

    #: Peak displacement is roughly the per-axis amplitude sum, ~4 mm here.
    components: tuple = (
        # amplitude (mm)        wavelength (mm)        phase (rad)
        ((2.2, -1.8, 1.5), (95.0, 130.0, 110.0), (0.3, 1.1, -0.7)),
        ((-1.3, 1.1, -1.0), (60.0, 75.0, 68.0), (-1.4, 0.5, 2.0)),
        ((0.8, 0.9, 0.7), (48.0, 52.0, 45.0), (2.2, -0.9, 0.8)),
    )
    #: The field is tapered to zero this far (mm) outside the head's RAS extent,
    #: so the deformation cannot push anatomy off the grid or distort the air.
    taper_mm: float = 40.0


#: The single deformation the phantom ships with. Bump ``GENERATOR_VERSION``
#: whenever this changes so the on-disk cache and ground truth stay in step.
DEFORMATION = DeformationSpec()


def displacement(coords_ras: np.ndarray, spec: DeformationSpec = DEFORMATION):
    """Return the displacement ``D(x)`` in RAS mm for world points ``coords_ras``.

    ``coords_ras`` has shape ``(..., 3)``; the result has the same shape. This
    is the field itself — the ground-truth deformation — independent of any grid.
    """
    coords = np.asarray(coords_ras, dtype=np.float64)
    disp = np.zeros_like(coords)
    for amp, wavelength, phase in spec.components:
        for axis in range(3):
            k = 2.0 * np.pi / wavelength[axis]
            disp[..., axis] += amp[axis] * np.sin(k * coords[..., axis] + phase[axis])
    return disp


def _taper(coords_ras: np.ndarray, head_mask, affine, zooms, taper_mm: float):
    """A 0..1 weight that fades the field out beyond the head, in world space."""
    from scipy import ndimage as ndi

    # Distance (mm) from the head; 1 inside, ramping to 0 over ``taper_mm``.
    outside = ndi.distance_transform_edt(~head_mask, sampling=zooms)
    weight = np.clip(1.0 - outside / max(taper_mm, 1e-3), 0.0, 1.0)
    return weight.astype(np.float64)


def deform_anatomy(labels, masks, cst_dir, affine, zooms, spec=DEFORMATION):
    """Warp the anatomy in place-like fashion, returning deformed copies.

    Parameters
    ----------
    labels : (X, Y, Z) int
        The tissue class map; warped with nearest-neighbour so boundaries stay
        crisp and no spurious intermediate classes appear.
    masks : dict[str, ndarray(bool)]
        Feature masks (precentral, cst, ...) warped the same way, so they stay
        registered to the deformed labels.
    cst_dir : (X, Y, Z, 3) float or None
        Per-voxel fibre direction; warped positionally and rotated by the local
        Jacobian of the deformation so it still follows the (now bent) corridor.
    affine, zooms
        Grid geometry (voxel -> RAS) and voxel sizes in mm.

    Returns
    -------
    (labels, masks, cst_dir) : the deformed arrays.
    """
    from scipy import ndimage as ndi

    shape = labels.shape
    # World coordinates of every voxel centre.
    ii, jj, kk = np.meshgrid(
        np.arange(shape[0]),
        np.arange(shape[1]),
        np.arange(shape[2]),
        indexing="ij",
    )
    vox = np.stack([ii, jj, kk], axis=-1).astype(np.float64)
    world = vox @ affine[:3, :3].T + affine[:3, 3]

    from swane.tests.helpers.phantom.tissue import TissueClass

    head = np.asarray(labels) != TissueClass.AIR
    weight = _taper(world, head, affine, zooms, spec.taper_mm)

    disp = displacement(world, spec) * weight[..., None]  # (X, Y, Z, 3) RAS mm

    # Pull warp: value at grid point w comes from source location w - D(w).
    src_world = world - disp
    inv = np.linalg.inv(affine)
    src_vox = src_world @ inv[:3, :3].T + inv[:3, 3]
    coords = np.moveaxis(src_vox, -1, 0)  # (3, X, Y, Z) for map_coordinates

    def _pull(volume, order):
        return ndi.map_coordinates(volume, coords, order=order, mode="nearest")

    warped_labels = _pull(np.asarray(labels), order=0).astype(labels.dtype)
    warped_masks = {
        name: _pull(np.asarray(mask, dtype=np.uint8), order=0).astype(bool)
        for name, mask in masks.items()
    }

    warped_dir = None
    if cst_dir is not None:
        warped_dir = np.zeros_like(cst_dir)
        for axis in range(3):
            warped_dir[..., axis] = _pull(cst_dir[..., axis], order=1)
        # Keep a direction only inside the (warped) CST corridor: order-1
        # interpolation of the components bleeds small values past the crisp
        # mask, so re-mask to preserve the original "direction ⊆ CST" invariant.
        corridor = warped_masks.get("cst")
        if corridor is not None:
            warped_dir[~corridor] = 0.0
        # The Jacobian rotation and re-normalisation run only on the corridor
        # voxels (a few thousand), never the whole 256^3 grid.
        norm = np.linalg.norm(warped_dir, axis=-1)
        sel = norm > 1e-6
        if sel.any():
            rotated = _rotate_directions(warped_dir[sel], world[sel], weight[sel], spec)
            rotated /= np.linalg.norm(rotated, axis=-1, keepdims=True)
            warped_dir[sel] = rotated

    return warped_labels, warped_masks, warped_dir


def _rotate_directions(vectors, world_pts, weight, spec):
    """Rotate fibre directions by the local rotation of the deformation.

    ``vectors``, ``world_pts`` and ``weight`` are flat arrays over the selected
    corridor voxels: ``(N, 3)``, ``(N, 3)`` and ``(N,)``.

    The forward map is ``phi(x) = x + D(x)``; its Jacobian is ``I + J_D``. For a
    small smooth field the local rotation is the orthogonal polar factor of that
    Jacobian. ``J_D`` is analytic here (the field is a sum of sinusoids), so it
    is evaluated directly rather than by finite differences.
    """
    jac = _displacement_jacobian(world_pts, spec) * weight[..., None, None]
    full = np.eye(3) + jac  # (N, 3, 3)

    # Polar factor R = A (A^T A)^{-1/2}, per voxel, via eigen-decomposition of
    # the small 3x3 symmetric A^T A.
    ata = np.einsum("...ki,...kj->...ij", full, full)
    evals, evecs = np.linalg.eigh(ata)
    inv_sqrt = np.einsum(
        "...ij,...j,...kj->...ik",
        evecs,
        1.0 / np.sqrt(np.clip(evals, 1e-9, None)),
        evecs,
    )
    rot = np.einsum("...ij,...jk->...ik", full, inv_sqrt)
    return np.einsum("...ij,...j->...i", rot, vectors)


def _displacement_jacobian(coords_ras, spec):
    """Analytic Jacobian ``dD_i/dx_j`` of the displacement field (diagonal).

    Each component depends on axis ``j`` only through ``sin(k_j x_j + p_j)``, so
    ``dD_i/dx_j`` is non-zero only for ``i == j``: the field is separable and its
    Jacobian is diagonal.
    """
    coords = np.asarray(coords_ras, dtype=np.float64)
    jac = np.zeros(coords.shape[:-1] + (3, 3), dtype=np.float64)
    for amp, wavelength, phase in spec.components:
        for axis in range(3):
            k = 2.0 * np.pi / wavelength[axis]
            jac[..., axis, axis] += (
                amp[axis] * k * np.cos(k * coords[..., axis] + phase[axis])
            )
    return jac
