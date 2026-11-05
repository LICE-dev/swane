"""Heavy check that every ITK node honours its own thread cap.

ITK reads ``ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS`` once per process, on the
first filter it runs, and caches it. Before ITK interfaces declared
``fresh_process`` the first ITK node of a reused Nipype worker fixed the thread
count of every later one: a node capped to 1 thread after a 4-thread node still
ran on 4 cores, beyond the scheduler's reservation.

The workflow runs under :class:`MonitoredMultiProcPlugin` with the platform's
pool start method, from a fresh interpreter: like ``WorkflowProcess`` in
production, the scheduling process itself has never run an ITK filter (this
pytest process may have). Each node records two measures: its parallelism
(process CPU time over wall time), and the number of OS threads of its process
after the filter ran -- ITK's thread pool holds exactly one thread per
configured ITK thread, so this one does not depend on how loaded the machine
is.
"""

import json
import os
import subprocess
import sys
import time

import numpy as np
import pytest

from swane.nipype_pipeline.interfaces.ants.AntsN4BiasFieldCorrection import (
    AntsN4BiasFieldCorrection,
)

PARALLELISM_FILE = "parallelism.json"
MAX_THREADS = 4


class TimedN4(AntsN4BiasFieldCorrection):
    """N4 that records how many cores and threads it effectively used."""

    def _run_interface(self, runtime):
        import psutil

        start_wall, start_cpu = time.perf_counter(), time.process_time()
        runtime = super()._run_interface(runtime)
        wall = time.perf_counter() - start_wall
        cpu = time.process_time() - start_cpu
        with open(PARALLELISM_FILE, "w") as handle:
            json.dump(
                {
                    "parallelism": cpu / wall,
                    "os_threads": psutil.Process().num_threads(),
                    "pid": os.getpid(),
                },
                handle,
            )
        return runtime


def _phantom(path):
    """A smooth bias over a sphere: enough work for N4 to dominate the I/O."""
    import nibabel as nib

    n = 128
    axis = np.linspace(-1, 1, n, dtype=np.float32)
    xx, yy, zz = np.meshgrid(axis, axis, axis, indexing="ij")
    data = (1 + 0.5 * xx) * (xx**2 + yy**2 + zz**2 < 0.8) * 100
    data += np.random.default_rng(0).normal(0, 2, data.shape).astype(np.float32)
    nib.save(nib.Nifti1Image(data.astype(np.float32), np.eye(4)), path)


def run_two_n4(work_dir, threads):
    """Run a ``threads``-thread N4 followed by a 1-thread N4; return both
    nodes' parallelism. Called in a fresh interpreter (see the module doc)."""
    from queue import Queue

    from nipype import Node, Workflow

    from swane.nipype_pipeline.engine.MonitoredMultiProcPlugin import (
        MonitoredMultiProcPlugin,
    )
    from swane.utils.mp_start_method import worker_pool_start_method

    image = os.path.join(work_dir, "phantom.nii.gz")
    _phantom(image)

    workflow = Workflow(name="itk_cap", base_dir=work_dir)
    workflow.config["execution"]["poll_sleep_duration"] = "0.1"
    # keep PARALLELISM_FILE, which is not a declared output
    workflow.config["execution"]["remove_unnecessary_outputs"] = False
    # A one-worker pool (n_procs=1 below, so the wide node reserves 1 core
    # too) makes the shared-worker case deterministic: without fresh
    # processes both nodes would run in that single worker. With more
    # workers the pool may or may not reuse the wide node's one.
    wide = Node(TimedN4(), name="wide", n_procs=1)
    wide.inputs.in_file = image
    wide.inputs.skull_stripped = True
    wide.inputs.num_threads = threads
    narrow = Node(TimedN4(), name="narrow", n_procs=1)
    narrow.inputs.skull_stripped = True
    narrow.inputs.num_threads = 1
    workflow.connect(wide, "out_file", narrow, "in_file")

    workflow.run(
        plugin=MonitoredMultiProcPlugin(
            plugin_args={
                "n_procs": 1,
                "memory_gb": 4.0,
                "n_gpu_procs": 0,
                "mp_context": worker_pool_start_method(),
                "queue": Queue(),
            }
        )
    )
    result = {}
    for name in ("wide", "narrow"):
        with open(os.path.join(work_dir, "itk_cap", name, PARALLELISM_FILE)) as f:
            result[name] = json.load(f)
    return result


_CHILD = (
    "import json, sys\n"
    "sys.path.insert(1, sys.argv[1])\n"
    "from swane.tests.nipype_pipeline.interfaces.ants.test_itk_thread_cap "
    "import run_two_n4\n"
    "print('RESULT=' + json.dumps(run_two_n4(sys.argv[2], int(sys.argv[3]))))\n"
)


@pytest.mark.heavy
def test_second_itk_node_in_a_run_honours_its_own_thread_cap(tmp_path):
    pytest.importorskip("ants")
    threads = min(os.cpu_count() or 1, MAX_THREADS)
    if threads < 3:
        pytest.skip("needs at least 3 cores to tell 1 thread from many")

    import swane

    package_root = os.path.dirname(os.path.dirname(os.path.abspath(swane.__file__)))
    env = os.environ.copy()
    env.pop("ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS", None)
    proc = subprocess.run(
        [sys.executable, "-c", _CHILD, package_root, str(tmp_path), str(threads)],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        timeout=900,
    )
    assert proc.returncode == 0, proc.stderr[-4000:]
    line = [l for l in proc.stdout.splitlines() if l.startswith("RESULT=")][-1]
    result = json.loads(line[len("RESULT=") :])

    wide, narrow = result["wide"], result["narrow"]
    # Both nodes run the same code in identically started processes, so their
    # thread counts differ only by ITK's pool: `threads` threads for the wide
    # node, 1 for the narrow one. Sharing a process, the narrow node would
    # inherit the wide pool and the difference would be 0.
    assert wide["os_threads"] - narrow["os_threads"] >= threads - 1, result
    # The narrow node really runs on one core (load can only lower this).
    assert narrow["parallelism"] < 1.3, result
