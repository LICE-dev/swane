import tempfile
from configparser import ConfigParser
from swane.config.config_enums import SliceTiming, FmriEngine
from swane.nipype_pipeline.workflows.fMRI_preproc_workflow import fMRI_preproc_workflow


class MockConfig:
    def __init__(self, engine: FmriEngine):
        self.engine = engine

    def getenum_safe(self, key):
        if key == "fmri_engine":
            return self.engine
        return None

    def getboolean_safe(self, key):
        return False


def test_fmri_preproc_nilearn_engine_nodes():
    config = MockConfig(FmriEngine.NILEARN)

    wf = fMRI_preproc_workflow(
        name="test_preproc_nilearn",
        dicom_dir=tempfile.gettempdir(),
        TR=2.0,
        slice_timing=SliceTiming.UNKNOWN,
        n_vols=100,
        del_start_vols=0,
        del_end_vols=0,
        hpcutoff=100,
        synth_config=config,
    )

    # Assert specific node classes are absent/present
    node_classes = [type(n.interface).__name__ for n in wf._get_all_nodes()]

    assert "MCFLIRT" not in node_classes
    assert "SUSAN" not in node_classes
    assert "CustomSliceTimer" not in node_classes
    assert "AntsMotionCorrection" in node_classes
    assert "NilearnSmooth" in node_classes

    # Assert exposed handles
    assert hasattr(wf, "intnorm_node")
    assert wf.intnorm_node.name == "test_preproc_nilearn_intnorm"


def test_fmri_preproc_fsl_engine_nodes():
    config = MockConfig(FmriEngine.FSL)

    wf = fMRI_preproc_workflow(
        name="test_preproc_fsl",
        dicom_dir=tempfile.gettempdir(),
        TR=2.0,
        slice_timing=SliceTiming.UNKNOWN,
        n_vols=100,
        del_start_vols=0,
        del_end_vols=0,
        hpcutoff=100,
        synth_config=config,
    )

    node_classes = [type(n.interface).__name__ for n in wf._get_all_nodes()]

    assert "MCFLIRT" in node_classes
    assert "SUSAN" in node_classes
    assert "AntsMotionCorrection" not in node_classes
    assert "NilearnSmooth" not in node_classes

    # Intnorm node should also be exposed in FSL now (as implemented)
    assert hasattr(wf, "intnorm_node")
    assert wf.intnorm_node.name == "test_preproc_fsl_intnorm"


def _build(engine, slice_timing, name="test_st"):
    return fMRI_preproc_workflow(
        name=name,
        dicom_dir=tempfile.gettempdir(),
        TR=2.0,
        slice_timing=slice_timing,
        n_vols=100,
        del_start_vols=0,
        del_end_vols=0,
        hpcutoff=100,
        synth_config=MockConfig(engine),
    )


def _consumers(wf, src_node):
    return {
        (dst.name, dst_field)
        for src, dst, data in wf._graph.edges(data=True)
        if src is src_node
        for _, dst_field in data.get("connect", [])
    }


def test_nilearn_known_slice_timing_uses_niimath_node():
    wf = _build(FmriEngine.NILEARN, SliceTiming.UP)
    node = wf.get_node("test_st_timing_correction")
    assert type(node.interface).__name__ == "NiiMathSliceTimer"
    assert node.inputs.slice_timing == SliceTiming.UP
    assert node.inputs.suffix == "_st"
    assert "CustomSliceTimer" not in [
        type(n.interface).__name__ for n in wf._get_all_nodes()
    ]
    assert _consumers(wf, node) == {
        ("test_st_meanfunc", "in_file"),
        ("test_st_maskfunc", "in_file"),
        ("test_st_medianval", "in_file"),
        ("test_st_maskfunc2", "in_file"),
    }


def test_nilearn_unknown_slice_timing_has_no_correction_node():
    wf = _build(FmriEngine.NILEARN, SliceTiming.UNKNOWN)
    assert wf.get_node("test_st_timing_correction") is None
    motion = wf.get_node("test_st_motion_correct")
    assert ("test_st_meanfunc", "in_file") in _consumers(wf, motion)


def test_fsl_known_slice_timing_keeps_custom_slice_timer():
    wf = _build(FmriEngine.FSL, SliceTiming.UP)
    node = wf.get_node("test_st_timing_correction")
    assert type(node.interface).__name__ == "CustomSliceTimer"
    classes = [type(n.interface).__name__ for n in wf._get_all_nodes()]
    assert "NiiMathSliceTimer" not in classes
