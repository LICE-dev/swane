"""Settings matrix for
:func:`swane.nipype_pipeline.workflows.nonlinear_reg_workflow.nonlinear_reg_workflow`.

Non-linear atlas registration (used for the FLAT1 MNI warp and the symmetric
asymmetry-index warp). The only branch is the backend: FSL (FLIRT + FNIRT +
InvWarp + ApplyWarp) versus SynthMorph. One snapshot per backend under
``snapshots/nonlinear_reg/``.
"""

import pytest

from swane.config.config_enums import GlobalPrefCategoryList
from swane.nipype_pipeline.workflows.nonlinear_reg_workflow import (
    nonlinear_reg_workflow,
)

SUBDIR = "nonlinear_reg"

SCENARIOS = {"fsl_backend": False, "synthmorph_backend": True}


@pytest.mark.parametrize("scenario", list(SCENARIOS), ids=list(SCENARIOS))
def test_nonlinear_reg_matrix(scenario, global_config, graph_snapshot):
    synth_morph = SCENARIOS[scenario]
    synth = global_config[GlobalPrefCategoryList.SYNTH]
    synth["morph"] = "true" if synth_morph else "false"

    wf = nonlinear_reg_workflow("sym", synth_config=synth)

    graph_snapshot(
        wf,
        subdir=SUBDIR,
        name=scenario,
        config={"synth_morph": synth["morph"]},
        title="nonlinear_reg / %s" % scenario,
    )
