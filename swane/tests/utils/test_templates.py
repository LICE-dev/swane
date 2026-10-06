import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

import swane.utils.templates as templates_module
from swane.utils.templates import get_swane_template, _compute_brain_template


def test_get_swane_template_bypasses_templateflow_if_cached(tmp_path):
    """
    If the LAS converted file already exists in the SWANe cache,
    get_swane_template should return immediately without importing
    or calling templateflow.api.
    """
    with patch.object(templates_module, "_SWANE_TEMPLATE_CACHE", tmp_path):
        name = "FakeMNI"
        resolution = 1
        desc = "brain"
        suffix = "T1w"

        expected_filename = f"{name}_res-{resolution}_desc-{desc}_{suffix}_LAS.nii.gz"
        expected_path = tmp_path / expected_filename
        expected_path.touch()

        # If the code tries to use templateflow.api, it will call this mock
        fake_tf = MagicMock()

        with patch.dict("sys.modules", {"templateflow.api": fake_tf}):
            result = get_swane_template(
                name=name,
                resolution=resolution,
                desc=desc,
                suffix=suffix,
                enforce_las=True,
            )

            assert result == str(expected_path)
            fake_tf.get.assert_not_called()


def test_compute_brain_template_bypasses_templateflow_if_cached(tmp_path):
    """
    Same for _compute_brain_template.
    """
    with patch.object(templates_module, "_SWANE_TEMPLATE_CACHE", tmp_path):
        name = "FakeMNI"
        resolution = 1

        expected_filename = f"{name}_res-{resolution}_desc-brain_T1w_LAS.nii.gz"
        expected_path = tmp_path / expected_filename
        expected_path.touch()

        fake_tf = MagicMock()

        with patch.dict("sys.modules", {"templateflow.api": fake_tf}):
            result = _compute_brain_template(
                name=name, resolution=resolution, enforce_las=True
            )

            assert result == str(expected_path)
            fake_tf.get.assert_not_called()


def test_las_template_falls_back_to_copy_without_symlink_rights(tmp_path, monkeypatch):
    """Windows without Developer Mode cannot create symlinks: the already-LAS
    template must then be copied into the SWANe cache instead of crashing."""
    import os
    import numpy as np
    import nibabel as nib

    src_dir = tmp_path / "tf"
    src_dir.mkdir()
    src = src_dir / "tpl-FakeMNI_res-01_desc-brain_T1w.nii.gz"
    affine = np.diag([-1.0, 1.0, 1.0, 1.0])  # LAS
    nib.save(nib.Nifti1Image(np.zeros((2, 2, 2), np.float32), affine), str(src))

    cache = tmp_path / "cache"
    cache.mkdir()
    fake_tf = MagicMock()
    fake_tf.get.return_value = str(src)
    # "import templateflow.api as tf" binds the "api" attribute of the package
    fake_pkg = MagicMock()
    fake_pkg.api = fake_tf

    def no_symlink(*args, **kwargs):
        raise OSError(1314, "A required privilege is not held by the client")

    monkeypatch.setattr(os, "symlink", no_symlink)
    with patch.object(templates_module, "_SWANE_TEMPLATE_CACHE", cache), patch.dict(
        "sys.modules", {"templateflow": fake_pkg, "templateflow.api": fake_tf}
    ):
        result = get_swane_template(
            name="FakeMNI", resolution=1, desc="brain", enforce_las=True
        )

    out = Path(result)
    assert out.exists() and not out.is_symlink()
    assert out.read_bytes() == src.read_bytes()
