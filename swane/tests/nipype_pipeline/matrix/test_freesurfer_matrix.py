"""Settings matrix for
:func:`swane.nipype_pipeline.workflows.freesurfer_workflow.freesurfer_workflow`.

Sweeps the FreeSurfer step enum (SYNTHSEG vs the multi-stage recon-all variants)
and the hippocampal/amygdala substructure option, with an explicit ``max_cpu``
and ``SOFT_CAP`` so the ``openmp``/``n_procs`` hints stay host-independent.
``DISABLED`` is a guard returning ``None`` and is snapshotted as such.
Snapshots live under ``snapshots/freesurfer/``.
"""

import pytest

from swane.config.config_enums import GlobalPrefCategoryList, CoreLimit, FreesurferStep
from swane.tests.nipype_pipeline.matrix.conftest import import_workflow_or_skip

freesurfer_workflow = import_workflow_or_skip(
    "swane.nipype_pipeline.workflows.freesurfer_workflow", "freesurfer_workflow"
)

SUBDIR = "freesurfer"
MAX_CPU = 4

# name -> (step, hippo, synth_reconall, limit_synth_cores)
SCENARIOS = {
    "disabled_returns_none": (FreesurferStep.DISABLED, False, False, False),
    "synthseg": (FreesurferStep.SYNTHSEG, False, False, False),
    "synthseg_limit_cores": (FreesurferStep.SYNTHSEG, False, False, True),
    "autorecon_pial": (FreesurferStep.AUTORECON_PIAL, False, False, False),
    "reconall": (FreesurferStep.RECONALL, False, False, False),
    "reconall_hippo": (FreesurferStep.RECONALL, True, False, False),
    "reconall_synth_tools": (FreesurferStep.RECONALL, False, True, False),
}


@pytest.mark.parametrize("scenario", list(SCENARIOS), ids=list(SCENARIOS))
def test_freesurfer_matrix(scenario, global_config, graph_snapshot):
    step, hippo, synth_reconall, limit_synth_cores = SCENARIOS[scenario]
    synth = global_config[GlobalPrefCategoryList.SYNTH]
    synth["reconall"] = "true" if synth_reconall else "false"
    synth["limit_cores"] = "true" if limit_synth_cores else "false"

    wf = freesurfer_workflow(
        "freesurfer",
        step=step,
        is_hippo_amyg_labels=hippo,
        max_cpu=MAX_CPU,
        multicore_node_limit=CoreLimit.SOFT_CAP,
        synth_config=synth,
    )

    config_echo = {
        "step": step.name,
        "hippo_amyg_labels": hippo,
        "synth_reconall": synth["reconall"],
        "limit_synth_cores": synth["limit_cores"],
        "max_cpu": MAX_CPU,
        "multicore_node_limit": CoreLimit.SOFT_CAP.name,
    }
    graph_snapshot(
        wf,
        subdir=SUBDIR,
        name=scenario,
        config=config_echo,
        title="freesurfer / %s" % scenario,
    )


# name -> step (test_run only branches on SYNTHSEG vs any recon-all directive,
# not on hippo/synth_reconall, so one representative scenario per branch)
TEST_RUN_SCENARIOS = {
    "synthseg_test_run": FreesurferStep.SYNTHSEG,
    "reconall_test_run": FreesurferStep.RECONALL,
}


@pytest.mark.parametrize(
    "scenario", list(TEST_RUN_SCENARIOS), ids=list(TEST_RUN_SCENARIOS)
)
def test_freesurfer_matrix_test_run(scenario, global_config, graph_snapshot):
    """test_run=True: SynthSeg gets --fast/no-robust, recon-all gets the
    top-level flags + -expert file. Golden reference for what prerelease's
    default test_run=True actually builds (recon-all is opt-in there via
    --with-reconall, but test_run applies to it all the same).
    """
    step = TEST_RUN_SCENARIOS[scenario]
    synth = global_config[GlobalPrefCategoryList.SYNTH]

    wf = freesurfer_workflow(
        "freesurfer",
        step=step,
        is_hippo_amyg_labels=False,
        max_cpu=MAX_CPU,
        multicore_node_limit=CoreLimit.SOFT_CAP,
        synth_config=synth,
        test_run=True,
    )

    config_echo = {
        "step": step.name,
        "max_cpu": MAX_CPU,
        "multicore_node_limit": CoreLimit.SOFT_CAP.name,
        "test_run": True,
    }
    graph_snapshot(
        wf,
        subdir=SUBDIR,
        name=scenario,
        config=config_echo,
        title="freesurfer / %s" % scenario,
    )
