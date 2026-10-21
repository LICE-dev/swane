from nipype.interfaces.fsl.utils import ImageMathsInputSpec, ImageMathsOutputSpec
from swane.nipype_pipeline.interfaces.niimath.maths import ImageMaths
from nipype.interfaces.base import traits


class NiiMathRobustFovInputSpec(ImageMathsInputSpec):
    brainsize = traits.Int(desc="size of brain in z-dimension")


class NiiMathRobustFov(ImageMaths):
    """
    Robust FOV cropping executed through the niimath binary.
    Emulates FSL's robustfov by chaining -robustfov with internal niimath logic.
    The cropped volume is the ``out_file`` output.
    """

    input_spec = NiiMathRobustFovInputSpec
    output_spec = ImageMathsOutputSpec

    def _parse_inputs(self, skip=None):
        if self.inputs.brainsize:
            self.inputs.op_string = f"-robustfov {self.inputs.brainsize}"
        else:
            self.inputs.op_string = "-robustfov"

        return super(NiiMathRobustFov, self)._parse_inputs(skip)
