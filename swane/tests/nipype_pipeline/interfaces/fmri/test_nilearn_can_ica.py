import os
import numpy as np
import nibabel as nib
from swane.nipype_pipeline.interfaces.fmri.NilearnCanICA import NilearnCanICA


def test_nilearn_can_ica(tmp_path, monkeypatch):
    # The interface writes its outputs to the current directory.
    monkeypatch.chdir(tmp_path)
    preproc_file = tmp_path / "preproc.nii.gz"
    mask_file = tmp_path / "mask.nii.gz"

    # Create synthetic 4D data (5x5x5x60)
    data = np.random.RandomState(0).randn(5, 5, 5, 60)
    data[1:3, 1:3, 1:3, :] += np.sin(np.linspace(0, 10, 60))
    data[2:4, 2:4, 2:4, :] += np.cos(np.linspace(0, 20, 60))
    nib.save(nib.Nifti1Image(data, np.eye(4)), preproc_file)

    mask = np.zeros((5, 5, 5))
    mask[1:4, 1:4, 1:4] = 1
    nib.save(nib.Nifti1Image(mask, np.eye(4)), mask_file)

    interface = NilearnCanICA()
    interface.inputs.preproc_file = str(preproc_file)
    interface.inputs.mask_file = str(mask_file)
    interface.inputs.n_components = 2

    result = interface.run()

    assert os.path.exists(result.outputs.components_file)
    out_img = nib.load(result.outputs.components_file)
    # Output should have 4 dimensions, 4th dim is n_components
    assert out_img.shape == (5, 5, 5, 2)
