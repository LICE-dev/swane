# -*- DISCLAIMER: this file monkeypatches Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-

"""
Monkeypatches for Nipype needed by SWANe.

Resource Monitor ``.proc`` redirection
--------------------------------------
Nipype's :class:`nipype.utils.profiler.ResourceMonitor` writes its per-node
``.proc-<pid>_time-..._freq-...`` sample files using a *relative* filename that
``os.path.abspath`` resolves against the **current working directory** of the
worker process. In SWANe that CWD is the subject ``base_dir`` (see
``WorkflowProcess.workflow_run_worker``), so the ``.proc`` files end up scattered
next to the node outputs instead of in the log folder.

We want them in the same directory already configured as
``crashdump_dir`` (the ``log`` folder). That value is *not* reachable from
``ResourceMonitor.__init__`` (it only receives the pid), so we:

1. wrap Nipype's ``run_node`` with :func:`swane_run_node`, which reads the
   directory from the pickled ``node.config["execution"]["crashdump_dir"]`` and
   stores it in the module-level :data:`proc_dir`, then delegates to the
   original ``run_node``;
2. patch :meth:`ResourceMonitor.__init__` so that, when it would build the
   default filename, it places it inside :data:`proc_dir`.

Why this is ``spawn``-safe
--------------------------
``swane_run_node`` lives in *this* module and is the callable submitted to the
worker pool by :class:`MonitoredMultiProcPlugin`. When a ``spawn`` worker
unpickles it, Python is forced to import ``swane.patches.nipype_patches``, and
that import applies the ``ResourceMonitor`` patch in the fresh interpreter
*before* the callable runs. The target directory travels with the pickled
``node`` (``node.config``), so nothing relies on ``fork`` inheritance,
environment variables or ``sitecustomize``.
"""

import os
from time import time

from nipype import config as _nipype_config
from nipype.utils.profiler import ResourceMonitor
from nipype.pipeline.plugins.multiproc import run_node as _orig_run_node

# Directory where the *next* ``.proc`` file must be written. Set per-node by
# :func:`swane_run_node` inside each worker process (workers run one node at a
# time, so a module-level value is safe). ``None`` means "keep Nipype's default
# behaviour" (filename resolved against the current working directory).
proc_dir = None

# Captured once, at first import, so it is always the genuine original even if
# :func:`apply_patches` is (idempotently) called more than once.
_orig_rm_init = ResourceMonitor.__init__

_PATCHED = False


def _default_proc_name(pid, freq):
    """Reproduce Nipype's default ``.proc`` filename (see profiler.py)."""
    return ".proc-%d_time-%s_freq-%0.2f" % (pid, time(), freq)


def _patched_rm_init(self, pid, freq=5, fname=None, python=True):
    """
    ResourceMonitor.__init__ that redirects the default ``.proc`` file into
    :data:`proc_dir` when set. Falls back to the original behaviour otherwise.
    """
    if fname is None and proc_dir:
        os.makedirs(proc_dir, exist_ok=True)
        fname = os.path.join(proc_dir, _default_proc_name(pid, freq))
    _orig_rm_init(self, pid, freq=freq, fname=fname, python=python)


def _is_monitor_enabled(node):
    """Return True if the pickled node config asks for the resource monitor."""
    try:
        enabled = node.config["monitoring"]["enabled"]
    except (TypeError, KeyError, AttributeError):
        return False
    return str(enabled).strip().lower() in ("true", "1", "yes")


def swane_run_node(node, updatehash, taskid):
    """
    Drop-in replacement for Nipype's ``run_node`` submitted to the worker pool.

    Two things must be reconstructed inside the worker from the pickled
    ``node.config``, because a ``spawn`` worker starts with a fresh Nipype global
    config that lost the parent's runtime mutations:

    1. the resource monitor must be re-enabled (otherwise Nipype uses the
       ``ResourceMonitorMock`` and no ``.proc`` file is written at all);
    2. the target ``.proc`` directory (``crashdump_dir``) must be exposed to the
       patched :class:`ResourceMonitor` via :data:`proc_dir`.

    Both values travel inside ``node.config`` (``enable_resource_monitor`` writes
    ``monitoring.enabled`` into the config sections that get merged into every
    node), so this works identically under ``fork`` (no-op) and ``spawn``.
    """
    global proc_dir
    try:
        proc_dir = node.config["execution"]["crashdump_dir"]
    except (TypeError, KeyError, AttributeError):
        proc_dir = None

    if _is_monitor_enabled(node):
        _nipype_config.enable_resource_monitor()

    return _orig_run_node(node, updatehash, taskid)


def apply_patches():
    """Install the ResourceMonitor patch (idempotent)."""
    global _PATCHED
    if _PATCHED:
        return
    ResourceMonitor.__init__ = _patched_rm_init
    _PATCHED = True


# Applied as an import side-effect so that merely importing this module (e.g.
# when a spawn worker unpickles ``swane_run_node``) activates the patch.
apply_patches()
