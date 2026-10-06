import os
import subprocess
import sys

import pytest

# Thread variables read once per process by ITK, OpenMP and TensorFlow.
SINGLE_THREAD_ENV = {
    "ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS": "1",
    "OMP_NUM_THREADS": "1",
    "TF_NUM_INTRAOP_THREADS": "1",
    "TF_NUM_INTEROP_THREADS": "1",
}


@pytest.fixture
def run_single_thread_child():
    """Run Python ``code`` in a fresh single-threaded interpreter.

    ITK (and TensorFlow) read their thread counts once per process and cache
    them, so in a pytest session that already ran an ITK filter a later
    single-thread setting has no effect. Reproducibility checks therefore run
    each repetition in a new interpreter. The child imports this same swane
    package, installed or not, through AntsMotionCorrection's bootstrap;
    ``args`` are available to ``code`` as ``sys.argv[5:]``.
    """
    from swane.nipype_pipeline.interfaces.ants.AntsMotionCorrection import (
        _CHILD_BOOTSTRAP,
    )
    import swane

    package_root = os.path.dirname(os.path.dirname(os.path.abspath(swane.__file__)))

    def _run(code, *args, cwd):
        proc = subprocess.run(
            # the bootstrap reads the package root from sys.argv[4]
            [sys.executable, "-c", _CHILD_BOOTSTRAP + code, "-", "-", "-"]
            + [package_root]
            + [str(a) for a in args],
            cwd=cwd,
            env=dict(os.environ, **SINGLE_THREAD_ENV),
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stderr[-4000:]

    return _run
