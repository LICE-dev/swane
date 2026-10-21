"""Tests for :class:`NiiMathRobustFov`.

The cropped image is the interface's ``out_file`` (the niimath output). The
former ``out_roi`` alias, copied into ``out_file`` only while the command line
was being built, made ``_list_outputs`` report the wrong file on an interface
that had never built it (for instance when Nipype re-aggregates the outputs of
a node whose result file cannot be loaded).
"""

import os

import nibabel as nib
import numpy as np
import pytest

from swane.nipype_pipeline.interfaces.niimath import NiiMathRobustFov


def _fresh(in_file, out_file=None, brainsize=None):
    """A new interface that has never built its command line."""
    interface = NiiMathRobustFov()
    interface.inputs.in_file = in_file
    if out_file is not None:
        interface.inputs.out_file = out_file
    if brainsize is not None:
        interface.inputs.brainsize = brainsize
    return interface


class TestSpec:
    def test_the_cropped_image_is_out_file_only(self):
        assert "out_roi" not in NiiMathRobustFov.input_spec().class_editable_traits()
        assert "out_roi" not in NiiMathRobustFov.output_spec().class_editable_traits()
        assert "out_file" in NiiMathRobustFov.output_spec().class_editable_traits()


class TestOutputs:
    def test_out_file_is_reported_without_building_the_command(
        self, workspace, make_nifti
    ):
        in_file = make_nifti("in.nii.gz")

        outputs = _fresh(in_file, out_file="ref_robustfov.nii.gz")._list_outputs()

        assert outputs == {"out_file": str(workspace / "ref_robustfov.nii.gz")}

    def test_default_output_name(self, workspace, make_nifti):
        in_file = make_nifti("in.nii.gz")

        outputs = _fresh(in_file)._list_outputs()

        assert os.path.basename(outputs["out_file"]) == "in_maths.nii.gz"

    def test_building_the_command_does_not_change_the_outputs(
        self, workspace, make_nifti
    ):
        interface = _fresh(make_nifti("in.nii.gz"), out_file="cropped.nii.gz")
        before = interface._list_outputs()

        interface.cmdline

        assert interface._list_outputs() == before
        assert interface.inputs.out_file == "cropped.nii.gz"


class TestCommandLine:
    @pytest.mark.parametrize(
        "brainsize, expected_op",
        [(None, "-robustfov"), (170, "-robustfov 170"), (120, "-robustfov 120")],
    )
    def test_operation_and_output(self, workspace, make_nifti, brainsize, expected_op):
        interface = _fresh(
            make_nifti("in.nii.gz"), out_file="cropped.nii.gz", brainsize=brainsize
        )

        args = interface.cmdline.split(" ", 1)[1]

        assert args == "%s %s cropped.nii.gz" % (workspace / "in.nii.gz", expected_op)


def _head_and_neck():
    """A 40x40x260 mm volume: a bright head on top of a thin dim neck."""
    x, y, z = np.mgrid[0:40, 0:40, 0:260]
    head = (
        ((x - 20) / 15.0) ** 2 + ((y - 20) / 17.0) ** 2 + ((z - 190) / 60.0) ** 2
    ) < 1
    neck = (((x - 20) / 8.0) ** 2 + ((y - 20) / 8.0) ** 2 < 1) & (z < 130)
    return (head * 100.0 + neck * 40.0).astype(np.float32)


@pytest.mark.parametrize("brainsize, expected_slices", [(None, 170), (120, 120)])
def test_real_niimath_crops_the_neck(workspace, make_nifti, brainsize, expected_slices):
    """The declared output is the real niimath crop, geometry included."""
    data = _head_and_neck()
    in_file = make_nifti("in.nii.gz", data=data)
    interface = _fresh(in_file, out_file="ref_robustfov.nii.gz", brainsize=brainsize)

    out_file = interface.run().outputs.out_file

    assert out_file == str(workspace / "ref_robustfov.nii.gz")
    out = nib.load(out_file)
    assert out.shape == (40, 40, expected_slices)
    # the output is the matching slab of the input, with the shifted origin
    first = int(round(out.affine[2, 3]))
    assert 0 < first < 260 - expected_slices
    np.testing.assert_allclose(
        out.get_fdata(), data[:, :, first : first + expected_slices]
    )
