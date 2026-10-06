import pytest
from swane.config.config_enums import FmriEngine, RegistrationEngine
from swane.nipype_pipeline.workflows.fMRI_resting_state_workflow import (
    fMRI_resting_state_workflow,
)

# ---------------------------------------------------------------------------
# Dispatcher, shared AROMA module and FSL builder.
#
# Built with real ConfigManager sections (fixtures from
# ``swane/tests/nipype_pipeline/conftest.py``) for both fMRI engines, AROMA on
# and off, and registration engine ANTS and FSL.
# ---------------------------------------------------------------------------
from nipype.utils.functions import getsource

from swane.config.config_enums import GlobalPrefCategoryList
from swane.utils.DataInputList import DataInputList
from swane.nipype_pipeline.workflows.fMRI_preproc_workflow import highpass_op_string

NAME = "fmri_rs"

AROMA_NODE_NAMES = [
    "feature_spatial_prep",
    "feature_spatial",
    "feature_time_series",
    "feature_frequency",
    "aroma_classification",
]


def _build(subject_config, global_config, make_input_dir, fmri_engine, aroma, reg):
    section = subject_config[DataInputList.FMRI_RS]
    section["aroma"] = "true" if aroma else "false"
    section["ic_dim"] = "0"
    section["melodic_thr"] = "0.5"
    synth = global_config[GlobalPrefCategoryList.SYNTH]
    synth["engine"] = reg
    synth["fmri_engine"] = fmri_engine
    return fMRI_resting_state_workflow(
        NAME, dicom_dir=make_input_dir(), config=section, synth_config=synth
    )


def _incoming(wf, dst_node):
    conns = []
    for src, dst, data in wf._graph.edges(data=True):
        if dst is dst_node:
            for src_field, dst_field in data.get("connect", []):
                conns.append((src, src_field, dst_field))
    return conns


def _names(wf):
    return {n.name for n in wf._graph.nodes()}


def _node(wf, name):
    node = wf.get_node(name)
    assert node is not None, "missing node %s" % name
    return node


@pytest.mark.parametrize("reg", ["ANTS", "FSL"])
def test_fsl_aroma_pass_on_unfiltered_intnorm(
    subject_config, global_config, make_input_dir, reg
):
    wf = _build(subject_config, global_config, make_input_dir, "FSL", True, reg)
    intnorm = _node(wf, "%s_intnorm" % NAME)
    highpass = _node(wf, "%s_highpass" % NAME)
    merge_node = _node(wf, "merge_node")
    preproc_melodic = _node(wf, "preproc_melodic")

    assert _incoming(wf, merge_node) == [(intnorm, "out_file", "in1")]
    assert (merge_node, "out", "in_files") in _incoming(wf, preproc_melodic)

    nonaggr = _node(wf, "nonaggr_denoising")
    assert type(nonaggr.interface).__name__ == "FilterRegressor"
    inc = _incoming(wf, nonaggr)
    assert (intnorm, "out_file", "in_file") in inc
    assert not any(src is highpass for src, _, _ in inc)


@pytest.mark.parametrize("reg", ["ANTS", "FSL"])
def test_fsl_aroma_highpass_after_denoising(
    subject_config, global_config, make_input_dir, reg
):
    wf = _build(subject_config, global_config, make_input_dir, "FSL", True, reg)
    nonaggr = _node(wf, "nonaggr_denoising")
    get_tr = _node(wf, "%s_getTR" % NAME)
    mean_den = _node(wf, "%s_meanfunc_denoised" % NAME)
    merge_den = _node(wf, "%s_merge_tr_meanfunc_denoised" % NAME)
    hp_den = _node(wf, "%s_highpass_denoised" % NAME)
    input_list_denoised = _node(wf, "input_list_denoised")
    melodic = _node(wf, "melodic")

    assert type(mean_den.interface).__name__ == "ImageMaths"
    assert mean_den.inputs.op_string == "-Tmean"
    assert _incoming(wf, mean_den) == [(nonaggr, "out_file", "in_file")]

    assert sorted(
        (src.name, sf, df) for src, sf, df in _incoming(wf, merge_den)
    ) == sorted(
        [
            (get_tr.name, "TR", "in1"),
            (mean_den.name, "out_file", "in2"),
        ]
    )

    inc = _incoming(wf, hp_den)
    assert (nonaggr, "out_file", "in_file") in inc
    op = [(src, sf) for src, sf, df in inc if df == "op_string"]
    assert len(op) == 1
    src, src_field = op[0]
    assert src is merge_den
    # Same function (same source) and cutoff as the preprocessing high-pass.
    assert src_field[0] == "out"
    assert src_field[1] == getsource(highpass_op_string)
    assert tuple(src_field[2]) == (100,)
    preproc_hp_op = [
        sf
        for _, sf, df in _incoming(wf, _node(wf, "%s_highpass" % NAME))
        if df == "op_string"
    ][0]
    assert preproc_hp_op == src_field

    assert _incoming(wf, input_list_denoised) == [(hp_den, "out_file", "in1")]
    assert (input_list_denoised, "out", "in_files") in _incoming(wf, melodic)


@pytest.mark.parametrize("reg", ["ANTS", "FSL"])
def test_fsl_no_aroma_unchanged(subject_config, global_config, make_input_dir, reg):
    wf = _build(subject_config, global_config, make_input_dir, "FSL", False, reg)
    names = _names(wf)
    highpass = _node(wf, "%s_highpass" % NAME)
    merge_node = _node(wf, "merge_node")
    melodic = _node(wf, "melodic")

    assert _incoming(wf, merge_node) == [(highpass, "out_file", "in1")]
    assert (merge_node, "out", "in_files") in _incoming(wf, melodic)
    for absent in AROMA_NODE_NAMES + [
        "preproc_melodic",
        "nonaggr_denoising",
        "%s_meanfunc_denoised" % NAME,
        "%s_merge_tr_meanfunc_denoised" % NAME,
        "%s_highpass_denoised" % NAME,
    ]:
        assert absent not in names


@pytest.mark.parametrize("fmri_engine", ["FSL", "NILEARN"])
@pytest.mark.parametrize("aroma", [True, False])
@pytest.mark.parametrize("reg", ["ANTS", "FSL"])
def test_outputnode_fields(
    subject_config, global_config, make_input_dir, fmri_engine, aroma, reg
):
    wf = _build(subject_config, global_config, make_input_dir, fmri_engine, aroma, reg)
    outputnode = _node(wf, "outputnode")
    assert set(outputnode.inputs.copyable_trait_names()) == {
        "thresh_zstat_files",
        "aroma_classification",
        "ic_mix",
    }
    inc = {df: (src.name, sf) for src, sf, df in _incoming(wf, outputnode)}
    final_output = "melodic_output" if fmri_engine == "FSL" else "ica_output"
    assert inc["ic_mix"] == (final_output, "ic_mix")
    assert inc["thresh_zstat_files"][1] == "out_file"
    if aroma:
        assert inc["aroma_classification"] == (
            "aroma_classification",
            "classification_overview",
        )
        for node_name in AROMA_NODE_NAMES:
            assert node_name in _names(wf)
    else:
        assert "aroma_classification" not in inc
        for node_name in AROMA_NODE_NAMES:
            assert node_name not in _names(wf)


@pytest.mark.parametrize("fmri_engine", ["FSL", "NILEARN"])
@pytest.mark.parametrize("reg", ["ANTS", "FSL"])
def test_aroma_module_node_names(
    subject_config, global_config, make_input_dir, fmri_engine, reg
):
    wf = _build(subject_config, global_config, make_input_dir, fmri_engine, True, reg)
    names = _names(wf)
    if reg == "ANTS":
        assert {"ref_2_mni_antsreg", "func2mni_ants_apply"} <= names
        assert "func_2_mni_warp" not in names
    else:
        assert {"ref_2_mni_fnirt", "func_2_mni_warp", "func2mni_apply_warp"} <= names


@pytest.mark.parametrize("reg", ["ANTS", "FSL"])
def test_nilearn_aroma_pass_dual_regression_flags(
    subject_config, global_config, make_input_dir, reg
):
    wf = _build(subject_config, global_config, make_input_dir, "NILEARN", True, reg)
    dual_reg = _node(wf, "preproc_ica_dual_reg")
    assert dual_reg.inputs.centre_maps is False
    assert dual_reg.inputs.t_to_z is False


def test_build_aroma_classification_returns_node_and_registration(
    subject_config, global_config, make_input_dir
):
    from swane.nipype_pipeline.workflows import fMRI_resting_state_aroma
    from swane.nipype_pipeline.workflows import fMRI_resting_state_fsl
    from swane.nipype_pipeline.workflows import fMRI_resting_state_nilearn

    assert callable(fMRI_resting_state_aroma.build_aroma_classification)
    assert callable(fMRI_resting_state_fsl.build_fsl_resting)
    assert callable(fMRI_resting_state_nilearn.build_nilearn_resting)
