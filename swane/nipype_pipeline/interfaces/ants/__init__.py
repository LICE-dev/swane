# -*- coding: utf-8 -*-
from contextlib import contextmanager

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
