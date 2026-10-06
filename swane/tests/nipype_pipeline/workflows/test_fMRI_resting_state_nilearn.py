"""Graph tests for the Python (nilearn/scikit-learn) resting-state builder.

Built with real ConfigManager sections (fixtures from
``swane/tests/nipype_pipeline/conftest.py``) for AROMA on and off, registration
engine ANTS, FSL and SYNTH (EPI folds SYNTH to ANTS), and ``ic_dim`` 0 / 20.
Only the graph is built; no node is executed, except the transform-list Merge
nodes and the small Function helpers, which are run in ``tmp_path``.
"""

import pytest
from nipype.utils.functions import getsource

from swane.config.config_enums import GlobalPrefCategoryList
from swane.utils.DataInputList import DataInputList
from swane.nipype_pipeline.workflows.fMRI_resting_state_workflow import (
    fMRI_resting_state_workflow,
)
from swane.nipype_pipeline.workflows import fMRI_resting_state_nilearn as nl

NAME = "fmri_rs"

AROMA_NODE_NAMES = [
    "preproc_ica_auto_dim",
    "preproc_ica_canica",
    "preproc_ica_dual_reg",
    "preproc_ica_ggm",
    "preproc_ica_output",
    "feature_spatial_prep",
    "feature_spatial",
    "feature_time_series",
    "feature_frequency",
    "aroma_classification",
    "nonaggr_denoising",
    "nonaggr_denoising_unsmoothed",
    "count_motion_ics",
]


def _build(
    subject_config,
    global_config,
    make_input_dir,
    aroma=True,
    reg="ANTS",
    ic_dim=0,
    segmentation="ANTS",
    spatial_z_thr="1.95",
    max_cpu=0,
):
    section = subject_config[DataInputList.FMRI_RS]
    section["aroma"] = "true" if aroma else "false"
    section["ic_dim"] = str(ic_dim)
    section["spatial_z_thr"] = spatial_z_thr
    synth = global_config[GlobalPrefCategoryList.SYNTH]
    synth["engine"] = reg
    synth["fmri_engine"] = "NILEARN"
    synth["segmentation_engine"] = segmentation
    return fMRI_resting_state_workflow(
        NAME,
        dicom_dir=make_input_dir(),
        config=section,
        synth_config=synth,
        max_cpu=max_cpu,
    )


def _incoming(wf, dst_node):
    conns = []
    for src, dst, data in wf._graph.edges(data=True):
        if dst is dst_node:
            for src_field, dst_field in data.get("connect", []):
                conns.append((src, src_field, dst_field))
    return conns


def _source(wf, dst_node, dst_field):
    found = [(src, sf) for src, sf, df in _incoming(wf, dst_node) if df == dst_field]
    assert len(found) == 1, "%s.%s has %d sources" % (
        dst_node.name,
        dst_field,
        len(found),
    )
    return found[0]


def _names(wf):
    return {n.name for n in wf._graph.nodes()}


def _node(wf, name):
    node = wf.get_node(name)
    assert node is not None, "missing node %s" % name
    return node


def _iface(node):
    return type(node.interface).__name__


REGS = ["ANTS", "FSL"]


# ---------------------------------------------------------------------------
# AROMA pass
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("reg", REGS)
def test_aroma_pass_on_unfiltered_intnorm(
    subject_config, global_config, make_input_dir, reg
):
    wf = _build(subject_config, global_config, make_input_dir, True, reg)
    intnorm = _node(wf, "%s_intnorm" % NAME)
    mc = _node(wf, "%s_motion_correct" % NAME)
    tight = wf.meanfuncmask
    dil = _node(wf, "%s_dilatemask" % NAME)

    auto_dim = _node(wf, "preproc_ica_auto_dim")
    assert _source(wf, auto_dim, "in_file") == (mc, "out_file")
    assert _source(wf, auto_dim, "mask_file") == (tight, "mask_file")

    canica = _node(wf, "preproc_ica_canica")
    assert _source(wf, canica, "preproc_file") == (intnorm, "out_file")
    assert _source(wf, canica, "mask_file") == (tight, "mask_file")
    assert _source(wf, canica, "n_components") == (auto_dim, "n_components")

    dual_reg = _node(wf, "preproc_ica_dual_reg")
    assert _source(wf, dual_reg, "preproc_file") == (intnorm, "out_file")
    assert dual_reg.inputs.centre_maps is False
    assert dual_reg.inputs.t_to_z is False

    ggm = _node(wf, "preproc_ica_ggm")
    assert ggm.inputs.mm_thresh == 0.5

    # Motion feature from the motion-correction parameters.
    assert (mc, "par_file", "mc") in _incoming(wf, _node(wf, "feature_time_series"))

    out = _node(wf, "preproc_ica_output")
    aroma = _node(wf, "aroma_classification")
    twin = _node(wf, "%s_intnorm_unsmoothed" % NAME)
    for den_name, src in (
        ("nonaggr_denoising", intnorm),
        ("nonaggr_denoising_unsmoothed", twin),
    ):
        den = _node(wf, den_name)
        assert _iface(den) == "IcaDenoise"
        assert den.inputs.aggressive is False
        assert _source(wf, den, "in_file") == (src, "out_file")
        assert _source(wf, den, "mask_file") == (dil, "out_file")
        assert _source(wf, den, "ic_mix") == (out, "mel_mix")
        assert _source(wf, den, "motion_ics") == (aroma, "motion_ics")

    assert "merge_node" not in _names(wf)


def test_mm_thresh_ignores_melodic_thr(subject_config, global_config, make_input_dir):
    subject_config[DataInputList.FMRI_RS]["melodic_thr"] = "0.9"
    wf = _build(subject_config, global_config, make_input_dir, True, "ANTS")
    assert _node(wf, "preproc_ica_ggm").inputs.mm_thresh == 0.5


# ---------------------------------------------------------------------------
# Unsmoothed twin
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("aroma", [True, False])
def test_unsmoothed_twin(subject_config, global_config, make_input_dir, aroma):
    wf = _build(subject_config, global_config, make_input_dir, aroma, "ANTS")
    mc = _node(wf, "%s_motion_correct" % NAME)
    dil = _node(wf, "%s_dilatemask" % NAME)
    median = _node(wf, "%s_medianval" % NAME)
    masked = _node(wf, "%s_maskfunc_unsmoothed" % NAME)
    twin = _node(wf, "%s_intnorm_unsmoothed" % NAME)

    assert masked.inputs.op_string == "-mas"
    assert _source(wf, masked, "in_file") == (mc, "out_file")
    assert _source(wf, masked, "in_file2") == (dil, "out_file")
    assert _source(wf, twin, "in_file") == (masked, "out_file")
    src, field = _source(wf, twin, "op_string")
    assert src is median
    # Same scale as the smoothed intnorm: the same function on the same median.
    intnorm_op = _source(wf, _node(wf, "%s_intnorm" % NAME), "op_string")
    assert (src, field) == intnorm_op

    nuisance = _node(wf, "nuisance_regression")
    expected = (
        (_node(wf, "nonaggr_denoising_unsmoothed"), "denoised_file")
        if aroma
        else (twin, "out_file")
    )
    assert _source(wf, nuisance, "twin_file") == expected


# ---------------------------------------------------------------------------
# ROIs, nuisance regression and high-pass
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("segmentation", ["ANTS", "FSL"])
def test_tissue_pve_from_shared_segmentation(
    subject_config, global_config, make_input_dir, segmentation
):
    """The subject tissue posteriors come from the shared reference
    segmentation (inputnode.tissue_pve) for every segmentation engine: the
    workflow builds no segmentation node of its own."""
    wf = _build(
        subject_config,
        global_config,
        make_input_dir,
        True,
        "ANTS",
        segmentation=segmentation,
    )
    assert "t1_segmentation" not in _names(wf)
    ifaces = {_iface(n) for n in wf._graph.nodes()}
    assert "AntsAtropos" not in ifaces and "FAST" not in ifaces
    inputnode = _node(wf, "inputnode")
    assert "tissue_pve" in inputnode.interface._fields
    for tissue, index in (("csf", 0), ("wm", 2)):
        thr = _node(wf, "%s_subject_thr" % tissue)
        assert thr.inputs.op_string == "-thr 0.95 -bin"
        src, field = _source(wf, thr, "in_file")
        assert src is inputnode
        assert field[0] == "tissue_pve"
        assert tuple(field[2]) == (index,)


@pytest.mark.parametrize("aroma", [True, False])
@pytest.mark.parametrize("reg", REGS)
def test_nuisance_and_highpass(
    subject_config, global_config, make_input_dir, aroma, reg
):
    from swane.nipype_pipeline.workflows.fMRI_preproc_workflow import (
        highpass_op_string,
    )

    wf = _build(subject_config, global_config, make_input_dir, aroma, reg)
    nuisance = _node(wf, "nuisance_regression")
    dil = _node(wf, "%s_dilatemask" % NAME)
    tight = wf.meanfuncmask
    mc = _node(wf, "%s_motion_correct" % NAME)

    smoothed = (
        (_node(wf, "nonaggr_denoising"), "denoised_file")
        if aroma
        else (_node(wf, "%s_intnorm" % NAME), "out_file")
    )
    assert _source(wf, nuisance, "in_file") == smoothed
    assert _source(wf, nuisance, "mask_file") == (dil, "out_file")
    assert _source(wf, nuisance, "wm_roi_file") == (_node(wf, "wm_roi"), "out_file")
    assert _source(wf, nuisance, "csf_roi_file") == (
        _node(wf, "csf_roi"),
        "out_file",
    )
    if aroma:
        assert nuisance.inputs.motion24 is False
        assert "par_file" not in {df for _, _, df in _incoming(wf, nuisance)}
    else:
        assert nuisance.inputs.motion24 is True
        assert _source(wf, nuisance, "par_file") == (mc, "par_file")

    for tissue in ("csf", "wm"):
        prior_thr = _node(wf, "%s_prior_thr_bin" % tissue)
        assert _iface(prior_thr) == "ImageMaths"
        assert prior_thr.inputs.op_string == "-thr 0.5 -bin -mas"
        assert prior_thr.inputs.out_data_type == "char"
        prior_src, _ = _source(wf, prior_thr, "in_file")
        assert prior_src.name.startswith("%s_prior_2_func" % tissue)
        assert _source(wf, prior_thr, "in_file2") == (tight, "mask_file")

        roi = _node(wf, "%s_roi" % tissue)
        assert _iface(roi) == "ImageMaths"
        assert roi.inputs.op_string == "-thr 0.5 -bin -mas"
        assert roi.inputs.out_data_type == "char"
        subj_src, _ = _source(wf, roi, "in_file")
        assert subj_src.name.startswith("%s_subject_2_func" % tissue)
        assert _source(wf, roi, "in_file2") == (prior_thr, "out_file")

    mean_clean = _node(wf, "meanfunc_clean")
    assert mean_clean.inputs.op_string == "-Tmean"
    assert _source(wf, mean_clean, "in_file") == (nuisance, "out_file")
    hp = _node(wf, "highpass_clean")
    assert _source(wf, hp, "in_file") == (nuisance, "out_file")
    op_src, op_field = _source(wf, hp, "op_string")
    assert op_field[0] == "out"
    assert op_field[1] == getsource(highpass_op_string)
    assert tuple(op_field[2]) == (100,)
    assert sorted((s.name, sf, df) for s, sf, df in _incoming(wf, op_src)) == sorted(
        [
            ("%s_getTR" % NAME, "TR", "in1"),
            ("meanfunc_clean", "out_file", "in2"),
        ]
    )


# ---------------------------------------------------------------------------
# Inverse transforms for the ROIs (MNI -> ref -> func, ref -> func)
# ---------------------------------------------------------------------------
def test_ants_inverse_transform_order(
    subject_config, global_config, make_input_dir, tmp_path, monkeypatch
):
    wf = _build(subject_config, global_config, make_input_dir, False, "ANTS")
    func_2_ref = _node(wf, "%s_2_ref_antsreg" % NAME)
    ref_2_mni = _node(wf, "ref_2_mni_antsreg")
    meanfunc2 = _node(wf, "%s_meanfunc2" % NAME)

    for tissue in ("csf", "wm"):
        subj = _node(wf, "%s_subject_2_func_ants_apply" % tissue)
        assert subj.inputs.interpolator == "linear"
        assert _source(wf, subj, "transformlist") == (func_2_ref, "inv_transforms")
        assert _source(wf, subj, "which_to_invert") == (
            func_2_ref,
            "inv_which_to_invert",
        )
        assert _source(wf, subj, "reference_image") == (meanfunc2, "out_file")

        prior = _node(wf, "%s_prior_2_func_ants_apply" % tissue)
        assert prior.inputs.interpolator == "linear"
        assert _source(wf, prior, "reference_image") == (meanfunc2, "out_file")
        tl_merge, _ = _source(wf, prior, "transformlist")
        wi_merge, _ = _source(wf, prior, "which_to_invert")
        # Output (func) -> input (MNI): func<-ref first, ref<-MNI second.
        assert sorted(
            (s.name, sf, df) for s, sf, df in _incoming(wf, tl_merge)
        ) == sorted(
            [
                (func_2_ref.name, "inv_transforms", "in1"),
                (ref_2_mni.name, "inv_transforms", "in2"),
            ]
        )
        assert sorted(
            (s.name, sf, df) for s, sf, df in _incoming(wf, wi_merge)
        ) == sorted(
            [
                (func_2_ref.name, "inv_which_to_invert", "in1"),
                (ref_2_mni.name, "inv_which_to_invert", "in2"),
            ]
        )

    # Run the two ravel Merges with the lists AntsRegistration publishes
    # (rigid func->ref: [affine]; SyN ref->MNI: [affine, inverse warp]) and
    # check the list and flags that reach the apply node.
    monkeypatch.chdir(tmp_path)
    tl_merge, _ = _source(wf, _node(wf, "csf_prior_2_func_ants_apply"), "transformlist")
    wi_merge, _ = _source(
        wf, _node(wf, "csf_prior_2_func_ants_apply"), "which_to_invert"
    )
    tl = tl_merge.interface
    tl.inputs.in1 = ["func2ref_0GenericAffine.mat"]
    tl.inputs.in2 = ["ref2mni_0GenericAffine.mat", "ref2mni_1InverseWarp.nii.gz"]
    wi = wi_merge.interface
    wi.inputs.in1 = [True]
    wi.inputs.in2 = [True, False]
    assert tl.run().outputs.out == [
        "func2ref_0GenericAffine.mat",
        "ref2mni_0GenericAffine.mat",
        "ref2mni_1InverseWarp.nii.gz",
    ]
    assert wi.run().outputs.out == [True, True, False]


def test_fsl_inverse_transform_chain(subject_config, global_config, make_input_dir):
    wf = _build(subject_config, global_config, make_input_dir, False, "FSL")
    inputnode = _node(wf, "inputnode")
    flirt = _node(wf, "%s_2_ref_flirt" % NAME)
    fnirt = _node(wf, "ref_2_mni_fnirt")
    meanfunc2 = _node(wf, "%s_meanfunc2" % NAME)

    inv_xfm = _node(wf, "%s_2_ref_invwarp" % NAME)
    assert _iface(inv_xfm) == "ConvertXFM"
    assert inv_xfm.inputs.invert_xfm is True
    assert _source(wf, inv_xfm, "in_file") == (flirt, "out_matrix_file")

    inv_warp = _node(wf, "ref_2_mni_invwarp")
    assert _iface(inv_warp) == "InvWarp"
    assert _source(wf, inv_warp, "warp") == (fnirt, "fieldcoeff_file")
    assert _source(wf, inv_warp, "reference") == (inputnode, "reference_brain")

    mni_2_func = _node(wf, "mni_2_func_warp")
    assert _iface(mni_2_func) == "ConvertWarp"
    assert _source(wf, mni_2_func, "warp1") == (inv_warp, "inverse_warp")
    assert _source(wf, mni_2_func, "postmat") == (inv_xfm, "out_file")
    assert _source(wf, mni_2_func, "reference") == (meanfunc2, "out_file")

    for tissue in ("csf", "wm"):
        subj = _node(wf, "%s_subject_2_func_apply_xfm" % tissue)
        assert _iface(subj) == "ApplyXFM"
        assert _source(wf, subj, "in_matrix_file") == (inv_xfm, "out_file")
        assert _source(wf, subj, "reference") == (meanfunc2, "out_file")
        assert subj.inputs.datatype == "float"
        prior = _node(wf, "%s_prior_2_func_apply_warp" % tissue)
        assert _iface(prior) == "ApplyWarp"
        assert _source(wf, prior, "field_file") == (mni_2_func, "out_file")
        assert _source(wf, prior, "ref_file") == (meanfunc2, "out_file")
        assert prior.inputs.datatype == "float"
    assert "AntsApplyTransforms" not in [_iface(n) for n in wf._graph.nodes()]


def test_synth_uses_ants_path(subject_config, global_config, make_input_dir):
    wf = _build(subject_config, global_config, make_input_dir, False, "SYNTH")
    names = _names(wf)
    assert {
        "csf_prior_2_func_ants_apply",
        "wm_prior_2_func_ants_apply",
        "csf_subject_2_func_ants_apply",
        "wm_subject_2_func_ants_apply",
    } <= names
    ifaces = [_iface(n) for n in wf._graph.nodes()]
    for absent in ("ConvertWarp", "InvWarp", "ConvertXFM", "SynthMorphReg"):
        assert absent not in ifaces


def test_priors(subject_config, global_config, make_input_dir):
    from ica_aroma_py import aroma_mask_csf

    wf = _build(subject_config, global_config, make_input_dir, False, "ANTS")
    assert _node(wf, "csf_prior_2_func_ants_apply").inputs.input_image == (
        aroma_mask_csf
    )
    wm_prior = _node(wf, "wm_prior_mni")
    assert _source(wf, _node(wf, "wm_prior_2_func_ants_apply"), "input_image") == (
        wm_prior,
        "prior_file",
    )
    assert "nlin6_wm_prior" in wm_prior.interface.inputs.function_str


# ---------------------------------------------------------------------------
# Final ICA
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("aroma", [True, False])
@pytest.mark.parametrize("reg", REGS)
def test_final_ica(subject_config, global_config, make_input_dir, aroma, reg):
    wf = _build(
        subject_config,
        global_config,
        make_input_dir,
        aroma,
        reg,
        spatial_z_thr="2.3",
    )
    names = _names(wf)
    tight = wf.meanfuncmask
    dil = _node(wf, "%s_dilatemask" % NAME)
    nuisance = _node(wf, "nuisance_regression")
    hp = _node(wf, "highpass_clean")

    auto_dim = _node(wf, "ica_auto_dim")
    assert _source(wf, auto_dim, "in_file") == (nuisance, "twin_out_file")
    assert _source(wf, auto_dim, "mask_file") == (tight, "mask_file")
    n_removed = _node(wf, "n_removed")
    assert _source(wf, auto_dim, "n_removed") == (n_removed, "n_removed")
    assert _source(wf, n_removed, "rank") == (nuisance, "rank")

    ica = _node(wf, "ica_fastica_icasso")
    assert _iface(ica) == "FastIcaIcasso"
    assert _source(wf, ica, "in_file") == (hp, "out_file")
    assert _source(wf, ica, "mask_file") == (dil, "out_file")
    assert _source(wf, ica, "n_components") == (auto_dim, "n_components")

    dual_reg = _node(wf, "ica_dual_reg")
    assert dual_reg.inputs.centre_maps is True
    assert dual_reg.inputs.t_to_z is True
    assert _source(wf, dual_reg, "preproc_file") == (hp, "out_file")
    assert _source(wf, dual_reg, "mask_file") == (dil, "out_file")
    assert _source(wf, dual_reg, "components_file") == (ica, "components_file")
    dof = _node(wf, "dof")
    assert _iface(dof) == "Function"
    assert _source(wf, dual_reg, "dof") == (dof, "dof")
    assert _source(wf, dof, "in_file") == (hp, "out_file")
    assert _source(wf, dof, "TR") == (_node(wf, "%s_getTR" % NAME), "TR")
    assert _source(wf, dof, "rank") == (nuisance, "rank")

    if aroma:
        count = _node(wf, "count_motion_ics")
        assert _source(wf, count, "motion_ics") == (
            _node(wf, "aroma_classification"),
            "motion_ics",
        )
        assert _source(wf, dof, "n_aroma") == (count, "n_aroma")
        assert _source(wf, n_removed, "n_aroma") == (count, "n_aroma")
    else:
        for absent in AROMA_NODE_NAMES:
            assert absent not in names
        assert dof.inputs.n_aroma == 0
        assert n_removed.inputs.n_aroma == 0

    cluster = _node(wf, "ica_cluster_extent")
    assert _source(wf, cluster, "residual_file") == (dual_reg, "residual_file")
    assert _source(wf, cluster, "mask_file") == (dil, "out_file")
    spatialz = _node(wf, "ica_spatialz")
    assert spatialz.inputs.z_thr == 2.3
    # k must come from null fields thresholded at the same |z| as the maps
    assert cluster.inputs.z_thr == 2.3
    assert _source(wf, spatialz, "zstat_file") == (dual_reg, "zstat_file")
    assert _source(wf, spatialz, "mask_file") == (dil, "out_file")
    assert _source(wf, spatialz, "min_cluster_voxels") == (
        cluster,
        "min_cluster_voxels",
    )

    ica_output = _node(wf, "ica_output")
    assert _source(wf, ica_output, "ic_mix") == (dual_reg, "ic_mix")
    assert _source(wf, ica_output, "thresh_zstat_files") == (
        spatialz,
        "thresh_zstat_files",
    )
    for absent in ("ica_canica", "ica_ggm", "ica_auto_dim_mc"):
        assert absent not in names


def test_fixed_ic_dim(subject_config, global_config, make_input_dir):
    wf = _build(subject_config, global_config, make_input_dir, True, "ANTS", ic_dim=20)
    ica = _node(wf, "ica_fastica_icasso")
    assert ica.inputs.n_components == 20
    assert "n_components" not in {df for _, _, df in _incoming(wf, ica)}
    assert "ica_auto_dim" not in _names(wf)
    assert "n_removed" not in _names(wf)
    # The AROMA pass keeps its own automatic estimate.
    assert "preproc_ica_auto_dim" in _names(wf)


# Nodes whose BLAS work gets the per-node budget, and nodes whose work is
# (almost) single-threaded, which are pinned to one thread.
BUDGET_NODES = [
    "preproc_ica_auto_dim",
    "preproc_ica_canica",
    "preproc_ica_dual_reg",
    "nonaggr_denoising",
    "nonaggr_denoising_unsmoothed",
    "nuisance_regression",
    "ica_auto_dim",
    "ica_fastica_icasso",
    "ica_dual_reg",
]
SINGLE_THREAD_NODES = ["preproc_ica_ggm", "ica_cluster_extent"]


@pytest.mark.parametrize("max_cpu, budget", [(0, 1), (8, 8)])
def test_thread_budget(subject_config, global_config, make_input_dir, max_cpu, budget):
    wf = _build(
        subject_config,
        global_config,
        make_input_dir,
        True,
        "ANTS",
        max_cpu=max_cpu,
    )
    for name in BUDGET_NODES:
        node = _node(wf, name)
        assert node.inputs.num_threads == budget, name
        # Nipype derives the reservation from num_threads.
        assert node.n_procs == node.inputs.num_threads, name
    for name in SINGLE_THREAD_NODES:
        node = _node(wf, name)
        assert node.inputs.num_threads == 1, name
        assert node.n_procs == node.inputs.num_threads, name


# Nodes that load whole 4D series in Python, and the RAM estimator that sizes
# their reservation from the series at run time.
RAM_ESTIMATED_NODES = {
    "preproc_ica_auto_dim": "NilearnAutoDimRamEstimator",
    "preproc_ica_canica": "NilearnCanICARamEstimator",
    "preproc_ica_dual_reg": "DualRegressionRamEstimator",
    "nuisance_regression": "NuisanceRegressionRamEstimator",
    "ica_auto_dim": "NilearnAutoDimRamEstimator",
    "ica_fastica_icasso": "FastIcaIcassoRamEstimator",
    "ica_dual_reg": "DualRegressionRamEstimator",
    "ica_cluster_extent": "ClusterExtentMCRamEstimator",
}


def test_residuals_written_only_by_the_final_dual_regression(
    subject_config, global_config, make_input_dir
):
    """The AROMA-pass residuals have no consumer; the final-pass residuals feed
    the cluster-extent estimate."""
    wf = _build(subject_config, global_config, make_input_dir, True, "ANTS")
    assert _node(wf, "preproc_ica_dual_reg").inputs.write_residuals is False
    final = _node(wf, "ica_dual_reg")
    assert final.inputs.write_residuals is True
    cluster = _node(wf, "ica_cluster_extent")
    assert _source(wf, cluster, "residual_file") == (final, "residual_file")


def test_ram_reservation(subject_config, global_config, make_input_dir):
    from swane.nipype_pipeline.interfaces import ram_estimators

    wf = _build(subject_config, global_config, make_input_dir, True, "ANTS")
    for name, cls_name in RAM_ESTIMATED_NODES.items():
        node = _node(wf, name)
        cls = getattr(ram_estimators, cls_name)
        assert isinstance(getattr(node, "ram_estimator", None), cls), name
        # Static reservation used only when the estimate cannot run.
        assert node.mem_gb == cls.STATIC_FALLBACK_GB, name


@pytest.mark.parametrize("aroma", [True, False])
def test_preproc_highpass_not_built(
    subject_config, global_config, make_input_dir, aroma
):
    """The resting chain high-passes after the nuisance regression: the
    preprocessing high-pass (and its mean/TR setup) would have no consumer."""
    wf = _build(subject_config, global_config, make_input_dir, aroma, "ANTS")
    names = _names(wf)
    for suffix in ("highpass", "meanfunc3", "merge_tr_meanfunc3"):
        assert "%s_%s" % (NAME, suffix) not in names
    assert "highpass_clean" in names
    # The intensity normalisation stays.
    assert "%s_intnorm" % NAME in names


def test_fsl_engine_keeps_preproc_highpass(
    subject_config, global_config, make_input_dir
):
    section = subject_config[DataInputList.FMRI_RS]
    section["aroma"] = "false"
    synth = global_config[GlobalPrefCategoryList.SYNTH]
    synth["engine"] = "FSL"
    synth["fmri_engine"] = "FSL"
    wf = fMRI_resting_state_workflow(
        NAME, dicom_dir=make_input_dir(), config=section, synth_config=synth
    )
    names = _names(wf)
    for suffix in ("highpass", "meanfunc3", "merge_tr_meanfunc3"):
        assert "%s_%s" % (NAME, suffix) in names


def test_dof_and_counts():
    # n_HP = min(floor(2*T*TR/100), T-1) DCT columns at a 100 s cutoff.
    assert nl.n_hp_columns(200, 2.0) == 8
    assert nl.n_hp_columns(10, 100.0) == 9
    assert nl.n_hp_columns(50, 0.5) == 0
    assert nl.count_motion_ics([3, 5, 9]) == 3
    assert nl.count_motion_ics([]) == 0
    assert nl.removed_rank(4, 7) == 11


def test_dof_function_node(tmp_path, monkeypatch, make_nifti):
    import numpy as np

    monkeypatch.chdir(tmp_path)
    img = make_nifti("hp.nii.gz", data=np.zeros((2, 2, 2, 200), np.float32))
    node_iface = nl.dof_node().interface
    node_iface.inputs.in_file = img
    node_iface.inputs.TR = 2.0
    node_iface.inputs.rank = 4
    node_iface.inputs.n_aroma = 10
    # 200 - 4 - 8 - 10
    assert node_iface.run().outputs.dof == 178


# ---------------------------------------------------------------------------
# Output space (approach A)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("aroma", [True, False])
@pytest.mark.parametrize("reg", REGS)
def test_output_space_resampling(
    subject_config, global_config, make_input_dir, aroma, reg
):
    from swane.nipype_pipeline.workflows.fMRI_resting_state_workflow import (
        registered_file_name,
    )

    wf = _build(subject_config, global_config, make_input_dir, aroma, reg)
    names = _names(wf)
    ica_output = _node(wf, "ica_output")
    inputnode = _node(wf, "inputnode")
    outputnode = _node(wf, "outputnode")
    suffix = "_ants_apply" if reg == "ANTS" else "_apply_xfm"
    assert not any(n.startswith("zstats%s" % suffix) for n in names)

    split = _node(wf, "ica_zstat_split")
    assert _source(wf, split, "in_file") == (ica_output, "zstat_file")

    applies = {}
    for stem, src in (
        ("zstats_unthr_2_ref", (split, "out_files")),
        ("survivors_pos_2_ref", (ica_output, "survivor_pos_files")),
        ("survivors_neg_2_ref", (ica_output, "survivor_neg_files")),
    ):
        node = _node(wf, stem + suffix)
        applies[stem] = node
        if reg == "ANTS":
            assert node.inputs.interpolator == "linear"
            assert _source(wf, node, "input_image") == src
            assert _source(wf, node, "reference_image") == (
                inputnode,
                "reference_brain",
            )
            assert _source(wf, node, "transformlist") == (
                _node(wf, "%s_2_ref_antsreg" % NAME),
                "fwd_transforms",
            )
            assert node.iterfield == ["input_image"]
        else:
            assert _source(wf, node, "in_file") == src
            assert _source(wf, node, "in_matrix_file") == (
                _node(wf, "%s_2_ref_flirt" % NAME),
                "out_matrix_file",
            )
            assert node.inputs.datatype == "float"
            assert node.iterfield == ["in_file"]

    combine = _node(wf, "zstats_combine")
    assert _iface(combine) == "MaskedResampleCombine"
    assert sorted(combine.iterfield) == sorted(
        ["z_file", "pos_mask_file", "neg_mask_file", "out_file"]
    )
    assert combine.inputs.mask_thr == 0.5
    assert _source(wf, combine, "z_file") == (applies["zstats_unthr_2_ref"], "out_file")
    assert _source(wf, combine, "pos_mask_file") == (
        applies["survivors_pos_2_ref"],
        "out_file",
    )
    assert _source(wf, combine, "neg_mask_file") == (
        applies["survivors_neg_2_ref"],
        "out_file",
    )
    src, field = _source(wf, combine, "out_file")
    assert src is ica_output
    assert field[0] == "thresh_zstat_files"
    assert field[1] == getsource(registered_file_name)
    assert _source(wf, outputnode, "thresh_zstat_files") == (combine, "out_file")


def test_fsl_engine_keeps_zstats_2_ref(subject_config, global_config, make_input_dir):
    section = subject_config[DataInputList.FMRI_RS]
    section["aroma"] = "false"
    synth = global_config[GlobalPrefCategoryList.SYNTH]
    synth["engine"] = "FSL"
    synth["fmri_engine"] = "FSL"
    wf = fMRI_resting_state_workflow(
        NAME, dicom_dir=make_input_dir(), config=section, synth_config=synth
    )
    names = _names(wf)
    assert "zstats_apply_xfm" in names
    assert "zstats_combine" not in names
    assert (
        _node(wf, "zstats_apply_xfm"),
        "out_file",
    ) == _source(wf, _node(wf, "outputnode"), "thresh_zstat_files")


def test_zstat_split(tmp_path, monkeypatch, make_nifti):
    import os
    import numpy as np
    import nibabel as nib

    monkeypatch.chdir(tmp_path)
    data = np.arange(2 * 2 * 2 * 3, dtype=np.float32).reshape(2, 2, 2, 3)
    img = make_nifti("z.nii.gz", data=data)
    out = nl.zstat_split_node().interface
    out.inputs.in_file = img
    files = out.run().outputs.out_files
    assert [os.path.basename(f) for f in files] == [
        "zstat01.nii.gz",
        "zstat02.nii.gz",
        "zstat03.nii.gz",
    ]
    for k, f in enumerate(files):
        np.testing.assert_array_equal(nib.load(f).get_fdata(), data[..., k])
