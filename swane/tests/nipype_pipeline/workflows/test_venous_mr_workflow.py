"""Construction tests for
:func:`swane.nipype_pipeline.workflows.venous_mr_workflow.venous_mr_workflow`.

The builder only assembles a nipype graph (instantiating interface objects
never runs the underlying tools), so the resulting node structure can be
asserted with no FSL/FreeSurfer and no DICOM data — the input directory is an
empty folder whose path is merely stored on the conversion node.
"""

import pytest

from swane.config.config_enums import GlobalPrefCategoryList, VeinDetectionMode
from swane.utils.DataInputList import DataInputList
from swane.nipype_pipeline.workflows.venous_mr_workflow import venous_mr_workflow

WF_NAME = "venous_mr"


def _node_names(workflow):
    """Return the set of node names in a (non-nested) workflow graph."""
    return {node.name for node in workflow._graph.nodes()}


def _build(subject_config, global_config, dicom_dir, second_dir=None):
    """Assemble the venous workflow from real config sections."""
    return venous_mr_workflow(
        WF_NAME,
        venous_mr_dir=dicom_dir,
        config=subject_config[DataInputList.VENOUS_MR],
        synth_config=global_config[GlobalPrefCategoryList.SYNTH],
        venous2_mr_dir=second_dir,
    )


class TestSingleSeries:
    def test_core_nodes_present(self, subject_config, global_config, make_input_dir):
        """The always-present pipeline stages are wired into the graph."""
        wf = _build(subject_config, global_config, make_input_dir())
        names = _node_names(wf)
        for expected in (
            "inputnode",
            "outputnode",
            "veins_conv",
            "veins_reOrient",
            "veins_check",
            "veins_inskull_mask",
            "veins_range",
            "veins_rescale",
        ):
            assert expected in names

    def test_single_series_splits_and_has_no_second_conversion(
        self, subject_config, global_config, make_input_dir
    ):
        """A single 4D series is split in time; no second-series nodes appear."""
        wf = _build(subject_config, global_config, make_input_dir())
        names = _node_names(wf)
        assert "veins_split" in names
        assert "veins2_conv" not in names
        assert "veins_merge" not in names

    def test_default_detection_mode_is_standard_deviation(
        self, subject_config, global_config, make_input_dir
    ):
        """The ``veins_check`` node receives the configured detection mode."""
        wf = _build(subject_config, global_config, make_input_dir())
        assert wf.get_node("veins_check").inputs.detection_mode == VeinDetectionMode.SD

    def test_detection_mode_follows_configuration(
        self, subject_config, global_config, make_input_dir
    ):
        """Changing the preference propagates to the ``veins_check`` node."""
        subject_config[DataInputList.VENOUS_MR][
            "vein_detection_mode"
        ] = VeinDetectionMode.FIRST.name
        wf = _build(subject_config, global_config, make_input_dir())
        assert (
            wf.get_node("veins_check").inputs.detection_mode == VeinDetectionMode.FIRST
        )


class TestTwoSeries:
    def test_second_series_nodes_present(
        self, subject_config, global_config, make_input_dir
    ):
        """A separate anatomic series adds a second conversion + merge, no split."""
        wf = _build(
            subject_config,
            global_config,
            make_input_dir("phase1"),
            second_dir=make_input_dir("phase2"),
        )
        names = _node_names(wf)
        assert "veins2_conv" in names
        assert "veins2_reOrient" in names
        assert "veins_merge" in names
        assert "veins_split" not in names


class TestDeskullAndRegistrationBackend:
    def test_fsl_backend_uses_bet_and_flirt(
        self, subject_config, global_config, make_input_dir
    ):
        """With Synth tools disabled the graph uses BET + FLIRT/ApplyXFM nodes."""
        global_config[GlobalPrefCategoryList.SYNTH]["strip"] = "false"
        global_config[GlobalPrefCategoryList.SYNTH]["morph"] = "false"
        wf = _build(subject_config, global_config, make_input_dir())
        names = _node_names(wf)
        assert "vein_mr_deskull_bet" in names
        assert "anat_2_ref_flirt" in names
        assert "veins_2_ref_apply_xfm" in names
        assert "vein_mr_deskull_synthstrip" not in names

    def test_synth_backend_uses_synthstrip_and_synthmorph(
        self, subject_config, global_config, make_input_dir
    ):
        """With Synth tools enabled the graph swaps in SynthStrip/SynthMorph nodes."""
        global_config[GlobalPrefCategoryList.SYNTH]["strip"] = "true"
        global_config[GlobalPrefCategoryList.SYNTH]["morph"] = "true"
        wf = _build(subject_config, global_config, make_input_dir())
        names = _node_names(wf)
        assert "vein_mr_deskull_synthstrip" in names
        assert "anat_2_ref_synthmorphreg" in names
        assert "veins_2_ref_morph_apply" in names
        assert "vein_mr_deskull_bet" not in names
