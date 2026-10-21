import os
import pytest
import numpy as np
import nibabel as nib
import pandas as pd
from nipype.interfaces.base import Bunch
from swane.nipype_pipeline.interfaces.fmri.NilearnFirstLevel import NilearnFirstLevel


def test_nilearn_first_level(tmp_path, monkeypatch):
    # The interface writes its outputs to the current directory.
    monkeypatch.chdir(tmp_path)
    preproc_file = tmp_path / "preproc.nii.gz"
    mask_file = tmp_path / "mask.nii.gz"
    motion_file = tmp_path / "motion.par"
    outlier_file = tmp_path / "outliers.txt"

    # Synthetic 4D data (5x5x5x30)
    data = np.random.RandomState(0).randn(5, 5, 5, 30)
    data[1:4, 1:4, 1:4, 10:20] += 5.0  # Synthetic activation
    nib.save(nib.Nifti1Image(data, np.eye(4)), preproc_file)

    mask = np.zeros((5, 5, 5))
    mask[1:4, 1:4, 1:4] = 1
    nib.save(nib.Nifti1Image(mask, np.eye(4)), mask_file)

    # Motion params (30x6)
    motion = np.zeros((30, 6))
    np.savetxt(motion_file, motion, fmt="%.6f")

    # Outliers
    with open(outlier_file, "w") as f:
        f.write("5\n15\n")

    # Events from FMRIGenSpec (Bunch)
    events = Bunch(conditions=["TaskA"], onsets=[[10]], durations=[[10]])

    # Contrasts from FMRIGenSpec
    contrasts = [["TaskA", "T", ["TaskA"], [1]]]

    interface = NilearnFirstLevel()
    interface.inputs.in_file = str(preproc_file)
    interface.inputs.mask_file = str(mask_file)
    interface.inputs.tr = 2.0
    interface.inputs.subject_info = events
    interface.inputs.realignment_parameters = str(motion_file)
    interface.inputs.outlier_files = str(outlier_file)
    interface.inputs.contrasts = contrasts

    result = interface.run()

    # Outputs to check
    # one z-map per contrast plus fixed-z cluster-extent thresholded maps at 3.1 / 5 / 7
    # So for 1 contrast, we expect 3 thresholded maps + 1 z-map
    assert hasattr(result.outputs, "zstats")
    assert hasattr(result.outputs, "threshold_file_cont1_thresh1")
    assert hasattr(result.outputs, "threshold_file_cont1_thresh2")
    assert hasattr(result.outputs, "threshold_file_cont1_thresh3")

    zstats = result.outputs.zstats
    assert isinstance(zstats, list)
    assert len(zstats) == 1
    assert os.path.exists(zstats[0])

    t1 = result.outputs.threshold_file_cont1_thresh1
    t2 = result.outputs.threshold_file_cont1_thresh2
    t3 = result.outputs.threshold_file_cont1_thresh3

    assert os.path.exists(t1)
    assert os.path.exists(t2)
    assert os.path.exists(t3)


def test_slice_time_ref_default():
    assert NilearnFirstLevel().inputs.slice_time_ref == 0.0


@pytest.mark.parametrize("slice_time_ref", [None, 0.5])
def test_slice_time_ref_reaches_first_level_model(
    tmp_path, monkeypatch, slice_time_ref
):
    """The input is forwarded to nilearn's FirstLevelModel (default 0.0)."""
    import nilearn.glm.first_level as first_level

    seen = {}
    real_model = first_level.FirstLevelModel

    def recording_model(*args, **kwargs):
        seen.update(kwargs)
        return real_model(*args, **kwargs)

    monkeypatch.setattr(first_level, "FirstLevelModel", recording_model)
    monkeypatch.chdir(tmp_path)

    data = np.random.RandomState(0).randn(5, 5, 5, 30)
    nib.save(nib.Nifti1Image(data, np.eye(4)), tmp_path / "preproc.nii.gz")
    mask = np.zeros((5, 5, 5))
    mask[1:4, 1:4, 1:4] = 1
    nib.save(nib.Nifti1Image(mask, np.eye(4)), tmp_path / "mask.nii.gz")
    np.savetxt(tmp_path / "motion.par", np.zeros((30, 6)), fmt="%.6f")
    (tmp_path / "outliers.txt").write_text("5\n")

    interface = NilearnFirstLevel()
    interface.inputs.in_file = str(tmp_path / "preproc.nii.gz")
    interface.inputs.mask_file = str(tmp_path / "mask.nii.gz")
    interface.inputs.tr = 2.0
    interface.inputs.subject_info = Bunch(
        conditions=["TaskA"], onsets=[[10]], durations=[[10]]
    )
    interface.inputs.realignment_parameters = str(tmp_path / "motion.par")
    interface.inputs.outlier_files = str(tmp_path / "outliers.txt")
    interface.inputs.contrasts = [["TaskA", "T", ["TaskA"], [1]]]
    if slice_time_ref is not None:
        interface.inputs.slice_time_ref = slice_time_ref
    interface.run()

    assert seen["slice_time_ref"] == (slice_time_ref or 0.0)


# --- Free-text task names -------------------------------------------------
# The task names are free text preferences. nilearn evaluates the contrast
# expression as Python code and names the design matrix columns after the
# conditions, so they must not reach it as they are.

N_VOLS = 40
ONSETS_A = [10, 50]
ONSETS_B = [30, 70]


def _synthetic_inputs(directory):
    """4D data: noise plus an A-locked response and a B-locked (negative) one.

    Both responses are the SPM-HRF regressors of the block design, so the
    contrasts below have a known sign and a clearly non-null z in the mask.
    """
    from nilearn.glm.first_level import make_first_level_design_matrix

    events = pd.DataFrame(
        [("A", o, 10) for o in ONSETS_A] + [("B", o, 10) for o in ONSETS_B],
        columns=["trial_type", "onset", "duration"],
    )
    design = make_first_level_design_matrix(
        np.arange(N_VOLS) * 2.0, events, hrf_model="spm", drift_model=None
    )
    data = np.random.RandomState(0).randn(5, 5, 5, N_VOLS)
    data[1:4, 1:4, 1:4, :] += 3.0 * design["A"].to_numpy()
    data[1:4, 1:4, 1:4, :] -= 2.0 * design["B"].to_numpy()
    nib.save(nib.Nifti1Image(data, np.eye(4)), directory / "preproc.nii.gz")
    mask = np.zeros((5, 5, 5))
    mask[1:4, 1:4, 1:4] = 1
    nib.save(nib.Nifti1Image(mask, np.eye(4)), directory / "mask.nii.gz")
    np.savetxt(directory / "motion.par", np.zeros((N_VOLS, 6)), fmt="%.6f")
    (directory / "outliers.txt").write_text("5\n")


def _run_first_level(directory, monkeypatch, task_names):
    """Run the node in ``directory``; one task -> A vs rest, two -> A-B and B-A."""
    _synthetic_inputs(directory)
    monkeypatch.chdir(directory)
    if len(task_names) == 1:
        (a,) = task_names
        subject_info = Bunch(conditions=[a], onsets=[ONSETS_A], durations=[[10]])
        contrasts = [["%s_versus_Rest" % a, "T", [a], [1]]]
    else:
        a, b = task_names
        subject_info = Bunch(
            conditions=[a, b], onsets=[ONSETS_A, ONSETS_B], durations=[[10], [10]]
        )
        contrasts = [
            ["%s_versus_%s" % (a, b), "T", [a, b], [1, -1]],
            ["%s_versus_%s" % (b, a), "T", [a, b], [-1, 1]],
        ]
    interface = NilearnFirstLevel()
    interface.inputs.in_file = str(directory / "preproc.nii.gz")
    interface.inputs.mask_file = str(directory / "mask.nii.gz")
    interface.inputs.tr = 2.0
    interface.inputs.subject_info = subject_info
    interface.inputs.realignment_parameters = str(directory / "motion.par")
    interface.inputs.outlier_files = str(directory / "outliers.txt")
    interface.inputs.contrasts = contrasts
    return interface.run().outputs, contrasts


def _zmap(path):
    return nib.load(path).get_fdata()


@pytest.mark.parametrize(
    "task_name",
    [
        "finger-tapping",  # hyphen: read as a subtraction
        "2back",  # starts with a digit
        "a.b",  # attribute access
        "class",  # Python keyword
        "constant",  # nilearn's own design matrix column
        "mot00",  # a motion confound column
        "été",  # accents are fine as-is
    ],
)
def test_task_names_that_are_not_python_identifiers(tmp_path, monkeypatch, task_name):
    outputs, contrasts = _run_first_level(tmp_path, monkeypatch, (task_name,))

    # the files keep the user's name: only the nilearn-facing labels are internal
    assert [os.path.basename(z) for z in outputs.zstats] == [
        "z_%s_versus_Rest.nii.gz" % task_name
    ]
    zmap = _zmap(outputs.zstats[0])
    assert np.isfinite(zmap).all()
    # the A-locked signal in the mask is actually found, not a null map
    assert zmap[2, 2, 2] > 3.0


def test_two_task_names_give_opposite_contrasts(tmp_path, monkeypatch):
    outputs, _ = _run_first_level(tmp_path, monkeypatch, ("finger-tapping", "2back"))

    a_vs_b, b_vs_a = (_zmap(z) for z in outputs.zstats)
    assert a_vs_b[2, 2, 2] > 3.0
    np.testing.assert_allclose(a_vs_b, -b_vs_a)


def test_task_names_do_not_change_the_numbers(tmp_path, monkeypatch):
    """Same design under a valid and an invalid name: identical z-maps."""
    valid_dir = tmp_path / "valid"
    other_dir = tmp_path / "other"
    valid_dir.mkdir()
    other_dir.mkdir()

    valid, _ = _run_first_level(valid_dir, monkeypatch, ("Task_A", "Task_B"))
    other, _ = _run_first_level(other_dir, monkeypatch, ("finger-tapping", "2back"))

    assert len(valid.zstats) == len(other.zstats) == 2
    for z_valid, z_other in zip(valid.zstats, other.zstats):
        np.testing.assert_array_equal(_zmap(z_valid), _zmap(z_other))
    for key in (
        "threshold_file_cont1_thresh1",
        "threshold_file_cont2_thresh2",
        "threshold_file_cont2_thresh3",
    ):
        np.testing.assert_array_equal(
            _zmap(getattr(valid, key)), _zmap(getattr(other, key))
        )
