"""
Top-level (picklable) helpers for the ``spawn`` end-to-end test.

They must live in a regular importable module -- not the test module itself --
so that a ``spawn`` child can import them by qualified name.
"""


class FakeNode:
    """
    Minimal stand-in for a Nipype node.

    Carries the same configuration a real node would receive once SWANe has set
    ``crashdump_dir`` and enabled the resource monitor: both live in
    ``node.config`` because ``enable_resource_monitor()`` writes
    ``monitoring.enabled`` into the config sections that get merged into every
    node.
    """

    def __init__(self, crashdump_dir, monitor_enabled=True):
        self.config = {
            "execution": {"crashdump_dir": crashdump_dir},
            "monitoring": {"enabled": "true" if monitor_enabled else "false"},
        }

    def run(self, updatehash=False):
        # Reproduce the real Nipype gate: the monitor is a real ResourceMonitor
        # only when the *global* config says so (see interfaces/base/core.py).
        from nipype import config
        from nipype.interfaces.base.support import RuntimeContext

        rtc = RuntimeContext(resource_monitor=config.resource_monitor)
        resmon = rtc._resmon
        fname = resmon.fname  # None for the Mock, a real path otherwise
        logfile = getattr(resmon, "_logfile", None)
        if logfile is not None:
            logfile.close()
        return {"resource_monitor": config.resource_monitor, "fname": fname}


def spawn_worker(crashdump_dir, queue):
    """
    Entry point executed in a fresh ``spawn`` process.

    Importing ``swane.patches.nipype_patches`` (to reach ``swane_run_node``) must
    be enough to activate the patch in this brand-new interpreter, with no fork
    inheritance available.
    """
    import swane.patches.nipype_patches as npx

    node = FakeNode(crashdump_dir)
    result = npx.swane_run_node(node, False, 1)
    # Nipype's run_node returns dict(result=..., traceback=..., taskid=...).
    queue.put(result["result"])


def eddy_hash_worker(queue):
    """Verify the Eddy hash patch in a fresh multiprocessing interpreter."""
    import swane.patches.nipype_patches  # noqa: F401
    from nipype.interfaces.fsl.epi import Eddy

    eddy = Eddy()
    eddy.inputs.args = "--nthr=2"
    hashed_inputs, two_thread_hash = eddy.inputs.get_hashval()
    eddy.inputs.args = "--nthr=8"
    _, eight_thread_hash = eddy.inputs.get_hashval()
    queue.put(
        {
            "args_in_hash": "args" in dict(hashed_inputs),
            "same_hash": two_thread_hash == eight_thread_hash,
        }
    )
