# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-
import SimpleITK as sitk
from os.path import abspath
import os
import numpy as np
from nipype.interfaces.base import (
    traits,
    BaseInterface,
    BaseInterfaceInputSpec,
    TraitedSpec,
    File,
    isdefined,
)


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
        "(SimpleITK default is [50, 50, 50, 50])",
    )
    num_threads = traits.Int(nohash=True, desc="number of ITK threads")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class N4BiasFieldCorrectionOutputSpec(TraitedSpec):
    out_file = File(desc="the output unbiased image")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class N4BiasFieldCorrection(BaseInterface):
    """
    Apply N4 bias field correction algorithm

    """

    input_spec = N4BiasFieldCorrectionInputSpec
    output_spec = N4BiasFieldCorrectionOutputSpec

    def _run_interface(self, runtime):
        out_file = self._gen_outfilename()

        # load image as float, as requested by N4
        img = sitk.ReadImage(self.inputs.in_file, sitk.sitkFloat32)

        # --- MASK LOGIC ---
        if isdefined(self.inputs.mask_file):
            # If a mask is provided, use it
            mask = sitk.ReadImage(self.inputs.mask_file, sitk.sitkUInt8)
            mask = sitk.Cast(mask > 0, sitk.sitkUInt8)
        elif self.inputs.skull_stripped:
            # Otherwise, if the input sequence is skull stripped, assume brain for every non 0 voxel
            mask = sitk.Cast(img > 0, sitk.sitkUInt8)
        else:
            # In other cases use automatic thresholding
            mask = sitk.OtsuThreshold(img, 0, 1, 200)

        # --- Check geometrical coherence between mask and img ---
        max_tolerance = 0.1
        origin_img = np.array(img.GetOrigin())
        origin_mask = np.array(mask.GetOrigin())
        distance = np.linalg.norm(origin_img - origin_mask)
        if distance > 0:
            if distance <= max_tolerance:
                # If mask and img have minimal difference, force mask in img geometrical space
                mask.CopyInformation(img)
            else:
                # If difference is bigger, stop
                raise RuntimeError(
                    f"Image and Mask do not coincide! Origin distance: {distance:.4f} mm. "
                    f"Maximum allowed threshold is {max_tolerance} mm."
                )

        # --- Threads control ---
        if isdefined(self.inputs.num_threads):
            sitk.ProcessObject.SetGlobalDefaultNumberOfThreads(self.inputs.num_threads)

        # --- Apply a minimal shrink factor to speed up ---
        shrink_factor = 2
        img_shrunk = sitk.Shrink(img, [shrink_factor] * img.GetDimension())
        mask_shrunk = sitk.Shrink(mask, [shrink_factor] * mask.GetDimension())

        # --- N4 ---
        corrector = sitk.N4BiasFieldCorrectionImageFilter()
        if isdefined(self.inputs.max_iterations):
            corrector.SetMaximumNumberOfIterations(self.inputs.max_iterations)
        corrector.Execute(img_shrunk, mask_shrunk)

        # --- Apply full resolution bias fied ---
        log_bias_field = corrector.GetLogBiasFieldAsImage(img)
        corrected = img / sitk.Exp(log_bias_field)

        # save output
        sitk.WriteImage(corrected, out_file)

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
