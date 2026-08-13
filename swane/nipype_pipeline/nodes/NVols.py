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
class NVolsInputSpec(BaseInterfaceInputSpec):
    in_file = File(exists=True, mandatory=True, desc="the input image")
    force_value = traits.Int(mandatory=False, desc="value forced by user")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class NVolsOutputSpec(TraitedSpec):
    nvols = traits.Int(desc="Number of EPI runs")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class NVols(BaseInterface):
    """
    Reads the num. of volumes from a 4d NIFTI file.

    """

    input_spec = NVolsInputSpec
    output_spec = NVolsOutputSpec

    def _run_interface(self, runtime):
        # se l'utente ha inserito un valore forzo quello invece della lettura automatica
        if isdefined(self.inputs.force_value) and self.inputs.force_value != -1:
            self.nvols = self.inputs.force_value
        else:
            shape = nib.load(self.inputs.in_file).shape
            self.nvols = shape[3] if len(shape) > 3 else 1

        return runtime

    def _list_outputs(self):
        outputs = self.output_spec().get()
        outputs["nvols"] = self.nvols
        return outputs
