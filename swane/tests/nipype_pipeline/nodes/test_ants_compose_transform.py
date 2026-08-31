"""Unit tests for
:class:`swane.nipype_pipeline.nodes.AntsComposeTransform.AntsComposeTransform`.

The node flattens an ordered ANTs transform list (plus its ``which_to_invert``
flags) into a single displacement field, so that a workflow boundary can carry
one file instead of a list + flags pair. Only ``ants.apply_transforms`` is
spied on here -- it still runs for real, so the composed field on disk, its
grid and its ITK vector metadata are checked against actual files.
"""

import os

import numpy as np
import nibabel as nib
import pytest

from swane.nipype_pipeline.nodes.AntsComposeTransform import AntsComposeTransform


@pytest.fixture
def spy_apply(monkeypatch):
    """Capture the kwargs handed to ``ants.apply_transforms``."""
    import ants

    seen = {}
    real = ants.apply_transforms

    def _spy(**kwargs):
        seen.update(kwargs)
        return real(**kwargs)

    monkeypatch.setattr(ants, "apply_transforms", _spy)
    return seen


@pytest.fixture
def identity_transform(tmp_path):
    """A real, valid ANTs affine ``.mat`` (identity) to compose."""
    import ants

    path = str(tmp_path / "identity.mat")
    ants.write_transform(
        ants.create_ants_transform(transform_type="AffineTransform", dimension=3), path
    )
    return path


def _configured_node(make_nifti, identity_transform, **ref_kwargs):
    node = AntsComposeTransform()
    node.inputs.transformlist = [identity_transform]
    node.inputs.reference_image = make_nifti(
        "ref.nii.gz", shape=ref_kwargs.pop("shape", (6, 6, 6)), **ref_kwargs
    )
    return node


class TestAntsComposeTransformSpec:
    def test_outputs_declared(self):
        assert "out_field" in AntsComposeTransform().output_spec().get()

    def test_transformlist_mandatory(self, workspace, make_nifti):
        node = AntsComposeTransform()
        node.inputs.reference_image = make_nifti("ref.nii.gz", shape=(6, 6, 6))
        with pytest.raises(Exception):
            node.run()

    def test_reference_image_mandatory(self, workspace, identity_transform):
        node = AntsComposeTransform()
        node.inputs.transformlist = [identity_transform]
        with pytest.raises(Exception):
            node.run()

    def test_which_to_invert_is_undefined_by_default(self):
        from nipype.interfaces.base import isdefined

        assert not isdefined(AntsComposeTransform().inputs.which_to_invert)


class TestAntsComposeTransformOutput:
    def test_out_field_is_absolute_and_written(
        self, workspace, make_nifti, identity_transform, spy_apply
    ):
        node = _configured_node(make_nifti, identity_transform)
        node.run()
        out = node._list_outputs()["out_field"]
        assert os.path.isabs(out)
        assert os.path.exists(out)

    def test_out_field_lives_in_the_node_directory(
        self, workspace, make_nifti, identity_transform, spy_apply
    ):
        """nipype must be able to hash, cache and clean the composed field."""
        node = _configured_node(make_nifti, identity_transform)
        node.run()
        out = node._list_outputs()["out_field"]
        assert os.path.dirname(out) == os.path.realpath(str(workspace))

    def test_compose_is_requested_from_antspyx(
        self, workspace, make_nifti, identity_transform, spy_apply
    ):
        """Without ``compose=`` antspyx would resample an image instead."""
        node = _configured_node(make_nifti, identity_transform)
        node.run()
        assert spy_apply["compose"]
        assert os.path.isabs(spy_apply["compose"])

    def test_reference_is_both_fixed_and_moving(
        self, workspace, make_nifti, identity_transform, spy_apply
    ):
        """The composite only depends on the reference domain: antspyx still
        wants a moving image, so the reference is handed over twice rather than
        loading an unrelated volume that cannot influence the result."""
        node = _configured_node(make_nifti, identity_transform)
        node.run()
        assert spy_apply["fixed"] is spy_apply["moving"]


class TestAntsComposeTransformGeometry:
    def test_field_is_sampled_on_the_reference_grid(
        self, workspace, make_nifti, identity_transform, spy_apply
    ):
        affine = np.diag([-1.5, 1.2, 2.0, 1.0])
        affine[:3, 3] = [90.0, -120.0, -70.0]
        node = _configured_node(
            make_nifti, identity_transform, shape=(10, 12, 14), affine=affine
        )
        node.run()
        field = nib.load(node._list_outputs()["out_field"])
        assert field.shape[:3] == (10, 12, 14)
        assert np.allclose(field.affine, affine, atol=1e-4)

    def test_field_keeps_its_itk_vector_metadata(
        self, workspace, make_nifti, identity_transform, spy_apply
    ):
        """The product is a displacement field, not a scalar volume: its ITK
        vector intent and its 5-D (x, y, z, 1, 3) layout must survive, so it
        must not be re-stamped with the reference's scalar header."""
        node = _configured_node(make_nifti, identity_transform)
        node.run()
        field = nib.load(node._list_outputs()["out_field"])
        assert field.header.get_intent()[0] == "vector"
        assert len(field.shape) == 5
        assert field.shape[-1] == 3


class TestAntsComposeTransformInversion:
    def test_which_to_invert_is_forwarded_when_given(
        self, workspace, make_nifti, identity_transform, spy_apply
    ):
        node = _configured_node(make_nifti, identity_transform)
        node.inputs.which_to_invert = [True]
        node.run()
        assert spy_apply["whichtoinvert"] == [True]

    def test_which_to_invert_is_omitted_when_unset(
        self, workspace, make_nifti, identity_transform, spy_apply
    ):
        """Unset must not become ``[]``/``None`` guesswork: leave antspyx alone."""
        node = _configured_node(make_nifti, identity_transform)
        node.run()
        assert "whichtoinvert" not in spy_apply

    def test_length_mismatch_is_rejected(
        self, workspace, make_nifti, identity_transform
    ):
        """antspyx requires one flag per transform; catch it before it runs."""
        node = _configured_node(make_nifti, identity_transform)
        node.inputs.which_to_invert = [True, False]
        with pytest.raises(ValueError):
            node.run()

    def test_inverting_the_affine_changes_the_field(
        self, workspace, make_nifti, identity_transform, tmp_path, spy_apply
    ):
        """The flags are resolved *into* the field: the same transform list
        composed with and without inversion cannot produce the same field."""
        import ants

        shift = ants.create_ants_transform(
            transform_type="AffineTransform", dimension=3
        )
        shift.set_parameters(
            np.array([1, 0, 0, 0, 1, 0, 0, 0, 1, 3.0, -2.0, 1.0], dtype=float)
        )
        matrix = str(tmp_path / "shift.mat")
        ants.write_transform(shift, matrix)

        forward = AntsComposeTransform()
        forward.inputs.transformlist = [matrix]
        forward.inputs.reference_image = make_nifti("ref.nii.gz", shape=(6, 6, 6))
        forward.run()
        forward_field = nib.load(forward._list_outputs()["out_field"]).get_fdata()

        os.mkdir(str(workspace / "inverted"))
        os.chdir(str(workspace / "inverted"))
        inverted = AntsComposeTransform()
        inverted.inputs.transformlist = [matrix]
        inverted.inputs.which_to_invert = [True]
        inverted.inputs.reference_image = make_nifti("ref.nii.gz", shape=(6, 6, 6))
        inverted.run()
        inverted_field = nib.load(inverted._list_outputs()["out_field"]).get_fdata()

        assert np.allclose(forward_field, -inverted_field, atol=1e-4)


class TestAntsComposeTransformThreads:
    def test_num_threads_is_restored(
        self, workspace, make_nifti, identity_transform, monkeypatch, spy_apply
    ):
        from swane.nipype_pipeline.nodes.AntsRegistration import ITK_THREADS_VAR

        monkeypatch.setenv(ITK_THREADS_VAR, "7")
        node = _configured_node(make_nifti, identity_transform)
        node.inputs.num_threads = 2
        node.run()
        assert os.environ[ITK_THREADS_VAR] == "7"

    def test_num_threads_is_unset_again_when_it_was_unset(
        self, workspace, make_nifti, identity_transform, monkeypatch, spy_apply
    ):
        from swane.nipype_pipeline.nodes.AntsRegistration import ITK_THREADS_VAR

        monkeypatch.delenv(ITK_THREADS_VAR, raising=False)
        node = _configured_node(make_nifti, identity_transform)
        node.inputs.num_threads = 2
        node.run()
        assert ITK_THREADS_VAR not in os.environ


@pytest.mark.heavy
class TestAntsComposeTransformRealRun:
    """Composes a real SyN registration; opt-in via --run-heavy."""

    @staticmethod
    def _sphere(shape, center, radius):
        grid = np.mgrid[0 : shape[0], 0 : shape[1], 0 : shape[2]].astype(float)
        distance = sum((grid[i] - center[i]) ** 2 for i in range(3))
        return (distance < radius**2).astype(np.float32)

    def test_composed_field_reproduces_the_raw_transform_list(
        self, workspace, make_nifti
    ):
        """Both directions: resampling through the single composed field must
        match resampling through ``[warp, affine]`` + ``which_to_invert``. This
        is the guard on the composition's direction and space -- a field built
        in the wrong space still resamples, just silently wrongly.
        """
        from swane.nipype_pipeline.nodes.AntsRegistration import AntsRegistration
        from swane.nipype_pipeline.nodes.AntsApplyTransforms import AntsApplyTransforms

        fixed_data = self._sphere((32, 32, 32), (16, 16, 16), 8)
        moving_data = self._sphere((32, 32, 32), (18, 15, 16), 7)
        fixed = make_nifti("fixed.nii.gz", data=fixed_data)
        moving = make_nifti(
            "moving.nii.gz", data=moving_data, affine=np.diag([1.2, 1.2, 1.2, 1.0])
        )

        reg = AntsRegistration()
        reg.inputs.fixed = fixed
        reg.inputs.moving = moving
        reg.inputs.transform_type = "SyN"
        reg.inputs.test_run = True
        reg.run()
        reg_out = reg._list_outputs()

        def _apply(input_image, reference, transformlist, which_to_invert, out_file):
            node = AntsApplyTransforms()
            node.inputs.input_image = input_image
            node.inputs.reference_image = reference
            node.inputs.transformlist = transformlist
            if which_to_invert is not None:
                node.inputs.which_to_invert = which_to_invert
            node.inputs.out_file = out_file
            node.run()
            return nib.load(node._list_outputs()["out_file"]).get_fdata()

        def _compose(transformlist, which_to_invert, reference, directory):
            os.mkdir(str(workspace / directory))
            os.chdir(str(workspace / directory))
            node = AntsComposeTransform()
            node.inputs.transformlist = transformlist
            node.inputs.which_to_invert = which_to_invert
            node.inputs.reference_image = reference
            node.run()
            field = node._list_outputs()["out_field"]
            os.chdir(str(workspace))
            return field

        # forward: moving -> fixed, composed on the fixed grid
        raw_forward = _apply(
            moving,
            fixed,
            reg_out["fwd_transforms"],
            reg_out["fwd_which_to_invert"],
            "raw_forward.nii.gz",
        )
        forward_field = _compose(
            reg_out["fwd_transforms"],
            reg_out["fwd_which_to_invert"],
            fixed,
            "compose_forward",
        )
        composed_forward = _apply(
            moving, fixed, [forward_field], None, "composed_forward.nii.gz"
        )
        # a pair of empty volumes would satisfy allclose without proving a thing
        assert np.count_nonzero(raw_forward) > 100
        assert np.allclose(raw_forward, composed_forward, atol=1e-4)

        # inverse: fixed -> moving, composed on the moving grid. The inverse
        # list carries the *forward* affine, so its invert flag must be baked
        # into the field for this to hold.
        raw_inverse = _apply(
            fixed,
            moving,
            reg_out["inv_transforms"],
            reg_out["inv_which_to_invert"],
            "raw_inverse.nii.gz",
        )
        inverse_field = _compose(
            reg_out["inv_transforms"],
            reg_out["inv_which_to_invert"],
            moving,
            "compose_inverse",
        )
        composed_inverse = _apply(
            fixed, moving, [inverse_field], None, "composed_inverse.nii.gz"
        )
        assert np.count_nonzero(raw_inverse) > 100
        assert np.allclose(raw_inverse, composed_inverse, atol=1e-4)
