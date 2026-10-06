import os
import numpy as np
import nibabel as nib
from swane.nipype_pipeline.interfaces.fmri.NilearnSmooth import NilearnSmooth


def test_nilearn_smooth(tmp_path):
    data = np.random.rand(10, 10, 10, 4)
    mask_data = np.ones((10, 10, 10))
    affine = np.eye(4)

    in_file = str(tmp_path / "func.nii.gz")
    nib.save(nib.Nifti1Image(data, affine), in_file)

    mask_file = str(tmp_path / "mask.nii.gz")
    nib.save(nib.Nifti1Image(mask_data, affine), mask_file)

    interface = NilearnSmooth()
    interface.inputs.in_file = in_file
    interface.inputs.mask_file = mask_file

    result = interface.run(cwd=str(tmp_path))

    assert os.path.exists(result.outputs.out_file)
    out_img = nib.load(result.outputs.out_file)
    assert out_img.shape == (10, 10, 10, 4)
