import tempfile
import pytest
from swane.config.config_enums import FmriEngine, BlockDesign
from swane.nipype_pipeline.workflows.fMRI_task_workflow import fMRI_task_workflow


class MockConfig:
    def __init__(
        self,
        engine: FmriEngine,
        block_design: BlockDesign = BlockDesign.RARA,
        slice_timing=None,
    ):
        from swane.config.config_enums import SliceTiming

        self.slice_timing = slice_timing or SliceTiming.UP
        self.engine = engine
        self.block_design = block_design
        self._dict = {}

    def getenum_safe(self, key):
        if key == "fmri_engine":
            return self.engine
        elif key == "block_design":
            return self.block_design
        elif key == "slice_timing":
            return self.slice_timing
        return None

    def getboolean_safe(self, key):
        return False

    def getfloat_safe(self, key):
        return 2.0

    def getint_safe(self, key):
        return 30

    def get_safe(self, key):
        if key in ["task_a_name", "task_b_name"]:
            return "TaskName"
        return ""

    def __getitem__(self, key):
        return self._dict.get(key, "0")


def test_fmri_task_nilearn_engine_nodes():
    config = MockConfig(FmriEngine.NILEARN, BlockDesign.RARB)

    wf = fMRI_task_workflow(
        name="test_task_nilearn",
        dicom_dir=tempfile.gettempdir(),
        config=config,
        synth_config=config,
        test_run=False,
    )

    node_classes = [type(n.interface).__name__ for n in wf._get_all_nodes()]

    # Assert specific FSL node classes are absent
    assert "Level1Design" not in node_classes
    assert "FEATModel" not in node_classes
    assert "FILMGLS" not in node_classes
    assert "SmoothEstimate" not in node_classes
    assert "Cluster" not in node_classes

    # Assert Nilearn node is present
    assert "NilearnFirstLevel" in node_classes

    # ArtifactDetect must read SPM-order params (AntsMotionCorrection writes
    # translations-then-rotations), not FSL order.
    assert wf.get_node("test_task_nilearn_art").inputs.parameter_source == "SPM"

    # Verify the outputnode has the threshold_file fields for 2 contrasts
    outputnode = wf.get_node("outputnode")
    assert hasattr(outputnode.inputs, "threshold_file_cont1_thresh1")
    assert hasattr(outputnode.inputs, "threshold_file_cont1_thresh2")
    assert hasattr(outputnode.inputs, "threshold_file_cont1_thresh3")
    assert hasattr(outputnode.inputs, "threshold_file_cont2_thresh1")
    assert hasattr(outputnode.inputs, "threshold_file_cont2_thresh2")
    assert hasattr(outputnode.inputs, "threshold_file_cont2_thresh3")


def test_fmri_task_fsl_engine_nodes():
    config = MockConfig(FmriEngine.FSL, BlockDesign.RARB)

    wf = fMRI_task_workflow(
        name="test_task_fsl",
        dicom_dir=tempfile.gettempdir(),
        config=config,
        synth_config=config,
        test_run=False,
    )

    node_classes = [type(n.interface).__name__ for n in wf._get_all_nodes()]

    # Assert FSL node classes are present
    assert "Level1Design" in node_classes
    assert "FEATModel" in node_classes
    assert "FILMGLS" in node_classes
    assert "SmoothEstimate" in node_classes
    assert "Cluster" in node_classes

    # Assert Nilearn node is absent
    assert "NilearnFirstLevel" not in node_classes

    # FSL MCFLIRT writes FSL-order motion params.
    assert wf.get_node("test_task_fsl_art").inputs.parameter_source == "FSL"


@pytest.mark.parametrize("max_cpu, budget", [(0, 1), (8, 8)])
def test_fmri_task_nilearn_glm_thread_budget(max_cpu, budget):
    config = MockConfig(FmriEngine.NILEARN, BlockDesign.RARB)
    wf = fMRI_task_workflow(
        name="test_task_nilearn",
        dicom_dir=tempfile.gettempdir(),
        config=config,
        synth_config=config,
        test_run=False,
        max_cpu=max_cpu,
    )
    glm = wf.get_node("test_task_nilearn_nilearn_glm")
    assert glm.inputs.num_threads == budget
    assert glm.n_procs == glm.inputs.num_threads
    # The task GLM reads the preprocessing high-pass.
    assert wf.get_node("test_task_nilearn_highpass") is not None


@pytest.mark.parametrize("timing, expected", [("UP", 0.5), ("UNKNOWN", 0.0)])
def test_fmri_task_nilearn_glm_slice_time_ref(timing, expected):
    from swane.config.config_enums import SliceTiming

    config = MockConfig(FmriEngine.NILEARN, BlockDesign.RARB, SliceTiming[timing])
    wf = fMRI_task_workflow(
        name="test_task_nilearn",
        dicom_dir=tempfile.gettempdir(),
        config=config,
        synth_config=config,
        test_run=False,
    )
    glm = wf.get_node("test_task_nilearn_nilearn_glm")
    assert glm.inputs.slice_time_ref == expected
    has_stc = wf.get_node("test_task_nilearn_timing_correction") is not None
    assert has_stc == (timing != "UNKNOWN")
