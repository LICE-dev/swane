"""Fixtures for the settings-matrix / snapshot tests.

The construction fixtures (``subject_config``, ``global_config``,
``make_input_dir``, ``isolated_home``) are inherited from
``swane/tests/nipype_pipeline/conftest.py``. This module only adds the snapshot
comparison helper.

Golden snapshots live under ``matrix/snapshots/<builder>/<combo>.txt`` and are
committed so they can be reviewed by hand. Regenerate them after an intentional
change with::

    SWANE_SNAPSHOT_UPDATE=1 pytest swane/tests/nipype_pipeline/matrix

On a normal run a mismatch fails the test and prints how to update.
"""

import importlib
import os

import pytest

from swane.tests.nipype_pipeline.matrix._snapshot import render_snapshot

SNAPSHOTS_DIR = os.path.join(os.path.dirname(__file__), "snapshots")
_UPDATE = os.environ.get("SWANE_SNAPSHOT_UPDATE") == "1"


def fsl_data_path(*relparts):
    """Return an ``$FSLDIR``-relative data path, or ``None`` if FSL is absent."""
    fsldir = os.environ.get("FSLDIR")
    return os.path.join(fsldir, *relparts) if fsldir else None


def require_fsl_data(*paths):
    """Skip unless every ``path`` exists.

    The baseline these snapshots describe is a **fully-equipped** neuroimaging
    box (FSL + its data: MNI templates, XTRACT protocols); those branches are
    the norm and must be exercised where the data is present. A box that simply
    lacks a given data file (or FSL entirely) degrades to a *skip*, never a
    failure — the tool-gated scenarios are opt-out on a bare box, not opt-in on
    an equipped one.
    """
    if any(p is None for p in paths):
        pytest.skip("needs a real FSL install ($FSLDIR unset)")
    missing = [str(p) for p in paths if not os.path.exists(p)]
    if missing:
        pytest.skip("needs FSL data, missing: %s" % ", ".join(missing))


def import_workflow_or_skip(module_name, attr):
    """Import a workflow builder, or SKIP the whole test module with a clear
    reason when a required tool/dependency is not importable here.

    Workflow modules import their tool packages at module load (e.g.
    ``import dcm2niix`` to resolve the bundled binary path at construction), so
    on an environment lacking a given neuroimaging tool the import raises
    ``ImportError``. Rather than let that hard-error at collection time, we turn
    it into an explanatory module-level skip — the suite stays runnable on any
    environment and says *why* it could not test a given builder. Where the tool
    IS present (any OS), the builder is imported and its matrix runs normally.
    """
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        pytest.skip(
            "cannot test %s in this environment — missing tool/dependency: %s"
            % (attr, exc),
            allow_module_level=True,
        )
    return getattr(module, attr)


@pytest.fixture
def graph_snapshot(tmp_path):
    """Return ``check(workflow, subdir, name, config, title=None)``.

    It renders the built ``workflow`` to deterministic text and either
    (re)writes the golden file (update mode) or asserts it matches.
    """

    def check(workflow, *, subdir, name, config, title=None):
        text = render_snapshot(
            workflow,
            str(tmp_path),
            title=title or "%s/%s" % (subdir, name),
            config=config,
        )
        folder = os.path.join(SNAPSHOTS_DIR, subdir)
        golden = os.path.join(folder, name + ".txt")

        if _UPDATE:
            os.makedirs(folder, exist_ok=True)
            with open(golden, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
            return text

        assert os.path.exists(golden), (
            "Missing snapshot %s.\nGenerate it with:\n"
            "  SWANE_SNAPSHOT_UPDATE=1 pytest swane/tests/nipype_pipeline/matrix"
            % os.path.relpath(golden)
        )
        with open(golden, encoding="utf-8") as handle:
            expected = handle.read()
        assert text == expected, (
            "Workflow snapshot changed for %s/%s.\n"
            "If this change is intentional, refresh the golden files with:\n"
            "  SWANE_SNAPSHOT_UPDATE=1 pytest swane/tests/nipype_pipeline/matrix\n"
            % (subdir, name)
        )
        return text

    return check
