"""Settings matrix for
:func:`swane.nipype_pipeline.workflows.func_map_workflow.func_map_workflow`.

The ASL/PET functional-map builder is gated on two axes: the FreeSurfer step
(no FreeSurfer / parcellation-only SYNTHSEG / full RECONALL surfaces) and the
asymmetry-index (``ai``) preference. Each combination gets a golden snapshot
under ``snapshots/func_map/``. The builder itself has no ASL/PET branching, but
the two inputs have separate preference sections with a different default
``cost_func`` (see ``preference_list.py``: ASL -> NORMALIZED_MUTUAL_INFORMATION,
PET -> MUTUAL_INFORMATION) — ``pet_reconall_ai`` builds from
``DataInputList.PET``'s own section so that default is actually exercised
rather than assumed identical to ASL's.
"""

import pytest

from swane.config.config_enums import GlobalPrefCategoryList, FreesurferStep
from swane.utils.DataInputList import DataInputList
from swane.nipype_pipeline.workflows.func_map_workflow import func_map_workflow

SUBDIR = "func_map"

# name -> (freesurfer_step, ai, config_input, wf_name)
SCENARIOS = {
    "no_freesurfer_no_ai": (FreesurferStep.DISABLED, False, DataInputList.ASL, "asl"),
    "no_freesurfer_ai": (FreesurferStep.DISABLED, True, DataInputList.ASL, "asl"),
    "synthseg_no_ai": (FreesurferStep.SYNTHSEG, False, DataInputList.ASL, "asl"),
    "reconall_no_ai": (FreesurferStep.RECONALL, False, DataInputList.ASL, "asl"),
    "reconall_ai": (FreesurferStep.RECONALL, True, DataInputList.ASL, "asl"),
    "pet_reconall_ai": (FreesurferStep.RECONALL, True, DataInputList.PET, "pet"),
}


@pytest.mark.parametrize("scenario", list(SCENARIOS), ids=list(SCENARIOS))
def test_func_map_matrix(
    scenario, subject_config, global_config, make_input_dir, graph_snapshot
):
    freesurfer_step, ai, config_input, wf_name = SCENARIOS[scenario]
    section = subject_config[config_input]
    section["ai"] = "true" if ai else "false"

    wf = func_map_workflow(
        wf_name,
        dicom_dir=make_input_dir(),
        freesurfer_step=freesurfer_step,
        config=section,
        synth_config=global_config[GlobalPrefCategoryList.SYNTH],
    )

    config_echo = {
        "freesurfer_step": freesurfer_step.name,
        "ai": section["ai"],
        "cost_func": section["cost_func"],
        "config": config_input.name,
    }
    graph_snapshot(
        wf,
        subdir=SUBDIR,
        name=scenario,
        config=config_echo,
        title="func_map / %s" % scenario,
    )
