"""Start method for the Nipype worker pool.

The worker pool is created by the workflow process, which on macOS already
holds Qt and system-framework state (CoreFoundation, SystemConfiguration).
Apple's frameworks are not fork-safe: a worker ``fork``-ed from such a process
can segfault the first time it touches them, e.g. when antspynet downloads its
weights and urllib reads the system proxy configuration through ``_scproxy``.
Python itself has defaulted to ``spawn`` on macOS since 3.8 for this reason.

On macOS the pool therefore uses ``forkserver``: workers are forked from a
small server started with ``exec``, which never initializes those frameworks.
Linux keeps ``fork``, which is safe there, keeps copy-on-write memory sharing
with the workflow process, and is the path SWANe has always run.

The choice can be overridden for debugging with :data:`START_METHOD_ENV_VAR`.
"""

import logging
import multiprocessing
import os
import sys

logger = logging.getLogger("nipype.workflow")

#: Environment variable forcing the worker pool start method
#: (``fork``, ``forkserver`` or ``spawn``). Invalid values are ignored.
START_METHOD_ENV_VAR = "SWANE_MP_START_METHOD"


def worker_pool_start_method() -> str:
    """Return the multiprocessing start method for the Nipype worker pool.

    Returns
    -------
    str
        The :data:`START_METHOD_ENV_VAR` override when it names a start method
        available on this platform, otherwise ``forkserver`` on macOS and
        ``fork`` elsewhere. Falls back to ``spawn`` when neither is available
        (Windows, where ``spawn`` is the only start method).
    """
    available = multiprocessing.get_all_start_methods()

    override = os.environ.get(START_METHOD_ENV_VAR, "").strip().lower()
    if override:
        if override in available:
            return override
        logger.warning(
            "Ignoring %s=%r: not one of the start methods available here (%s)",
            START_METHOD_ENV_VAR,
            override,
            ", ".join(available),
        )

    default = "forkserver" if sys.platform == "darwin" else "fork"
    if default in available:
        return default
    return "spawn"
