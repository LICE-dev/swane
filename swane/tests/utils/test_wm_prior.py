import os
import pytest
import nibabel as nib
import numpy as np

from swane.utils.templates import get_swane_template
from swane.utils.wm_prior import nlin6_wm_prior, WM_PROBSEG_THRESHOLD


@pytest.mark.heavy
def test_wm_prior_heavy(tmp_path):
    try:
        import templateflow.api as tf

        tf.get("MNI152NLin2009cAsym", resolution=2, label="WM", suffix="probseg")
        get_swane_template(
            name="MNI152NLin6Asym",
            resolution=2,
            desc="brain",
            enforce_las=True,
        )
    except Exception as e:
        pytest.skip(f"TemplateFlow not available: {e}")

    out_file = nlin6_wm_prior(cache_dir=str(tmp_path))
    assert os.path.exists(out_file)

    img = nib.load(out_file)
    data = np.asarray(img.dataobj)

    assert np.any(data > 0)
    assert set(np.unique(data)) <= {0, 1}
    assert img.get_data_dtype() == np.uint8

    # Same grid used as the reg_2_mni fixed image in fMRI_resting_state_workflow.py.
    ref_path = get_swane_template(
        name="MNI152NLin6Asym", resolution=2, desc="brain", enforce_las=True
    )
    ref_img = nib.load(ref_path)

    assert img.shape == ref_img.shape
    assert np.allclose(img.affine, ref_img.affine)


def test_wm_prior_light(tmp_path, monkeypatch):
    import nibabel as nib
    import numpy as np

    shape = (10, 10, 10)
    affine = np.eye(4)

    dummy_tf = tmp_path / "dummy_tf.nii.gz"
    nib.save(nib.Nifti1Image(np.zeros(shape), affine), str(dummy_tf))

    def mock_tf_get(*args, **kwargs):
        return str(dummy_tf)

    def mock_get_swane_template(*args, **kwargs):
        return str(dummy_tf)

    monkeypatch.setattr("templateflow.api.get", mock_tf_get)
    monkeypatch.setattr(
        "swane.utils.wm_prior.get_swane_template", mock_get_swane_template
    )

    import ants

    # Values straddling WM_PROBSEG_THRESHOLD on both sides, to exercise the
    # binarisation boundary rather than an all-above or all-below fixture.
    probseg = np.full(shape, WM_PROBSEG_THRESHOLD - 0.1)
    probseg[:5] = WM_PROBSEG_THRESHOLD + 0.1

    def mock_apply_transforms(*args, **kwargs):
        return ants.from_numpy(probseg)

    monkeypatch.setattr("ants.apply_transforms", mock_apply_transforms)

    out = nlin6_wm_prior(cache_dir=str(tmp_path))
    assert os.path.exists(out)
    assert out.startswith(str(tmp_path))

    img = nib.load(out)
    data = np.asarray(img.dataobj)
    assert set(np.unique(data)) == {0, 1}
    assert img.get_data_dtype() == np.uint8
    assert np.array_equal(data, (probseg > WM_PROBSEG_THRESHOLD).astype(np.uint8))

    monkeypatch.delattr("ants.apply_transforms")
    out2 = nlin6_wm_prior(cache_dir=str(tmp_path))
    assert out2 == out


def test_wm_prior_does_not_hold_the_template_lock(tmp_path, monkeypatch):
    """The reference grid is fetched through get_swane_template, which takes
    the same cache lock: nlin6_wm_prior must not hold that lock meanwhile
    (a second FileLock on the same file in one process never acquires)."""
    import ants
    from filelock import FileLock, Timeout

    shape = (4, 4, 4)
    dummy = tmp_path / "dummy.nii.gz"
    nib.save(nib.Nifti1Image(np.zeros(shape), np.eye(4)), str(dummy))

    def locking_get_swane_template(*args, **kwargs):
        # Same lock file as swane.utils.templates for this cache directory.
        lock = FileLock(str(tmp_path / ".templateflow_fetch.lock"))
        try:
            with lock.acquire(timeout=2):
                return str(dummy)
        except Timeout:
            pytest.fail("get_swane_template called while the lock is held")

    monkeypatch.setattr("templateflow.api.get", lambda *a, **k: str(dummy))
    monkeypatch.setattr(
        "swane.utils.wm_prior.get_swane_template", locking_get_swane_template
    )
    monkeypatch.setattr(
        "ants.apply_transforms", lambda *a, **k: ants.from_numpy(np.ones(shape))
    )

    out = nlin6_wm_prior(cache_dir=str(tmp_path))
    assert os.path.exists(out)


def test_wm_prior_write_is_atomic(tmp_path, monkeypatch):
    """The prior is written to a temporary file in the cache directory and
    renamed: a write interrupted half-way never leaves a partial file at the
    cached path, which the lock-free fast path would return to every later
    run."""
    import ants
    from swane.utils.wm_prior import PRIOR

    shape = (4, 4, 4)
    dummy = tmp_path / "dummy.nii.gz"
    nib.save(nib.Nifti1Image(np.zeros(shape), np.eye(4)), str(dummy))
    monkeypatch.setattr("templateflow.api.get", lambda *a, **k: str(dummy))
    monkeypatch.setattr(
        "swane.utils.wm_prior.get_swane_template", lambda *a, **k: str(dummy)
    )
    monkeypatch.setattr(
        "ants.apply_transforms", lambda *a, **k: ants.from_numpy(np.ones(shape))
    )

    cache = tmp_path / "cache"
    out = str(cache / PRIOR)
    real_write = ants.image_write
    written = []

    def interrupted_write(image, filename, *args, **kwargs):
        written.append(filename)
        with open(filename, "wb") as fh:
            fh.write(b"\x1f\x8b partial")
        raise KeyboardInterrupt("killed during the write")

    monkeypatch.setattr("ants.image_write", interrupted_write)
    with pytest.raises(KeyboardInterrupt):
        nlin6_wm_prior(cache_dir=str(cache))

    assert written and written[0] != out
    assert os.path.dirname(written[0]) == str(cache)
    assert not os.path.exists(out)
    assert not os.path.exists(written[0])

    monkeypatch.setattr("ants.image_write", real_write)
    assert nlin6_wm_prior(cache_dir=str(cache)) == out
    assert np.asarray(nib.load(out).dataobj).all()
    # No leftover temporary/partial file. The filelock lock file is ignored: it
    # persists on POSIX but is deleted on release on Windows.
    assert [n for n in os.listdir(cache) if n != ".templateflow_fetch.lock"] == [PRIOR]
