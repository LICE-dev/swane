# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-

from nipype.interfaces.dcm2nii import Dcm2niix, Dcm2niixInputSpec
import os
from nipype.pipeline.engine.nodes import NodeExecutionError
from nipype.interfaces.base import traits


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.dcm2nii.Dcm2niixInputSpec)  -*-
class CustomDcm2niixInputSpec(Dcm2niixInputSpec):
    name_conflicts = traits.Enum(
        2,
        1,
        0,
        argstr="-w %d",
        usedefault=True,
        descr="write behavior for name conflicts - [0=skip duplicates, 1=overwrite, 2=add suffix]",
    )
    expected_files = traits.Int(default_value=1, usedefault=True)
    request_dti = traits.Bool(default_value=False, usedefault=True)


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.dcm2nii.Dcm2niix)  -*-
class CustomDcm2niix(Dcm2niix):
    """
    Custom implementation of Dcm2niix Nipype Node to support crop and merge parameters.

    """
    
    input_spec = CustomDcm2niixInputSpec

    def _run_interface(self, runtime):
        runtime = super(CustomDcm2niix, self)._run_interface(runtime)

        # Expected files check
        if self.inputs.expected_files > 0 and len(self.output_files) != self.inputs.expected_files:
                raise NodeExecutionError("Dcm2niix generated %d nifti files while %s were expected" % (len(self.output_files), self.inputs.expected_files))

        # Bvec and Bvals check
        if self.inputs.request_dti and (len(self.bvals) == 0 or len(self.bvecs) == 0):
                raise NodeExecutionError("Dcm2niix could not generate requested bvals and bvecs files")

        return runtime
