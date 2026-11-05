"""Launch a script inside a real, installed 3D Slicer for heavy tests."""

import os
import subprocess


def run_slicer_script(slicer_cmd, script, args=(), timeout=600):
    """Run ``script`` the way SWANe's Slicer nodes and workers do
    (``--no-splash --no-main-window --python-script``).

    Returns
    -------
    subprocess.CompletedProcess
        With text stdout/stderr captured.
    """
    # conftest forces QT_QPA_PLATFORM=offscreen for swane's own Qt app;
    # Slicer's bundled Qt has no such plugin and would refuse to start.
    env = dict(os.environ)
    env.pop("QT_QPA_PLATFORM", None)
    return subprocess.run(
        [
            slicer_cmd,
            "--no-splash",
            "--no-main-window",
            "--python-script",
            str(script),
            *map(str, args),
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
