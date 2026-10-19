# -*- coding: utf-8 -*-
import os
from contextlib import contextmanager

from nipype.interfaces.base import isdefined

ITK_THREADS_VAR = "ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS"


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
