import os
import numpy as np
import nibabel as nib
from swane.nipype_pipeline.interfaces.fmri.GgmThreshold import GgmThreshold


def test_ggm_threshold(tmp_path, monkeypatch):
    # The interface writes its outputs to the current directory.
    monkeypatch.chdir(tmp_path)
    zstat_file = tmp_path / "zstat.nii.gz"
    mask_file = tmp_path / "mask.nii.gz"

    # 5x5x5x2
    z_vol = np.random.RandomState(0).randn(5, 5, 5, 2)
    # add some strong signal
    z_vol[2:4, 2:4, 2:4, 0] += 5.0
    nib.save(nib.Nifti1Image(z_vol, np.eye(4)), zstat_file)

    mask = np.zeros((5, 5, 5))
    mask[1:4, 1:4, 1:4] = 1
    nib.save(nib.Nifti1Image(mask, np.eye(4)), mask_file)

    interface = GgmThreshold()
    interface.inputs.zstat_file = str(zstat_file)
    interface.inputs.mask_file = str(mask_file)
    interface.inputs.mm_thresh = 0.5

    result = interface.run()

    assert len(result.outputs.thresh_zstat_files) == 2
    for f in result.outputs.thresh_zstat_files:
        assert os.path.exists(f)
    out_img = nib.load(result.outputs.thresh_zstat_files[0])
    assert out_img.shape == (5, 5, 5)
