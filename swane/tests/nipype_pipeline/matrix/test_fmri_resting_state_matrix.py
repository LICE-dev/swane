"""Settings matrix for
:func:`swane.nipype_pipeline.workflows.fMRI_resting_state_workflow.fMRI_resting_state_workflow`.

Wires MELODIC ICA on the preprocessed data. The ``aroma=True`` path additionally
reads the ``$FSLDIR`` MNI 2mm template at construction and adds the ICA-AROMA
denoising branch: on a fully-equipped box that is the norm and is snapshotted;
on a box without the template it degrades to a skip (see
``conftest.require_fsl_data``). Snapshots under ``snapshots/fmri_resting_state/``.
"""

import pytest

from swane.utils.DataInputList import DataInputList
from swane.nipype_pipeline.workflows.fMRI_resting_state_workflow import (
    fMRI_resting_state_workflow,
)
from swane.tests.nipype_pipeline.matrix.conftest import fsl_data_path, require_fsl_data

SUBDIR = "fmri_resting_state"

# name -> (melodic_dim, melodic_thr, aroma)
SCENARIOS = {
    "melodic_auto_dim": ("0", "0.5", False),
    "melodic_fixed_dim": ("30", "0.9", False),
    "aroma_on": ("0", "0.5", True),
}


@pytest.mark.parametrize("scenario", list(SCENARIOS), ids=list(SCENARIOS))
def test_fmri_resting_state_matrix(
    scenario, subject_config, make_input_dir, graph_snapshot
):
    melodic_dim, melodic_thr, aroma = SCENARIOS[scenario]
    if aroma:
        # aroma=True reads the MNI 2mm brain template at construction time.
        require_fsl_data(
            fsl_data_path("data", "standard", "MNI152_T1_2mm_brain.nii.gz")
        )
    section = subject_config[DataInputList.FMRI_RS]
    section["aroma"] = "true" if aroma else "false"
    section["melodic_dim"] = melodic_dim
    section["melodic_thr"] = melodic_thr

    wf = fMRI_resting_state_workflow(
        "fmri_rs", dicom_dir=make_input_dir(), config=section
    )

    config_echo = {
        "aroma": section["aroma"],
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


def test_fmri_resting_state_matrix_test_run(
    subject_config, make_input_dir, graph_snapshot
):
    """test_run=True with aroma on: the ref_2_mni_fnirt node (built only in
    the aroma branch) is the only place in this workflow test_run touches,
    getting the same FNIRT strategy A as get_registration_node. melodic_dim
    stays untouched -- the phantom dataset is built to yield a specific
    component count, forcing a fixed dim would defeat that (see
    fMRI_resting_state_workflow.py).
    """
    require_fsl_data(fsl_data_path("data", "standard", "MNI152_T1_2mm_brain.nii.gz"))

    section = subject_config[DataInputList.FMRI_RS]
    section["aroma"] = "true"
    section["melodic_dim"] = "0"
    section["melodic_thr"] = "0.5"

    wf = fMRI_resting_state_workflow(
        "fmri_rs", dicom_dir=make_input_dir(), config=section, test_run=True
    )

    config_echo = {
        "aroma": "true",
        "melodic_dim": "0",
        "melodic_thr": "0.5",
        "test_run": True,
    }
    graph_snapshot(
        wf,
        subdir=SUBDIR,
        name="test_run",
        config=config_echo,
        title="fmri_resting_state / test_run",
    )
