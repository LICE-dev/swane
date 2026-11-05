"""Tests for :class:`CustomFilterRegressor`.

``fsl_regfilt`` rejects an empty component list (``-f ''`` -> "Missing
non-optional argument!", exit 1). The ICA-AROMA classification can legitimately
flag no component as motion, so the interface must pass the data through
instead of failing the resting-state analysis.
"""

import nibabel as nib
import numpy as np
import pytest
from nipype import Function, Node, Workflow
from nipype.interfaces.fsl.utils import FilterRegressor

from swane.nipype_pipeline.interfaces.fsl.CustomFilterRegressor import (
    CustomFilterRegressor,
)


def _make_inputs(directory, suffix=".nii.gz"):
    """A small synthetic 4D image (non-trivial affine and TR) and a 3-IC mix."""
    rng = np.random.default_rng(0)
    data = rng.normal(100, 5, (5, 6, 7, 12)).astype("float32")
    affine = np.diag([2.0, 2.5, 3.0, 1.0])
    affine[:3, 3] = [-5.0, 7.0, 11.0]
    img = nib.Nifti1Image(data, affine)
    img.header.set_zooms((2.0, 2.5, 3.0, 2.0))
    img.header.set_xyzt_units("mm", "sec")
    in_file = directory / ("func" + suffix)
    nib.save(img, in_file)
    mix = directory / "mix"
    np.savetxt(mix, rng.normal(size=(12, 3)))
    return str(in_file), str(mix)


def _interface(in_file, mix, columns, out_file="denoised.nii.gz"):
    regfilt = CustomFilterRegressor()
    regfilt.inputs.in_file = in_file
    regfilt.inputs.design_file = mix
    regfilt.inputs.filter_columns = columns
    if out_file is not None:
        regfilt.inputs.out_file = out_file
    return regfilt


@pytest.fixture
def forbid_fsl_regfilt(monkeypatch):
    """Make any delegation to the real ``fsl_regfilt`` run fail the test."""

    def _fail(self, runtime):
        raise AssertionError("fsl_regfilt must not run without components")

    monkeypatch.setattr(FilterRegressor, "_run_interface", _fail, raising=False)


def _assert_same_image(path, reference):
    ref = nib.load(reference)
    out = nib.load(path)
    assert out.shape == ref.shape
    assert out.get_data_dtype() == ref.get_data_dtype()
    np.testing.assert_array_equal(out.affine, ref.affine)
    np.testing.assert_array_equal(out.header.get_zooms(), ref.header.get_zooms())
    np.testing.assert_array_equal(out.get_fdata(), ref.get_fdata())


def test_empty_columns_pass_the_input_through(
    tmp_path, monkeypatch, forbid_fsl_regfilt
):
    in_file, mix = _make_inputs(tmp_path)
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)

    outputs = _interface(in_file, mix, []).run().outputs

    assert outputs.out_file == str(work / "denoised.nii.gz")
    _assert_same_image(outputs.out_file, in_file)
    # a real copy, not a link that would dangle if the input's work dir is cleaned
    assert not (work / "denoised.nii.gz").is_symlink()
    assert (work / "denoised.nii.gz").read_bytes() == open(in_file, "rb").read()


def test_empty_columns_without_out_file_use_the_default_name(
    tmp_path, monkeypatch, forbid_fsl_regfilt
):
    in_file, mix = _make_inputs(tmp_path)
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)

    outputs = _interface(in_file, mix, [], out_file=None).run().outputs

    assert outputs.out_file.startswith(str(work))
    assert "_regfilt" in outputs.out_file
    _assert_same_image(outputs.out_file, in_file)


def test_empty_columns_convert_when_the_output_format_differs(
    tmp_path, monkeypatch, forbid_fsl_regfilt
):
    in_file, mix = _make_inputs(tmp_path)
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)

    outputs = _interface(in_file, mix, [], out_file="denoised.nii").run().outputs

    assert outputs.out_file.endswith("denoised.nii")
    # the file really is an uncompressed NIfTI, not gzip data under a .nii name
    with open(outputs.out_file, "rb") as handle:
        assert handle.read(2) != b"\x1f\x8b"
    _assert_same_image(outputs.out_file, in_file)


def test_non_empty_columns_still_run_fsl_regfilt(tmp_path, monkeypatch):
    in_file, mix = _make_inputs(tmp_path)
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    calls = []

    def _fake_run(self, runtime):
        calls.append(self.cmdline)
        open(self._list_outputs()["out_file"], "wb").close()
        runtime.returncode = 0
        return runtime

    monkeypatch.setattr(FilterRegressor, "_run_interface", _fake_run, raising=False)

    regfilt = _interface(in_file, mix, [1, 3])
    regfilt.run()

    assert len(calls) == 1
    assert "-f '1,3'" in calls[0]
    # the fake tool wrote an empty file: the input was not copied over
    assert (work / "denoised.nii.gz").stat().st_size == 0


def _no_motion_ics():
    return []


def test_empty_list_from_an_upstream_node_passes_through(tmp_path, forbid_fsl_regfilt):
    """The empty list reaches the interface through a workflow connection."""
    in_file, mix = _make_inputs(tmp_path)
    source = Node(
        Function(function=_no_motion_ics, output_names=["motion_ics"]),
        name="source",
    )
    denoise = Node(CustomFilterRegressor(), name="nonaggr_denoising")
    denoise.inputs.in_file = in_file
    denoise.inputs.design_file = mix
    denoise.inputs.out_file = "denoised_func_data_nonaggr.nii.gz"
    wf = Workflow(name="wf", base_dir=str(tmp_path / "work"))
    wf.connect(source, "motion_ics", denoise, "filter_columns")

    wf.run()

    # wf.run() executes copies of the nodes: read the file from the node folder
    out_file = tmp_path / "work" / "wf" / "nonaggr_denoising"
    out_file /= "denoised_func_data_nonaggr.nii.gz"
    _assert_same_image(str(out_file), in_file)


@pytest.mark.heavy
@pytest.mark.requires_fsl
def test_real_fsl_regfilt_with_and_without_components(tmp_path, monkeypatch):
    in_file, mix = _make_inputs(tmp_path)
    ref = nib.load(in_file)

    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.chdir(empty)
    outputs = _interface(in_file, mix, []).run().outputs
    _assert_same_image(outputs.out_file, in_file)

    one = tmp_path / "one"
    one.mkdir()
    monkeypatch.chdir(one)
    outputs = _interface(in_file, mix, [1]).run().outputs
    filtered = nib.load(outputs.out_file)
    assert filtered.shape == ref.shape
    np.testing.assert_array_equal(filtered.affine, ref.affine)
    # the real tool regressed IC 1 out: the data must have changed
    assert not np.allclose(filtered.get_fdata(), ref.get_fdata())
