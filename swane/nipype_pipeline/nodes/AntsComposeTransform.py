# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-
import os

from nipype.interfaces.base import (
    BaseInterface,
    BaseInterfaceInputSpec,
    TraitedSpec,
    File,
    traits,
    isdefined,
)

from swane.nipype_pipeline.nodes.AntsRegistration import ITK_THREADS_VAR

# antspyx is imported lazily inside _run_interface, as in AntsRegistration.

# antspyx builds the composite's file name itself: with compose="<prefix>" it
# writes "<prefix>comptx.nii.gz" (ants.apply_transforms, antspyx 0.6.3) and
# returns that path, or None when nothing was written. The prefix is ours, so
# the resulting name is deterministic and _list_outputs can be state-free.
COMPOSE_PREFIX = "composed_"
COMPOSE_SUFFIX = "comptx.nii.gz"


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
class AntsComposeTransformInputSpec(BaseInterfaceInputSpec):
    transformlist = traits.List(
        File(exists=True),
        mandatory=True,
        desc="ordered ANTs transform list to flatten (applied right-to-left)",
    )
    which_to_invert = traits.List(
        traits.Bool(),
        desc="one flag per transform, as produced by AntsRegistration; "
        "left unset, antspyx applies its own default",
    )
    reference_image = File(
        exists=True,
        mandatory=True,
        desc="the image defining the grid the field is sampled on",
    )
    num_threads = traits.Int(nohash=True, desc="number of ITK threads")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class AntsComposeTransformOutputSpec(TraitedSpec):
    out_field = File(desc="the composed displacement field")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class AntsComposeTransform(BaseInterface):
    """Flattens an ordered ANTs transform list into one displacement field.

    ANTs describes a registration as a *list* of transforms plus a matching
    list of ``which_to_invert`` flags, which is exactly what ``AntsRegistration``
    publishes. That pair travels fine inside a workflow, but a workflow
    *boundary* in swane carries a single warp file per direction. Composing
    resolves the pair into one directional field sampled on ``reference_image``:
    the ordering and the inversion flags are baked in, so a consumer applies the
    result with ``transformlist=[field]`` and **no** ``which_to_invert`` at all.

    Two properties of the antspyx composition drive this implementation:

    * the composite depends only on the transform list and the *reference*
      domain, never on the moving image (verified against antspyx 0.6.3), so
      the reference is handed to ``apply_transforms`` as both ``fixed`` and
      ``moving`` rather than loading an unrelated volume;
    * the direction is the one ANTs uses everywhere -- the field maps the
      reference grid back into the source domain, i.e. it is the field that
      resamples an image *into* ``reference_image``. Composing the forward list
      therefore takes the registration's *fixed* image as reference, and the
      inverse list its *moving* image.
    """

    input_spec = AntsComposeTransformInputSpec
    output_spec = AntsComposeTransformOutputSpec

    def _run_interface(self, runtime):
        import ants

        kwargs = {}
        if isdefined(self.inputs.which_to_invert):
            if len(self.inputs.which_to_invert) != len(self.inputs.transformlist):
                raise ValueError(
                    "which_to_invert must hold exactly one flag per transform "
                    f"({len(self.inputs.which_to_invert)} flags for "
                    f"{len(self.inputs.transformlist)} transforms)"
                )
            kwargs["whichtoinvert"] = self.inputs.which_to_invert

        reference = ants.image_read(self.inputs.reference_image)

        previous_threads = os.environ.get(ITK_THREADS_VAR)
        if isdefined(self.inputs.num_threads):
            os.environ[ITK_THREADS_VAR] = str(self.inputs.num_threads)
        try:
            composed = ants.apply_transforms(
                fixed=reference,
                moving=reference,
                transformlist=self.inputs.transformlist,
                compose=self._compose_prefix(),
                **kwargs,
            )
        finally:
            if previous_threads is None:
                os.environ.pop(ITK_THREADS_VAR, None)
            else:
                os.environ[ITK_THREADS_VAR] = previous_threads

        # antspyx returns None instead of raising when the composite was not
        # written, and the name it picks is the contract _list_outputs relies
        # on: check both rather than let a later node fail on a missing file.
        expected = self._composed_field()
        if composed is None or not os.path.exists(expected):
            raise RuntimeError(
                "antspyx did not write the composed transform expected at "
                f"{expected}"
            )
        if os.path.abspath(composed) != expected:
            raise RuntimeError(
                f"antspyx wrote the composed transform to {composed}, not to "
                f"the expected {expected}: the installed antspyx names compose "
                "products differently than this node assumes"
            )

        # No header re-stamping here, unlike AntsApplyTransforms: the product is
        # an ITK displacement field, a 5-D (x, y, z, 1, 3) vector image whose
        # intent code ITK needs to read it back as a transform. It already
        # carries the reference image's grid and affine (antspyx samples it on
        # the domain given as `fixed`), so there is nothing to restore and a
        # scalar header would only corrupt it.
        return runtime

    def _compose_prefix(self):
        return os.path.abspath(COMPOSE_PREFIX)

    def _composed_field(self):
        return self._compose_prefix() + COMPOSE_SUFFIX

    def _list_outputs(self):
        outputs = self._outputs().get()
        outputs["out_field"] = self._composed_field()
        return outputs
