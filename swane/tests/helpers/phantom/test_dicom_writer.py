"""Unit tests for :mod:`swane.tests.helpers.phantom.dicom_writer`."""

import numpy as np
import pydicom

from swane.tests.helpers.phantom.dicom_writer import write_volume_series


class TestDiffusionGradientFrame:
    """``bvecs`` are given in RAS like the affine, while DICOM's
    ``DiffusionGradientOrientation`` is in the patient (LPS) frame: the writer
    must convert them, as it converts the geometry. Writing RAS vectors as LPS
    mirrors x and y of every gradient, which the RAS phantom grid used to hide
    behind ForceOrient's unreoriented b-vectors."""

    def test_gradients_are_written_in_lps(self, tmp_path):
        bvals = [0.0, 1000.0, 1000.0]
        bvecs_ras = np.array([[0.0, 0.0, 0.0], [0.6, 0.48, 0.64], [-0.8, 0.0, 0.6]])
        data = np.full((4, 4, 10, 3), 100.0)
        paths = write_volume_series(
            str(tmp_path), data, np.eye(4), bvals=bvals, bvecs=bvecs_ras
        )

        n_slices = data.shape[2]
        for t in (1, 2):
            ds = pydicom.dcmread(paths[t * n_slices])
            assert int(ds.TemporalPositionIdentifier) == t + 1
            assert np.allclose(
                [float(v) for v in ds.DiffusionGradientOrientation],
                bvecs_ras[t] * [-1.0, -1.0, 1.0],
            )
