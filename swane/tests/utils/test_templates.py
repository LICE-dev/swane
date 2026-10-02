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
