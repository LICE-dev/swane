# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-

from nipype.interfaces.fsl import ProbTrackX2
from nipype.interfaces.fsl.dti import ProbTrackX2InputSpec
from nipype.interfaces.base import traits


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.fsl.dti.ProbTrackX2InputSpec)  -*-
class CustomProbTrackX2InputSpec(ProbTrackX2InputSpec):
    rseed = traits.Int(argstr="--rseed=%s", desc="random seed")
    sample_random_points = traits.Float(
        argstr="--sampvox=%f", desc="sample random points within seed voxels"
    )


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.fsl.ProbTrackX2)  -*-
class CustomProbTrackX2(ProbTrackX2):
    """
    Custom implementation of ProbTrackX2 Nipype Node to support --rseed as Int and --sampvox as Float.

    """
    
    input_spec = CustomProbTrackX2InputSpec
