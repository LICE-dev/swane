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
from swane.nipype_pipeline.workflows.freesurfer_workflow import freesurfer_workflow

SUBDIR = "freesurfer"
MAX_CPU = 4

# name -> (step, hippo, synth_reconall)
SCENARIOS = {
    "disabled_returns_none": (FreesurferStep.DISABLED, False, False),
    "synthseg": (FreesurferStep.SYNTHSEG, False, False),
    "autorecon_pial": (FreesurferStep.AUTORECON_PIAL, False, False),
    "reconall": (FreesurferStep.RECONALL, False, False),
    "reconall_hippo": (FreesurferStep.RECONALL, True, False),
    "reconall_synth_tools": (FreesurferStep.RECONALL, False, True),
}


@pytest.mark.parametrize("scenario", list(SCENARIOS), ids=list(SCENARIOS))
def test_freesurfer_matrix(scenario, global_config, graph_snapshot):
    step, hippo, synth_reconall = SCENARIOS[scenario]
    synth = global_config[GlobalPrefCategoryList.SYNTH]
    synth["reconall"] = "true" if synth_reconall else "false"

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
