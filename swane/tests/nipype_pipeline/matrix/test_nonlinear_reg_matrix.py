"""Settings matrix for
:func:`swane.nipype_pipeline.workflows.nonlinear_reg_workflow.nonlinear_reg_workflow`.

Non-linear atlas registration (used for the FLAT1 MNI warp and the symmetric
asymmetry-index warp). One snapshot per backend under
``snapshots/nonlinear_reg/``.

Unlike ``linear_reg_workflow``, this workflow's ``fieldcoeff_file``/
``inverse_warp`` outputs are read FSL-specifically downstream (flat1/func_map/
tractography ``ApplyWarp``, per the CP-C audit), so it resolves its engine with
``allow_ants=False`` -- it stays pinned to FSL regardless of the ``engine``
preference until those consumers are ported (Phase 2/3). The ``ants_backend``
scenario below is construction-only coverage proving that pin: with
``engine=ANTS`` configured, the built graph is still the FSL one (identical to
``fsl_backend``'s), not an ``AntsRegistration`` node -- it is NOT the
MainWorkflow default and must not be read as one.
"""

import pytest

from swane.config.config_enums import GlobalPrefCategoryList, CoreLimit
from swane.tests.nipype_pipeline.matrix.conftest import import_workflow_or_skip

nonlinear_reg_workflow = import_workflow_or_skip(
    "swane.nipype_pipeline.workflows.nonlinear_reg_workflow", "nonlinear_reg_workflow"
)

SUBDIR = "nonlinear_reg"
MAX_CPU = 4

# name -> dict(engine preference + limit_cores)
SCENARIOS = {
    "fsl_backend": dict(engine="FSL"),
    "synthmorph_backend": dict(engine="SYNTH"),
    "synthmorph_backend_limit_cores": dict(engine="SYNTH", limit_cores=True),
    # Construction-only coverage of the FSL pin (see module docstring): the
    # engine preference is ANTS, but the built graph must still be FSL's.
    "ants_backend": dict(engine="ANTS"),
}


@pytest.mark.parametrize("scenario", list(SCENARIOS), ids=list(SCENARIOS))
def test_nonlinear_reg_matrix(scenario, global_config, graph_snapshot):
    params = SCENARIOS[scenario]
    synth = global_config[GlobalPrefCategoryList.SYNTH]
    # ``morph`` is gone; pin the backend through the ``engine`` enum (``morph``
    # kept only so the snapshot header echo stays identical).
    synth["morph"] = "true" if params["engine"] == "SYNTH" else "false"
    synth["engine"] = params["engine"]
    synth["limit_cores"] = "true" if params.get("limit_cores") else "false"

    wf = nonlinear_reg_workflow(
        "sym",
        synth_config=synth,
        max_cpu=MAX_CPU,
        multicore_node_limit=CoreLimit.SOFT_CAP,
    )

    graph_snapshot(
        wf,
        subdir=SUBDIR,
        name=scenario,
        config={
            "synth_morph": synth["morph"],
            "registration_engine": synth["engine"],
            "limit_synth_cores": synth["limit_cores"],
            "max_cpu": MAX_CPU,
            "multicore_node_limit": CoreLimit.SOFT_CAP.name,
        },
        title="nonlinear_reg / %s" % scenario,
    )


TEST_RUN_SCENARIOS = {
    "fsl_backend_test_run": False,
    "synthmorph_backend_test_run": True,
}


@pytest.mark.parametrize(
    "scenario", list(TEST_RUN_SCENARIOS), ids=list(TEST_RUN_SCENARIOS)
)
def test_nonlinear_reg_matrix_test_run(scenario, global_config, graph_snapshot):
    """test_run=True on both backends: FNIRT/InvWarp strategy A (FSL) and
    SynthMorphReg steps=5 (Synth) -- this is the shared registration used by
    sym/mni1, which prerelease's default test_run=True actually builds.
    """
    synth_morph = TEST_RUN_SCENARIOS[scenario]
    synth = global_config[GlobalPrefCategoryList.SYNTH]
    synth["morph"] = "true" if synth_morph else "false"
    synth["engine"] = "SYNTH" if synth_morph else "FSL"

    wf = nonlinear_reg_workflow(
        "sym",
        synth_config=synth,
        max_cpu=MAX_CPU,
        multicore_node_limit=CoreLimit.SOFT_CAP,
        test_run=True,
    )

    graph_snapshot(
        wf,
        subdir=SUBDIR,
        name=scenario,
        config={
            "synth_morph": synth["morph"],
            "max_cpu": MAX_CPU,
            "multicore_node_limit": CoreLimit.SOFT_CAP.name,
            "test_run": True,
        },
        title="nonlinear_reg / %s" % scenario,
    )
