"""Settings matrix for
:func:`swane.nipype_pipeline.workflows.func_map_workflow.func_map_workflow`.

The ASL/PET functional-map builder is gated on two axes: the FreeSurfer step
(no FreeSurfer / parcellation-only SYNTHSEG / full RECONALL surfaces) and the
asymmetry-index (``ai``) preference. Each combination gets a golden snapshot
under ``snapshots/func_map/``.
"""

import pytest

from swane.config.config_enums import GlobalPrefCategoryList, FreesurferStep
from swane.utils.DataInputList import DataInputList
from swane.nipype_pipeline.workflows.func_map_workflow import func_map_workflow

SUBDIR = "func_map"

# name -> (freesurfer_step, ai)
SCENARIOS = {
    "no_freesurfer_no_ai": (FreesurferStep.DISABLED, False),
    "no_freesurfer_ai": (FreesurferStep.DISABLED, True),
    "synthseg_no_ai": (FreesurferStep.SYNTHSEG, False),
    "reconall_no_ai": (FreesurferStep.RECONALL, False),
    "reconall_ai": (FreesurferStep.RECONALL, True),
}


@pytest.mark.parametrize("scenario", list(SCENARIOS), ids=list(SCENARIOS))
def test_func_map_matrix(
    scenario, subject_config, global_config, make_input_dir, graph_snapshot
):
    freesurfer_step, ai = SCENARIOS[scenario]
    section = subject_config[DataInputList.ASL]
    section["ai"] = "true" if ai else "false"

    wf = func_map_workflow(
        "asl",
        dicom_dir=make_input_dir(),
        freesurfer_step=freesurfer_step,
        config=section,
        synth_config=global_config[GlobalPrefCategoryList.SYNTH],
    )

    config_echo = {
        "freesurfer_step": freesurfer_step.name,
        "ai": section["ai"],
        "cost_func": section["cost_func"],
    }
    graph_snapshot(
        wf,
        subdir=SUBDIR,
        name=scenario,
        config=config_echo,
        title="func_map / %s" % scenario,
    )
