import os

import numpy as np
import nibabel as nib
from nipype.interfaces.base import (
    BaseInterface,
    BaseInterfaceInputSpec,
    TraitedSpec,
    File,
    traits,
    isdefined,
)

# antspyx is imported lazily inside _run_interface, as in AntsRegistration.


class AntsApplyTransformsInputSpec(BaseInterfaceInputSpec):
    input_image = File(exists=True, mandatory=True, desc="the image to resample")
    reference_image = File(
        exists=True, mandatory=True, desc="the image defining the output grid"
    )
    transformlist = traits.List(
        File(exists=True),
        mandatory=True,
        desc="ordered ANTs transform list (applied right-to-left)",
    )
    interpolator = traits.Enum(
        "linear",
        "nearestNeighbor",
        "genericLabel",
        "bSpline",
        usedefault=True,
        desc="antspyx interpolator; nearestNeighbor for label maps",
    )
    which_to_invert = traits.List(
        traits.Bool(),
        desc="one flag per transform, as produced by AntsRegistration; "
        "left unset, antspyx applies its own default",
    )
    out_file = File(genfile=True, hash_files=False, desc="the resampled image")


class AntsApplyTransformsOutputSpec(TraitedSpec):
    out_file = File(desc="the resampled image")


class AntsApplyTransforms(BaseInterface):
    """Resamples an image through an ordered ANTs transform list.

    ``transformlist`` is passed to antspyx untouched: ANTs applies it
    right-to-left, so the caller owns the ordering (``AntsRegistration``
    publishes lists already in that order).

    ``which_to_invert`` maps onto the antspyx ``whichtoinvert`` parameter and
    should be fed from the matching ``*_which_to_invert`` output of
    ``AntsRegistration``. It is forwarded only when set, so that leaving it
    alone keeps the antspyx default rather than substituting a guess.
    """

    input_spec = AntsApplyTransformsInputSpec
    output_spec = AntsApplyTransformsOutputSpec

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

        moving = ants.image_read(self.inputs.input_image)
        # antspyx refuses a 4D moving image (e.g. a whole fMRI run) under the
        # default imagetype=0 (scalar) with "Set imagetype 3 to transform time
        # series images." -- moving.dimension is 4 exactly for that case in
        # every caller of this generic node (every 3D use -- FA, CT, ROI masks
        # -- stays imagetype 0).
        imagetype = 3 if moving.dimension == 4 else 0

        resampled = ants.apply_transforms(
            fixed=ants.image_read(self.inputs.reference_image),
            moving=moving,
            transformlist=self.inputs.transformlist,
            interpolator=self.inputs.interpolator,
            imagetype=imagetype,
            **kwargs,
        )

        out_file = self._gen_outfilename()
        ants.image_write(resampled, out_file)
        self._restamp_reference_header(out_file)

        return runtime

    def _restamp_reference_header(self, out_file):
        """Give the result the reference image's exact header.

        ``apply_transforms`` resamples into the reference grid, so the two share
        a geometry; writing through ITK nevertheless rewrites header fields the
        rest of the pipeline relies on (it normalises ``sform_code`` and
        ``xyzt_units``). Copying the reference header keeps the output in
        exactly the image space swane's other nibabel nodes produce, and
        ``set_data_dtype`` clears any residual scaling so values are not
        re-scaled on write. Skipped if the result is not on the reference grid
        (nothing to preserve, and the reference header would be wrong).

        A time-series moving image (``imagetype=3``, e.g. a whole fMRI run)
        resamples onto the reference's spatial grid plus its own, unrelated
        time axis: the reference (a static volume) has no repetition time to
        borrow, so that axis's size/zoom/units are taken from the original
        moving image instead of the reference.
        """
        reference = nib.load(self.inputs.reference_image)
        resampled = nib.load(out_file)
        ref_shape = reference.shape
        if resampled.shape[: len(ref_shape)] != ref_shape:
            return
        header = reference.header.copy()
        header.set_data_dtype(np.float32)
        if resampled.ndim > reference.ndim:
            moving = nib.load(self.inputs.input_image)
            header.set_data_shape(resampled.shape)
            header.set_zooms(
                reference.header.get_zooms()
                + moving.header.get_zooms()[len(ref_shape) :]
            )
            xyz_unit, _ = header.get_xyzt_units()
            _, t_unit = moving.header.get_xyzt_units()
            header.set_xyzt_units(xyz_unit, t_unit)
            data = resampled.get_fdata(dtype=np.float32)
            nib.save(nib.Nifti1Image(data, reference.affine, header), out_file)
            return
        data = resampled.get_fdata(dtype=np.float32)
        nib.save(nib.Nifti1Image(data, reference.affine, header), out_file)

    def _gen_outfilename(self):
        out_file = self.inputs.out_file
        if not isdefined(out_file):
            out_file = "ants_resampled_" + os.path.basename(self.inputs.input_image)
        return os.path.abspath(out_file)

    def _gen_filename(self, name):
        if name == "out_file":
            return self._gen_outfilename()
        return None

    def _list_outputs(self):
        outputs = self._outputs().get()
        outputs["out_file"] = self._gen_outfilename()
        return outputs
