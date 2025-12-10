# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-
from nipype.interfaces.freesurfer.base import FSTraitedSpec, FSCommand
from nipype.interfaces.base import (
    TraitedSpec,
    File,
    traits,
    isdefined,
)
import os
from nipype.utils.filemanip import fname_presuffix


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.freesurfer.base.FSTraitedSpec)  -*-
class SynthMorphRegInputSpec(FSTraitedSpec):
    in_file = File(
        exists=True,
        mandatory=True,
        position=2,
        argstr="%s",
        desc="the moving image",
    )
    reference = File(
        exists=True,
        mandatory=True,
        position=3,
        argstr="%s",
        desc="the reference image",
    )
    model = traits.Enum(
        "joint", "deform", "affine", "rigid",
        desc="Transformation model",
        argstr="-m %s",
        usedefault=True
    )
    out_file = File(
        argstr="-o %s",
        hash_files=False,
        name_source=["in_file"],
        name_template="%s_registered",
        keep_extension=True,
        desc="the moved image filename",
    )
    initial_mat = File(
        exists=True,
        argstr="-i %s",
        desc="Apply a matrix to moving before the registration")
    warp_file = File(
        argstr="-t %s",
        genfile=True,
        hash_files=False,
        desc="the warp filename")
    inv_warp_file = File(
        argstr="-T %s",
        genfile=True,
        hash_files=False,
        desc="the inversion warp filename")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class SynthMorphRegOutputSpec(TraitedSpec):
    out_file = File(desc="the output image")
    warp_file = File(desc="the warp filename")
    inv_warp_file = File(desc="the inversion warp filename")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.freesurfer.base.FSCommand)  -*-
class SynthMorphReg(FSCommand):
    """
    If FOV exceeds 250mm, crop the borders.

    """

    input_spec = SynthMorphRegInputSpec
    output_spec = SynthMorphRegOutputSpec
    _cmd = "mri_synthmorph register"


    def _list_outputs(self):
        outputs = super()._list_outputs()
        for name in ["warp_file", "inv_warp_file"]:
            ext = ".mgz"
            if self.inputs.model == "affine":
                ext = ".lta"
            out_file = fname_presuffix(self.inputs.in_file, suffix="_"+name+ext, use_ext=False)
            outputs[name] = os.path.abspath(out_file)
        return outputs

    def _gen_filename(self, name):
        if name in ["warp_file", "inv_warp_file"]:
            return self._list_outputs()[name]
        return None
