# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-

from nipype.interfaces.dcm2nii import Dcm2niix, Dcm2niixInputSpec
import os
from nipype.interfaces.base import traits


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.dcm2nii.Dcm2niixInputSpec)  -*-
class CustomDcm2niixInputSpec(Dcm2niixInputSpec):
    merge_imgs = traits.Enum(
        2,
        1,
        0,
        argstr="-m %d",
        usedefault=True)


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.dcm2nii.Dcm2niix)  -*-
class CustomDcm2niix(Dcm2niix):
    """
    Custom implementation of Dcm2niix Nipype Node to support crop and merge parameters.

    """
    
    input_spec = CustomDcm2niixInputSpec

    def _run_interface(self, runtime):
        self.inputs.args = "-w 1"
        runtime = super(CustomDcm2niix, self)._run_interface(runtime)
        if self.inputs.crop is True and len(self.output_files) > 0 and os.path.exists(self.output_files[0].replace(".nii.gz", "_Crop_1.nii.gz")):
            os.remove(self.output_files[0])
            os.rename(self.output_files[0].replace(".nii.gz", "_Crop_1.nii.gz"), self.output_files[0])
        return runtime
