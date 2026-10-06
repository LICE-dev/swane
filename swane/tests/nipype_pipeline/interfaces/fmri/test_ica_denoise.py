import os
import numpy as np
import nibabel as nib
from swane.nipype_pipeline.interfaces.fmri.IcaDenoise import IcaDenoise


def test_ica_denoise(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    in_file = tmp_path / "in_file.nii.gz"
    mask_file = tmp_path / "mask.nii.gz"
    ic_mix = tmp_path / "ic_mix.txt"

    # Create synthetic 4D data (4x4x4x50)
    data = np.random.RandomState(0).randn(4, 4, 4, 50)
    nib.save(nib.Nifti1Image(data, np.eye(4)), in_file)

    mask = np.zeros((4, 4, 4))
    mask[1:3, 1:3, 1:3] = 1
    nib.save(nib.Nifti1Image(mask, np.eye(4)), mask_file)

    # Create mix (50x3)
    mix = np.random.RandomState(1).randn(50, 3)
    np.savetxt(ic_mix, mix)

    interface = IcaDenoise()
    interface.inputs.in_file = str(in_file)
    interface.inputs.mask_file = str(mask_file)
    interface.inputs.ic_mix = str(ic_mix)
    interface.inputs.motion_ics = [0, 2]  # regress out IC0 and IC2 (0-based)
    interface.inputs.aggressive = False

    result = interface.run()

    assert os.path.exists(result.outputs.denoised_file)
    out_img = nib.load(result.outputs.denoised_file)
    assert out_img.shape == (4, 4, 4, 50)
