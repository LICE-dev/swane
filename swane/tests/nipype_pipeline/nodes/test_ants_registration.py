"""Unit tests for :class:`swane.nipype_pipeline.nodes.AntsRegistration.AntsRegistration`.

The node wraps the ``antspyx`` Python library (never the ANTs binaries). The
tests below fake only ``ants.registration`` itself -- image reading/writing and
the ANTs file-naming convention stay real -- so the parts that carry scientific
meaning are exercised for real:

* the **order** of the forward/inverse transform lists (ANTs applies a
  transform list right-to-left, so order is not cosmetic);
* the ``which_to_invert`` flags that accompany the inverse list. ANTs reuses the
  *same* forward affine ``.mat`` file in both lists and expects the caller to
  invert it at apply time; getting this wrong resamples silently and wrongly.
"""

import os

import numpy as np
import pytest

from swane.nipype_pipeline.nodes.AntsRegistration import AntsRegistration


def inspect_default(func, param):
    """The default value antspyx declares for one of ``func``'s parameters."""
    import inspect

    return inspect.signature(func).parameters[param].default


def _fake_registration(created, transforms):
    """Build a stand-in for ``ants.registration``.

    ``transforms`` maps the ANTs suffix of each file to create onto the role it
    plays, mirroring the real naming convention
    (``<prefix>0GenericAffine.mat`` / ``<prefix>1Warp.nii.gz`` /
    ``<prefix>1InverseWarp.nii.gz``).
    """

    def _fake(fixed, moving, type_of_transform, outprefix="", **kwargs):
        created["kwargs"] = dict(kwargs)
        created["type_of_transform"] = type_of_transform
        created["outprefix"] = outprefix
        paths = {}
        for suffix in transforms:
            path = outprefix + suffix
            with open(path, "w") as handle:
                handle.write("fake transform")
            paths[suffix] = path
        import ants

        warped = ants.from_numpy(np.zeros((4, 4, 4), dtype=np.float32))
        if "1Warp.nii.gz" in paths:
            fwd = [paths["1Warp.nii.gz"], paths["0GenericAffine.mat"]]
            inv = [paths["0GenericAffine.mat"], paths["1InverseWarp.nii.gz"]]
        else:
            fwd = [paths["0GenericAffine.mat"]]
            inv = [paths["0GenericAffine.mat"]]
        return {
            "fwdtransforms": fwd,
            "invtransforms": inv,
            "warpedmovout": warped,
            "warpedfixout": warped,
        }

    return _fake


LINEAR_FILES = ["0GenericAffine.mat"]
NONLINEAR_FILES = ["0GenericAffine.mat", "1Warp.nii.gz", "1InverseWarp.nii.gz"]


def _run(node, monkeypatch, transforms):
    import ants

    created = {}
    monkeypatch.setattr(ants, "registration", _fake_registration(created, transforms))
    node.run()
    return created


class TestAntsRegistrationSpec:
    def test_transform_type_is_constrained(self):
        node = AntsRegistration()
        with pytest.raises(Exception):
            node.inputs.transform_type = "not-a-real-transform"

    def test_moving_mask_optional_and_undefined_by_default(self):
        from nipype.interfaces.base import isdefined

        node = AntsRegistration()
        assert not isdefined(node.inputs.moving_mask)

    def test_moving_mask_accepts_existing_file(self, make_nifti):
        node = AntsRegistration()
        node.inputs.moving_mask = make_nifti("mask.nii.gz", shape=(6, 6, 6))
        assert node.inputs.moving_mask.endswith("mask.nii.gz")

    def test_metrics_are_constrained_to_the_documented_antspyx_values(self):
        """antspyx silently accepts an unknown metric, so the spec must not."""
        node = AntsRegistration()
        with pytest.raises(Exception):
            node.inputs.aff_metric = "MI"
        with pytest.raises(Exception):
            node.inputs.syn_metric = "MI"

    def test_outputs_declared(self):
        out = AntsRegistration().output_spec().get()
        for field in [
            "fwd_transforms",
            "inv_transforms",
            "fwd_which_to_invert",
            "inv_which_to_invert",
            "warped_file",
            "affine_transform",
            "warp_field",
            "inverse_warp_field",
        ]:
            assert field in out


class TestAntsRegistrationLinear:
    """A Rigid/Affine run advertises exactly one forward transform."""

    @pytest.fixture
    def outputs(self, workspace, make_nifti, monkeypatch):
        node = AntsRegistration()
        node.inputs.moving = make_nifti("m.nii.gz", shape=(6, 6, 6))
        node.inputs.fixed = make_nifti("f.nii.gz", shape=(6, 6, 6))
        node.inputs.transform_type = "Affine"
        _run(node, monkeypatch, LINEAR_FILES)
        return node._list_outputs()

    def test_single_forward_transform(self, outputs):
        assert len(outputs["fwd_transforms"]) == 1
        assert outputs["fwd_transforms"][0].endswith("0GenericAffine.mat")

    def test_inverse_reuses_the_same_affine_file(self, outputs):
        """ANTs lists the *forward* affine in both directions."""
        assert outputs["inv_transforms"] == outputs["fwd_transforms"]

    def test_inverse_affine_is_flagged_for_inversion(self, outputs):
        """The load-bearing flag: without it the inverse resamples wrongly."""
        assert outputs["inv_which_to_invert"] == [True]

    def test_forward_affine_is_not_flagged_for_inversion(self, outputs):
        assert outputs["fwd_which_to_invert"] == [False]

    def test_no_warp_field_for_a_linear_registration(self, outputs):
        from nipype.interfaces.base import isdefined

        assert not isdefined(outputs["warp_field"])
        assert not isdefined(outputs["inverse_warp_field"])

    def test_affine_component_is_exposed(self, outputs):
        assert outputs["affine_transform"] == outputs["fwd_transforms"][0]

    def test_paths_are_absolute_and_exist(self, outputs):
        for path in outputs["fwd_transforms"] + outputs["inv_transforms"]:
            assert os.path.isabs(path) and os.path.exists(path)
        assert os.path.isabs(outputs["warped_file"])
        assert os.path.exists(outputs["warped_file"])


class TestAntsRegistrationNonlinear:
    """A SyN run carries the warp *and* the affine, in ANTs order."""

    @pytest.fixture
    def outputs(self, workspace, make_nifti, monkeypatch):
        node = AntsRegistration()
        node.inputs.moving = make_nifti("m.nii.gz", shape=(6, 6, 6))
        node.inputs.fixed = make_nifti("f.nii.gz", shape=(6, 6, 6))
        node.inputs.transform_type = "SyN"
        _run(node, monkeypatch, NONLINEAR_FILES)
        return node._list_outputs()

    def test_forward_order_is_warp_then_affine(self, outputs):
        """ANTs applies right-to-left: the affine must run *before* the warp."""
        fwd = outputs["fwd_transforms"]
        assert len(fwd) == 2
        assert fwd[0].endswith("1Warp.nii.gz")
        assert fwd[1].endswith("0GenericAffine.mat")

    def test_inverse_order_is_affine_then_inverse_warp(self, outputs):
        inv = outputs["inv_transforms"]
        assert len(inv) == 2
        assert inv[0].endswith("0GenericAffine.mat")
        assert inv[1].endswith("1InverseWarp.nii.gz")

    def test_invert_flags_match_the_lists(self, outputs):
        assert outputs["fwd_which_to_invert"] == [False, False]
        # only the matrix is inverted; the InverseWarp is already inverted
        assert outputs["inv_which_to_invert"] == [True, False]

    def test_components_are_exposed(self, outputs):
        assert outputs["affine_transform"].endswith("0GenericAffine.mat")
        assert outputs["warp_field"].endswith("1Warp.nii.gz")
        assert outputs["inverse_warp_field"].endswith("1InverseWarp.nii.gz")


class TestAntsRegistrationRuntime:
    def test_transforms_are_written_into_the_node_directory(
        self, workspace, make_nifti, monkeypatch
    ):
        """Nipype needs the products inside the node's cwd, not a temp dir."""
        node = AntsRegistration()
        node.inputs.moving = make_nifti("m.nii.gz", shape=(6, 6, 6))
        node.inputs.fixed = make_nifti("f.nii.gz", shape=(6, 6, 6))
        node.inputs.transform_type = "Affine"
        _run(node, monkeypatch, LINEAR_FILES)
        outputs = node._list_outputs()
        for path in outputs["fwd_transforms"]:
            assert os.path.dirname(path) == os.getcwd()

    def test_metrics_are_forwarded_to_antspyx(self, workspace, make_nifti, monkeypatch):
        node = AntsRegistration()
        node.inputs.moving = make_nifti("m.nii.gz", shape=(6, 6, 6))
        node.inputs.fixed = make_nifti("f.nii.gz", shape=(6, 6, 6))
        node.inputs.transform_type = "SyN"
        node.inputs.aff_metric = "GC"
        node.inputs.syn_metric = "CC"
        created = _run(node, monkeypatch, NONLINEAR_FILES)
        assert created["kwargs"]["aff_metric"] == "GC"
        assert created["kwargs"]["syn_metric"] == "CC"
        assert created["type_of_transform"] == "SyN"

    def test_num_threads_is_exported_then_restored(
        self, workspace, make_nifti, monkeypatch
    ):
        var = "ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS"
        monkeypatch.delenv(var, raising=False)
        seen = {}

        node = AntsRegistration()
        node.inputs.moving = make_nifti("m.nii.gz", shape=(6, 6, 6))
        node.inputs.fixed = make_nifti("f.nii.gz", shape=(6, 6, 6))
        node.inputs.transform_type = "Affine"
        node.inputs.num_threads = 3

        import ants

        real_fake = _fake_registration({}, LINEAR_FILES)

        def _spy(*args, **kwargs):
            seen["threads"] = os.environ.get(var)
            return real_fake(*args, **kwargs)

        monkeypatch.setattr(ants, "registration", _spy)
        node.run()

        assert seen["threads"] == "3"
        assert var not in os.environ

    def test_initial_transform_is_forwarded(
        self, workspace, make_nifti, make_file, monkeypatch
    ):
        node = AntsRegistration()
        node.inputs.moving = make_nifti("m.nii.gz", shape=(6, 6, 6))
        node.inputs.fixed = make_nifti("f.nii.gz", shape=(6, 6, 6))
        node.inputs.transform_type = "Affine"
        node.inputs.initial_transform = make_file("init.mat", "x")
        created = _run(node, monkeypatch, LINEAR_FILES)
        assert created["kwargs"]["initial_transform"] == node.inputs.initial_transform


class TestAntsRegistrationTestRun:
    """The ``test_run`` speed knob trades accuracy for a much faster sweep by
    slashing antspyx's per-level iteration counts, without touching the graph."""

    def _kwargs(self, monkeypatch, make_nifti, **inputs):
        node = AntsRegistration()
        node.inputs.moving = make_nifti("m.nii.gz", shape=(6, 6, 6))
        node.inputs.fixed = make_nifti("f.nii.gz", shape=(6, 6, 6))
        node.inputs.transform_type = "SyN"
        for key, value in inputs.items():
            setattr(node.inputs, key, value)
        return _run(node, monkeypatch, NONLINEAR_FILES)["kwargs"]

    def test_full_accuracy_by_default(self, workspace, make_nifti, monkeypatch):
        """Without the knob, antspyx keeps its own (full-accuracy) defaults: the
        node must not override the iteration schedules at all."""
        kwargs = self._kwargs(monkeypatch, make_nifti)
        assert "aff_iterations" not in kwargs
        assert "reg_iterations" not in kwargs

    def test_test_run_cuts_both_iteration_schedules(
        self, workspace, make_nifti, monkeypatch
    ):
        kwargs = self._kwargs(monkeypatch, make_nifti, test_run=True)
        # The affine/rigid stage: fewer iterations, but the tuple must stay
        # length 4 to match antspyx's default aff_shrink_factors /
        # aff_smoothing_sigmas (a length mismatch raises ValueError).
        assert "aff_iterations" in kwargs
        assert len(kwargs["aff_iterations"]) == 4
        assert max(kwargs["aff_iterations"]) < 2100  # antspyx default coarsest
        # The SyN deformable stage: fewer iterations than the (40, 20, 0) default.
        assert "reg_iterations" in kwargs
        assert max(kwargs["reg_iterations"]) < 40

    def test_reduced_affine_schedule_is_antspyx_valid(self):
        """A real antspyx call raises if aff_iterations length does not match the
        default aff_shrink_factors/aff_smoothing_sigmas -- guard that invariant
        against the live antspyx signature (no monkeypatch here)."""
        import ants

        from swane.nipype_pipeline.nodes.AntsRegistration import TEST_RUN_AFF_ITERATIONS

        default_shrink = inspect_default(ants.registration, "aff_shrink_factors")
        default_smooth = inspect_default(ants.registration, "aff_smoothing_sigmas")
        assert (
            len(TEST_RUN_AFF_ITERATIONS) == len(default_shrink) == len(default_smooth)
        )


@pytest.mark.heavy
class TestAntsRegistrationRealRun:
    """A real (tiny) antspyx registration; opt-in via ``--run-heavy``."""

    def test_linear_inverse_needs_the_invert_flag(self, workspace, make_nifti):
        import ants
        import nibabel as nib

        fixed_data = np.zeros((24, 24, 24), dtype=np.float32)
        fixed_data[6:18, 6:18, 6:18] = 1.0
        moving_data = np.zeros((24, 24, 24), dtype=np.float32)
        moving_data[10:22, 4:16, 6:18] = 1.0
        fixed = make_nifti("f.nii.gz", data=fixed_data)
        moving = make_nifti("m.nii.gz", data=moving_data)

        node = AntsRegistration()
        node.inputs.fixed = fixed
        node.inputs.moving = moving
        node.inputs.transform_type = "Affine"
        node.run()
        outputs = node._list_outputs()

        ants_fixed = ants.image_read(fixed)
        ants_moving = ants.image_read(moving)
        # applying the inverse with the node's flags recovers the moving image
        back = ants.apply_transforms(
            fixed=ants_moving,
            moving=ants_fixed,
            transformlist=outputs["inv_transforms"],
            whichtoinvert=outputs["inv_which_to_invert"],
        )
        recovered = np.corrcoef(back.numpy().ravel(), moving_data.ravel())[0, 1]
        assert recovered > 0.9

        # and the warped output really lives in the fixed image's grid
        warped = nib.load(outputs["warped_file"])
        assert warped.shape == nib.load(fixed).shape
        assert np.allclose(warped.affine, nib.load(fixed).affine, atol=1e-4)
