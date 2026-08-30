"""Settings matrix for
:func:`swane.nipype_pipeline.workflows.fMRI_resting_state_workflow.fMRI_resting_state_workflow`.

Wires MELODIC ICA on the preprocessed data. The ``aroma=True`` path additionally
reads the ``$FSLDIR`` MNI 2mm template at construction and adds the ICA-AROMA
denoising branch: on a fully-equipped box that is the norm and is snapshotted;
on a box without the template it degrades to a skip (see
``conftest.require_fsl_data``). Snapshots under ``snapshots/fmri_resting_state/``.
"""

import pytest

from swane.config.config_enums import GlobalPrefCategoryList, RegistrationEngine
from swane.utils.DataInputList import DataInputList
from swane.tests.nipype_pipeline.matrix.conftest import import_workflow_or_skip

fMRI_resting_state_workflow = import_workflow_or_skip(
    "swane.nipype_pipeline.workflows.fMRI_resting_state_workflow",
    "fMRI_resting_state_workflow",
)
from swane.tests.nipype_pipeline.matrix.conftest import fsl_data_path, require_fsl_data

SUBDIR = "fmri_resting_state"

# name -> (melodic_dim, melodic_thr, aroma)
SCENARIOS = {
    "melodic_auto_dim": ("0", "0.5", False),
    "melodic_fixed_dim": ("30", "0.9", False),
    "aroma_on": ("0", "0.5", True),
}


@pytest.mark.parametrize("scenario", list(SCENARIOS), ids=list(SCENARIOS))
def test_fmri_resting_state_matrix(
    scenario, subject_config, global_config, make_input_dir, graph_snapshot
):
    melodic_dim, melodic_thr, aroma = SCENARIOS[scenario]
    if aroma:
        # aroma=True reads the MNI 2mm brain template at construction time.
        require_fsl_data(
            fsl_data_path("data", "standard", "MNI152_T1_2mm_brain.nii.gz")
        )
    section = subject_config[DataInputList.FMRI_RS]
    section["aroma"] = "true" if aroma else "false"
    section["melodic_dim"] = melodic_dim
    section["melodic_thr"] = melodic_thr
    # These byte snapshots describe the FSL construction; pin the engine so the
    # golden files stay valid. The ANTS-default snapshots are Session F's job.
    synth = global_config[GlobalPrefCategoryList.SYNTH]
    synth["engine"] = "FSL"

    wf = fMRI_resting_state_workflow(
        "fmri_rs",
        dicom_dir=make_input_dir(),
        config=section,
        synth_config=synth,
    )

    config_echo = {
        "aroma": section["aroma"],
        "melodic_dim": melodic_dim,
        "melodic_thr": melodic_thr,
    }
    graph_snapshot(
        wf,
        subdir=SUBDIR,
        name=scenario,
        config=config_echo,
        title="fmri_resting_state / %s" % scenario,
    )


def test_fmri_resting_state_matrix_test_run(
    subject_config, global_config, make_input_dir, graph_snapshot
):
    """test_run=True with aroma on: the ref_2_mni_fnirt node (built only in
    the aroma branch) is the only place in this workflow test_run touches,
    getting the same FNIRT strategy A as get_registration_node. melodic_dim
    stays untouched -- the phantom dataset is built to yield a specific
    component count, forcing a fixed dim would defeat that (see
    fMRI_resting_state_workflow.py).
    """
    require_fsl_data(fsl_data_path("data", "standard", "MNI152_T1_2mm_brain.nii.gz"))

    section = subject_config[DataInputList.FMRI_RS]
    section["aroma"] = "true"
    section["melodic_dim"] = "0"
    section["melodic_thr"] = "0.5"
    synth = global_config[GlobalPrefCategoryList.SYNTH]
    synth["engine"] = "FSL"

    wf = fMRI_resting_state_workflow(
        "fmri_rs",
        dicom_dir=make_input_dir(),
        config=section,
        synth_config=synth,
        test_run=True,
    )

    config_echo = {
        "aroma": "true",
        "melodic_dim": "0",
        "melodic_thr": "0.5",
        "test_run": True,
    }
    graph_snapshot(
        wf,
        subdir=SUBDIR,
        name="test_run",
        config=config_echo,
        title="fmri_resting_state / test_run",
    )


# ---------------------------------------------------------------------------
# Construction asserts for the EPI engine flip + the func->ref->mni concat
# (Phase 3, Session C / Tasks 3-4).
#
# zstats_2_ref consumes workflow.reg_2_ref through ``registration=`` instead of
# the FSL node-name lookup. In the AROMA branch the func->mni resample is a
# single ANTs apply fed a stacked transformlist [ref->mni, func->ref] (no
# ConvertWarp) under ANTS, and keeps the ConvertWarp + ApplyWarp pair under
# FSL/SYNTH->FSL. Graph-shape asserts, independent of the byte snapshots
# (regenerated in Session F).
# ---------------------------------------------------------------------------


def _iface(node):
    return type(node.interface).__name__


def _incoming(wf, dst_node):
    conns = []
    for src, dst, data in wf._graph.edges(data=True):
        if dst is dst_node:
            for src_field, dst_field in data.get("connect", []):
                conns.append((src, src_field, dst_field))
    return conns


def _node_by_name(wf, name):
    return next(n for n in wf._graph.nodes() if n.name == name)


def _build_engine(engine_name, subject_config, global_config, make_input_dir):
    """Build the AROMA resting-state branch under a forced registration engine."""
    require_fsl_data(fsl_data_path("data", "standard", "MNI152_T1_2mm_brain.nii.gz"))
    section = subject_config[DataInputList.FMRI_RS]
    section["aroma"] = "true"
    section["melodic_dim"] = "0"
    section["melodic_thr"] = "0.5"
    synth = global_config[GlobalPrefCategoryList.SYNTH]
    synth["engine"] = engine_name
    return fMRI_resting_state_workflow(
        "fmri_rs",
        dicom_dir=make_input_dir(),
        config=section,
        synth_config=synth,
    )


def test_fmri_resting_state_ants_zstats_use_reg_2_ref(
    subject_config, global_config, make_input_dir
):
    """ANTS: zstats->ref is an AntsApplyTransforms fed the func->ref
    registration's transform list + which_to_invert, never a bare
    in_matrix_file."""
    wf = _build_engine("ANTS", subject_config, global_config, make_input_dir)
    assert wf.reg_2_ref.engine == RegistrationEngine.ANTS
    ants_reg = _node_by_name(wf, "fmri_rs_2_ref_antsreg")

    zstats = _node_by_name(wf, "zstats_ants_apply")
    assert _iface(zstats) == "AntsApplyTransforms"
    inc = _incoming(wf, zstats)
    assert (ants_reg, "fwd_transforms", "transformlist") in inc
    assert (ants_reg, "fwd_which_to_invert", "which_to_invert") in inc
    assert "in_matrix_file" not in {df for _, _, df in inc}
    assert zstats.iterfield == ["input_image", "out_file"]

    ifaces = [_iface(n) for n in wf._graph.nodes()]
    assert "ApplyXFM" not in ifaces
    assert "FLIRT" not in ifaces


def test_fmri_resting_state_ants_func2mni_is_one_stacked_apply(
    subject_config, global_config, make_input_dir
):
    """ANTS: no ConvertWarp anywhere; func->mni is ONE AntsApplyTransforms whose
    transformlist/which_to_invert come from ravel Merges stacking ref->mni first
    and func->ref second (output->input order)."""
    wf = _build_engine("ANTS", subject_config, global_config, make_input_dir)

    assert "ConvertWarp" not in [_iface(n) for n in wf._graph.nodes()]

    func2mni = _node_by_name(wf, "func2mni_ants_apply")
    assert _iface(func2mni) == "AntsApplyTransforms"

    transformlist_merge = _node_by_name(wf, "func2mni_transformlist")
    which_merge = _node_by_name(wf, "func2mni_which_to_invert")
    assert transformlist_merge.inputs.ravel_inputs is True
    assert which_merge.inputs.ravel_inputs is True

    inc = _incoming(wf, func2mni)
    assert (transformlist_merge, "out", "transformlist") in inc
    assert (which_merge, "out", "which_to_invert") in inc

    ref_2_mni = _node_by_name(wf, "ref_2_mni_antsreg")
    func_2_ref = _node_by_name(wf, "fmri_rs_2_ref_antsreg")
    # in1 = ref->mni, in2 = func->ref: ANTs applies the list right-to-left, so
    # the func->ref affine acts on the moving image first.
    assert (ref_2_mni, "fwd_transforms", "in1") in _incoming(wf, transformlist_merge)
    assert (func_2_ref, "fwd_transforms", "in2") in _incoming(wf, transformlist_merge)
    assert (ref_2_mni, "fwd_which_to_invert", "in1") in _incoming(wf, which_merge)
    assert (func_2_ref, "fwd_which_to_invert", "in2") in _incoming(wf, which_merge)


def test_fmri_resting_state_fsl_keeps_convert_warp(
    subject_config, global_config, make_input_dir
):
    """FSL: unchanged construction -- ConvertWarp combines the func->ref .mat
    (premat, now read off the wrapper) with the ref->mni fieldcoeff (warp1) and
    feeds a single ApplyWarp."""
    wf = _build_engine("FSL", subject_config, global_config, make_input_dir)
    assert wf.reg_2_ref.engine == RegistrationEngine.FSL

    convert_warp = _node_by_name(wf, "func_2_mni_warp")
    assert _iface(convert_warp) == "ConvertWarp"
    flirt_2_ref = _node_by_name(wf, "fmri_rs_2_ref_flirt")
    fnirt_2_mni = _node_by_name(wf, "ref_2_mni_fnirt")
    inc = _incoming(wf, convert_warp)
    assert (flirt_2_ref, "out_matrix_file", "premat") in inc
    assert (fnirt_2_mni, "fieldcoeff_file", "warp1") in inc

    func2mni = _node_by_name(wf, "func2mni_apply_warp")
    assert _iface(func2mni) == "ApplyWarp"
    assert (convert_warp, "out_file", "field_file") in _incoming(wf, func2mni)

    zstats = _node_by_name(wf, "zstats_apply_xfm")
    assert _iface(zstats) == "ApplyXFM"
    assert (flirt_2_ref, "out_matrix_file", "in_matrix_file") in _incoming(wf, zstats)
    assert zstats.iterfield == ["in_file", "out_file"]

    assert "AntsApplyTransforms" not in [_iface(n) for n in wf._graph.nodes()]


def test_fmri_resting_state_synth_falls_back_to_fsl(
    subject_config, global_config, make_input_dir
):
    """EPI avoids SynthMorph: SYNTH resolves to FSL for func->ref, ref->mni and
    every apply, so the ConvertWarp path is kept."""
    wf = _build_engine("SYNTH", subject_config, global_config, make_input_dir)
    assert wf.reg_2_ref.engine == RegistrationEngine.FSL
    ifaces = [_iface(n) for n in wf._graph.nodes()]
    assert "ConvertWarp" in ifaces
    assert "ApplyXFM" in ifaces
    assert "ApplyWarp" in ifaces
    assert "SynthMorphReg" not in ifaces
    assert "SynthMorphApply" not in ifaces
    assert "AntsApplyTransforms" not in ifaces
