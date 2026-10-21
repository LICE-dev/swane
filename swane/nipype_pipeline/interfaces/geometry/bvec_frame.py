"""The frame FSL-convention b-vectors are expressed in."""

import numpy as np
from scipy.linalg import polar


def fsl_bvec_frame(image_affine):
    """Orthonormal 3x3 taking an FSL-convention b-vector to world (RAS) space.

    FSL b-vectors (as dcm2niix writes them) lie along the voxel axes, scaled to
    mm, with x mirrored when the voxel-to-world determinant is positive. The
    voxel axes are the orthonormal (polar) factor of the affine's 3x3, which
    drops the zooms and keeps any obliquity.

    Parameters
    ----------
    image_affine : array-like of shape (4, 4)
        The voxel-to-world affine of the series the b-vectors refer to.

    Returns
    -------
    ndarray of shape (3, 3)
        W such that ``W @ b`` is the world direction of the b-vector ``b``.
    """
    frame, _ = polar(np.asarray(image_affine, dtype=float)[:3, :3])
    if np.linalg.det(frame) > 0:
        frame = frame @ np.diag([-1.0, 1.0, 1.0])
    return frame
