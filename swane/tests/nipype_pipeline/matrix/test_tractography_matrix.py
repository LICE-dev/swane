"""Settings matrix for
:func:`swane.nipype_pipeline.workflows.tractography_workflow.tractography_workflow`.

The baseline is a fully-equipped FSL install: with the XTRACT protocol data
present (``$FSLDIR/data/xtract_data/.../<tract>_l|_r``) the builder assembles
the real per-hemisphere probtrackx graph, which is what we snapshot. On a box
without that data the *known-tract* scenario degrades to a skip (never a
failure). The *unknown-tract* scenario is genuinely tool-independent — a name
that is not in ``TRACTS`` always returns ``None`` regardless of what is
installed — so it is asserted directly. Snapshots under ``snapshots/tractography/``.
"""

import os

import pytest

from swane.config.config_enums import GlobalPrefCategoryList
from swane.config.preference_list import XTRACT_DATA_DIR
from swane.utils.DataInputList import DataInputList
from swane.nipype_pipeline.workflows.tractography_workflow import tractography_workflow
from swane.tests.nipype_pipeline.matrix.conftest import require_fsl_data

SUBDIR = "tractography"


def test_unknown_tract_returns_none(subject_config, global_config):
    """A tract name not in ``TRACTS`` is rejected before any FSL data is read."""
    wf = tractography_workflow(
        "definitely_not_a_tract",
        config=subject_config[DataInputList.DTI],
        synth_config=global_config[GlobalPrefCategoryList.SYNTH],
    )
    assert wf is None, "an unknown tract name must return None on any box"


def test_known_tract_real_graph(subject_config, global_config, graph_snapshot):
    """With XTRACT data present (the norm), the real cst graph is built and snapshotted."""
    require_fsl_data(os.path.join(XTRACT_DATA_DIR, "cst_l"))

    section = subject_config[DataInputList.DTI]
    section["cuda"] = "false"

    wf = tractography_workflow(
        "cst",
        config=section,
        synth_config=global_config[GlobalPrefCategoryList.SYNTH],
    )
    assert wf is not None, "cst graph should build when XTRACT data is present"

    graph_snapshot(
        wf,
        subdir=SUBDIR,
        name="cst_real_graph",
        config={"tract": "cst", "cuda": "false", "xtract_data": "present"},
        title="tractography / cst_real_graph",
    )


def test_known_tract_real_graph_test_run(subject_config, global_config, graph_snapshot):
    """test_run=True: n_samples is halved from the xtract-protocol value.
    Unvalidated end-to-end yet -- see prerelease/TODO.md.
    """
    require_fsl_data(os.path.join(XTRACT_DATA_DIR, "cst_l"))

    section = subject_config[DataInputList.DTI]
    section["cuda"] = "false"

    wf = tractography_workflow(
        "cst",
        config=section,
        synth_config=global_config[GlobalPrefCategoryList.SYNTH],
        test_run=True,
    )
    assert wf is not None, "cst graph should build when XTRACT data is present"

    graph_snapshot(
        wf,
        subdir=SUBDIR,
        name="cst_real_graph_test_run",
        config={
            "tract": "cst",
            "cuda": "false",
            "xtract_data": "present",
            "test_run": True,
        },
        title="tractography / cst_real_graph_test_run",
    )
