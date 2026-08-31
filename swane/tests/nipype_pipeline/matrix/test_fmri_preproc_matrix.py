"""Settings matrix for
:func:`swane.nipype_pipeline.workflows.fMRI_preproc_workflow.fMRI_preproc_workflow`.

The shared fMRI preprocessing chain (trim, motion-correct, slice-timing, SUSAN
smoothing, highpass, coregistration). It takes scalar parameters directly, so
the matrix sweeps the ``slice_timing`` enum and start/end volume trimming,
recording snapshots under ``snapshots/fmri_preproc/``.
"""

import pytest

from swane.config.config_enums import (
    SliceTiming,
    RegistrationEngine,
    GlobalPrefCategoryList,
)
from swane.nipype_pipeline.nodes.utils import RegistrationNodeWrapper
from swane.tests.nipype_pipeline.matrix.conftest import import_workflow_or_skip

fMRI_preproc_workflow = import_workflow_or_skip(
    "swane.nipype_pipeline.workflows.fMRI_preproc_workflow", "fMRI_preproc_workflow"
)

SUBDIR = "fmri_preproc"


def _iface(node):
    return type(node.interface).__name__


# name -> dict(TR, slice_timing, n_vols, del_start, del_end, hpcutoff)
SCENARIOS = {
    "slicetiming_up": dict(
        TR=2.0, slice_timing=SliceTiming.UP, n_vols=100, del_start=0, del_end=0, hp=30
    ),
    "slicetiming_interleaved": dict(
        TR=2.0,
        slice_timing=SliceTiming.INTERLEAVED,
        n_vols=100,
        del_start=0,
        del_end=0,
        hp=30,
    ),
    "slicetiming_unknown": dict(
        TR=2.0,
        slice_timing=SliceTiming.UNKNOWN,
        n_vols=100,
        del_start=0,
        del_end=0,
        hp=30,
    ),
    "trim_start_end_vols": dict(
        TR=3.0, slice_timing=SliceTiming.UP, n_vols=120, del_start=5, del_end=3, hp=50
    ),
}


@pytest.mark.parametrize("scenario", list(SCENARIOS), ids=list(SCENARIOS))
def test_fmri_preproc_matrix(scenario, global_config, make_input_dir, graph_snapshot):
    p = SCENARIOS[scenario]
    # These byte snapshots describe the FSL construction; pin the engine so the
    # golden files stay valid. The ANTS-default snapshots are Session F's job.
    synth = global_config[GlobalPrefCategoryList.SYNTH]
    synth["engine"] = "FSL"
    wf = fMRI_preproc_workflow(
        "fmri_0",
        dicom_dir=make_input_dir(),
        TR=p["TR"],
        slice_timing=p["slice_timing"],
        n_vols=p["n_vols"],
        del_start_vols=p["del_start"],
        del_end_vols=p["del_end"],
        hpcutoff=p["hp"],
        synth_config=synth,
    )

    config_echo = {
        "TR": p["TR"],
        "slice_timing": p["slice_timing"].name,
        "n_vols": p["n_vols"],
        "del_start_vols": p["del_start"],
        "del_end_vols": p["del_end"],
        "hpcutoff": p["hp"],
    }
    graph_snapshot(
        wf,
        subdir=SUBDIR,
        name=scenario,
        config=config_echo,
        title="fmri_preproc / %s" % scenario,
    )


def test_fmri_preproc_matrix_test_run(global_config, make_input_dir, graph_snapshot):
    """test_run=True: MCFLIRT drops to stages=1 with the tool's own trilinear
    default (leaving `interpolation` unset -- nipype's MCFLIRT only accepts
    'spline'/'nn'/'sinc' explicitly, passing 'trilinear' crashes construction,
    see the fix in fMRI_preproc_workflow.py). This scenario is the regression
    guard for that.
    """
    p = SCENARIOS["slicetiming_up"]
    synth = global_config[GlobalPrefCategoryList.SYNTH]
    synth["engine"] = "FSL"
    wf = fMRI_preproc_workflow(
        "fmri_0",
        dicom_dir=make_input_dir(),
        TR=p["TR"],
        slice_timing=p["slice_timing"],
        n_vols=p["n_vols"],
        del_start_vols=p["del_start"],
        del_end_vols=p["del_end"],
        hpcutoff=p["hp"],
        synth_config=synth,
        test_run=True,
    )

    config_echo = {
        "TR": p["TR"],
        "slice_timing": p["slice_timing"].name,
        "n_vols": p["n_vols"],
        "del_start_vols": p["del_start"],
        "del_end_vols": p["del_end"],
        "hpcutoff": p["hp"],
        "test_run": True,
    }
    graph_snapshot(
        wf,
        subdir=SUBDIR,
        name="test_run",
        config=config_echo,
        title="fmri_preproc / test_run",
    )


def _build_engine(global_config, make_input_dir, engine):
    """Build fMRI_preproc under a forced registration engine."""
    synth = global_config[GlobalPrefCategoryList.SYNTH]
    synth["engine"] = engine
    return fMRI_preproc_workflow(
        "fmri_0",
        dicom_dir=make_input_dir(),
        TR=2.0,
        slice_timing=SliceTiming.UNKNOWN,
        n_vols=100,
        del_start_vols=0,
        del_end_vols=0,
        hpcutoff=30,
        synth_config=synth,
    )


def test_fmri_preproc_exposes_reg_2_ref_ants(global_config, make_input_dir):
    """Under ANTS the func->ref registration is exposed as workflow.reg_2_ref
    (a RegistrationNodeWrapper) and is an AntsRegistration node, no FLIRT."""
    wf = _build_engine(global_config, make_input_dir, "ANTS")
    assert isinstance(wf.reg_2_ref, RegistrationNodeWrapper)
    assert wf.reg_2_ref.engine == RegistrationEngine.ANTS
    node_types = {_iface(n) for n in wf._graph.nodes()}
    assert "AntsRegistration" in node_types
    assert "FLIRT" not in node_types


def test_fmri_preproc_reg_2_ref_fsl_unchanged(global_config, make_input_dir):
    """Under FSL the construction is unchanged: a FLIRT node named
    <name>_2_ref_flirt (the historical consumer lookup name), no ANTs node,
    exposed as the same wrapper."""
    wf = _build_engine(global_config, make_input_dir, "FSL")
    assert isinstance(wf.reg_2_ref, RegistrationNodeWrapper)
    assert wf.reg_2_ref.engine == RegistrationEngine.FSL
    node_types = {_iface(n) for n in wf._graph.nodes()}
    assert "FLIRT" in node_types
    assert "AntsRegistration" not in node_types
    assert wf.get_node("fmri_0_2_ref_flirt") is not None


def test_fmri_preproc_reg_2_ref_synth_falls_back_to_fsl(global_config, make_input_dir):
    """EPI avoids SynthMorph: SYNTH resolves to FSL (a FLIRT node, no
    SynthMorphReg / AntsRegistration)."""
    wf = _build_engine(global_config, make_input_dir, "SYNTH")
    assert isinstance(wf.reg_2_ref, RegistrationNodeWrapper)
    assert wf.reg_2_ref.engine == RegistrationEngine.FSL
    node_types = {_iface(n) for n in wf._graph.nodes()}
    assert "FLIRT" in node_types
    assert "SynthMorphReg" not in node_types
    assert "AntsRegistration" not in node_types
