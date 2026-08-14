"""Settings matrix for
:func:`swane.nipype_pipeline.workflows.venous_mr_workflow.venous_mr_workflow`.

Covers the single 4D series (split in time) vs two separate phase series
(converted + merged) topologies, the venous-phase ``vein_detection_mode`` enum,
and the SynthStrip/SynthMorph backend. Snapshots under ``snapshots/venous_mr/``.
"""

import pytest

from swane.config.config_enums import GlobalPrefCategoryList, VeinDetectionMode
from swane.utils.DataInputList import DataInputList
from swane.nipype_pipeline.workflows.venous_mr_workflow import venous_mr_workflow

SUBDIR = "venous_mr"

# name -> (two_series, detection_mode, synth)
SCENARIOS = {
    "single_series_sd": (False, VeinDetectionMode.SD, False),
    "single_series_first": (False, VeinDetectionMode.FIRST, False),
    "two_series": (True, VeinDetectionMode.SD, False),
    "single_series_synth_backend": (False, VeinDetectionMode.SD, True),
}


@pytest.mark.parametrize("scenario", list(SCENARIOS), ids=list(SCENARIOS))
def test_venous_mr_matrix(
    scenario, subject_config, global_config, make_input_dir, graph_snapshot
):
    two_series, detection_mode, synth_backend = SCENARIOS[scenario]
    section = subject_config[DataInputList.VENOUS_MR]
    section["vein_detection_mode"] = detection_mode.name
    synth = global_config[GlobalPrefCategoryList.SYNTH]
    synth["strip"] = "true" if synth_backend else "false"
    synth["morph"] = "true" if synth_backend else "false"

    second_dir = make_input_dir("phase2") if two_series else None
    wf = venous_mr_workflow(
        "venous_mr",
        venous_mr_dir=make_input_dir("phase1"),
        config=section,
        synth_config=synth,
        venous2_mr_dir=second_dir,
    )

    config_echo = {
        "two_series": two_series,
        "vein_detection_mode": detection_mode.name,
        "synth_strip": synth["strip"],
        "synth_morph": synth["morph"],
    }
    graph_snapshot(
        wf,
        subdir=SUBDIR,
        name=scenario,
        config=config_echo,
        title="venous_mr / %s" % scenario,
    )
