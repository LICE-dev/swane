"""Construction tests for
:func:`swane.nipype_pipeline.workflows.venous_ct_workflow.venous_ct_workflow`.

CT angiography veins pipeline. The contrast scans are handled by MapNodes over
a list of (empty) directories, and scalp removal uses the Slicer-backed
SegmentEndocranium node — its ``slicer_cmd`` only needs an existing file path.
Nothing is executed and no DICOM data is read.
"""

from swane.utils.DataInputList import DataInputList
from swane.nipype_pipeline.workflows.venous_ct_workflow import venous_ct_workflow


def _names(workflow):
    return {node.name for node in workflow._graph.nodes()}


class TestVenousCtWorkflow:
    def test_core_nodes_present(self, subject_config, make_input_dir, make_file):
        """The non-contrast, contrast, registration and rescale stages are wired."""
        wf = venous_ct_workflow(
            "venous_ct",
            venous_ct_dir=make_input_dir("noncontrast"),
            config=subject_config[DataInputList.VENOUS_CT],
            venous2_ct_dir=[make_input_dir("c1"), make_input_dir("c2")],
            slicer_path=make_file("Slicer.exe", "x"),
        )
        names = _names(wf)
        for expected in (
            "inputnode",
            "outputnode",
            "veins_ct_conv",
            "veins_ct_reOrient",
            "segment_endocranium",
            "veins_ct_flirt_2_ref",
            "veins_ct_sum",
            "veins_ct_rescale",
            "veins_flirt",
        ):
            assert expected in names

    def test_contrast_scans_use_mapnode_stages(
        self, subject_config, make_input_dir, make_file
    ):
        """The contrast scans are converted/oriented/registered via MapNodes."""
        wf = venous_ct_workflow(
            "venous_ct",
            venous_ct_dir=make_input_dir("noncontrast"),
            config=subject_config[DataInputList.VENOUS_CT],
            venous2_ct_dir=[make_input_dir("c1"), make_input_dir("c2")],
            slicer_path=make_file("Slicer.exe", "x"),
        )
        names = _names(wf)
        assert "veins_2conv" in names
        assert "veins2_ct_reOrient" in names
        assert "veins_ct_flirt_2_contrast" in names
        assert "veins_ct_subtraction" in names
