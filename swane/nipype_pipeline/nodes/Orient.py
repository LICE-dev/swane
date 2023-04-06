# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-

from nipype.interfaces.fsl.base import FSLCommand, FSLCommandInputSpec
from nipype.interfaces.base import (traits, TraitedSpec, File, isdefined)


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.fsl.base.FSLCommandInputSpec)  -*-
class OrientInputSpec(FSLCommandInputSpec):
    in_file = File(exists=True, mandatory=True, argstr="%s", position="2", desc="input image")
    _options_xor = ['get_orient', "swap_orient"]
    get_orient = traits.Bool(argstr="-getorient", position="1", xor=_options_xor,
                             desc="gets FSL left-right orientation")
    swap_orient = traits.Bool(argstr="-swaporient", position="1", xor=_options_xor,
                              desc="swaps FSL radiological and FSL neurological")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class OrientOutputSpec(TraitedSpec):
    out_file = File(exists=True, desc="image with modified orientation")
    orient = traits.Str(desc="FSL left-right orientation")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.fsl.base.FSLCommand)  -*-
class Orient(FSLCommand):
    """
    Returns the image orientation as neurological or radiological conventions.

    """
    
    _cmd = 'fslorient'
    input_spec = OrientInputSpec
    output_spec = OrientOutputSpec

    def aggregate_outputs(self, runtime=None, needed_outputs=None):

        outputs = self._outputs()
        info = runtime.stdout

        # Modified file
        if isdefined(self.inputs.swap_orient):
            outputs.out_file = self.inputs.in_file

        # Get information
        if isdefined(self.inputs.get_orient):
            outputs.orient = info

        return outputs
