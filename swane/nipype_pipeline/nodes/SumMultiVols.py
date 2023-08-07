# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-

from nipype.interfaces.fsl.utils import ImageMaths, ImageMathsInputSpec
from nipype.interfaces.base import InputMultiPath, File


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.fsl.utils.ImageMathsInputSpec)  -*-
class SumMultiVolsInputSpec(ImageMathsInputSpec):
    vol_files = InputMultiPath(File(exists=True), mandatory=True, desc="list of path file to sum togheter")
    in_file = File(exists=True, argstr="%s", position=1)


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.fsl.utils.ImageMaths)  -*-
class SumMultiVols(ImageMaths):
    """
    Sum multiple volumes.

    """
    
    input_spec = SumMultiVolsInputSpec

    def _parse_inputs(self, skip=None):
        """
        Custom implementation of _parse_inputs func to manage summ.

        """

        first = True

        for vol in self.inputs.vol_files:
            if first:
                self.inputs.op_string = ""
                self.inputs.in_file = vol
                first = False
            else:
                self.inputs.op_string += "-add " + vol + " "

        parse = super(SumMultiVols, self)._parse_inputs(skip)

        return parse
