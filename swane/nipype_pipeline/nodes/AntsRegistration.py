import os

from nipype.interfaces.base import (
    BaseInterface,
    BaseInterfaceInputSpec,
    TraitedSpec,
    File,
    traits,
    isdefined,
)

# antspyx is imported lazily inside _run_interface so that merely importing this
# module (as the workflow builders and the graph tests do) never pays the cost of
# loading the ITK bindings.

ITK_THREADS_VAR = "ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS"

# ANTs names its products by role, and antspyx returns those file names as-is:
# <prefix>0GenericAffine.mat, <prefix>1Warp.nii.gz, <prefix>1InverseWarp.nii.gz.
AFFINE_SUFFIX = ".mat"
INVERSE_WARP_MARKER = "InverseWarp"

# test_run schedules: drastically fewer iterations than the antspyx defaults
# (aff_iterations=(2100, 1200, 1200, 10), reg_iterations=(40, 20, 0)), trading
# registration accuracy for the speed the prerelease sweep needs. aff_iterations
# MUST stay length 4: antspyx raises if it does not match the default
# aff_shrink_factors/aff_smoothing_sigmas (both length 4). reg_iterations keeps
# the default's 3-level shape. These only apply to the affine/rigid stage
# (aff_iterations) and, for SyN, the deformable stage (reg_iterations); a
# Rigid/Affine run simply ignores reg_iterations.
TEST_RUN_AFF_ITERATIONS = (100, 100, 50, 10)
TEST_RUN_REG_ITERATIONS = (10, 5, 0)


class AntsRegistrationInputSpec(BaseInterfaceInputSpec):
    moving = File(exists=True, mandatory=True, desc="the moving image")
    fixed = File(exists=True, mandatory=True, desc="the reference image")
    transform_type = traits.Enum(
        "Rigid",
        "Affine",
        "SyN",
        "SyNRA",
        mandatory=True,
        desc="antspyx type_of_transform",
    )
    # antspyx silently ignores an unrecognised metric rather than raising, so
    # these enums are the only guard against a typo quietly changing the
    # registration. Values are the ones documented by ants.registration.
    aff_metric = traits.Enum(
        "mattes",
        "GC",
        "meansquares",
        usedefault=True,
        desc="metric for the affine stage",
    )
    syn_metric = traits.Enum(
        "mattes",
        "CC",
        "meansquares",
        "demons",
        usedefault=True,
        desc="metric for the deformable stage",
    )
    num_threads = traits.Int(nohash=True, desc="number of ITK threads")
    initial_transform = File(exists=True, desc="initial moving transform")
    test_run = traits.Bool(
        desc="reduce antspyx iterations for a faster, lower-accuracy sweep run"
    )
    out_prefix = traits.Str(
        "ants_reg_",
        usedefault=True,
        desc="prefix for the transform files written in the node directory",
    )


class AntsRegistrationOutputSpec(TraitedSpec):
    fwd_transforms = traits.List(
        File(exists=True), desc="ordered moving->fixed transforms (ANTs order)"
    )
    inv_transforms = traits.List(
        File(exists=True), desc="ordered fixed->moving transforms (ANTs order)"
    )
    fwd_which_to_invert = traits.List(
        traits.Bool(), desc="whichtoinvert flags matching fwd_transforms"
    )
    inv_which_to_invert = traits.List(
        traits.Bool(), desc="whichtoinvert flags matching inv_transforms"
    )
    warped_file = File(desc="moving resampled into fixed space")
    affine_transform = File(desc="affine component of the registration")
    warp_field = File(desc="forward warp component (nonlinear only)")
    inverse_warp_field = File(desc="inverse warp component (nonlinear only)")


class AntsRegistration(BaseInterface):
    """Registers a moving image to a fixed image with the antspyx library.

    Two ANTs conventions drive the output contract and are easy to get wrong:

    * a transform list is applied **right-to-left**, so ``ants.registration``
      returns the forward list as ``[warp, affine]`` -- the affine runs first;
    * the *forward* affine ``.mat`` is the only matrix ANTs ever writes, so it
      appears in the inverse list too and must be inverted when applied in that
      direction. The ``*_which_to_invert`` outputs carry exactly the flags that
      ``ants.apply_transforms`` expects alongside each list, so callers never
      have to re-derive them. Relying on the antspyx default instead is unsafe:
      it is correct for a nonlinear inverse (``matrix`` then ``warp``) but wrong
      for a linear one (a lone matrix defaults to *not* inverted), which
      resamples silently and incorrectly.
    """

    input_spec = AntsRegistrationInputSpec
    output_spec = AntsRegistrationOutputSpec

    def _run_interface(self, runtime):
        import ants

        kwargs = {
            "aff_metric": self.inputs.aff_metric,
            "syn_metric": self.inputs.syn_metric,
        }
        if isdefined(self.inputs.initial_transform):
            kwargs["initial_transform"] = self.inputs.initial_transform
        if isdefined(self.inputs.test_run) and self.inputs.test_run:
            # Fast, lower-accuracy schedules for the prerelease sweep; the graph
            # is unchanged (see TEST_RUN_* above).
            kwargs["aff_iterations"] = TEST_RUN_AFF_ITERATIONS
            kwargs["reg_iterations"] = TEST_RUN_REG_ITERATIONS

        previous_threads = os.environ.get(ITK_THREADS_VAR)
        if isdefined(self.inputs.num_threads):
            os.environ[ITK_THREADS_VAR] = str(self.inputs.num_threads)
        try:
            result = ants.registration(
                fixed=ants.image_read(self.inputs.fixed),
                moving=ants.image_read(self.inputs.moving),
                type_of_transform=self.inputs.transform_type,
                # keep the products inside the node directory so nipype can
                # hash, cache and clean them like any other node output
                outprefix=os.path.join(os.getcwd(), self.inputs.out_prefix),
                **kwargs,
            )
        finally:
            if previous_threads is None:
                os.environ.pop(ITK_THREADS_VAR, None)
            else:
                os.environ[ITK_THREADS_VAR] = previous_threads

        self._fwd = [os.path.abspath(path) for path in result["fwdtransforms"]]
        self._inv = [os.path.abspath(path) for path in result["invtransforms"]]

        self._warped = os.path.abspath(self.inputs.out_prefix + "warped.nii.gz")
        ants.image_write(result["warpedmovout"], self._warped)

        return runtime

    @staticmethod
    def _is_affine(path):
        return path.endswith(AFFINE_SUFFIX)

    def _list_outputs(self):
        outputs = self._outputs().get()
        outputs["fwd_transforms"] = self._fwd
        outputs["inv_transforms"] = self._inv
        outputs["warped_file"] = self._warped

        # Nothing in the forward list is ever inverted; in the inverse list the
        # matrix is (it is the forward affine), while a warp field is not (ANTs
        # already wrote the inverted field as 1InverseWarp).
        outputs["fwd_which_to_invert"] = [False] * len(self._fwd)
        outputs["inv_which_to_invert"] = [self._is_affine(p) for p in self._inv]

        affine = [p for p in self._fwd if self._is_affine(p)]
        if affine:
            outputs["affine_transform"] = affine[0]
        warp = [p for p in self._fwd if not self._is_affine(p)]
        if warp:
            outputs["warp_field"] = warp[0]
        inverse_warp = [
            p
            for p in self._inv
            if not self._is_affine(p) and INVERSE_WARP_MARKER in os.path.basename(p)
        ]
        if inverse_warp:
            outputs["inverse_warp_field"] = inverse_warp[0]

        return outputs
