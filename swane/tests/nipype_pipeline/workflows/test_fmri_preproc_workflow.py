"""Construction tests for
:func:`swane.nipype_pipeline.workflows.fMRI_preproc_workflow.fMRI_preproc_workflow`.

The shared fMRI preprocessing graph (volume trimming, motion correction, slice
timing, SUSAN smoothing, highpass, coregistration). It takes scalar parameters
directly, so no config, FSL execution, or DICOM data is required.
"""

from swane.config.config_enums import SliceTiming
from swane.nipype_pipeline.workflows.fMRI_preproc_workflow import fMRI_preproc_workflow


def _names(workflow):
    return {node.name for node in workflow._graph.nodes()}


def _build(dicom_dir, slice_timing=SliceTiming.UP):
    return fMRI_preproc_workflow(
        "fmri_0",
        dicom_dir=dicom_dir,
        TR=2.0,
        slice_timing=slice_timing,
        n_vols=100,
        del_start_vols=0,
        del_end_vols=0,
        hpcutoff=30,
    )


class TestFmriPreprocWorkflow:
    def test_core_preprocessing_chain(self, make_input_dir):
        """The full preprocessing chain from conversion to coregistration is wired."""
        wf = _build(make_input_dir())
        names = _names(wf)
        for expected in (
            "inputnode",
            "fmri_0_conv",
            "fmri_0_nvols",
            "fmri_0_getTR",
            "fmri_0_del_vols",
            "fmri_0_motion_correct",
            "fmri_0_timing_correction",
            "fmri_0_smooth",
            "fmri_0_highpass",
            "fmri_0_flirt_2_ref",
        ):
            assert expected in names

    def test_volume_count_and_tr_forwarded_to_nodes(self, make_input_dir):
        """The forced volume count and TR reach the FslNVols / GetNiftiTR nodes."""
        wf = _build(make_input_dir())
        assert wf.get_node("fmri_0_nvols").inputs.force_value == 100
        assert wf.get_node("fmri_0_getTR").inputs.force_value == 2.0
