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

import os

import pytest

from swane.tests.nipype_pipeline.matrix._snapshot import render_snapshot

SNAPSHOTS_DIR = os.path.join(os.path.dirname(__file__), "snapshots")
_UPDATE = os.environ.get("SWANE_SNAPSHOT_UPDATE") == "1"


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
