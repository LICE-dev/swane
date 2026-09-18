# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-

import nibabel as nib
from nipype.interfaces.base import (
    traits,
    BaseInterface,
    BaseInterfaceInputSpec,
    TraitedSpec,
    File,
    isdefined,
)


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
class GetNiftiTRInputSpec(BaseInterfaceInputSpec):
    in_file = File(exists=True, mandatory=True, desc="the input image")
    force_value = traits.Float(mandatory=False, desc="value forced by user")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class GetNiftiTROutputSpec(TraitedSpec):
    TR = traits.Float(desc="Repetition Time")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class GetNiftiTR(BaseInterface):
    """
    Reads the time of repetition from a NIFTI file.

    """

    input_spec = GetNiftiTRInputSpec
    output_spec = GetNiftiTROutputSpec

    def _run_interface(self, runtime):
        # if the user entered a value, force that instead of automatic reading
        if isdefined(self.inputs.force_value) and self.inputs.force_value != -1:
            self.TR = self.inputs.force_value
        else:
            # pixdim[4] is the repetition time
            self.TR = float(nib.load(self.inputs.in_file).header["pixdim"][4])

        return runtime

    def _list_outputs(self):
        outputs = self.output_spec().get()
        outputs["TR"] = self.TR
        return outputs
