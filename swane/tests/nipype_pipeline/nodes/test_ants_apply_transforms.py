"""Unit tests for
:class:`swane.nipype_pipeline.nodes.AntsApplyTransforms.AntsApplyTransforms`.

The node resamples an image through an ordered ANTs transform list. Only
``ants.apply_transforms`` is faked here; the reference/label images and the
NIfTI written out are real, so the geometry and interpolation contracts are
checked against actual files.
"""

import os

import numpy as np
import nibabel as nib
import pytest

from swane.nipype_pipeline.nodes.AntsApplyTransforms import AntsApplyTransforms


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
    """A real, valid ANTs affine ``.mat`` (identity) to populate a transform list."""
    import ants

    path = str(tmp_path / "identity.mat")
    ants.write_transform(
        ants.create_ants_transform(transform_type="AffineTransform", dimension=3), path
    )
    return path


class TestAntsApplyTransformsSpec:
    def test_interpolator_constrained(self):
        node = AntsApplyTransforms()
        with pytest.raises(Exception):
            node.inputs.interpolator = "bogus"

    def test_default_interpolator_is_linear(self):
        assert AntsApplyTransforms().inputs.interpolator == "linear"

    def test_nearest_neighbor_is_the_antspyx_spelling(self):
        """antspyx spells it ``nearestNeighbor``; a wrong spelling must fail."""
        node = AntsApplyTransforms()
        node.inputs.interpolator = "nearestNeighbor"
        assert node.inputs.interpolator == "nearestNeighbor"
        with pytest.raises(Exception):
            node.inputs.interpolator = "nearestneighbour"


class TestAntsApplyTransformsOutput:
    def test_out_file_is_absolute_and_written(self, workspace, make_nifti, spy_apply):
        node = AntsApplyTransforms()
        node.inputs.input_image = make_nifti("in.nii.gz", shape=(6, 6, 6))
        node.inputs.reference_image = make_nifti("ref.nii.gz", shape=(6, 6, 6))
        node.inputs.transformlist = []
        node.run()
        out = node._list_outputs()["out_file"]
        assert os.path.isabs(out)
        assert os.path.exists(out)

    def test_explicit_out_file_is_honoured(self, workspace, make_nifti, spy_apply):
        node = AntsApplyTransforms()
        node.inputs.input_image = make_nifti("in.nii.gz", shape=(6, 6, 6))
        node.inputs.reference_image = make_nifti("ref.nii.gz", shape=(6, 6, 6))
        node.inputs.transformlist = []
        node.inputs.out_file = "custom.nii.gz"
        node.run()
        out = node._list_outputs()["out_file"]
        assert os.path.basename(out) == "custom.nii.gz"
        assert os.path.exists(out)

    def test_output_lives_in_the_reference_grid(self, workspace, make_nifti, spy_apply):
        """Resampling targets the reference space, not the input's."""
        affine = np.diag([-1.5, 1.2, 2.0, 1.0])
        affine[:3, 3] = [90.0, -120.0, -70.0]
        node = AntsApplyTransforms()
        node.inputs.input_image = make_nifti("in.nii.gz", shape=(4, 4, 4))
        node.inputs.reference_image = make_nifti(
            "ref.nii.gz", shape=(10, 12, 14), affine=affine
        )
        node.inputs.transformlist = []
        node.run()
        out = nib.load(node._list_outputs()["out_file"])
        assert out.shape == (10, 12, 14)
        assert np.allclose(out.affine, affine, atol=1e-4)


class TestAntsApplyTransformsInterpolation:
    def test_interpolator_is_forwarded(self, workspace, make_nifti, spy_apply):
        node = AntsApplyTransforms()
        node.inputs.input_image = make_nifti("in.nii.gz", shape=(6, 6, 6))
        node.inputs.reference_image = make_nifti("ref.nii.gz", shape=(6, 6, 6))
        node.inputs.transformlist = []
        node.inputs.interpolator = "nearestNeighbor"
        node.run()
        assert spy_apply["interpolator"] == "nearestNeighbor"

    def test_labelmap_values_are_not_blended(self, workspace, make_nifti, spy_apply):
        """A nearest-neighbour resample must not invent intermediate labels."""
        labels = np.zeros((10, 10, 10), dtype=np.float32)
        labels[2:6, 3:7, 4:8] = 3.0
        labels[6:9, 3:7, 4:8] = 7.0
        node = AntsApplyTransforms()
        node.inputs.input_image = make_nifti("lab.nii.gz", data=labels)
        node.inputs.reference_image = make_nifti("ref.nii.gz", shape=(10, 10, 10))
        node.inputs.transformlist = []
        node.inputs.interpolator = "nearestNeighbor"
        node.run()
        out = nib.load(node._list_outputs()["out_file"]).get_fdata()
        assert set(np.unique(out)) <= {0.0, 3.0, 7.0}


class TestAntsApplyTransformsInversion:
    def test_which_to_invert_is_forwarded_when_given(
        self, workspace, make_nifti, identity_transform, spy_apply
    ):
        node = AntsApplyTransforms()
        node.inputs.input_image = make_nifti("in.nii.gz", shape=(6, 6, 6))
        node.inputs.reference_image = make_nifti("ref.nii.gz", shape=(6, 6, 6))
        node.inputs.transformlist = [identity_transform]
        node.inputs.which_to_invert = [True]
        node.run()
        assert spy_apply["whichtoinvert"] == [True]

    def test_which_to_invert_is_omitted_when_unset(
        self, workspace, make_nifti, spy_apply
    ):
        """Unset must not become ``[]``/``None`` guesswork: leave antspyx alone."""
        node = AntsApplyTransforms()
        node.inputs.input_image = make_nifti("in.nii.gz", shape=(6, 6, 6))
        node.inputs.reference_image = make_nifti("ref.nii.gz", shape=(6, 6, 6))
        node.inputs.transformlist = []
        node.run()
        assert "whichtoinvert" not in spy_apply

    def test_length_mismatch_is_rejected(
        self, workspace, make_nifti, identity_transform
    ):
        """antspyx requires one flag per transform; catch it before it runs."""
        node = AntsApplyTransforms()
        node.inputs.input_image = make_nifti("in.nii.gz", shape=(6, 6, 6))
        node.inputs.reference_image = make_nifti("ref.nii.gz", shape=(6, 6, 6))
        node.inputs.transformlist = [identity_transform]
        node.inputs.which_to_invert = [True, False]
        with pytest.raises(ValueError):
            node.run()


class TestAntsApplyTransformsTimeSeries:
    """A 4D moving image (e.g. a whole fMRI run) needs antspyx's imagetype=3;
    the default imagetype=0 raises "Set imagetype 3 to transform time series
    images." (discovered by the ANTs-default resting-state prerelease smoke)."""

    def test_3d_moving_forwards_scalar_imagetype(
        self, workspace, make_nifti, spy_apply
    ):
        node = AntsApplyTransforms()
        node.inputs.input_image = make_nifti("in.nii.gz", shape=(6, 6, 6))
        node.inputs.reference_image = make_nifti("ref.nii.gz", shape=(6, 6, 6))
        node.inputs.transformlist = []
        node.run()
        assert spy_apply["imagetype"] == 0

    def test_4d_moving_forwards_time_series_imagetype(
        self, workspace, make_nifti, spy_apply
    ):
        node = AntsApplyTransforms()
        node.inputs.input_image = make_nifti(
            "in.nii.gz", shape=(6, 6, 6, 5), zooms=(3.0, 3.0, 3.0, 2.5)
        )
        node.inputs.reference_image = make_nifti("ref.nii.gz", shape=(8, 8, 8))
        node.inputs.transformlist = []
        node.run()
        assert spy_apply["imagetype"] == 3

    def test_4d_result_keeps_reference_grid_and_moving_tr(
        self, workspace, make_nifti, spy_apply
    ):
        """The resampled time series lands on the reference's spatial grid but
        keeps the original moving image's TR/temporal units: the reference (a
        static volume) has no repetition time of its own to borrow."""
        affine = np.diag([2.0, 2.0, 2.0, 1.0])
        node = AntsApplyTransforms()
        node.inputs.input_image = make_nifti(
            "in.nii.gz", shape=(6, 6, 6, 5), zooms=(3.0, 3.0, 3.0, 2.5)
        )
        node.inputs.reference_image = make_nifti(
            "ref.nii.gz", shape=(8, 8, 8), zooms=(2.0, 2.0, 2.0), affine=affine
        )
        node.inputs.transformlist = []
        node.run()
        out = nib.load(node._list_outputs()["out_file"])
        assert out.shape == (8, 8, 8, 5)
        zooms = out.header.get_zooms()
        assert zooms[:3] == pytest.approx((2.0, 2.0, 2.0))
        assert zooms[3] == pytest.approx(2.5)
        assert np.allclose(out.affine, affine, atol=1e-4)


@pytest.mark.heavy
class TestAntsApplyTransformsRealRun:
    """Round-trips a real registration through the node; opt-in via --run-heavy."""

    def test_inverse_round_trip_recovers_the_moving_image(self, workspace, make_nifti):
        import ants

        from swane.nipype_pipeline.nodes.AntsRegistration import AntsRegistration

        # antspyx's affine stage samples points randomly each iteration
        # (aff_random_sampling_rate) and AntsRegistration exposes no seed input,
        # so this real registration flips pass/fail run to run unless pinned
        # deterministic for the duration of this test. seed_value=123 is
        # antspyx's own default and was confirmed to clear the corr>0.9 bar.
        previous_deterministic = ants.config._deterministic
        previous_seed = ants.config._random_seed
        threads_var = "ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS"
        previous_threads = os.environ.get(threads_var)
        ants.config.set_ants_deterministic(True, seed_value=123)
        try:
            fixed_data = np.zeros((24, 24, 24), dtype=np.float32)
            fixed_data[6:18, 6:18, 6:18] = 1.0
            moving_data = np.zeros((24, 24, 24), dtype=np.float32)
            moving_data[10:22, 4:16, 6:18] = 1.0
            fixed = make_nifti("f.nii.gz", data=fixed_data)
            moving = make_nifti("m.nii.gz", data=moving_data)

            reg = AntsRegistration()
            reg.inputs.fixed = fixed
            reg.inputs.moving = moving
            reg.inputs.transform_type = "Affine"
            reg.run()
            reg_out = reg._list_outputs()

            apply_node = AntsApplyTransforms()
            apply_node.inputs.input_image = fixed
            apply_node.inputs.reference_image = moving
            apply_node.inputs.transformlist = reg_out["inv_transforms"]
            apply_node.inputs.which_to_invert = reg_out["inv_which_to_invert"]
            apply_node.inputs.out_file = "back.nii.gz"
            apply_node.run()

            back = nib.load(apply_node._list_outputs()["out_file"]).get_fdata()
            assert np.corrcoef(back.ravel(), moving_data.ravel())[0, 1] > 0.9
        finally:
            ants.config.set_ants_deterministic(
                previous_deterministic, seed_value=previous_seed
            )
            if previous_threads is None:
                os.environ.pop(threads_var, None)
            else:
                os.environ[threads_var] = previous_threads
