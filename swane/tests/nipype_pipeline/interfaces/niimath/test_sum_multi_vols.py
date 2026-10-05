"""SumMultiVols writes every volume after the first into its op_string.

Nipype quotes the first volume (it becomes ``in_file``) but not the paths the
interface concatenates itself. On Windows, where SWANe allows blank spaces in
the subject path, those are quoted for cmd.exe; Linux/macOS command lines are
unchanged.
"""

import nibabel as nib
import numpy as np
import pytest
from nipype.interfaces.base import core as nipype_core

import swane.patches.nipype_patches as nipype_patches
from swane.nipype_pipeline.interfaces.niimath.maths import NIIMATH_CMD
from swane.nipype_pipeline.interfaces.niimath.SumMultiVols import SumMultiVols
from swane.patches import windows_compat


@pytest.fixture
def volumes(tmp_path):
    folder = tmp_path / "sub ject"
    folder.mkdir()
    image = nib.Nifti1Image(np.zeros((2, 2, 2), np.float32), np.eye(4))
    paths = []
    for i in range(3):
        path = folder / ("vol %d.nii.gz" % i)
        nib.save(image, str(path))
        paths.append(str(path))
    return paths


def _sum(volumes, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    return SumMultiVols(vol_files=volumes, out_file="sum.nii.gz")


@pytest.mark.skipif(
    windows_compat.is_windows(),
    reason="on real Windows the quoting proxy is installed at import time",
)
def test_posix_command_line_is_unchanged(volumes, monkeypatch, tmp_path):
    monkeypatch.setattr(windows_compat, "is_windows", lambda: False)
    node = _sum(volumes, monkeypatch, tmp_path)
    assert node.cmdline == "%s '%s' -add %s -add %s  %s" % (
        NIIMATH_CMD,
        volumes[0],
        volumes[1],
        volumes[2],
        "sum.nii.gz",
    )


def test_windows_quotes_every_volume(volumes, monkeypatch, tmp_path):
    monkeypatch.setattr(windows_compat, "is_windows", lambda: True)
    monkeypatch.setattr(nipype_core, "shlex", nipype_core.shlex)
    assert nipype_patches.install_windows_cmdline_quoting() is True

    node = _sum(volumes, monkeypatch, tmp_path)
    tokens = windows_compat.windows_split(node.cmdline)
    assert tokens[1:] == [
        volumes[0],
        "-add",
        volumes[1],
        "-add",
        volumes[2],
        "sum.nii.gz",
    ]
