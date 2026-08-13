"""Construction tests for
:func:`swane.nipype_pipeline.workflows.freesurfer_workflow.freesurfer_workflow`.

The builder selects between a SynthSeg-only graph and the multi-stage recon-all
graph, with optional hippocampal/amygdala substructure segmentation. Nodes are
instantiated but never run, so no FreeSurfer install or DICOM data is needed.
"""

from swane.config.config_enums import GlobalPrefCategoryList, FreesurferStep
from swane.nipype_pipeline.workflows.freesurfer_workflow import freesurfer_workflow


def _names(workflow):
    return {node.name for node in workflow._graph.nodes()}


def _build(global_config, step, hippo=False):
    return freesurfer_workflow(
        "freesurfer",
        step=step,
        is_hippo_amyg_labels=hippo,
        synth_config=global_config[GlobalPrefCategoryList.SYNTH],
    )


class TestFreesurferWorkflow:
    def test_disabled_step_returns_none(self, global_config):
        """The DISABLED step is a guard: the builder returns ``None``."""
        assert _build(global_config, FreesurferStep.DISABLED) is None

    def test_synthseg_step_uses_synthseg_nodes(self, global_config):
        """SYNTHSEG builds the SynthSeg + conversion + basal-ganglia ROI graph."""
        wf = _build(global_config, FreesurferStep.SYNTHSEG)
        names = _names(wf)
        assert "synth_seg" in names
        assert "synth_seg2nii" in names
        assert {"lhbgROI", "rhbgROI", "bgROI"} <= names
        assert "recon_all_recon1" not in names

    def test_autorecon_pial_builds_recon_stages_without_finalization(
        self, global_config
    ):
        """AUTORECON_PIAL runs recon1/2/pial but not the autorecon3 finalization."""
        wf = _build(global_config, FreesurferStep.AUTORECON_PIAL)
        names = _names(wf)
        assert {"recon_all_recon1", "recon_all_recon2", "recon_all_recon_pial"} <= names
        assert "reconAll" not in names

    def test_reconall_step_adds_finalization_node(self, global_config):
        """The full RECONALL step adds the autorecon3 ``reconAll`` node."""
        wf = _build(global_config, FreesurferStep.RECONALL)
        assert "reconAll" in _names(wf)

    def test_hippo_amyg_labels_add_segmentation_nodes(self, global_config):
        """Enabling hippo/amygdala labels adds SegmentHA + per-side transforms."""
        wf = _build(global_config, FreesurferStep.RECONALL, hippo=True)
        names = _names(wf)
        assert {"segment_ha", "lh_ha2ref", "rh_ha2ref"} <= names

    def test_hippo_labels_absent_when_disabled(self, global_config):
        """Without the option the SegmentHA node is not created."""
        wf = _build(global_config, FreesurferStep.RECONALL, hippo=False)
        assert "segment_ha" not in _names(wf)
