"""Engine resolution for the two abstracted registration workflows.

``linear_reg_workflow`` followed the configured engine from Phase 1.
Phase 2 (CP-D/E) ported ``nonlinear_reg_workflow``'s FSL-specific consumers
(flat1, func_map, tractography) to the ANTs transform-list/composed-field
contract and lifted its FSL pin, so ``nonlinear_reg_workflow`` now follows the
configured engine too: under ANTS it composes its ordered transform list into a
single directional displacement field per direction (``*_fwd_compose`` /
``*_inv_compose``) instead of building FLIRT/FNIRT.
"""

from swane.config.config_enums import GlobalPrefCategoryList, CoreLimit
from swane.tests.nipype_pipeline.matrix.conftest import import_workflow_or_skip

linear_reg_workflow = import_workflow_or_skip(
    "swane.nipype_pipeline.workflows.linear_reg_workflow", "linear_reg_workflow"
)
nonlinear_reg_workflow = import_workflow_or_skip(
    "swane.nipype_pipeline.workflows.nonlinear_reg_workflow", "nonlinear_reg_workflow"
)


class TestLinearRegFollowsConfiguredEngine:
    def test_ants_preference_builds_ants_node(
        self, subject_config, global_config, make_input_dir
    ):
        synth = global_config[GlobalPrefCategoryList.SYNTH]
        synth["engine"] = "ANTS"

        wf = linear_reg_workflow(
            "flair3d",
            dicom_dir=make_input_dir(),
            config=None,
            synth_config=synth,
            multicore_node_limit=CoreLimit.SOFT_CAP,
        )

        assert wf.get_node("flair3d_antsreg") is not None
        assert "flair3d_flirt" not in wf.list_node_names()

    def test_fsl_preference_builds_fsl_node(
        self, subject_config, global_config, make_input_dir
    ):
        synth = global_config[GlobalPrefCategoryList.SYNTH]
        synth["engine"] = "FSL"

        wf = linear_reg_workflow(
            "flair3d",
            dicom_dir=make_input_dir(),
            config=None,
            synth_config=synth,
            multicore_node_limit=CoreLimit.SOFT_CAP,
        )

        assert wf.get_node("flair3d_flirt") is not None
        assert "flair3d_antsreg" not in wf.list_node_names()


class TestNonlinearRegFollowsConfiguredEngine:
    def test_ants_preference_builds_ants_node(self, global_config):
        """Phase 2 (CP-D/E): with the FSL pin lifted, nonlinear_reg_workflow
        follows the ANTs default -- it builds an AntsRegistration node and the
        two AntsComposeTransform nodes (one per direction) and no FLIRT/FNIRT."""
        synth = global_config[GlobalPrefCategoryList.SYNTH]
        synth["engine"] = "ANTS"

        wf = nonlinear_reg_workflow(
            "sym",
            synth_config=synth,
            multicore_node_limit=CoreLimit.SOFT_CAP,
        )

        assert wf.get_node("sym_antsreg") is not None
        assert wf.get_node("sym_fwd_compose") is not None
        assert wf.get_node("sym_inv_compose") is not None
        assert "sym_flirt" not in wf.list_node_names()
        assert "sym_fnirt" not in wf.list_node_names()

    def test_fsl_preference_builds_fsl_nodes(self, global_config):
        synth = global_config[GlobalPrefCategoryList.SYNTH]
        synth["engine"] = "FSL"

        wf = nonlinear_reg_workflow(
            "sym",
            synth_config=synth,
            multicore_node_limit=CoreLimit.SOFT_CAP,
        )

        assert wf.get_node("sym_flirt") is not None
        assert wf.get_node("sym_fnirt") is not None
