# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-

from nipype.interfaces.fsl.base import FSLCommand, FSLCommandInputSpec
from nipype.interfaces.base import (traits, TraitedSpec, File, isdefined)


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.fsl.base.FSLCommandInputSpec)  -*-
class GetNiftiTRInputSpec(FSLCommandInputSpec):
    in_file = File(exists=True, mandatory=True, argstr="%s pixdim4", position="1", desc='the input image')
    force_value = traits.Float(mandatory=False, desc='value forced by user')


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class GetNiftiTROutputSpec(TraitedSpec):
    TR = traits.Float(desc="Repetition Time")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.fsl.base.FSLCommand)  -*-
class GetNiftiTR(FSLCommand):
    """
    Reads the time of repetition from a NIFTI file.

    """
    
    _cmd = 'fslval'
    input_spec = GetNiftiTRInputSpec
    output_spec = GetNiftiTROutputSpec

    def aggregate_outputs(self, runtime=None, needed_outputs=None):
        outputs = self._outputs()

        # se l'utente ha inserito un valore forzo quello invece del risultato della lettura automatica
        if isdefined(self.inputs.force_value) and self.inputs.force_value != -1:
            outputs.TR = self.inputs.force_value
            return outputs

        info = runtime.stdout
        try:
            outputs.TR = float(info)
        except:
            outputs.TR = 0.

        return outputs
