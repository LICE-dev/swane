"""Construction tests for
:func:`swane.nipype_pipeline.workflows.nonlinear_reg_workflow.nonlinear_reg_workflow`.

This builder takes no DICOM directory at all — only a Synth config that selects
the FSL (FLIRT+FNIRT+InvWarp) or SynthMorph registration backend.
"""

from swane.config.config_enums import GlobalPrefCategoryList
from swane.nipype_pipeline.workflows.nonlinear_reg_workflow import (
    nonlinear_reg_workflow,
)


def _names(workflow):
    return {node.name for node in workflow._graph.nodes()}


class TestNonlinearRegWorkflow:
    def test_fsl_backend_builds_flirt_fnirt_invwarp(self, global_config):
        """With Synth disabled the graph is FLIRT + FNIRT + InvWarp + ApplyWarp."""
        global_config[GlobalPrefCategoryList.SYNTH]["morph"] = "false"
        wf = nonlinear_reg_workflow(
            "sym", synth_config=global_config[GlobalPrefCategoryList.SYNTH]
        )
        names = _names(wf)
        for expected in ("sym_flirt", "sym_fnirt", "sym_invwarp", "sym_apply_warp"):
            assert expected in names

    def test_synth_backend_builds_synthmorph(self, global_config):
        """With Synth enabled the graph collapses to SynthMorphReg + apply."""
        global_config[GlobalPrefCategoryList.SYNTH]["morph"] = "true"
        wf = nonlinear_reg_workflow(
            "sym", synth_config=global_config[GlobalPrefCategoryList.SYNTH]
        )
        names = _names(wf)
        assert "sym_synthmorphreg" in names
        assert "sym_morph_apply" in names
        assert "sym_flirt" not in names
