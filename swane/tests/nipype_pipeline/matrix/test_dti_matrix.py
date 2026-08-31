"""Settings matrix for
:func:`swane.nipype_pipeline.workflows.dti_preproc_workflow.dti_preproc_workflow`.

Sweeps the eddy-correction backend and the **CUDA on/off** axis (the flagship
GPU dimension: ``eddy.use_cuda`` / command choice / thread handling) and records
one golden graph snapshot per scenario under ``snapshots/dti_preproc/``.

CPU thread counts are made deterministic by passing an explicit ``max_cpu`` and
only using the ``SOFT_CAP`` / ``HARD_CAP`` core-limit modes; ``NO_LIMIT`` would
fall back to the host ``cpu_count()`` and is left to a behavioural assertion.

The ``tractography=True`` branch adds BEDPOSTX. The MNI-to-reference nonlinear
registration used to be built here too, but it is the same registration FLAT1
relies on (see ``test_nonlinear_reg_matrix.py``), so it now lives in the shared
``mni1`` workflow instantiated once by ``MainWorkflow`` and is out of scope for
this per-builder snapshot; ``dti_preproc_workflow`` no longer reads ``$FSLDIR``
MNI templates at construction time.
"""

import pytest

from swane.config.config_enums import GlobalPrefCategoryList, CoreLimit
from swane.utils.DataInputList import DataInputList
from swane.tests.nipype_pipeline.matrix.conftest import import_workflow_or_skip

dti_preproc_workflow = import_workflow_or_skip(
    "swane.nipype_pipeline.workflows.dti_preproc_workflow", "dti_preproc_workflow"
)

SUBDIR = "dti_preproc"
MAX_CPU = 4

# name -> (cuda, old_eddy, multicore_node_limit, tractography)
SCENARIOS = {
    "new_eddy_cpu_softcap": (False, False, CoreLimit.SOFT_CAP, False),
    "new_eddy_cpu_hardcap": (False, False, CoreLimit.HARD_CAP, False),
    "new_eddy_cuda": (True, False, CoreLimit.SOFT_CAP, False),
    "old_eddy_correct": (False, True, CoreLimit.SOFT_CAP, False),
    "new_eddy_tractography": (False, False, CoreLimit.SOFT_CAP, True),
}


def _bool(value):
    return "true" if value else "false"


@pytest.mark.parametrize("scenario", list(SCENARIOS), ids=list(SCENARIOS))
def test_dti_matrix(
    scenario, subject_config, global_config, make_input_dir, graph_snapshot
):
    cuda, old_eddy, multicore, tractography = SCENARIOS[scenario]
    section = subject_config[DataInputList.DTI]
    section["cuda"] = _bool(cuda)
    section["old_eddy_correct"] = _bool(old_eddy)
    section["tractography"] = _bool(tractography)
    synth = global_config[GlobalPrefCategoryList.SYNTH]
    # dti is not yet ported to ANTs -> FSL (old morph default); morph kept
    # only for the header echo.
    synth["morph"] = "False"
    synth["engine"] = "FSL"

    wf = dti_preproc_workflow(
        "dti",
        dti_dir=make_input_dir(),
        config=section,
        synth_config=synth,
        max_cpu=MAX_CPU,
        multicore_node_limit=multicore,
    )

    config_echo = {
        "cuda": section["cuda"],
        "old_eddy_correct": section["old_eddy_correct"],
        "tractography": section["tractography"],
        "multicore_node_limit": multicore.name,
        "max_cpu": MAX_CPU,
        "synth_strip": synth["strip"],
        "synth_morph": synth["morph"],
    }
    graph_snapshot(
        wf,
        subdir=SUBDIR,
        name=scenario,
        config=config_echo,
        title="dti_preproc / %s" % scenario,
    )


def test_dti_matrix_test_run(
    subject_config, global_config, make_input_dir, graph_snapshot
):
    """test_run=True with tractography on: exercises CustomEddy niter=1 and
    BEDPOSTX5's cut MCMC parameters (n_fibres/n_jumps/burn_in/sample_every),
    both unvalidated end-to-end yet -- see prerelease/TODO.md.
    """
    section = subject_config[DataInputList.DTI]
    section["cuda"] = "false"
    section["old_eddy_correct"] = "false"
    section["tractography"] = "true"
    synth = global_config[GlobalPrefCategoryList.SYNTH]
    # dti is not yet ported to ANTs -> FSL (old morph default); morph kept
    # only for the header echo.
    synth["morph"] = "False"
    synth["engine"] = "FSL"

    wf = dti_preproc_workflow(
        "dti",
        dti_dir=make_input_dir(),
        config=section,
        synth_config=synth,
        max_cpu=MAX_CPU,
        multicore_node_limit=CoreLimit.SOFT_CAP,
        test_run=True,
    )

    config_echo = {
        "cuda": "false",
        "old_eddy_correct": "false",
        "tractography": "true",
        "multicore_node_limit": CoreLimit.SOFT_CAP.name,
        "max_cpu": MAX_CPU,
        "synth_strip": synth["strip"],
        "synth_morph": synth["morph"],
        "test_run": True,
    }
    graph_snapshot(
        wf,
        subdir=SUBDIR,
        name="test_run",
        config=config_echo,
        title="dti_preproc / test_run",
    )


# ---------------------------------------------------------------------------
# Construction asserts for the engine flip (Phase 3, Session D / Task 5).
#
# dti_preproc now follows resolve_registration_engine(synth_config,
# allow_ants=True) with SYNTH -> FSL. The diff<->ref outputnode contract moves
# off the FSL .mat (diff2ref_mat/ref2diff_mat) to the abstraction transform-list
# view (diff2ref_transforms/diff2ref_which_to_invert/ref2diff_transforms/
# ref2diff_which_to_invert), the betted b0 is exposed as nodif_brain, and the
# LTAConvert SYNTH special-case is deleted. These are graph-shape asserts,
# independent of the byte snapshots (regenerated in Session F).
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


def _node_by_prefix(wf, prefix):
    # The deskull node name gets a "_bet"/"_synthstrip" suffix depending on the
    # strip backend, which is orthogonal to the registration engine tested here.
    return next(n for n in wf._graph.nodes() if n.name.startswith(prefix))


def _build_engine(engine_name, subject_config, global_config, make_input_dir):
    section = subject_config[DataInputList.DTI]
    section["cuda"] = "false"
    section["old_eddy_correct"] = "false"
    section["tractography"] = "false"
    synth = global_config[GlobalPrefCategoryList.SYNTH]
    synth["engine"] = engine_name
    return dti_preproc_workflow(
        "dti",
        dti_dir=make_input_dir(),
        config=section,
        synth_config=synth,
        max_cpu=MAX_CPU,
        multicore_node_limit=CoreLimit.SOFT_CAP,
    )


def test_dti_ants_construction(subject_config, global_config, make_input_dir):
    wf = _build_engine("ANTS", subject_config, global_config, make_input_dir)
    ifaces = [_iface(n) for n in wf._graph.nodes()]
    # diff -> ref registration follows the ANTs engine.
    assert "AntsRegistration" in ifaces
    assert "FLIRT" not in ifaces
    # LTAConvert special-case is gone under every engine.
    assert "LTAConvert" not in ifaces

    outputnode = _node_by_name(wf, "outputnode")
    ants_reg = _node_by_name(wf, "dif2ref_antsreg")
    deskull = _node_by_prefix(wf, "dti_deskull")
    inc = _incoming(wf, outputnode)
    dst_fields = {df for _, _, df in inc}

    # New transform-list contract wired from the ANTs registration node.
    assert (ants_reg, "fwd_transforms", "diff2ref_transforms") in inc
    assert (ants_reg, "fwd_which_to_invert", "diff2ref_which_to_invert") in inc
    assert (ants_reg, "inv_transforms", "ref2diff_transforms") in inc
    assert (ants_reg, "inv_which_to_invert", "ref2diff_which_to_invert") in inc
    # Betted b0 exposed for probtrackx seed_ref (Session E).
    assert (deskull, "out_file", "nodif_brain") in inc
    # Old FSL .mat contract is gone.
    assert "diff2ref_mat" not in dst_fields
    assert "ref2diff_mat" not in dst_fields

    # FA apply follows the engine too (kept as-is, boundary single-field path).
    fa_apply = _node_by_name(wf, "fa_2_ref_ants_apply")
    assert _iface(fa_apply) == "AntsApplyTransforms"
    assert (fa_apply, "out_file", "FA") in inc


def test_dti_fsl_construction(subject_config, global_config, make_input_dir):
    wf = _build_engine("FSL", subject_config, global_config, make_input_dir)
    ifaces = [_iface(n) for n in wf._graph.nodes()]
    # diff -> ref registration is FLIRT on the FSL engine.
    assert "FLIRT" in ifaces
    assert "AntsRegistration" not in ifaces
    assert "LTAConvert" not in ifaces

    outputnode = _node_by_name(wf, "outputnode")
    flirt = _node_by_name(wf, "dif2ref_flirt")
    inv_xfm = _node_by_name(wf, "dif2ref_invwarp")
    deskull = _node_by_prefix(wf, "dti_deskull")
    inc = _incoming(wf, outputnode)
    dst_fields = {df for _, _, df in inc}

    # Same new field names, carrying the FSL .mat as the single-element list view.
    assert (flirt, "out_matrix_file", "diff2ref_transforms") in inc
    assert (inv_xfm, "out_file", "ref2diff_transforms") in inc
    assert (deskull, "out_file", "nodif_brain") in inc
    # FSL never inverts on apply: which_to_invert stays None (unconnected).
    assert "diff2ref_which_to_invert" not in dst_fields
    assert "ref2diff_which_to_invert" not in dst_fields
    # Old FSL .mat contract is gone.
    assert "diff2ref_mat" not in dst_fields
    assert "ref2diff_mat" not in dst_fields


def test_dti_synth_falls_back_to_fsl(subject_config, global_config, make_input_dir):
    wf = _build_engine("SYNTH", subject_config, global_config, make_input_dir)
    ifaces = [_iface(n) for n in wf._graph.nodes()]
    # SYNTH -> FSL for the diff -> ref registration (no SynthMorph, no LTAConvert).
    assert "FLIRT" in ifaces
    assert "SynthMorphReg" not in ifaces
    assert "LTAConvert" not in ifaces

    outputnode = _node_by_name(wf, "outputnode")
    dst_fields = {df for _, _, df in _incoming(wf, outputnode)}
    assert {"diff2ref_transforms", "ref2diff_transforms", "nodif_brain"} <= dst_fields
    assert "diff2ref_mat" not in dst_fields
    assert "ref2diff_mat" not in dst_fields


def test_no_limit_eddy_uses_host_cpu_count(
    subject_config, global_config, make_input_dir
):
    """NO_LIMIT is host-dependent (``cpu_count()``), so it is asserted, not snapshotted."""
    from multiprocessing import cpu_count

    section = subject_config[DataInputList.DTI]
    section["cuda"] = "false"
    section["old_eddy_correct"] = "false"
    section["tractography"] = "false"

    wf = dti_preproc_workflow(
        "dti",
        dti_dir=make_input_dir(),
        config=section,
        synth_config=global_config[GlobalPrefCategoryList.SYNTH],
        max_cpu=MAX_CPU,
        multicore_node_limit=CoreLimit.NO_LIMIT,
    )
    eddy = wf.get_node("dti_eddy")
    assert eddy.inputs.args == "--nthr=%d" % cpu_count()

    hashed_inputs, host_cpu_hash = eddy.inputs.get_hashval()
    assert "args" not in dict(hashed_inputs)

    eddy.inputs.args = "--nthr=1"
    _, single_cpu_hash = eddy.inputs.get_hashval()
    assert single_cpu_hash == host_cpu_hash
