"""Construction tests for
:func:`swane.nipype_pipeline.workflows.seeg_ct_workflow.seeg_ct_workflow`.

Post-implant CT electrode-extraction pipeline. Built from an empty input
directory and a config section; nothing is executed and no DICOM is read.
"""

from swane.utils.DataInputList import DataInputList
from swane.nipype_pipeline.workflows.seeg_ct_workflow import seeg_ct_workflow


def _names(workflow):
    return {node.name for node in workflow._graph.nodes()}


class TestSeegCtWorkflow:
    def test_core_nodes_present(self, subject_config, make_input_dir):
        """Conversion, weighting, registration, masking and combination are wired."""
        wf = seeg_ct_workflow(
            "seeg_ct",
            seeg_ct_dir=make_input_dir(),
            config=subject_config[DataInputList.SEEG_CT],
        )
        names = _names(wf)
        for expected in (
            "inputnode",
            "outputnode",
            "seeg_ct_conv",
            "seeg_ct_reOrient",
            "electrodes_weight_bin",
            "seeg_ct_2_ref_flirt",
            "seeg_electrodes_thr_ref",
            "seeg_no_electrodes_thr_ref",
            "ref_brain_erode",
            "ref_brain_dilate",
            "seeg_electodes",
        ):
            assert expected in names

    def test_electrode_output_exposed(self, subject_config, make_input_dir):
        """The combined electrodes+brain volume is exposed on the output node."""
        wf = seeg_ct_workflow(
            "seeg_ct",
            seeg_ct_dir=make_input_dir(),
            config=subject_config[DataInputList.SEEG_CT],
        )
        output = wf.get_node("outputnode")
        assert "electrodes" in set(output.inputs.copyable_trait_names())
