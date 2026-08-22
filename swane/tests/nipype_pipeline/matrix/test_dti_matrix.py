"""Settings matrix for
:func:`swane.nipype_pipeline.workflows.dti_preproc_workflow.dti_preproc_workflow`.

Sweeps the eddy-correction backend and the **CUDA on/off** axis (the flagship
GPU dimension: ``eddy.use_cuda`` / command choice / thread handling) and records
one golden graph snapshot per scenario under ``snapshots/dti_preproc/``.

CPU thread counts are made deterministic by passing an explicit ``max_cpu`` and
only using the ``SOFT_CAP`` / ``HARD_CAP`` core-limit modes; ``NO_LIMIT`` would
fall back to the host ``cpu_count()`` and is left to a behavioural assertion.

The ``tractography=True`` branch adds BEDPOSTX. The MNI-to-reference nonlinear
registration used to be built here too, but it is the same registration FLAT1
relies on (see ``test_nonlinear_reg_matrix.py``), so it now lives in the shared
``mni1`` workflow instantiated once by ``MainWorkflow`` and is out of scope for
this per-builder snapshot; ``dti_preproc_workflow`` no longer reads ``$FSLDIR``
MNI templates at construction time.
"""

import pytest

from swane.config.config_enums import GlobalPrefCategoryList, CoreLimit
from swane.utils.DataInputList import DataInputList
from swane.tests.nipype_pipeline.matrix.conftest import import_workflow_or_skip

dti_preproc_workflow = import_workflow_or_skip(
    "swane.nipype_pipeline.workflows.dti_preproc_workflow", "dti_preproc_workflow"
)

SUBDIR = "dti_preproc"
MAX_CPU = 4

# name -> (cuda, old_eddy, multicore_node_limit, tractography)
SCENARIOS = {
    "new_eddy_cpu_softcap": (False, False, CoreLimit.SOFT_CAP, False),
    "new_eddy_cpu_hardcap": (False, False, CoreLimit.HARD_CAP, False),
    "new_eddy_cuda": (True, False, CoreLimit.SOFT_CAP, False),
    "old_eddy_correct": (False, True, CoreLimit.SOFT_CAP, False),
    "new_eddy_tractography": (False, False, CoreLimit.SOFT_CAP, True),
}


def _bool(value):
    return "true" if value else "false"


@pytest.mark.parametrize("scenario", list(SCENARIOS), ids=list(SCENARIOS))
def test_dti_matrix(
    scenario, subject_config, global_config, make_input_dir, graph_snapshot
):
    cuda, old_eddy, multicore, tractography = SCENARIOS[scenario]
    section = subject_config[DataInputList.DTI]
    section["cuda"] = _bool(cuda)
    section["old_eddy_correct"] = _bool(old_eddy)
    section["tractography"] = _bool(tractography)
    synth = global_config[GlobalPrefCategoryList.SYNTH]

    wf = dti_preproc_workflow(
        "dti",
        dti_dir=make_input_dir(),
        config=section,
        synth_config=synth,
        max_cpu=MAX_CPU,
        multicore_node_limit=multicore,
    )

    config_echo = {
        "cuda": section["cuda"],
        "old_eddy_correct": section["old_eddy_correct"],
        "tractography": section["tractography"],
        "multicore_node_limit": multicore.name,
        "max_cpu": MAX_CPU,
        "synth_strip": synth["strip"],
        "synth_morph": synth["morph"],
    }
    graph_snapshot(
        wf,
        subdir=SUBDIR,
        name=scenario,
        config=config_echo,
        title="dti_preproc / %s" % scenario,
    )


def test_dti_matrix_test_run(
    subject_config, global_config, make_input_dir, graph_snapshot
):
    """test_run=True with tractography on: exercises CustomEddy niter=1 and
    BEDPOSTX5's cut MCMC parameters (n_fibres/n_jumps/burn_in/sample_every),
    both unvalidated end-to-end yet -- see prerelease/TODO.md.
    """
    section = subject_config[DataInputList.DTI]
    section["cuda"] = "false"
    section["old_eddy_correct"] = "false"
    section["tractography"] = "true"
    synth = global_config[GlobalPrefCategoryList.SYNTH]

    wf = dti_preproc_workflow(
        "dti",
        dti_dir=make_input_dir(),
        config=section,
        synth_config=synth,
        max_cpu=MAX_CPU,
        multicore_node_limit=CoreLimit.SOFT_CAP,
        test_run=True,
    )

    config_echo = {
        "cuda": "false",
        "old_eddy_correct": "false",
        "tractography": "true",
        "multicore_node_limit": CoreLimit.SOFT_CAP.name,
        "max_cpu": MAX_CPU,
        "synth_strip": synth["strip"],
        "synth_morph": synth["morph"],
        "test_run": True,
    }
    graph_snapshot(
        wf,
        subdir=SUBDIR,
        name="test_run",
        config=config_echo,
        title="dti_preproc / test_run",
    )


def test_no_limit_eddy_uses_host_cpu_count(
    subject_config, global_config, make_input_dir
):
    """NO_LIMIT is host-dependent (``cpu_count()``), so it is asserted, not snapshotted."""
    from multiprocessing import cpu_count

    section = subject_config[DataInputList.DTI]
    section["cuda"] = "false"
    section["old_eddy_correct"] = "false"
    section["tractography"] = "false"

    wf = dti_preproc_workflow(
        "dti",
        dti_dir=make_input_dir(),
        config=section,
        synth_config=global_config[GlobalPrefCategoryList.SYNTH],
        max_cpu=MAX_CPU,
        multicore_node_limit=CoreLimit.NO_LIMIT,
    )
    eddy = wf.get_node("dti_eddy")
    assert eddy.inputs.args == "--nthr=%d" % cpu_count()
