# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-

from nipype.interfaces.dcm2nii import Dcm2niix, Dcm2niixInputSpec
import os
from nipype.pipeline.engine.nodes import NodeExecutionError
from nipype.interfaces.base import traits


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.dcm2nii.Dcm2niixInputSpec)  -*-
class CustomDcm2niixInputSpec(Dcm2niixInputSpec):
    merge_imgs = traits.Enum(
        2,
        1,
        0,
        argstr="-m %d",
        usedefault=True)
    expected_files = traits.Int(default_value=1, usedefault=True)
    request_dti = traits.Bool(default_value=False, usedefault=True)


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.dcm2nii.Dcm2niix)  -*-
class CustomDcm2niix(Dcm2niix):
    """
    Custom implementation of Dcm2niix Nipype Node to support crop and merge parameters.

    """
    
    input_spec = CustomDcm2niixInputSpec

    def _run_interface(self, runtime):
        self.inputs.args = "-w 1"
        runtime = super(CustomDcm2niix, self)._run_interface(runtime)
        if self.inputs.crop:
            for index, value in enumerate(self.output_files):
                if os.path.exists(value.replace(".nii.gz", "_Crop_1.nii.gz")):
                    os.remove(self.output_files[index])
                    os.rename(self.output_files[index].replace(".nii.gz", "_Crop_1.nii.gz"), self.output_files[index])
            
        # in mosaic conversion, nipype misread dcm2niix output and generate a duplicate list of results
        # next line remove duplicates from output files array
        self.output_files = [*set(self.output_files)]

        # Expected files check
        if self.inputs.expected_files > 0 and len(self.output_files) != self.inputs.expected_files:
                raise NodeExecutionError("Dcm2niix generated %d nifti files while %s were expected" % (len(self.output_files), self.inputs.expected_files))

        # Bvec and Bvals check
        if self.inputs.request_dti and (len(self.bvals) == 0 or len(self.bvecs) == 0):
                raise NodeExecutionError("Dcm2niix could not generate requested bvals and bvecs files")

        return runtime
