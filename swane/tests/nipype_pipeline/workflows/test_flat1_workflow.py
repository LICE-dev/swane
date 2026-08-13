"""Construction tests for
:func:`swane.nipype_pipeline.workflows.flat1_workflow.flat1_workflow`.

FLAT1 junction/extension z-score pipeline. It references packaged
``swane_supplement`` template files and an MNI template path (``mni1_dir``); the
latter only needs to be an existing file. No FSL execution or DICOM involved.
"""

from swane.config.config_enums import GlobalPrefCategoryList
from swane.nipype_pipeline.workflows.flat1_workflow import flat1_workflow


def _names(workflow):
    return {node.name for node in workflow._graph.nodes()}


def _build(global_config, mni1_file):
    return flat1_workflow(
        "flat1",
        mni1_dir=mni1_file,
        synth_config=global_config[GlobalPrefCategoryList.SYNTH],
    )


class TestFlat1Workflow:
    def test_core_nodes_present(self, global_config, make_file):
        """The FAST segmentation, junction and extension z-score stages are wired."""
        wf = _build(global_config, make_file("mni1.nii.gz", "x"))
        names = _names(wf)
        for expected in (
            "inputnode",
            "outputnode",
            "flat1_fast",
            "fast_segment_split",
            "flat1_flairDIVref",
            "flat1_binaryFLAIR",
            "flat1_junctionz",
            "flat1_image_extensionz",
        ):
            assert expected in names

    def test_fsl_backend_uses_apply_warp(self, global_config, make_file):
        """With Synth disabled the atlas transforms use ApplyWarp nodes."""
        global_config[GlobalPrefCategoryList.SYNTH]["morph"] = "false"
        wf = _build(global_config, make_file("mni1.nii.gz", "x"))
        names = _names(wf)
        assert "extension_z_2_ref_apply_warp" in names
        assert "flair_2_mni1_apply_warp" in names

    def test_synth_backend_uses_morph_apply(self, global_config, make_file):
        """With Synth enabled the atlas transforms use SynthMorphApply nodes."""
        global_config[GlobalPrefCategoryList.SYNTH]["morph"] = "true"
        wf = _build(global_config, make_file("mni1.nii.gz", "x"))
        names = _names(wf)
        assert "extension_z_2_ref_morph_apply" in names
        assert "extension_z_2_ref_apply_warp" not in names
