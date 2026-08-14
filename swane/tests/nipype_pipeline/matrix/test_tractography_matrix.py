"""Settings matrix for
:func:`swane.nipype_pipeline.workflows.tractography_workflow.tractography_workflow`.

A real tract graph needs the FSL XTRACT protocol data directory
(``$FSLDIR/data/xtract_data``); without it the builder guards out and returns
``None`` for every tract, so only that guard is testable tool-free. The
CUDA/``use_gpu`` probtrackx branch and the populated tract graph belong to the
FSL-backed matrix (see ``TODO_dicom.md`` §2). Snapshot under
``snapshots/tractography/``.
"""

import pytest

from swane.config.config_enums import GlobalPrefCategoryList
from swane.utils.DataInputList import DataInputList
from swane.nipype_pipeline.workflows.tractography_workflow import tractography_workflow

SUBDIR = "tractography"

# Both an unknown name and a real tract name resolve to None without XTRACT data.
SCENARIOS = {
    "unknown_tract_guard": "definitely_not_a_tract",
    "known_tract_without_xtract": "cst",
}


@pytest.mark.parametrize("scenario", list(SCENARIOS), ids=list(SCENARIOS))
def test_tractography_matrix(scenario, subject_config, global_config, graph_snapshot):
    tract_name = SCENARIOS[scenario]
    wf = tractography_workflow(
        tract_name,
        config=subject_config[DataInputList.DTI],
        synth_config=global_config[GlobalPrefCategoryList.SYNTH],
    )
    assert wf is None, "expected the guard to return None without XTRACT data"

    graph_snapshot(
        wf,
        subdir=SUBDIR,
        name=scenario,
        config={"tract": tract_name, "xtract_data": "absent"},
        title="tractography / %s" % scenario,
    )
