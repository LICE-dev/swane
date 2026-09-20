from nipype.interfaces.fsl.utils import ImageMathsInputSpec, ImageMathsOutputSpec
from swane.nipype_pipeline.interfaces.niimath.maths import ImageMaths
from nipype.interfaces.base import traits, File


class NiiMathRobustFovInputSpec(ImageMathsInputSpec):
    out_roi = File(desc="ROI volume output name", genfile=True)
    brainsize = traits.Int(desc="size of brain in z-dimension")


class NiiMathRobustFovOutputSpec(ImageMathsOutputSpec):
    out_roi = File(exists=True, desc="ROI volume output name")


class NiiMathRobustFov(ImageMaths):
    """
    Robust FOV cropping executed through the niimath binary.
    Emulates FSL's robustfov by chaining -robustfov with internal niimath logic.
    """

    input_spec = NiiMathRobustFovInputSpec
    output_spec = NiiMathRobustFovOutputSpec

    def _parse_inputs(self, skip=None):
        if self.inputs.brainsize:
            self.inputs.op_string = f"-robustfov {self.inputs.brainsize}"
        else:
            self.inputs.op_string = "-robustfov"

        # niimath natively uses out_file. Map out_roi to out_file for drop-in compatibility.
        if self.inputs.out_roi:
            self.inputs.out_file = self.inputs.out_roi

        return super(NiiMathRobustFov, self)._parse_inputs(skip)

    def _list_outputs(self):
        outputs = super(NiiMathRobustFov, self)._list_outputs()
        # Ensure out_roi is populated in the outputs dictionary
        outputs["out_roi"] = outputs["out_file"]
        return outputs
