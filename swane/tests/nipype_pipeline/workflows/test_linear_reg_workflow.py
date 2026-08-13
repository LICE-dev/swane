"""Construction tests for
:func:`swane.nipype_pipeline.workflows.linear_reg_workflow.linear_reg_workflow`.

Exercises the branch flags (``is_partial_coverage``, ``bias_field_correction``)
that reshape the registration graph. No FSL execution or DICOM data involved.
"""

from swane.config.config_enums import GlobalPrefCategoryList
from swane.utils.DataInputList import DataInputList
from swane.nipype_pipeline.workflows.linear_reg_workflow import linear_reg_workflow


def _names(workflow):
    return {node.name for node in workflow._graph.nodes()}


def _build(subject_config, global_config, dicom_dir, **kwargs):
    return linear_reg_workflow(
        "flair",
        dicom_dir=dicom_dir,
        config=subject_config[DataInputList.FLAIR3D],
        synth_config=global_config[GlobalPrefCategoryList.SYNTH],
        **kwargs,
    )


class TestLinearRegWorkflow:
    def test_default_full_coverage(
        self, subject_config, global_config, make_input_dir
    ):
        """Full coverage deskulls the moving image and warps both versions."""
        wf = _build(subject_config, global_config, make_input_dir())
        names = _names(wf)
        for expected in (
            "flair_conv",
            "flair_reorient",
            "flair_robustfov",
            "flair_deskull_bet",
            "flair_flirt",
            "flair_apply_xfm",
            "deskulled_flair_apply_xfm",
        ):
            assert expected in names

    def test_partial_coverage_uses_external_brain_mask(
        self, subject_config, global_config, make_input_dir
    ):
        """Partial coverage skips local deskulling and masks with the input mask."""
        wf = _build(
            subject_config, global_config, make_input_dir(),
            is_partial_coverage=True,
        )
        names = _names(wf)
        assert "flair_brain_mask" in names
        assert "flair_deskull_bet" not in names
        assert "deskulled_flair_apply_xfm" not in names

    def test_bias_field_correction_adds_correction_nodes(
        self, subject_config, global_config, make_input_dir
    ):
        """Enabling bias correction inserts the N4 + re-deskull nodes."""
        wf = _build(
            subject_config, global_config, make_input_dir(),
            bias_field_correction=True,
        )
        names = _names(wf)
        assert "bias_correction" in names
        assert "corrected_deskull" in names
