# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-
import os
import nibabel as nib
import numpy as np
from nipype.interfaces.base import BaseInterface, BaseInterfaceInputSpec, TraitedSpec, File, traits

# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
class NilearnSmoothInputSpec(BaseInterfaceInputSpec):
    in_file = File(exists=True, mandatory=True, desc="4D EPI NIfTI image")
    mask_file = File(exists=True, mandatory=True, desc="3D brain mask")
    fwhm = traits.Float(5.0, usedefault=True, desc="FWHM in mm")

# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class NilearnSmoothOutputSpec(TraitedSpec):
    out_file = File(desc="Smoothed 4D image")

# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class NilearnSmooth(BaseInterface):
    """
    Plain isotropic Gaussian smoothing (FWHM in mm) of a 4D image with
    nilearn.image.smooth_img. The data are multiplied by the brain mask before
    smoothing (so out-of-mask voxels do not leak into the brain) and again
    after smoothing (so the output is zero outside the mask). The kernel is
    not edge-preserving and not intensity-adaptive.

    References:
    - Abraham A, et al. (2014). Machine learning for neuroimaging with scikit-learn.
      Front Neuroinform 8:14 (nilearn). doi:10.3389/fninf.2014.00014
    """
    input_spec = NilearnSmoothInputSpec
    output_spec = NilearnSmoothOutputSpec

    def _run_interface(self, runtime):
        from nilearn.image import smooth_img
        
        in_file = self.inputs.in_file
        mask_file = self.inputs.mask_file
        fwhm = self.inputs.fwhm
        out_dir = runtime.cwd
        
        mc = nib.load(in_file)
        mask_img = nib.load(mask_file)
        mask = mask_img.get_fdata() > 0
        
        # Mask before smoothing
        masked = nib.Nifti1Image(mc.get_fdata() * mask[..., None], mc.affine, mc.header)
        
        # Smooth
        sm = smooth_img(masked, fwhm)
        
        # Mask after smoothing
        out_data = sm.get_fdata() * mask[..., None]
        out_img = nib.Nifti1Image(out_data, sm.affine, sm.header)
        
        out_file = os.path.join(out_dir, "smooth.nii.gz")
        out_img.to_filename(out_file)
        
        self._out_file = out_file
        return runtime

    def _list_outputs(self):
        outputs = self._outputs().get()
        outputs["out_file"] = self._out_file
        return outputs
