# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-
import os
from os.path import abspath

from nipype.interfaces.base import (
    traits,
    BaseInterface,
    BaseInterfaceInputSpec,
    TraitedSpec,
    File,
    isdefined,
)

from swane.nipype_pipeline.interfaces.ants import match_mask_geometry, thread_env

# antspyx is imported lazily inside _run_interface, as in AntsRegistration.

# antspyx's own default tolerance for ants.n4_bias_field_correction's
# convergence dict; kept explicit here because passing max_iterations means
# supplying the whole dict (antspyx indexes convergence["tol"] unconditionally).
N4_DEFAULT_TOL = 1e-7


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
class AntsN4BiasFieldCorrectionInputSpec(BaseInterfaceInputSpec):
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
    spline_distance = traits.Int(
        desc="B-spline mesh distance in mm (antspyx spline_param); "
        "antspyx default if unset",
    )
    # More than one thread can make the output vary slightly run to run
    # (multithreaded ITK sums are not guaranteed to run in a fixed order).
    # Accepted for speed; the thread count is the user's choice.
    num_threads = traits.Int(nohash=True, desc="number of ITK threads")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class AntsN4BiasFieldCorrectionOutputSpec(TraitedSpec):
    out_file = File(desc="the output unbiased image")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class AntsN4BiasFieldCorrection(BaseInterface):
    """
    Apply N4 bias field correction algorithm via the antspyx library.

    """

    input_spec = AntsN4BiasFieldCorrectionInputSpec
    output_spec = AntsN4BiasFieldCorrectionOutputSpec

    # ITK caches its thread count on first use: run each node in a new process
    # so that num_threads is honoured (see MonitoredMultiProcPlugin).
    fresh_process = True

    def _run_interface(self, runtime):
        with thread_env(self.inputs.num_threads):
            import ants

            out_file = self._gen_outfilename()

            # load image as float, as requested by N4
            img = ants.image_read(self.inputs.in_file, pixeltype="float")

            # --- MASK LOGIC ---
            if isdefined(self.inputs.mask_file):
                # If a mask is provided, use it (binarize in case it isn't already).
                # Cast back to float: antspyx's N4 correction is markedly weaker when
                # given an unsigned-char mask (the boolean comparison's dtype) than a
                # float mask with the same 0/1 values.
                mask = ants.image_read(self.inputs.mask_file)
                mask = (mask > 0).clone("float")
            elif self.inputs.skull_stripped:
                # Otherwise, if the input sequence is skull stripped, assume brain for every non 0 voxel
                mask = (img > 0).clone("float")
            else:
                # In other cases use automatic Otsu thresholding
                mask = ants.otsu_segmentation(img, k=1)

            # --- Check geometrical coherence between mask and img ---
            mask = match_mask_geometry(img, mask)

            # --- N4 (antspyx standard parameters, aside from mask/iterations) ---
            kwargs = {}
            if isdefined(self.inputs.max_iterations):
                kwargs["convergence"] = {
                    "iters": list(self.inputs.max_iterations),
                    "tol": N4_DEFAULT_TOL,
                }
            if isdefined(self.inputs.spline_distance):
                kwargs["spline_param"] = self.inputs.spline_distance

            corrected = ants.n4_bias_field_correction(img, mask=mask, **kwargs)

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
