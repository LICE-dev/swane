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


def _fake_templateflow(src):
    """sys.modules patch making ``import templateflow.api`` return ``src``."""
    fake_tf = MagicMock()
    fake_tf.get.return_value = str(src)
    # "import templateflow.api as tf" binds the "api" attribute of the package
    fake_pkg = MagicMock()
    fake_pkg.api = fake_tf
    return patch.dict(
        "sys.modules", {"templateflow": fake_pkg, "templateflow.api": fake_tf}
    )


def _write_template(path, axcodes_affine):
    import numpy as np
    import nibabel as nib

    nib.save(
        nib.Nifti1Image(np.zeros((2, 2, 2), np.float32), axcodes_affine), str(path)
    )


def _cache_entries(cache):
    """Files left in the cache directory, the fetch lock aside."""
    return sorted(
        p.name for p in cache.iterdir() if p.name != ".templateflow_fetch.lock"
    )


def test_las_template_is_copied_never_symlinked(tmp_path, monkeypatch):
    """The cache entry must be a real file: a symlink into the TemplateFlow
    cache dangles when that is purged and is refused by some filesystems
    (Windows without Developer Mode)."""
    import os
    import numpy as np

    src_dir = tmp_path / "tf"
    src_dir.mkdir()
    src = src_dir / "tpl-FakeMNI_res-01_desc-brain_T1w.nii.gz"
    _write_template(src, np.diag([-1.0, 1.0, 1.0, 1.0]))  # LAS

    def no_symlink(*args, **kwargs):
        raise AssertionError("the LAS cache must not use symlinks")

    monkeypatch.setattr(os, "symlink", no_symlink)
    cache = tmp_path / "cache"
    cache.mkdir()
    with patch.object(templates_module, "_SWANE_TEMPLATE_CACHE", cache):
        with _fake_templateflow(src):
            result = get_swane_template(
                name="FakeMNI", resolution=1, desc="brain", enforce_las=True
            )

    out = Path(result)
    assert out.exists() and not out.is_symlink()
    assert out.read_bytes() == src.read_bytes()
    assert _cache_entries(cache) == [out.name]


def test_partial_las_conversion_is_never_cached(tmp_path, monkeypatch):
    """A save interrupted halfway (killed process, full disk) must leave no
    final file: the unlocked fast path trusts ``exists()`` forever."""
    import numpy as np

    src = tmp_path / "tpl-FakeMNI_res-01_desc-brain_T1w.nii.gz"
    _write_template(src, np.diag([1.0, 1.0, 1.0, 1.0]))  # RAS: needs reorienting

    def torn_save(img, filename, *args, **kwargs):
        Path(filename).write_bytes(b"truncated")
        raise OSError("disk full")

    cache = tmp_path / "cache"
    cache.mkdir()
    monkeypatch.setattr(templates_module.nib, "save", torn_save)
    with patch.object(templates_module, "_SWANE_TEMPLATE_CACHE", cache):
        with _fake_templateflow(src):
            with pytest.raises(OSError):
                get_swane_template(
                    name="FakeMNI", resolution=1, desc="brain", enforce_las=True
                )
        assert _cache_entries(cache) == []
        assert not templates_module.is_template_cached("FakeMNI", 1, "brain")

        # The failure leaves nothing behind: the next call converts normally.
        monkeypatch.undo()
        with _fake_templateflow(src):
            result = get_swane_template(
                name="FakeMNI", resolution=1, desc="brain", enforce_las=True
            )
    assert Path(result).stat().st_size > len(b"truncated")
    assert _cache_entries(cache) == [Path(result).name]


def test_partial_copy_of_a_las_template_is_never_cached(tmp_path, monkeypatch):
    import numpy as np

    src = tmp_path / "tpl-FakeMNI_res-01_desc-brain_T1w.nii.gz"
    _write_template(src, np.diag([-1.0, 1.0, 1.0, 1.0]))  # already LAS

    def torn_copy(source, destination, *args, **kwargs):
        Path(destination).write_bytes(b"truncated")
        raise OSError("disk full")

    cache = tmp_path / "cache"
    cache.mkdir()
    monkeypatch.setattr(templates_module.shutil, "copyfile", torn_copy)
    with patch.object(templates_module, "_SWANE_TEMPLATE_CACHE", cache):
        with _fake_templateflow(src):
            with pytest.raises(OSError):
                get_swane_template(
                    name="FakeMNI", resolution=1, desc="brain", enforce_las=True
                )
    assert _cache_entries(cache) == []


def test_partial_computed_brain_template_is_never_cached(tmp_path, monkeypatch):
    import numpy as np

    t1w = tmp_path / "t1w.nii.gz"
    mask = tmp_path / "mask.nii.gz"
    _write_template(t1w, np.diag([1.0, 1.0, 1.0, 1.0]))
    _write_template(mask, np.diag([1.0, 1.0, 1.0, 1.0]))
    fake_tf = MagicMock()
    fake_tf.get.side_effect = lambda *a, **k: str(
        mask if k.get("suffix") == "mask" else t1w
    )
    fake_pkg = MagicMock()
    fake_pkg.api = fake_tf

    def torn_save(img, filename, *args, **kwargs):
        Path(filename).write_bytes(b"truncated")
        raise OSError("disk full")

    cache = tmp_path / "cache"
    cache.mkdir()
    monkeypatch.setattr(templates_module.nib, "save", torn_save)
    with patch.object(templates_module, "_SWANE_TEMPLATE_CACHE", cache), patch.dict(
        "sys.modules", {"templateflow": fake_pkg, "templateflow.api": fake_tf}
    ):
        with pytest.raises(OSError):
            _compute_brain_template("FakeMNI", 1, enforce_las=True)
    assert _cache_entries(cache) == []


def test_template_cache_helpers_describe_the_cached_las_file(tmp_path):
    with patch.object(templates_module, "_SWANE_TEMPLATE_CACHE", tmp_path):
        path = templates_module.template_cache_path("FakeMNI", 2, "brain")
        assert path == tmp_path / "FakeMNI_res-2_desc-brain_T1w_LAS.nii.gz"
        assert not templates_module.is_template_cached("FakeMNI", 2, "brain")
        path.touch()
        assert templates_module.is_template_cached("FakeMNI", 2, "brain")
        # The suffix is part of the cache key.
        assert not templates_module.is_template_cached("FakeMNI", 2, "brain", "T2w")


def test_get_swane_template_returns_the_helper_path(tmp_path):
    """The fast path and the helper must name the same file: the generate
    worker decides whether to show the download message from the helper."""
    with patch.object(templates_module, "_SWANE_TEMPLATE_CACHE", tmp_path):
        expected = templates_module.template_cache_path("FakeMNI", 1, "brain")
        expected.touch()
        assert get_swane_template("FakeMNI", 1, "brain") == str(expected)
