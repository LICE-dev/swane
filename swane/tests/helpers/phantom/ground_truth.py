"""Phantom anatomy centroids — the pre-release "ground truth", built with the phantom.

The pre-release sweep grades every result against what the phantom *actually*
contains: the RAS-millimetre centre of mass of the brain, the motor cortex, the
corticospinal corridor, the venous sinuses (whole and per hemisphere) and the
SEEG contacts. All of these are a deterministic function of the very
:class:`~swane.tests.helpers.phantom.tissue.TissueModel` the generator renders
the DICOM from (plus the pure-geometry SEEG trajectories), so the ground truth
is a *property of the phantom*, not an independent quantity.

Because of that, it is computed once — at phantom build time, when the tissue
model is already in hand — and cached beside the DICOM as ``ground_truth.json``
under the phantom's own cache key. The pre-release run then loads it instead of
rebuilding the tissue model a second time. A phantom cached before this file
existed simply has no sidecar; :meth:`GroundTruth.load
<swane.tests.prerelease.checks.GroundTruth.load>` falls back to recomputing it,
so old caches keep working unchanged.

Nothing here reads FSL, its atlases, or the XTRACT data: the centroids come
from our own tissue model and our own closed-form SEEG geometry.
"""

from __future__ import annotations

import json
import os

import numpy as np

#: Sidecar file written into the phantom subject directory, next to the DICOM
#: and ``manifest.json``. Keyed implicitly by the phantom's cache directory,
#: which already hashes ``GENERATOR_VERSION`` + profile + FreeSurfer stamp, so a
#: stale sidecar can never outlive the phantom it describes.
GROUND_TRUTH_FILENAME = "ground_truth.json"


def world_x_ras(shape, affine: np.ndarray) -> np.ndarray:
    """World-space RAS x coordinate of every voxel of ``shape``, given ``affine``.

    Computed from ``affine`` rather than assumed from array layout, so it is
    correct whatever the grid's orientation -- in particular for a *result*
    image that has been resampled onto the reference/T1 grid by registration,
    whose axis order/direction need not match the phantom's native grid.
    """
    ii, jj, kk = np.indices(shape, dtype=np.float32)
    return affine[0, 0] * ii + affine[0, 1] * jj + affine[0, 2] * kk + affine[0, 3]


def centre_of_mass_ras(weights: np.ndarray, affine: np.ndarray):
    """Intensity-weighted centre of mass, in RAS millimetres."""
    total = float(weights.sum())
    if not np.isfinite(total) or total <= 0:
        return None
    grid = np.indices(weights.shape, dtype=float)
    voxel = np.array([float((grid[i] * weights).sum()) / total for i in range(3)])
    return affine[:3, :3].dot(voxel) + affine[:3, 3]


def compute_centres(model) -> dict:
    """Feature centroids in RAS millimetres, derived from a built tissue model.

    Returns a ``feature -> (x, y, z)`` dict of numpy arrays. Features whose mask
    is empty in this model are simply omitted (their centre of mass is
    undefined). Used both at phantom build time (the model is already in hand)
    and by the ground-truth fallback (which rebuilds the model first), so the
    cached answer and the recomputed one are identical by construction.
    """
    from swane.tests.helpers.phantom.tissue import TissueClass as TC

    sinus = model.labels == TC.VENOUS_SINUS
    # Same hemisphere split the phantom generator itself uses to opacify
    # venous_ct2/venous_ct3 one side each (world x > 0 = right; see
    # helpers/phantom/sequences.py:_apply_side_override), so the L/R ground
    # truth matches how the phantom was actually built.
    wx = world_x_ras(sinus.shape, model.affine)
    centres = {}
    for name, mask in (
        ("brain", np.isin(model.labels, [TC.CORTICAL_GM, TC.DEEP_GM, TC.WM])),
        ("precentral", model.precentral),
        ("cst", model.cst),
        ("venous_sinus", sinus),
        ("venous_sinus_L", sinus & (wx < 0)),
        ("venous_sinus_R", sinus & (wx > 0)),
    ):
        centre = centre_of_mass_ras(np.asarray(mask, dtype=float), model.affine)
        if centre is not None:
            centres[name] = centre

    # SEEG contacts are pure RAS-mm geometry (see
    # helpers/phantom/dataset.py:seeg_trajectories), not derived from the tissue
    # model -- their centroid needs no affine/voxel grid.
    from swane.tests.helpers.phantom.dataset import seeg_contact_points

    centres["seeg"] = seeg_contact_points().mean(axis=0)
    return centres


def build_centres(freesurfer_home: str = None) -> dict:
    """Build the phantom tissue model from scratch and return its feature centres.

    The fallback path for a phantom cache that predates the on-disk sidecar:
    rebuilds the tissue model (the expensive step this cache is meant to avoid)
    and derives the centroids from it.
    """
    from swane.tests.helpers.phantom.tissue import build_tissue_model

    return compute_centres(build_tissue_model(freesurfer_home))


def save_ground_truth(subject_dir: str, centres: dict) -> str:
    """Serialise feature centres as ``ground_truth.json`` in ``subject_dir``."""
    path = os.path.join(subject_dir, GROUND_TRUTH_FILENAME)
    payload = {
        name: np.asarray(centre, dtype=float).tolist()
        for name, centre in centres.items()
    }
    with open(path, "w") as handle:
        json.dump(payload, handle, indent=2)
    return path


def load_centres(subject_dir: str) -> dict | None:
    """Read cached feature centres from ``subject_dir``, or ``None`` if absent.

    ``None`` means "this phantom cache predates the sidecar" (or was written by
    an interrupted build): the caller recomputes the centres instead.
    """
    path = os.path.join(subject_dir, GROUND_TRUTH_FILENAME)
    if not os.path.isfile(path):
        return None
    with open(path) as handle:
        payload = json.load(handle)
    return {name: np.asarray(value, dtype=float) for name, value in payload.items()}
