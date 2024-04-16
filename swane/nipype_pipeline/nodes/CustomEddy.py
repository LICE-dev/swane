# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-

from nipype.interfaces.fsl.epi import Eddy, EddyInputSpec
from nipype.interfaces.base import (traits, isdefined)
from shutil import which


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.fsl.dti.EddyInputSpec)  -*-
class CustomEddyInputSpec(EddyInputSpec):
    use_gpu = traits.Bool(argstr="", mandatory=True)


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.epi.Eddy)  -*-
class CustomEddy(Eddy):
    """
    Custom implementation of Eddy subclass to support use_gpu input.

    """
    
    input_spec = CustomEddyInputSpec
    _cmd = "eddy"

    def __init__(self, **inputs):
        super().__init__(**inputs)
        self.inputs.on_trait_change(self._cuda_update, "use_gpu")

    def _cuda_update(self):
        # newer fsl version automatically use eddy_gpu if cuda is available, those version use eddy_cpu for cpu
        # older version has no automatic cuda usage and eddy_cpu did not exist

        if isdefined(self.inputs.use_gpu) and self.inputs.use_gpu:
            if which("eddy_cuda") is not None:
                self._cmd = "eddy_cuda"
        else:
            if which("eddy_cpu") is not None:
                self._cmd = "eddy_cpu"
            elif which("eddy_openmp") is not None:
                self._cmd = "eddy_openmp"



