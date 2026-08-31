"""Settings matrix for
:func:`swane.nipype_pipeline.workflows.fMRI_task_workflow.fMRI_task_workflow`.

Construction of this workflow needs a real (or emulated, see
``swane/tests/conftest.py``) FSL >= 5.0.7: nipype's ``FILMGLS`` only exposes
the ``tcon_file``/``fcon_file`` inputs the builder wires from that version on
(see the former ``TODO_dicom.md`` §3). The ``block_design`` axis is the
graph-shape-relevant one: ``RARB`` adds a second contrast (and therefore a
second cluster-thresholding branch) on top of ``RARA``. Snapshots live under
``snapshots/fmri_task/``.
"""

import pytest

from swane.config.config_enums import (
    BlockDesign,
    GlobalPrefCategoryList,
    RegistrationEngine,
)
from swane.utils.DataInputList import DataInputList
from swane.tests.nipype_pipeline.matrix.conftest import import_workflow_or_skip

fMRI_task_workflow = import_workflow_or_skip(
    "swane.nipype_pipeline.workflows.fMRI_task_workflow", "fMRI_task_workflow"
)

SUBDIR = "fmri_task"

SCENARIOS = {
    "single_contrast_rara": BlockDesign.RARA,
    "two_contrasts_rarb": BlockDesign.RARB,
}


@pytest.mark.parametrize("scenario", list(SCENARIOS), ids=list(SCENARIOS))
def test_fmri_task_matrix(
    scenario, subject_config, global_config, make_input_dir, graph_snapshot
):
    block_design = SCENARIOS[scenario]
    section = subject_config[DataInputList.FMRI_0]
    section["block_design"] = block_design.name
    # These byte snapshots describe the FSL construction; pin the engine so the
    # golden files stay valid. The ANTS-default snapshots are Session F's job.
    synth = global_config[GlobalPrefCategoryList.SYNTH]
    synth["engine"] = "FSL"

    wf = fMRI_task_workflow(
        "fmri_0",
        dicom_dir=make_input_dir(),
        config=section,
        synth_config=synth,
    )

    config_echo = {
        "block_design": block_design.name,
        "task_a_name": section["task_a_name"],
        "task_b_name": section["task_b_name"],
        "task_duration": section["task_duration"],
        "rest_duration": section["rest_duration"],
    }
    graph_snapshot(
        wf,
        subdir=SUBDIR,
        name=scenario,
        config=config_echo,
        title="fmri_task / %s" % scenario,
    )


def test_fmri_task_matrix_test_run(
    subject_config, global_config, make_input_dir, graph_snapshot
):
    """test_run=True on the single-contrast baseline: exercises the shared
    fMRI_preproc_workflow's MCFLIRT speed knobs through the task path too
    (slice_timing is a real enum here, unlike resting-state's UNKNOWN).
    """
    section = subject_config[DataInputList.FMRI_0]
    section["block_design"] = BlockDesign.RARA.name
    synth = global_config[GlobalPrefCategoryList.SYNTH]
    synth["engine"] = "FSL"

    wf = fMRI_task_workflow(
        "fmri_0",
        dicom_dir=make_input_dir(),
        config=section,
        synth_config=synth,
        test_run=True,
    )

    config_echo = {
        "block_design": BlockDesign.RARA.name,
        "task_a_name": section["task_a_name"],
        "task_b_name": section["task_b_name"],
        "task_duration": section["task_duration"],
        "rest_duration": section["rest_duration"],
        "test_run": True,
    }
    graph_snapshot(
        wf,
        subdir=SUBDIR,
        name="test_run",
        config=config_echo,
        title="fmri_task / test_run",
    )


# ---------------------------------------------------------------------------
# Construction asserts for the EPI engine flip (Phase 3, Session C / Task 3).
#
# The cluster -> ref applies no longer look the func->ref transform up by the
# FSL node name ("<name>_2_ref_flirt"): they consume the RegistrationNodeWrapper
# fMRI_preproc exposes as workflow.reg_2_ref through ``registration=``. Under
# ANTS that gives the apply node the registration's ordered transform list AND
# its which_to_invert flags instead of a bare in_matrix_file. Graph-shape
# asserts, independent of the byte snapshots (regenerated in Session F).
# ---------------------------------------------------------------------------

# The single-contrast (RARA) design builds one cluster branch per threshold.
CLUSTER_APPLY_NAMES = (
    "fmri_0_cluster_t3_1_to_ref",
    "fmri_0_cluster_t5_1_to_ref",
    "fmri_0_cluster_t7_1_to_ref",
)


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
    """Build fMRI_task under a forced registration engine (single contrast)."""
    section = subject_config[DataInputList.FMRI_0]
    section["block_design"] = BlockDesign.RARA.name
    synth = global_config[GlobalPrefCategoryList.SYNTH]
    synth["engine"] = engine_name
    return fMRI_task_workflow(
        "fmri_0",
        dicom_dir=make_input_dir(),
        config=section,
        synth_config=synth,
    )


def test_fmri_task_ants_cluster_applies_use_reg_2_ref(
    subject_config, global_config, make_input_dir
):
    """ANTS: every cluster->ref apply is an AntsApplyTransforms fed the func->ref
    registration's transform list + which_to_invert (wire_transforms), never a
    bare in_matrix_file."""
    wf = _build_engine("ANTS", subject_config, global_config, make_input_dir)
    assert wf.reg_2_ref.engine == RegistrationEngine.ANTS
    ants_reg = _node_by_name(wf, "fmri_0_2_ref_antsreg")

    for base in CLUSTER_APPLY_NAMES:
        apply_node = _node_by_name(wf, base + "_ants_apply")
        assert _iface(apply_node) == "AntsApplyTransforms"
        inc = _incoming(wf, apply_node)
        assert (ants_reg, "fwd_transforms", "transformlist") in inc
        assert (ants_reg, "fwd_which_to_invert", "which_to_invert") in inc
        assert "in_matrix_file" not in {df for _, _, df in inc}
        # The per-threshold MapNode still iterates the moving image and its
        # output name, under the ANTs input names.
        assert apply_node.iterfield == ["input_image", "out_file"]

    ifaces = [_iface(n) for n in wf._graph.nodes()]
    assert "ApplyXFM" not in ifaces
    assert "FLIRT" not in ifaces


def test_fmri_task_fsl_cluster_applies_unchanged(
    subject_config, global_config, make_input_dir
):
    """FSL: unchanged construction -- ApplyXFM MapNodes taking the FLIRT .mat as
    in_matrix_file, now reached through the wrapper instead of get_node()."""
    wf = _build_engine("FSL", subject_config, global_config, make_input_dir)
    assert wf.reg_2_ref.engine == RegistrationEngine.FSL
    flirt = _node_by_name(wf, "fmri_0_2_ref_flirt")

    for base in CLUSTER_APPLY_NAMES:
        apply_node = _node_by_name(wf, base + "_apply_xfm")
        assert _iface(apply_node) == "ApplyXFM"
        inc = _incoming(wf, apply_node)
        assert (flirt, "out_matrix_file", "in_matrix_file") in inc
        assert apply_node.iterfield == ["in_file", "out_file"]

    assert "AntsApplyTransforms" not in [_iface(n) for n in wf._graph.nodes()]


def test_fmri_task_synth_falls_back_to_fsl(
    subject_config, global_config, make_input_dir
):
    """EPI avoids SynthMorph: SYNTH resolves to FSL for both the func->ref
    registration and the cluster applies."""
    wf = _build_engine("SYNTH", subject_config, global_config, make_input_dir)
    assert wf.reg_2_ref.engine == RegistrationEngine.FSL
    ifaces = [_iface(n) for n in wf._graph.nodes()]
    assert "ApplyXFM" in ifaces
    assert "SynthMorphApply" not in ifaces
    assert "SynthMorphReg" not in ifaces
    assert "AntsApplyTransforms" not in ifaces
