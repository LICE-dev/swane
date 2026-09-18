# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-
"""
Upfront brain bounding-box crop of the 4D diffusion-weighted series.

A brain mask is estimated with :func:`dipy.segment.mask.median_otsu`
(``median_radius=4``, ``numpass=4`` -- dipy's documented robust defaults) from
the **mean across all volumes** of the series, and the 4D series is cropped to
that mask's bounding box, generously grown by ``DILATE_ITERATIONS`` mask
dilations and ``CROP_PAD_VOXELS`` of explicit voxel pad. Placed immediately after
orientation, this crop lets every upstream node (denoise -> motion -> bias ->
tensor -> CSD) work on the brain sub-box instead of paying for the empty margin,
avoiding dead weight in both time and RAM (spec section "C1 -- crop the 4D DWI upfront, with
median_otsu").

**Why the mean of all volumes, not the b0.** This node runs *before* motion
correction, so the series still carries inter-volume head motion: the brain sits
at a slightly different position in each volume. A bbox built from a single
volume (the b0) would follow only that one position and could clip the brain of
volumes shifted by motion. The mean across all volumes is the motion envelope --
it spans every head position -- which is exactly why dipy's ``reconst_dti``
example builds its mask from several volumes rather than one.

**Why median_otsu is fine here even though it is a weak brain extractor.** This
is a *crop*, not a *mask*: median_otsu only has to yield a rough envelope that,
once dilated and padded, comfortably contains the brain. It is never used to zero
out non-brain voxels. The pipeline's accurate brain extraction stays with the
deskull node (the optimised engine), whose ``nodif_brain`` still drives the tight
tracking crop downstream (``DipyTracking``). So the good extractor governs the
precise mask where precision matters, and median_otsu only sizes the cheap
upfront generous box where looseness is harmless (spec "Note on C1 and C5").

**The crop is generous, and lossless with respect to the brain.** A too-large
crop is correct; a too-small crop -- one that clips brain -- is an unrecoverable
defect. A crop is *not* a mask: the original voxel data is subselected, never
multiplied by the mask, so nothing downstream depends on a tight boundary.

**World coordinates are preserved end to end.** The cropped affine follows the
project's :func:`swane.nipype_pipeline.interfaces.dipy.DipyTracking.shift_affine_for_crop`
convention -- shifting the translation by the crop start offset so the
cropped-space voxel ``(0, 0, 0)`` maps to the same world point it did before the
crop. This keeps streamlines, registration matrices and the reference-space
transform unaffected: a full-FOV run and a cropped run produce the same
streamlines in world coordinates. ``shift_affine_for_crop`` (and its companion
:func:`foreground_bbox_slices`) are reused from ``DipyTracking`` as the single
source of truth for the crop geometry.

``median_otsu``'s own ``autocrop`` option is deliberately not used: it is
deprecated in dipy 1.11 (removed in 1.13), it returns no affine (so the affine
shift must be computed anyway), and it crops tightly to the mask with no room for
an explicit pad. Computing the bounding box from the mask and cropping with the
project convention gives the generous, pad-controlled, world-preserving crop this
node needs; :func:`foreground_bbox_slices` at ``pad=0`` coincides with dipy's own
``bounding_box``, so the crop convention is dipy's, not a divergent one.

**On-disk dtype.** A crop transforms no voxel value, so the source's on-disk
dtype is kept -- but only when it can actually represent the data. ``dataobj``
yields *scaled* values (``raw * scl_slope + scl_inter``), and dcm2niix writes a
scaling whenever the acquisition's dynamic range exceeds the integer type.
Casting those scaled values back to the source integer dtype then overflows and
wraps around, silently destroying the series; nibabel recomputes the scaling on
save, so the slope cannot be carried through either (verified against nibabel
5.4.2). When the source carries a scaling the crop is therefore written as
float32, exactly as DipyDenoise / DipyMotionCorrection / DwiBiasCorrection
downstream already do. Unscaled sources keep their dtype, so the common int16
case still pays no size penalty.

The b-values and b-vectors are invariant to a spatial crop -- gradient
directions and b-values do not change under a translation -- so they are not an
input here and continue to flow downstream unchanged from the conversion node.
"""

import os
from os.path import abspath, basename

import numpy as np
import nibabel as nib
from nipype.interfaces.base import (
    traits,
    BaseInterface,
    BaseInterfaceInputSpec,
    TraitedSpec,
    File,
    isdefined,
)

from swane.nipype_pipeline.interfaces.dipy.DipyTracking import (
    foreground_bbox_slices,
    shift_affine_for_crop,
)

# BLAS/OpenMP thread-count environment variables, pinned like the ITK variable
# in AntsN4BiasFieldCorrection so numpy's OpenBLAS backend does not multithread
# invisibly to nipype's resource accounting.
OMP_THREADS_VAR = "OMP_NUM_THREADS"
OPENBLAS_THREADS_VAR = "OPENBLAS_NUM_THREADS"

# median_otsu parameters: dipy's robust defaults for 1.5T/3T DWI from GE/Philips/
# Siemens (its docstring recommends median_radius=4, numpass=4).
MEDIAN_RADIUS = 4
NUMPASS = 4

# Generosity controls. The mask is dilated before the bounding box is taken, and
# the box is then grown by an explicit voxel pad and clipped to the FOV. Both are
# deliberately loose: cutting brain is unrecoverable, an oversized crop is not.
#
# DILATE follows dipy's reconst_dti example (dilate=2); it is median_otsu's own
# mask-shape control. The crop generosity is carried by the explicit PAD, ensuring
# the mean-of-volumes median_otsu box contains the nodif_brain and WM seed mask
# with margin to spare. A crop is not a mask -- this margin costs only a
# little more background, never a boundary anything downstream depends on.
DILATE_ITERATIONS = 2
CROP_PAD_VOXELS = 8


def lossless_out_dtype(in_nii):
    """The dtype the cropped series can be written in without losing data.

    ``dataobj`` yields scaled values; they round-trip through the source dtype
    only when the source carries no ``scl_slope``/``scl_inter``. With a scaling
    present the cast overflows (int16 wraps at 32767) and nibabel drops the
    slope on save, so float32 is the only faithful option.
    """
    slope = getattr(in_nii.dataobj, "slope", 1.0)
    inter = getattr(in_nii.dataobj, "inter", 0.0)
    if slope in (None, 1.0) and inter in (None, 0.0):
        return in_nii.get_data_dtype()
    return np.dtype(np.float32)


def crop_4d_median_otsu(
    data,
    affine,
    *,
    median_radius=MEDIAN_RADIUS,
    numpass=NUMPASS,
    dilate=DILATE_ITERATIONS,
    pad=CROP_PAD_VOXELS,
):
    """Generously crop a 4D DWI to its brain bounding box, world-preserving.

    ``median_otsu`` builds a brain mask from the **mean across all volumes** (the
    motion envelope, since this runs before motion correction); the mask -- not
    the masked volume -- is reduced to its bounding box via
    :func:`foreground_bbox_slices` grown by ``pad`` voxels, and the **original**
    4D ``data`` is subselected with those slices (a crop, not a mask). The
    returned affine follows :func:`shift_affine_for_crop`, so world coordinates
    are unchanged.

    Returns ``(cropped_4d, cropped_affine)``.
    """
    from dipy.segment.mask import median_otsu

    data = np.asarray(data)
    # Mean over every volume: a single volume follows only its own head position,
    # but the crop must contain the brain across all motion states in the series.
    mean_volume = data.mean(axis=-1)
    # median_otsu is used only for the mask; the first return (the masked volume)
    # is discarded because a crop must not zero out anything the mask excludes --
    # the original data is subselected below.
    _, mask = median_otsu(
        mean_volume,
        median_radius=median_radius,
        numpass=numpass,
        dilate=dilate,
    )
    crop = foreground_bbox_slices((mask,), data.shape[:3], pad=pad)
    cropped = np.ascontiguousarray(data[crop])
    cropped_affine = shift_affine_for_crop(affine, crop)
    return cropped, cropped_affine


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
class DwiCropInputSpec(BaseInterfaceInputSpec):
    in_file = File(
        exists=True, mandatory=True, desc="the input 4D diffusion-weighted image"
    )
    num_threads = traits.Int(
        nohash=True, desc="number of OpenMP/OpenBLAS threads to use"
    )
    out_file = File(desc="the output cropped 4D image")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class DwiCropOutputSpec(TraitedSpec):
    out_file = File(desc="the output cropped 4D image")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class DwiCrop(BaseInterface):
    """
    Crops a 4D DWI to a generous brain bounding box (dipy ``median_otsu`` mask on
    the mean of all volumes), shifting the affine so world coordinates are
    preserved. Placed upfront so the diffusion stream never carries the empty FOV
    margin.

    """

    input_spec = DwiCropInputSpec
    output_spec = DwiCropOutputSpec

    def _run_interface(self, runtime):
        out_file = self._gen_outfilename()

        in_nii = nib.load(self.inputs.in_file)
        # Read as float32 for the mask + crop geometry: the full-FOV 4D volume is
        # large and dipy upcasts only what it needs; the saved output is cast back
        # to the input dtype below (a crop transforms no voxel value).
        data = np.asarray(in_nii.dataobj, dtype=np.float32)

        # Pin the process-level thread environment to the declared count, saving
        # and restoring like the ITK variable in AntsN4BiasFieldCorrection.
        previous_omp = os.environ.get(OMP_THREADS_VAR)
        previous_openblas = os.environ.get(OPENBLAS_THREADS_VAR)
        if isdefined(self.inputs.num_threads):
            os.environ[OMP_THREADS_VAR] = str(self.inputs.num_threads)
            os.environ[OPENBLAS_THREADS_VAR] = str(self.inputs.num_threads)
        try:
            cropped, cropped_affine = crop_4d_median_otsu(data, in_nii.affine)
        finally:
            for var, previous in (
                (OMP_THREADS_VAR, previous_omp),
                (OPENBLAS_THREADS_VAR, previous_openblas),
            ):
                if previous is None:
                    os.environ.pop(var, None)
                else:
                    os.environ[var] = previous

        # Preserve the header (voxel sizes/orientation are unchanged by a crop);
        # the shifted affine replaces the header's, and nibabel recomputes the
        # dimensions from the cropped shape on save. The dtype is the source's
        # only when the source is unscaled -- see lossless_out_dtype.
        out_dtype = lossless_out_dtype(in_nii)
        out_nii = nib.Nifti1Image(
            cropped.astype(out_dtype), cropped_affine, in_nii.header
        )
        out_nii.header.set_data_dtype(out_dtype)
        nib.save(out_nii, out_file)

        return runtime

    def _gen_outfilename(self):
        out_file = self.inputs.out_file
        if not isdefined(out_file) and isdefined(self.inputs.in_file):
            out_file = "crop_" + basename(self.inputs.in_file)
        return abspath(out_file)

    def _list_outputs(self):
        outputs = self.output_spec().get()
        outputs["out_file"] = self._gen_outfilename()
        return outputs
