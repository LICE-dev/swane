"""Settings matrix for
:func:`swane.nipype_pipeline.workflows.ref_workflow.ref_workflow` (T13D reference).

Sweeps the scalp-removal backend (BET vs SynthStrip) and the BET tuning
preferences (bias reduction, threshold) that branch the graph, recording one
golden snapshot per scenario under ``snapshots/ref/``.

The bias/threshold preferences only affect the BET path, so they are varied
with SynthStrip off; a single SynthStrip scenario covers the Synth backend.
"""

import pytest

from swane.config.config_enums import GlobalPrefCategoryList, CoreLimit
from swane.utils.DataInputList import DataInputList
from swane.tests.nipype_pipeline.matrix.conftest import import_workflow_or_skip

ref_workflow = import_workflow_or_skip(
    "swane.nipype_pipeline.workflows.ref_workflow", "ref_workflow"
)

SUBDIR = "ref"
MAX_CPU = 4

# name -> (synth_strip, bet_bias_correction, bet_thr, limit_synth_cores)
SCENARIOS = {
    "bet_default": (False, False, "0.3", False),
    "bet_bias_thr0": (False, True, "0", False),
    "bet_thr_high": (False, False, "1", False),
    "synthstrip": (True, False, "0.3", False),
    "synthstrip_limit_cores": (True, False, "0.3", True),
}


def _bool(value):
    return "true" if value else "false"


@pytest.mark.parametrize("scenario", list(SCENARIOS), ids=list(SCENARIOS))
def test_ref_matrix(
    scenario, subject_config, global_config, make_input_dir, graph_snapshot
):
    synth_strip, bias, bet_thr, limit_synth_cores = SCENARIOS[scenario]
    section = subject_config[DataInputList.T13D]
    section["bet_bias_correction"] = _bool(bias)
    section["bet_thr"] = bet_thr
    synth = global_config[GlobalPrefCategoryList.SYNTH]
    synth["strip"] = _bool(synth_strip)
    synth["limit_cores"] = _bool(limit_synth_cores)

    wf = ref_workflow(
        "ref",
        dicom_dir=make_input_dir(),
        config=section,
        synth_config=synth,
        max_cpu=MAX_CPU,
        multicore_node_limit=CoreLimit.SOFT_CAP,
    )

    config_echo = {
        "synth_strip": synth["strip"],
        "bet_bias_correction": section["bet_bias_correction"],
        "bet_thr": section["bet_thr"],
        "limit_synth_cores": synth["limit_cores"],
        "max_cpu": MAX_CPU,
        "multicore_node_limit": CoreLimit.SOFT_CAP.name,
    }
    graph_snapshot(
        wf,
        subdir=SUBDIR,
        name=scenario,
        config=config_echo,
        title="ref / %s" % scenario,
    )


def test_ref_matrix_test_run(
    subject_config, global_config, make_input_dir, graph_snapshot
):
    """test_run=True over otherwise-default settings.

    The prerelease sweep runs with test_run=True by default, so this scenario
    is the golden reference for what it actually builds here: N4 gets a capped
    max_iterations, nothing else in the graph shape changes.
    """
    section = subject_config[DataInputList.T13D]
    synth = global_config[GlobalPrefCategoryList.SYNTH]

    wf = ref_workflow(
        "ref",
        dicom_dir=make_input_dir(),
        config=section,
        synth_config=synth,
        max_cpu=MAX_CPU,
        multicore_node_limit=CoreLimit.SOFT_CAP,
        test_run=True,
    )

    config_echo = {
        "synth_strip": synth["strip"],
        "bet_bias_correction": section["bet_bias_correction"],
        "bet_thr": section["bet_thr"],
        "test_run": True,
    }
    graph_snapshot(
        wf,
        subdir=SUBDIR,
        name="test_run",
        config=config_echo,
        title="ref / test_run",
    )
