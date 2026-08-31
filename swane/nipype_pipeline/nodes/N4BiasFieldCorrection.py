# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-
import os
from os.path import abspath

import numpy as np
from nipype.interfaces.base import (
    traits,
    BaseInterface,
    BaseInterfaceInputSpec,
    TraitedSpec,
    File,
    isdefined,
)

# antspyx is imported lazily inside _run_interface, as in AntsRegistration.

ITK_THREADS_VAR = "ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS"

# antspyx's own default tolerance for ants.n4_bias_field_correction's
# convergence dict; kept explicit here because passing max_iterations means
# supplying the whole dict (antspyx indexes convergence["tol"] unconditionally).
N4_DEFAULT_TOL = 1e-7


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
class N4BiasFieldCorrectionInputSpec(BaseInterfaceInputSpec):
    in_file = File(exists=True, mandatory=True, desc="the input image")
    out_file = File(desc="the output unbiased image")
    skull_stripped = traits.Bool(
        False,
        usedefault=True,
        desc="Set to True if the input image is already skull stripped",
    )
    mask_file = File(exists=True, desc="the mask image")
    max_iterations = traits.List(
        traits.Int,
        desc="maximum number of iterations per resolution level "
        "(antspyx default is [50, 50, 50, 50])",
    )
    num_threads = traits.Int(nohash=True, desc="number of ITK threads")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class N4BiasFieldCorrectionOutputSpec(TraitedSpec):
    out_file = File(desc="the output unbiased image")


class N4BiasFieldCorrection(BaseInterface):
    """
    Apply N4 bias field correction algorithm via the antspyx library.

    """

    input_spec = N4BiasFieldCorrectionInputSpec
    output_spec = N4BiasFieldCorrectionOutputSpec

    def _run_interface(self, runtime):
        import ants

        out_file = self._gen_outfilename()

        # load image as float, as requested by N4
        img = ants.image_read(self.inputs.in_file, pixeltype="float")

        # --- MASK LOGIC ---
        if isdefined(self.inputs.mask_file):
            # If a mask is provided, use it (binarize in case it isn't already)
            mask = ants.image_read(self.inputs.mask_file)
            mask = mask > 0
        elif self.inputs.skull_stripped:
            # Otherwise, if the input sequence is skull stripped, assume brain for every non 0 voxel
            mask = img > 0
        else:
            # In other cases use automatic Otsu thresholding
            mask = ants.otsu_segmentation(img, k=1)

        # --- Check geometrical coherence between mask and img ---
        max_tolerance = 0.1
        origin_img = np.array(img.origin)
        origin_mask = np.array(mask.origin)
        distance = np.linalg.norm(origin_img - origin_mask)
        if distance > 0:
            if distance <= max_tolerance:
                # If mask and img have minimal difference, force mask in img geometrical space
                mask.set_origin(img.origin)
                mask.set_spacing(img.spacing)
                mask.set_direction(img.direction)
            else:
                # If difference is bigger, stop
                raise RuntimeError(
                    f"Image and Mask do not coincide! Origin distance: {distance:.4f} mm. "
                    f"Maximum allowed threshold is {max_tolerance} mm."
                )

        # --- N4 (antspyx standard parameters, aside from mask/iterations) ---
        kwargs = {}
        if isdefined(self.inputs.max_iterations):
            kwargs["convergence"] = {
                "iters": list(self.inputs.max_iterations),
                "tol": N4_DEFAULT_TOL,
            }

        # --- Threads control ---
        previous_threads = os.environ.get(ITK_THREADS_VAR)
        if isdefined(self.inputs.num_threads):
            os.environ[ITK_THREADS_VAR] = str(self.inputs.num_threads)
        try:
            corrected = ants.n4_bias_field_correction(img, mask=mask, **kwargs)
        finally:
            if previous_threads is None:
                os.environ.pop(ITK_THREADS_VAR, None)
            else:
                os.environ[ITK_THREADS_VAR] = previous_threads

        # save output
        ants.image_write(corrected, out_file)

        return runtime

    def _gen_outfilename(self):
        out_file = self.inputs.out_file
        if not isdefined(out_file) and isdefined(self.inputs.in_file):
            out_file = "unbiased_" + os.path.basename(self.inputs.in_file)
        return abspath(out_file)

    def _list_outputs(self):
        outputs = self.output_spec().get()
        outputs["out_file"] = self._gen_outfilename()
        return outputs
