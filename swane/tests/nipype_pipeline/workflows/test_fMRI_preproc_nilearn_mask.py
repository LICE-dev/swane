"""Graph tests for the functional brain mask and median used by the preprocessing.

With the NILEARN engine the dilated mask and the median for the intensity
normalisation both come from the bold brain mask (``meanfuncmask.mask_file``);
the percentile-threshold mask (``%s_getthresh`` / ``%s_threshold``) is not built.
The FSL engine keeps the percentile-threshold mask.
"""

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


def _build(engine: FmriEngine, name: str):
    return fMRI_preproc_workflow(
        name=name,
        dicom_dir="/tmp",
        TR=2.0,
        slice_timing=SliceTiming.UNKNOWN,
        n_vols=100,
        del_start_vols=0,
        del_end_vols=0,
        hpcutoff=100,
        synth_config=MockConfig(engine),
    )


def _incoming(wf, dst_node):
    conns = []
    for src, dst, data in wf._graph.edges(data=True):
        if dst is dst_node:
            for src_field, dst_field in data.get("connect", []):
                conns.append((src, src_field, dst_field))
    return conns


def _node_names(wf):
    return {n.name for n in wf._graph.nodes()}


def test_nilearn_mask_and_median_from_bold_mask():
    name = "func_nl"
    wf = _build(FmriEngine.NILEARN, name)

    names = _node_names(wf)
    assert "%s_getthresh" % name not in names
    assert "%s_threshold" % name not in names

    meanfuncmask = wf.meanfuncmask
    dilatemask = wf.get_node("%s_dilatemask" % name)
    medianval = wf.get_node("%s_medianval" % name)
    motion_correct = wf.get_node("%s_motion_correct" % name)

    assert _incoming(wf, dilatemask) == [(meanfuncmask, "mask_file", "in_file")]
    inc = _incoming(wf, medianval)
    assert (meanfuncmask, "mask_file", "mask_file") in inc
    # Median of the motion-corrected data (no slice timing on NILEARN).
    assert (motion_correct, "out_file", "in_file") in inc
    assert len(inc) == 2

    assert wf.medianval_node is medianval


def test_fsl_mask_and_median_unchanged():
    name = "func_fsl"
    wf = _build(FmriEngine.FSL, name)

    names = _node_names(wf)
    assert "%s_getthresh" % name in names
    assert "%s_threshold" % name in names

    threshold = wf.get_node("%s_threshold" % name)
    getthresh = wf.get_node("%s_getthresh" % name)
    maskfunc = wf.get_node("%s_maskfunc" % name)
    dilatemask = wf.get_node("%s_dilatemask" % name)
    medianval = wf.get_node("%s_medianval" % name)
    motion_correct = wf.get_node("%s_motion_correct" % name)

    assert _incoming(wf, dilatemask) == [(threshold, "out_file", "in_file")]
    inc = _incoming(wf, medianval)
    assert (threshold, "out_file", "mask_file") in inc
    assert (motion_correct, "out_file", "in_file") in inc
    assert len(inc) == 2

    inc_thr = _incoming(wf, threshold)
    assert (maskfunc, "out_file", "in_file") in inc_thr
    assert any(src is getthresh and df == "op_string" for src, _, df in inc_thr)

    assert wf.medianval_node is medianval
