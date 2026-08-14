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
from swane.nipype_pipeline.workflows.flat1_workflow import flat1_workflow

SUBDIR = "flat1"

SCENARIOS = {"fsl_backend": False, "synthmorph_backend": True}


@pytest.mark.parametrize("scenario", list(SCENARIOS), ids=list(SCENARIOS))
def test_flat1_matrix(scenario, global_config, make_file, graph_snapshot):
    synth_morph = SCENARIOS[scenario]
    synth = global_config[GlobalPrefCategoryList.SYNTH]
    synth["morph"] = "true" if synth_morph else "false"

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
