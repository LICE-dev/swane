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
class SynthMorphApplyInputSpec(FSTraitedSpec):
    warp_file = File(
        exists=True,
        mandatory=True,
        position=1,
        argstr="%s",
        desc="the warp file for transformation",
    )
    in_file = File(
        exists=True,
        mandatory=True,
        position=2,
        argstr="%s",
        desc="the moving image",
    )
    out_file = File(
        argstr="%s",
        position=3,
        hash_files=False,
        name_source=["in_file"],
        name_template="%s_registered",
        keep_extension=True,
        desc="the moved image filename",
    )
    update_voxel = traits.Bool(
        desc="update voxel matrix instead of resampling",
        argstr="-H"
    )
    method = traits.Enum(
        "linear", "nearest",
        desc="Interpolation method, use linear for images and nearest for segmentation",
        argstr="-m %s",
    )
    type = traits.Enum(
        "float32", "uint8", "uint16", "int16", "int32",
        desc="Output data type",
        argstr="-t %s",
    )


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class SynthMorphApplyOutputSpec(TraitedSpec):
    out_file = File(desc="the output image")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.freesurfer.base.FSCommand)  -*-
class SynthMorphApply(FSCommand):
    """
    If FOV exceeds 250mm, crop the borders.

    """

    input_spec = SynthMorphApplyInputSpec
    output_spec = SynthMorphApplyOutputSpec
    _cmd = "mri_synthmorph apply"
