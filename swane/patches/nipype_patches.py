# -*- DISCLAIMER: this file monkeypatches Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-

"""
Monkeypatches for Nipype needed by SWANe.

Eddy thread argument hashing
----------------------------
Nipype's generic ``args`` trait contributes to an interface hash, but SWANe
uses it on Eddy only for ``--nthr=<count>``. The thread count controls resource
usage and does not change Eddy's result, so changing the CPU allocation must
not invalidate a valid cache entry.

We wrap :meth:`EddyInputSpec.get_hashval` and hash a clone with ``args``
undefined only when the complete argument string is exactly
``--nthr=<count>``. Other Eddy arguments retain Nipype's normal hashing
semantics.

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

Bidirectional RAM estimator ``negotiate``
-----------------------------------------
The upstream :class:`nipype.utils.ram_estimator.RamEstimator` is a *one-way*
estimator: ``__call__(inputs) -> (mem_gb, debug_str)`` reserves RAM only.
SWANe needs a *bidirectional* negotiation — reserve RAM **and** tune a node's
quality-neutral parameters so its estimated peak fits the RAM budget the host
is allowed to use — but must not modify the installed nipype. We therefore add
a default ``RamEstimator.negotiate(inputs, ram_budget_gb) -> RamPlan`` as a
monkeypatch: it wraps ``__call__`` with empty tuning, so the FSL estimators
keep identical behaviour, while SWANe's tunable estimators (dipy) subclass
``RamEstimator`` and override ``negotiate`` to walk their ladder. The plan is
consumed SWANe-side by :meth:`MonitoredMultiProcPlugin._negotiate_ram`.

Windows command-line quoting
----------------------------
:class:`nipype.interfaces.base.core.CommandLine` quotes path arguments with
``shlex.quote`` (POSIX single quotes) and finds the executable with
``shlex.split(cmd)[0]`` (POSIX rules, backslashes are escapes), then runs the
command line with ``shell=True`` -- ``cmd.exe`` on Windows, where single quotes
are literal and every path contains backslashes. On Windows only,
:func:`install_windows_cmdline_quoting` rebinds the module-level ``shlex``
name of ``nipype.interfaces.base.core`` (its only ``shlex`` user among the
modules SWANe's command-line interfaces run through) to
:data:`swane.patches.windows_compat.WINDOWS_SHLEX`, whose ``quote`` and
``split`` follow the MSVCRT argv rules. Scalar path arguments therefore become
``"C:\\...\\in.nii.gz"`` and the executable lookup keeps backslashes. Nipype
computes quoted list-of-path ``%s`` elements but never uses them (the result
is discarded), so list elements stay bare on every platform, exactly as stock
Nipype. On Linux/macOS nothing is rebound.

Windows total-RAM probe
-----------------------
``nipype.utils.profiler.get_system_total_memory_gb`` reads ``/proc/meminfo``
(Linux) or ``sysctl`` (macOS) and raises ``Exception("System platform: %s is
not supported")`` elsewhere. ``MultiProcPlugin.__init__`` (and the legacy
plugin's) evaluates it as the *eager* default of ``plugin_args.get("memory_gb",
...)``, so on Windows no workflow can start even when ``memory_gb`` is given.
On Windows only, :func:`install_windows_memory_probe` rebinds that name in the
profiler module and in the two plugin modules that imported it with
``from ... import`` to :func:`swane_system_total_memory_gb`, which asks
``psutil`` (already used by Nipype's resource monitor). Linux/macOS keep the
stock probe.

Windows ``stream`` terminal output
----------------------------------
``nipype.utils.subprocess.run_command`` reads the child's pipes with
``select.select`` when ``output == "stream"`` (the CommandLine default). On
Windows ``select`` accepts only sockets (``WinError 10038``), so every
CommandLine node fails. On Windows only, :func:`install_windows_run_command`
rebinds ``run_command`` in ``nipype.utils.subprocess`` and in
``nipype.interfaces.base.core`` (the module that calls it) to
:func:`swane_windows_run_command`, which runs ``"stream"`` through Nipype's own
``"allatonce"`` path (``Popen.communicate``) and then rebuilds what ``"stream"``
adds on top: each line is logged on ``nipype.interface`` and ``runtime.merged``
holds ``"<stream> <timestamp>:<line>"`` rows (stdout rows first, then stderr;
the per-line timestamps become the completion time). ``runtime.stdout``,
``runtime.stderr`` and ``runtime.returncode`` are identical to ``"stream"``.
Every other output mode is passed through unchanged.

Why this is ``spawn``-safe
--------------------------
``swane_run_node`` lives in *this* module and is the callable submitted to the
worker pool by :class:`MonitoredMultiProcPlugin`. When a ``spawn`` worker
unpickles it, Python is forced to import ``swane.patches.nipype_patches``, and
that import applies the ``ResourceMonitor`` patch in the fresh interpreter
*before* the callable runs. The target directory travels with the pickled
``node`` (``node.config``), so nothing relies on ``fork`` inheritance,
environment variables or ``sitecustomize``.

Worker pool initializer
-----------------------
Before a pool worker receives any task, it unpickles the pool's
``initializer``. Nipype's ``MultiProcPlugin.__init__`` passes its module-level
``process_initializer``, looked up at call time, so a ``spawn`` worker would
import ``nipype.pipeline.plugins`` (whose ``sge.py`` does ``import pwd``) before
swane -- on Windows, before SWANe's ``pwd`` stub exists, which kills the pool.
:func:`apply_patches` therefore replaces that module global with
:func:`swane_process_initializer`, which lives in this module: unpickling it
imports ``swane`` (and ``swane.patches``, which installs the stub) first, and it
then delegates to Nipype's original initializer.
"""

import datetime
import os
import re
from time import time
from dataclasses import dataclass, field

import psutil
from nipype import config as _nipype_config
from nipype.interfaces.base import core as _nipype_core
from nipype.interfaces.base import Undefined, isdefined
from nipype.interfaces.fsl.epi import EddyInputSpec
from nipype.utils import profiler as _nipype_profiler
from nipype.utils import subprocess as _nipype_subprocess
from nipype.utils.profiler import ResourceMonitor
from nipype.utils.ram_estimator import RamEstimator
from nipype.pipeline.plugins import legacymultiproc as _nipype_legacymultiproc
from nipype.pipeline.plugins import multiproc as _nipype_multiproc
from nipype.pipeline.plugins.multiproc import run_node as _orig_run_node

from swane.patches import windows_compat


@dataclass
class RamPlan:
    """Outcome of a bidirectional RAM negotiation for a single node.

    Produced by ``RamEstimator.negotiate`` (added by :func:`apply_patches`). It
    carries both the RAM reservation to hand nipype's scheduler and the
    quality-neutral parameters to apply to the node so its estimated peak fits
    the RAM budget.

    Attributes
    ----------
    mem_gb : float
        The RAM reservation (GB) to set on the node, post-tuning.
    tuned_params : dict
        Quality-neutral node parameters to apply (e.g. worker/thread count,
        chunk/buffer sizes). Empty for a non-tunable estimator.
    n_procs : int or None
        The CPU reservation, kept consistent with the tuned thread/worker
        count. ``None`` means "keep the node's declared value".
    debug_str : str
        Human-readable trace of the negotiation, stored in the node report.
    """

    mem_gb: float
    tuned_params: dict = field(default_factory=dict)
    n_procs: int = None
    debug_str: str = ""


def _ram_estimator_negotiate(self, inputs, ram_budget_gb):
    """Default (non-tunable) ``RamEstimator.negotiate``.

    Wraps the one-way ``__call__`` and returns its reservation with **empty
    tuning** and ``n_procs=None`` (keep the node's declared value). The FSL
    estimators, which have no quality-neutral levers, therefore keep their
    exact current behaviour through this entry point.

    SWANe's tunable estimators override this on their own class to walk an
    ordered ladder: from the full configuration, step down to the next
    quality-neutral rung while the estimate exceeds ``ram_budget_gb``, and
    return the first rung that fits (or the bottom rung when the ladder is
    exhausted).
    """
    mem_gb, debug_str = self.__call__(inputs)
    return RamPlan(mem_gb=mem_gb, tuned_params={}, n_procs=None, debug_str=debug_str)


# Directory where the *next* ``.proc`` file must be written. Set per-node by
# :func:`swane_run_node` inside each worker process (workers run one node at a
# time, so a module-level value is safe). ``None`` means "keep Nipype's default
# behaviour" (filename resolved against the current working directory).
proc_dir = None

# Captured once, at first import, so it is always the genuine original even if
# :func:`apply_patches` is (idempotently) called more than once.
_orig_rm_init = ResourceMonitor.__init__
_orig_eddy_get_hashval = EddyInputSpec.get_hashval
_orig_process_initializer = _nipype_multiproc.process_initializer
_orig_get_system_total_memory_gb = _nipype_profiler.get_system_total_memory_gb
_orig_run_command = _nipype_subprocess.run_command

# Modules holding their own ``get_system_total_memory_gb`` binding.
_MEMORY_PROBE_MODULES = (_nipype_profiler, _nipype_multiproc, _nipype_legacymultiproc)

_EDDY_NTHR_PATTERN = re.compile(r"--nthr=\d+")

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


def _patched_get_hashval(self, hash_method=None):
    """Exclude Eddy's resource-only ``--nthr`` argument from its hash."""
    args = getattr(self, "args", Undefined)
    if isdefined(args) and _EDDY_NTHR_PATTERN.fullmatch(args):
        hash_inputs = self.clone_traits()
        hash_inputs.trait_set(trait_change_notify=False, args=Undefined)
        return _orig_eddy_get_hashval(hash_inputs, hash_method=hash_method)
    return _orig_eddy_get_hashval(self, hash_method=hash_method)


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


def swane_process_initializer(*args, **kwargs):
    """
    Drop-in replacement for Nipype's MultiProc pool ``process_initializer``.

    It does nothing beyond delegating to the original; its only purpose is to
    live in a swane module. A ``spawn`` worker unpickles the initializer before
    any task, so with this one it imports ``swane`` -- and with it the Windows
    ``pwd`` stub -- before ``nipype.pipeline.plugins`` (see the module
    docstring, "Worker pool initializer").
    """
    return _orig_process_initializer(*args, **kwargs)


def install_windows_cmdline_quoting():
    """On Windows, make Nipype's CommandLine quote and split with the MSVCRT
    rules (see the module docstring). Returns True when installed."""
    if not windows_compat.is_windows():
        return False
    _nipype_core.shlex = windows_compat.WINDOWS_SHLEX
    return True


def swane_system_total_memory_gb():
    """Total system RAM in GB, from ``psutil`` (any platform)."""
    return psutil.virtual_memory().total / (1024.0**3)


def install_windows_memory_probe():
    """On Windows, give Nipype a working total-RAM probe (see the module
    docstring). Returns True when installed."""
    if not windows_compat.is_windows():
        return False
    for module in _MEMORY_PROBE_MODULES:
        module.get_system_total_memory_gb = swane_system_total_memory_gb
    return True


def swane_windows_run_command(runtime, output=None, timeout=0.01, write_cmdline=False):
    """``run_command`` for Windows: ``"stream"`` without ``select`` on pipes
    (see the module docstring); every other mode is delegated unchanged."""
    if output != "stream":
        return _orig_run_command(
            runtime, output=output, timeout=timeout, write_cmdline=write_cmdline
        )
    runtime = _orig_run_command(
        runtime, output="allatonce", timeout=timeout, write_cmdline=write_cmdline
    )
    now = datetime.datetime.now().isoformat()
    merged = []
    for name in ("stdout", "stderr"):
        text = getattr(runtime, name)
        for line in text.split("\n") if text else []:
            row = f"{name} {now}:{line}"
            _nipype_subprocess.iflogger.info(row)
            merged.append(row)
    runtime.merged = "\n".join(merged)
    return runtime


def install_windows_run_command():
    """On Windows, route Nipype's CommandLine through
    :func:`swane_windows_run_command`. Returns True when installed."""
    if not windows_compat.is_windows():
        return False
    _nipype_subprocess.run_command = swane_windows_run_command
    _nipype_core.run_command = swane_windows_run_command
    return True


def apply_patches():
    """Install SWANe's Nipype runtime patches (idempotent)."""
    global _PATCHED
    if _PATCHED:
        return
    ResourceMonitor.__init__ = _patched_rm_init
    EddyInputSpec.get_hashval = _patched_get_hashval
    # Add the default bidirectional negotiate onto the estimator base class.
    # Subclasses with quality-neutral levers override it; the FSL estimators
    # inherit this default, which wraps __call__ with empty tuning.
    RamEstimator.negotiate = _ram_estimator_negotiate
    # MultiProcPlugin.__init__ reads this module global when it builds the pool.
    _nipype_multiproc.process_initializer = swane_process_initializer
    install_windows_cmdline_quoting()
    install_windows_memory_probe()
    install_windows_run_command()
    _PATCHED = True


# Applied as an import side-effect so that merely importing this module (e.g.
# when a spawn worker unpickles ``swane_run_node``) activates the patch.
apply_patches()
