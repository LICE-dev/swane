"""Construction tests for
:func:`swane.nipype_pipeline.workflows.freesurfer_asymmetry_index_workflow.freesurfer_asymmetry_index_workflow`.

This builder takes only a name (no DICOM, no config) and expands a large
per-label graph. The test asserts the aggregation backbone and a representative
per-label node rather than the full node set.
"""

from swane.nipype_pipeline.workflows.freesurfer_asymmetry_index_workflow import (
    freesurfer_asymmetry_index_workflow,
)


def _names(workflow):
    return {node.name for node in workflow._graph.nodes()}


class TestFreesurferAsymmetryIndexWorkflow:
    def test_aggregation_backbone_present(self):
        """The four per-metric merge + sum aggregation nodes are all present."""
        wf = freesurfer_asymmetry_index_workflow("fs_ai")
        names = _names(wf)
        for metric in ("t", "p", "z", "ai"):
            assert "merge_node_%s" % metric in names
            assert "sum_masks_%s" % metric in names

    def test_per_label_nodes_are_generated(self):
        """A representative label (17, left hippocampus) yields its stat nodes."""
        wf = freesurfer_asymmetry_index_workflow("fs_ai")
        names = _names(wf)
        assert "ttest_17" in names
        assert "lh_mask_17" in names

    def test_outputs_exposed(self):
        """The workflow exposes the four asymmetry outputs on its output node."""
        wf = freesurfer_asymmetry_index_workflow("fs_ai")
        output = wf.get_node("outputnode")
        fields = set(output.inputs.copyable_trait_names())
        assert {
            "asymmetry_t",
            "asymmetry_p",
            "asymmetry_z",
            "asymmetry_ai",
        } <= fields
