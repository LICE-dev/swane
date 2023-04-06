# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-

from nipype.interfaces.fsl.base import FSLCommand, FSLCommandInputSpec
from nipype.interfaces.base import (traits, TraitedSpec, File, isdefined)


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.fsl.base.FSLCommandInputSpec)  -*-
class FslNVolsInputSpec(FSLCommandInputSpec):
    in_file = File(exists=True, mandatory=True, argstr="%s", position="1", desc='the input image')
    force_value = traits.Int(mandatory=False, desc='value forced by user')


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class FslNVolsOutputSpec(TraitedSpec):
    nvols = traits.Int(desc="Number of EPI runs")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.FSLCommand)  -*-
class FslNVols(FSLCommand):
    """
    Reads the num. of volumes from a 4d NIFTI file.

    """
    
    _cmd = 'fslnvols'
    input_spec = FslNVolsInputSpec
    output_spec = FslNVolsOutputSpec

    def aggregate_outputs(self, runtime=None, needed_outputs=None):
        outputs = self._outputs()

        # se l'utente ha inserito un valore forzo quello invece del risultato della lettura automatica
        if isdefined(self.inputs.force_value) and self.inputs.force_value != -1:
            outputs.nvols = self.inputs.force_value
            return outputs

        info = runtime.stdout
        try:
            outputs.nvols = int(info)
        except ValueError:
            outputs.nvols = 0

        return outputs
