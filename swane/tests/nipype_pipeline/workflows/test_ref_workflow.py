"""Construction tests for
:func:`swane.nipype_pipeline.workflows.ref_workflow.ref_workflow`.

Builds the T13D reference pipeline graph (conversion, neck crop, FOV crop,
scalp removal, N4 bias correction). No FSL/FreeSurfer execution and no DICOM
data are involved.
"""

from swane.config.config_enums import GlobalPrefCategoryList
from swane.utils.DataInputList import DataInputList
from swane.nipype_pipeline.workflows.ref_workflow import ref_workflow


def _names(workflow):
    return {node.name for node in workflow._graph.nodes()}


def _build(subject_config, global_config, dicom_dir):
    return ref_workflow(
        "ref",
        dicom_dir=dicom_dir,
        config=subject_config[DataInputList.T13D],
        synth_config=global_config[GlobalPrefCategoryList.SYNTH],
    )


class TestRefWorkflow:
    def test_core_nodes_present(self, subject_config, global_config, make_input_dir):
        """Conversion, orientation, crops and bias correction are all wired."""
        wf = _build(subject_config, global_config, make_input_dir())
        names = _names(wf)
        for expected in (
            "outputnode",
            "ref_conv",
            "ref_reOrient",
            "ref_robustfov",
            "ref_reScale",
            "ref_bias_correction",
            "ref_corrected_deskull",
        ):
            assert expected in names

    def test_fsl_backend_uses_bet(self, subject_config, global_config, make_input_dir):
        """With SynthStrip disabled the scalp-removal node is BET-based."""
        global_config[GlobalPrefCategoryList.SYNTH]["strip"] = "false"
        wf = _build(subject_config, global_config, make_input_dir())
        names = _names(wf)
        assert "ref_deskull_biased_bet" in names
        assert "ref_deskull_biased_synthstrip" not in names

    def test_synth_backend_uses_synthstrip(
        self, subject_config, global_config, make_input_dir
    ):
        """With SynthStrip enabled the scalp-removal node is SynthStrip-based."""
        global_config[GlobalPrefCategoryList.SYNTH]["strip"] = "true"
        wf = _build(subject_config, global_config, make_input_dir())
        names = _names(wf)
        assert "ref_deskull_biased_synthstrip" in names
        assert "ref_deskull_biased_bet" not in names
