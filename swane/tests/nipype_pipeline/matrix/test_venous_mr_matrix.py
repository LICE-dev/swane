"""Settings matrix for
:func:`swane.nipype_pipeline.workflows.venous_mr_workflow.venous_mr_workflow`.

Covers the single 4D series (split in time) vs two separate phase series
(converted + merged) topologies, the venous-phase ``vein_detection_mode`` enum,
the brain-extraction ``deskull_engine`` enum (BET / SynthStrip / the default
antspynet) and the SynthMorph registration backend. Snapshots under
``snapshots/venous_mr/``.
"""

import pytest

from swane.config.config_enums import (
    DeskullEngine,
    GlobalPrefCategoryList,
    VeinDetectionMode,
    CoreLimit,
)
from swane.utils.DataInputList import DataInputList
from swane.tests.nipype_pipeline.matrix.conftest import import_workflow_or_skip

venous_mr_workflow = import_workflow_or_skip(
    "swane.nipype_pipeline.workflows.venous_mr_workflow", "venous_mr_workflow"
)

SUBDIR = "venous_mr"
MAX_CPU = 4

# name -> (two_series, detection_mode, deskull_engine, synth, limit_synth_cores)
SCENARIOS = {
    "single_series_sd": (False, VeinDetectionMode.SD, DeskullEngine.BET, False, False),
    "single_series_first": (
        False,
        VeinDetectionMode.FIRST,
        DeskullEngine.BET,
        False,
        False,
    ),
    "two_series": (True, VeinDetectionMode.SD, DeskullEngine.BET, False, False),
    "single_series_synth_backend": (
        False,
        VeinDetectionMode.SD,
        DeskullEngine.SYNTHSTRIP,
        True,
        False,
    ),
    "single_series_synth_backend_limit_cores": (
        False,
        VeinDetectionMode.SD,
        DeskullEngine.SYNTHSTRIP,
        True,
        True,
    ),
    # The default engine since the antspynet flip, on the FSL registration
    # backend: only the deskull node differs from single_series_sd.
    "single_series_antspynet": (
        False,
        VeinDetectionMode.SD,
        DeskullEngine.ANTSPYNET,
        False,
        False,
    ),
}


@pytest.mark.parametrize("scenario", list(SCENARIOS), ids=list(SCENARIOS))
def test_venous_mr_matrix(
    scenario, subject_config, global_config, make_input_dir, graph_snapshot
):
    two_series, detection_mode, deskull_engine, synth_backend, limit_synth_cores = (
        SCENARIOS[scenario]
    )
    section = subject_config[DataInputList.VENOUS_MR]
    section["vein_detection_mode"] = detection_mode.name
    synth = global_config[GlobalPrefCategoryList.SYNTH]
    synth["deskull_engine"] = deskull_engine.name
    synth["morph"] = "true" if synth_backend else "false"
    synth["engine"] = "SYNTH" if synth_backend else "FSL"
    synth["limit_cores"] = "true" if limit_synth_cores else "false"

    second_dir = make_input_dir("phase2") if two_series else None
    wf = venous_mr_workflow(
        "venous_mr",
        venous_mr_dir=make_input_dir("phase1"),
        config=section,
        synth_config=synth,
        venous2_mr_dir=second_dir,
        max_cpu=MAX_CPU,
        multicore_node_limit=CoreLimit.SOFT_CAP,
    )

    config_echo = {
        "two_series": two_series,
        "vein_detection_mode": detection_mode.name,
        "deskull_engine": synth["deskull_engine"],
        "synth_morph": synth["morph"],
        "limit_synth_cores": synth["limit_cores"],
        "max_cpu": MAX_CPU,
        "multicore_node_limit": CoreLimit.SOFT_CAP.name,
    }
    graph_snapshot(
        wf,
        subdir=SUBDIR,
        name=scenario,
        config=config_echo,
        title="venous_mr / %s" % scenario,
    )


def test_venous_mr_matrix_test_run(
    subject_config, global_config, make_input_dir, graph_snapshot
):
    """test_run=True on the single-series baseline.

    venous_mr's registration to reference is linear-only, so this mainly
    locks in that test_run wiring doesn't break the graph.
    """
    section = subject_config[DataInputList.VENOUS_MR]
    section["vein_detection_mode"] = VeinDetectionMode.SD.name
    synth = global_config[GlobalPrefCategoryList.SYNTH]
    # venous_mr is not yet ported to ANTs -> FSL (old morph default); morph kept
    # only for the header echo.
    synth["morph"] = "False"
    synth["engine"] = "FSL"

    wf = venous_mr_workflow(
        "venous_mr",
        venous_mr_dir=make_input_dir("phase1"),
        config=section,
        synth_config=synth,
        max_cpu=MAX_CPU,
        multicore_node_limit=CoreLimit.SOFT_CAP,
        test_run=True,
    )

    config_echo = {
        "two_series": False,
        "vein_detection_mode": VeinDetectionMode.SD.name,
        "deskull_engine": synth["deskull_engine"],
        "synth_morph": synth["morph"],
        "test_run": True,
    }
    graph_snapshot(
        wf,
        subdir=SUBDIR,
        name="test_run",
        config=config_echo,
        title="venous_mr / test_run",
    )
