# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-

from nipype.interfaces.fsl.utils import ImageMathsInputSpec
from swane.nipype_pipeline.interfaces.niimath.maths import ImageMaths
from nipype.interfaces.base import InputMultiPath, File, isdefined


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.fsl.utils.ImageMathsInputSpec)  -*-
class SumMultiVolsInputSpec(ImageMathsInputSpec):
    vol_files = InputMultiPath(
        File(exists=True), mandatory=True, desc="list of path file to sum togheter"
    )
    in_file = File(exists=True, argstr="%s", position=1)


# -*- DISCLAIMER: this class extends the niimath-backed ImageMaths (derived from nipype.interfaces.fsl.utils.ImageMaths)  -*-
class SumMultiVols(ImageMaths):
    """
    Sum multiple volumes.

    The first volume is the command's ``in_file`` and the others are added to
    it. The default output name derives from the first volume.

    """

    input_spec = SumMultiVolsInputSpec

    def _command_inputs(self):
        """
        The first volume as in_file and the op_string adding the others.

        """

        if not self.inputs.vol_files:
            return {}
        first, *others = self.inputs.vol_files
        return {
            "in_file": first,
            "op_string": "".join("-add " + vol + " " for vol in others),
        }

    def _list_outputs(self):
        # The default output name derives from in_file, which is set only while
        # the command is built.
        if isdefined(self.inputs.out_file) or not isdefined(self.inputs.vol_files):
            return super()._list_outputs()
        with self._inputs_set(in_file=self.inputs.vol_files[0]):
            return super()._list_outputs()
