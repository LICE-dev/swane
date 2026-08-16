"""Settings matrix for
:func:`swane.nipype_pipeline.workflows.fMRI_preproc_workflow.fMRI_preproc_workflow`.

The shared fMRI preprocessing chain (trim, motion-correct, slice-timing, SUSAN
smoothing, highpass, coregistration). It takes scalar parameters directly, so
the matrix sweeps the ``slice_timing`` enum and start/end volume trimming,
recording snapshots under ``snapshots/fmri_preproc/``.
"""

import pytest

from swane.config.config_enums import SliceTiming
from swane.nipype_pipeline.workflows.fMRI_preproc_workflow import fMRI_preproc_workflow

SUBDIR = "fmri_preproc"

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
def test_fmri_preproc_matrix(scenario, make_input_dir, graph_snapshot):
    p = SCENARIOS[scenario]
    wf = fMRI_preproc_workflow(
        "fmri_0",
        dicom_dir=make_input_dir(),
        TR=p["TR"],
        slice_timing=p["slice_timing"],
        n_vols=p["n_vols"],
        del_start_vols=p["del_start"],
        del_end_vols=p["del_end"],
        hpcutoff=p["hp"],
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


def test_fmri_preproc_matrix_test_run(make_input_dir, graph_snapshot):
    """test_run=True: MCFLIRT drops to stages=1 with the tool's own trilinear
    default (leaving `interpolation` unset -- nipype's MCFLIRT only accepts
    'spline'/'nn'/'sinc' explicitly, passing 'trilinear' crashes construction,
    see the fix in fMRI_preproc_workflow.py). This scenario is the regression
    guard for that.
    """
    p = SCENARIOS["slicetiming_up"]
    wf = fMRI_preproc_workflow(
        "fmri_0",
        dicom_dir=make_input_dir(),
        TR=p["TR"],
        slice_timing=p["slice_timing"],
        n_vols=p["n_vols"],
        del_start_vols=p["del_start"],
        del_end_vols=p["del_end"],
        hpcutoff=p["hp"],
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
