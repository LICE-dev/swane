import os
import numpy as np
import nibabel as nib
import pytest
from swane.nipype_pipeline.interfaces.ants.AntsMotionCorrection import (
    AntsMotionCorrection,
)


def test_ants_motion_correction(tmp_path):
    """
    Test AntsMotionCorrection interface.
    Given a synthetic 4D NIfTI, it should output a motion-corrected file
    of the same shape, and a par_file with shape (nvols, 6).
    """
    # Create a synthetic 4D EPI image (small to keep tests fast)
    data = np.random.rand(10, 10, 10, 4)
    affine = np.eye(4)
    img = nib.Nifti1Image(data, affine)
    in_file = str(tmp_path / "func.nii.gz")
    nib.save(img, in_file)

    # Initialize interface
    interface = AntsMotionCorrection()
    interface.inputs.in_file = in_file

    # Run interface
    result = interface.run(cwd=str(tmp_path))

    # Assert outputs exist
    assert os.path.exists(result.outputs.out_file)
    assert os.path.exists(result.outputs.par_file)

    # Assert out_file shape matches in_file
    out_img = nib.load(result.outputs.out_file)
    assert out_img.shape == (10, 10, 10, 4)

    # Assert par_file shape is (nvols, 6)
    params = np.loadtxt(result.outputs.par_file)
    assert params.shape == (4, 6)


def _synthetic_moving_series(path, n=32, n_vols=6):
    """Write a small 4D series of a smooth blob with random rigid jitter.

    Random metric sampling and multithreaded ITK make an unseeded ANTs rigid
    registration differ run to run on this input (32x32x16, 6 volumes is the
    smallest size tried that shows it); the per-volume jitter gives the
    optimiser real work to do.
    """
    from scipy import ndimage

    rng = np.random.default_rng(0)
    x, y, z = np.mgrid[:n, :n, : n // 2]
    base = 1000 * np.exp(
        -(
            ((x - n / 2) / (n / 4)) ** 2
            + ((y - n / 2) / (n / 5)) ** 2
            + ((z - n / 4) / (n / 8)) ** 2
        )
    )
    base += 300 * (((x - n / 2) ** 2 + (y - n / 2) ** 2) < (n / 3) ** 2)
    vols = []
    for _ in range(n_vols):
        vol = ndimage.shift(base, rng.normal(0, 0.8, 3), order=1)
        vol = ndimage.rotate(vol, rng.normal(0, 2), axes=(0, 1), reshape=False, order=1)
        vols.append(vol + rng.normal(0, 20, vol.shape))
    data = np.stack(vols, -1).astype(np.float32)
    nib.save(nib.Nifti1Image(data, np.diag([3.0, 3.0, 3.0, 1.0])), str(path))
    return str(path)


def _run_in(tmp_path, name, in_file, **inputs):
    run_dir = tmp_path / name
    run_dir.mkdir()
    interface = AntsMotionCorrection(in_file=in_file, **inputs)
    result = interface.run(cwd=str(run_dir))
    image = np.asanyarray(nib.load(result.outputs.out_file).dataobj)
    with open(result.outputs.par_file, "rb") as handle:
        par_bytes = handle.read()
    return image, par_bytes


def test_ants_motion_correction_default_seed_is_fixed():
    assert AntsMotionCorrection().inputs.random_seed == 123


def test_ants_motion_correction_is_deterministic(tmp_path):
    """Two runs on the same input give bit-identical outputs."""
    in_file = _synthetic_moving_series(tmp_path / "func.nii.gz")

    image_1, par_1 = _run_in(tmp_path, "run1", in_file)
    image_2, par_2 = _run_in(tmp_path, "run2", in_file)

    assert np.array_equal(image_1, image_2), "motion corrected images differ"
    assert par_1 == par_2, "realignment parameters differ"


def test_ants_motion_correction_leaves_process_state_unchanged(tmp_path, monkeypatch):
    """The single-thread/seed setup never leaks into the calling process."""
    import ants

    monkeypatch.setenv("ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS", "7")
    monkeypatch.delenv("ANTS_RANDOM_SEED", raising=False)
    seed_before = ants.config._random_seed
    in_file = _synthetic_moving_series(tmp_path / "func.nii.gz", n=16, n_vols=2)

    _run_in(tmp_path, "run", in_file)

    assert os.environ["ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS"] == "7"
    assert "ANTS_RANDOM_SEED" not in os.environ
    assert ants.config._random_seed == seed_before


def test_nilearn_preproc_motion_correct_node_uses_one_core():
    """The single-threaded registration is accounted as one core."""
    from swane.config.config_enums import FmriEngine, SliceTiming
    from swane.nipype_pipeline.workflows.fMRI_preproc_workflow import (
        fMRI_preproc_workflow,
    )

    class _Config:
        def getenum_safe(self, key):
            return FmriEngine.NILEARN if key == "fmri_engine" else None

        def getboolean_safe(self, key):
            return False

    wf = fMRI_preproc_workflow(
        name="fmri_0",
        dicom_dir="/tmp",
        TR=2.0,
        slice_timing=SliceTiming.UNKNOWN,
        n_vols=100,
        del_start_vols=0,
        del_end_vols=0,
        hpcutoff=100,
        synth_config=_Config(),
    )
    node = wf.get_node("fmri_0_motion_correct")
    assert isinstance(node.interface, AntsMotionCorrection)
    assert node.n_procs == 1
    assert node.inputs.random_seed == 123


def test_child_environment_keeps_pythonpath(tmp_path, monkeypatch):
    """The child interpreter gets the caller's PYTHONPATH unchanged: for an
    installed SWANe the package root is site-packages, and putting it on
    PYTHONPATH would place it ahead of the standard library."""
    from swane.nipype_pipeline.interfaces.ants import AntsMotionCorrection as mod

    captured = {}

    class _Stop(Exception):
        pass

    def fake_run(cmd, env=None, **kwargs):
        captured["cmd"] = cmd
        captured["env"] = env
        raise _Stop()

    monkeypatch.setenv("PYTHONPATH", str(tmp_path / "user_dir"))
    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    in_file = _synthetic_moving_series(tmp_path / "func.nii.gz", n=8, n_vols=2)
    with pytest.raises(_Stop):
        AntsMotionCorrection(in_file=in_file)._run_interface(
            type("R", (), {"cwd": str(tmp_path)})()
        )
    assert captured["env"]["PYTHONPATH"] == str(tmp_path / "user_dir")
    assert captured["env"]["ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS"] == "1"


def _child_paths(root):
    """sys.path and the imported swane file of a fresh interpreter running
    the child bootstrap with ``root`` as the package root."""
    import json
    import subprocess
    import sys

    from swane.nipype_pipeline.interfaces.ants.AntsMotionCorrection import (
        _CHILD_BOOTSTRAP,
    )

    code = _CHILD_BOOTSTRAP + (
        "import json, swane\n"
        "print(json.dumps({'path': sys.path, 'swane': swane.__file__}))\n"
    )
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    out = subprocess.run(
        [sys.executable, "-c", code, "in", "out", "1", root],
        env=env,
        cwd=os.path.dirname(root),
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(out.stdout)


def test_child_bootstrap_does_not_shadow_the_stdlib():
    """A package root already on the default path (an installed SWANe in
    site-packages) is not moved ahead of the standard library."""
    import sysconfig

    purelib = sysconfig.get_paths()["purelib"]
    stdlib = sysconfig.get_paths()["stdlib"]
    found = _child_paths(purelib)
    path = [os.path.realpath(p) for p in found["path"]]
    assert path.index(os.path.realpath(stdlib)) < path.index(os.path.realpath(purelib))


def test_child_bootstrap_imports_this_checkout():
    """A package root outside the default path (a source checkout) is added,
    and the child imports this same swane package."""
    import swane

    root = os.path.dirname(os.path.dirname(os.path.abspath(swane.__file__)))
    found = _child_paths(root)
    assert os.path.realpath(found["swane"]) == os.path.realpath(swane.__file__)
