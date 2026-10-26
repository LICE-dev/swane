# -*- coding: utf-8 -*-
import os
from contextlib import contextmanager

import numpy as np
from nipype.interfaces.base import isdefined

ITK_THREADS_VAR = "ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS"

# How far a mask's geometry may drift from its image's before the pair is
# refused (match_mask_geometry). Within them the drift is header rounding
# (e.g. float32 qform/sform written by other tools) and the mask is given the
# image's exact geometry, since ITK itself demands agreement to about 1e-6.
MASK_ORIGIN_TOLERANCE_MM = 0.1
MASK_SPACING_TOLERANCE_MM = 1e-3
MASK_DIRECTION_TOLERANCE = 1e-3


@contextmanager
def thread_env(num_threads, variables=(ITK_THREADS_VAR,)):
    """Export ``num_threads`` in each of ``variables`` for the block.

    The previous values are restored on exit. Only a positive count is
    exported: an undefined or non-positive one means "the library's default"
    (all cores), and exporting 0 is undefined for OpenMP, so the environment is
    then left untouched.

    ITK (and TensorFlow) read these variables once per process, the first time
    they run, and cache them: setting them only takes effect in a process that
    has not run them yet. Interfaces using this helper therefore declare
    ``fresh_process = True``, so that MonitoredMultiProcPlugin runs each node
    in a new process (see its "Fresh processes" note).
    """
    saved = {var: os.environ.get(var) for var in variables}
    if isdefined(num_threads) and num_threads > 0:
        for var in variables:
            os.environ[var] = str(num_threads)
    try:
        yield
    finally:
        for var, previous in saved.items():
            if previous is None:
                os.environ.pop(var, None)
            else:
                os.environ[var] = previous


# Fixed seed for the random metric sampling of the ANTs registrations
# (antsRegistration --random-seed, set through ants.config._random_seed). It
# must be a non-zero integer: ANTs treats 0 as "no seed" and seeds from the
# clock. 123 is the default seed of antspyx's own deterministic mode
# (ants.config). It makes the sampling reproducible; the output is
# bit-identical run to run only with a single ITK thread, because
# multithreaded metric sums are accumulated in a non-deterministic order.
DEFAULT_RANDOM_SEED = 123


@contextmanager
def ants_random_seed(seed):
    """Set ``ants.config._random_seed`` for the duration of the block.

    ants.registration passes this module setting as --random-seed. The
    previous value is restored on exit, so a node never leaks its seed into
    the rest of the (worker) process. An explicit node seed takes precedence
    over any process-wide choice (``set_ants_deterministic``).
    """
    import ants

    previous = ants.config._random_seed
    ants.config._random_seed = int(seed)
    try:
        yield
    finally:
        ants.config._random_seed = previous


def match_mask_geometry(img, mask):
    """Give ``mask`` the exact geometry of ``img``, or refuse the pair.

    The shapes must be equal, and the spacing, direction cosines and origin
    within MASK_SPACING_TOLERANCE_MM, MASK_DIRECTION_TOLERANCE and
    MASK_ORIGIN_TOLERANCE_MM: the mask then takes the image's origin, spacing
    and direction. Anything further apart is a mask on another grid, which
    relabelling would silently misplace and ITK would reject with an opaque
    error, so a RuntimeError names what differs.

    Parameters
    ----------
    img : ants.ANTsImage
        The image the mask is used with.
    mask : ants.ANTsImage
        The mask, aligned in place.

    Returns
    -------
    ants.ANTsImage
        ``mask``, with the image's geometry.
    """
    problems = []
    if tuple(mask.shape) != tuple(img.shape):
        problems.append("shape %s vs %s" % (tuple(mask.shape), tuple(img.shape)))
    spacing_diff = np.max(np.abs(np.subtract(mask.spacing, img.spacing)))
    if spacing_diff > MASK_SPACING_TOLERANCE_MM:
        problems.append(
            "spacing %s vs %s mm"
            % (tuple(np.round(mask.spacing, 4)), tuple(np.round(img.spacing, 4)))
        )
    direction_diff = np.max(np.abs(np.subtract(mask.direction, img.direction)))
    if direction_diff > MASK_DIRECTION_TOLERANCE:
        problems.append("direction cosines differ by up to %.4g" % direction_diff)
    distance = np.linalg.norm(np.subtract(mask.origin, img.origin))
    if distance > MASK_ORIGIN_TOLERANCE_MM:
        problems.append(
            "origin distance %.4f mm (maximum %g mm)"
            % (distance, MASK_ORIGIN_TOLERANCE_MM)
        )
    if problems:
        raise RuntimeError("Image and Mask do not coincide! " + "; ".join(problems))

    mask.set_origin(img.origin)
    mask.set_spacing(img.spacing)
    mask.set_direction(img.direction)
    return mask
