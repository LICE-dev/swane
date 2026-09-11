# -*- DISCLAIMER: this file monkeypatches DIPY (https://github.com/dipy/dipy/blob/master/LICENSE)  -*-

"""
Monkeypatches for DIPY needed by SWANe.

StreamlineLinearRegistration thread count
-----------------------------------------
``dipy.align.streamlinear.progressive_slr`` (the default optimisation path of
``whole_brain_slr`` / ``slr_with_qbx``) accepts a ``num_threads`` argument but
never forwards it to the ``StreamlineLinearRegistration`` instances it builds.
Its streamline distance metric therefore ignores the requested thread count and
runs its OpenMP parallelisation on every available core.

:func:`dipy_slr_num_threads` is a context manager that, for its duration, wraps
``StreamlineLinearRegistration.__init__`` so every instance is constructed with
the given ``num_threads``, and restores the original constructor on exit. It is a
context manager rather than a permanent patch because the thread count is a
per-node input, so it must be scoped to a single registration run.
"""

from contextlib import contextmanager


@contextmanager
def dipy_slr_num_threads(num_threads):
    """
    Force every ``StreamlineLinearRegistration`` created while the context is
    active to use exactly ``num_threads`` OpenMP threads, restoring dipy's
    original constructor on exit.
    """
    from dipy.align import streamlinear

    original_init = streamlinear.StreamlineLinearRegistration.__init__

    def patched_init(self, *args, **kwargs):
        kwargs["num_threads"] = num_threads
        return original_init(self, *args, **kwargs)

    streamlinear.StreamlineLinearRegistration.__init__ = patched_init
    try:
        yield
    finally:
        streamlinear.StreamlineLinearRegistration.__init__ = original_init
