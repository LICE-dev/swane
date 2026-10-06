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
