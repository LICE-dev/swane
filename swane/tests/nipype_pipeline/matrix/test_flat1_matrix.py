"""Settings matrix for
:func:`swane.nipype_pipeline.workflows.flat1_workflow.flat1_workflow`.

FLAT1 junction/extension z-score pipeline. It references packaged
``swane_supplement`` templates (rewritten to ``<SUPPLEMENT>`` in snapshots) and
an MNI template path that only needs to exist. The single branch is the
atlas-transform backend (ApplyWarp vs SynthMorphApply). Snapshots under
``snapshots/flat1/``.
"""

import pytest

from swane.config.config_enums import GlobalPrefCategoryList
from swane.tests.nipype_pipeline.matrix.conftest import import_workflow_or_skip

flat1_workflow = import_workflow_or_skip(
    "swane.nipype_pipeline.workflows.flat1_workflow", "flat1_workflow"
)

SUBDIR = "flat1"

SCENARIOS = {"fsl_backend": False, "synthmorph_backend": True}


@pytest.mark.parametrize("scenario", list(SCENARIOS), ids=list(SCENARIOS))
def test_flat1_matrix(scenario, global_config, make_file, graph_snapshot):
    synth_morph = SCENARIOS[scenario]
    synth = global_config[GlobalPrefCategoryList.SYNTH]
    synth["morph"] = "true" if synth_morph else "false"
    # flat1 is not yet ported to ANTs; the engine drives FSL/SynthMorph.
    synth["engine"] = "SYNTH" if synth_morph else "FSL"

    wf = flat1_workflow(
        "flat1",
        mni1_dir=make_file("mni1.nii.gz", "x"),
        synth_config=synth,
    )

    graph_snapshot(
        wf,
        subdir=SUBDIR,
        name=scenario,
        config={"synth_morph": synth["morph"]},
        title="flat1 / %s" % scenario,
    )


TEST_RUN_SCENARIOS = {
    "fsl_backend_test_run": False,
    "synthmorph_backend_test_run": True,
}


@pytest.mark.parametrize(
    "scenario", list(TEST_RUN_SCENARIOS), ids=list(TEST_RUN_SCENARIOS)
)
def test_flat1_matrix_test_run(scenario, global_config, make_file, graph_snapshot):
    """test_run=True on both backends: FAST gets cut iterations (-I=1 -W=5
    -O=1, unvalidated -- see prerelease/TODO.md) regardless of backend.
    """
    synth_morph = TEST_RUN_SCENARIOS[scenario]
    synth = global_config[GlobalPrefCategoryList.SYNTH]
    synth["morph"] = "true" if synth_morph else "false"
    # flat1 is not yet ported to ANTs; the engine drives FSL/SynthMorph.
    synth["engine"] = "SYNTH" if synth_morph else "FSL"

    wf = flat1_workflow(
        "flat1",
        mni1_dir=make_file("mni1.nii.gz", "x"),
        synth_config=synth,
        test_run=True,
    )

    graph_snapshot(
        wf,
        subdir=SUBDIR,
        name=scenario,
        config={"synth_morph": synth["morph"], "test_run": True},
        title="flat1 / %s" % scenario,
    )
