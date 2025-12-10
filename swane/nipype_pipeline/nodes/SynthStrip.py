# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-
from nipype.interfaces.freesurfer.base import FSTraitedSpec, FSCommand
from nipype.interfaces.base import (
    TraitedSpec,
    File,
    traits,
    Tuple,
    Directory,
    InputMultiPath,
    OutputMultiPath,
    CommandLine,
    CommandLineInputSpec,
    isdefined,
    InputMultiObject,
    Undefined,
)
import os


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.freesurfer.base.FSTraitedSpec)  -*-
class SynthStripInputSpec(FSTraitedSpec):
    in_file = File(
        exists=True,
        mandatory=True,
        argstr="-i %s",
        desc="image to skullstrip",
    )
    out_file = File(
        argstr="-o %s",
        hash_files=False,
        name_source=["in_file"],
        name_template="%s_brain",
        keep_extension=True,
        desc="name of output skull stripped image",
    )
    mask_file = File(
        argstr="-m %s",
        desc="name of output skull binary mask",
    )
    exclude_csf = traits.Bool(desc="exclude CSF from brain border", argstr="--no-csf")
    use_gpu = traits.Bool(desc="use GPU", argstr="--gpu")
    model_file = File(
        exists=True,
        argstr="--model %s",
        desc="alternative model weights",
    )
    border = traits.Float(desc="mask border threshold in mm, defaults to 1", argstr="-f %.2f")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class SynthStripOutputSpec(TraitedSpec):
    out_file = File(desc="path/name of skull stripped file (if generated)")
    mask_file = File(desc="path/name of binary brain mask (if generated)")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.freesurfer.base.FSCommand)  -*-
class SynthStrip(FSCommand):
    _cmd = "mri_synthstrip"
    input_spec = SynthStripInputSpec
    output_spec = SynthStripOutputSpec

    def _list_outputs(self):
        outputs = super()._list_outputs()
        if isdefined(self.inputs.mask_file):
            outputs["mask_file"] = os.path.abspath(self.inputs.mask_file)
        return outputs
