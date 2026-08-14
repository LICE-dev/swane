"""Settings matrix for
:func:`swane.nipype_pipeline.workflows.fMRI_resting_state_workflow.fMRI_resting_state_workflow`.

Only the AROMA-disabled path builds tool-free: it wires MELODIC ICA on the
preprocessed data. The ``aroma=True`` path reads ``$FSLDIR`` MNI templates at
construction, so it belongs to the FSL-backed matrix (see ``TODO_dicom.md`` §2).
Snapshots under ``snapshots/fmri_resting_state/``.
"""

import pytest

from swane.utils.DataInputList import DataInputList
from swane.nipype_pipeline.workflows.fMRI_resting_state_workflow import (
    fMRI_resting_state_workflow,
)

SUBDIR = "fmri_resting_state"

# name -> (melodic_dim, melodic_thr)
SCENARIOS = {
    "melodic_auto_dim": ("0", "0.5"),
    "melodic_fixed_dim": ("30", "0.9"),
}


@pytest.mark.parametrize("scenario", list(SCENARIOS), ids=list(SCENARIOS))
def test_fmri_resting_state_matrix(
    scenario, subject_config, make_input_dir, graph_snapshot
):
    melodic_dim, melodic_thr = SCENARIOS[scenario]
    section = subject_config[DataInputList.FMRI_RS]
    section["aroma"] = "false"
    section["melodic_dim"] = melodic_dim
    section["melodic_thr"] = melodic_thr

    wf = fMRI_resting_state_workflow(
        "fmri_rs", dicom_dir=make_input_dir(), config=section
    )

    config_echo = {
        "aroma": "false",
        "melodic_dim": melodic_dim,
        "melodic_thr": melodic_thr,
    }
    graph_snapshot(
        wf,
        subdir=SUBDIR,
        name=scenario,
        config=config_echo,
        title="fmri_resting_state / %s" % scenario,
    )
