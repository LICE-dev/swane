# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-

from nipype.interfaces.fsl import ProbTrackX2
from nipype.interfaces.fsl.dti import ProbTrackX2InputSpec
from nipype.interfaces.base import traits, isdefined


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.fsl.dti.ProbTrackX2InputSpec)  -*-
class CustomProbTrackX2InputSpec(ProbTrackX2InputSpec):
    use_gpu = traits.Bool(False, desc="Use the GPU version of probtrackx")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.fsl.ProbTrackX2)  -*-
class CustomProbTrackX2(ProbTrackX2):
    """
    Custom implementation of ProbTrackX2 Nipype Node to support --rseed as Int and --sampvox as Float.

    """
    
    input_spec = CustomProbTrackX2InputSpec
    _default_cmd = ProbTrackX2._cmd

    def __init__(self, **inputs):
        super().__init__(**inputs)
        self.inputs.on_trait_change(self._cuda_update, "use_gpu")

    def _cuda_update(self):
        if isdefined(self.inputs.use_gpu) and self.inputs.use_gpu:
            self._cmd = "probtrackx2_gpu"
        else:
            self._cmd = self._default_cmd
