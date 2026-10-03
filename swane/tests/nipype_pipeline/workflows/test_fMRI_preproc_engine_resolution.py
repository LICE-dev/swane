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
        dicom_dir="/tmp",
        TR=2.0,
        slice_timing=SliceTiming.UNKNOWN,
        n_vols=100,
        del_start_vols=0,
        del_end_vols=0,
        hpcutoff=100,
        synth_config=config
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
        dicom_dir="/tmp",
        TR=2.0,
        slice_timing=SliceTiming.UNKNOWN,
        n_vols=100,
        del_start_vols=0,
        del_end_vols=0,
        hpcutoff=100,
        synth_config=config
    )
    
    node_classes = [type(n.interface).__name__ for n in wf._get_all_nodes()]
    
    assert "MCFLIRT" in node_classes
    assert "SUSAN" in node_classes
    assert "AntsMotionCorrection" not in node_classes
    assert "NilearnSmooth" not in node_classes
    
    # Intnorm node should also be exposed in FSL now (as implemented)
    assert hasattr(wf, "intnorm_node")
    assert wf.intnorm_node.name == "test_preproc_fsl_intnorm"
