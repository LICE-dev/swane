"""Group D / Task D1: engine resolution for the two abstracted registration
workflows.

Per the CP-C call-site audit
(``docs/superpowers/specs/2026-08-24-ants-phase1-callsite-audit.md``),
``linear_reg_workflow`` has no transform-field consumer and is safe to follow
the configured engine (ANTs by default in Phase 1). ``nonlinear_reg_workflow``
feeds FSL-specific ``ApplyWarp`` consumers (flat1, func_map, tractography) and
must stay pinned to FSL until those consumers are ported (Phase 2/3) --
regardless of what the ``engine`` preference says.
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


class TestNonlinearRegStaysPinnedToFsl:
    def test_ants_preference_still_builds_fsl_nodes(self, global_config):
        """The Phase-1 scope decision: nonlinear_reg_workflow must NOT follow
        the ANTs default -- its warp outputs are read FSL-specifically
        downstream (flat1/func_map/tractography ApplyWarp nodes)."""
        synth = global_config[GlobalPrefCategoryList.SYNTH]
        synth["engine"] = "ANTS"

        wf = nonlinear_reg_workflow(
            "sym",
            synth_config=synth,
            multicore_node_limit=CoreLimit.SOFT_CAP,
        )

        assert wf.get_node("sym_flirt") is not None
        assert wf.get_node("sym_fnirt") is not None
        assert "sym_antsreg" not in wf.list_node_names()

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
