# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-

import os
from os.path import abspath
import nibabel as nib
from nibabel.orientations import io_orientation, axcodes2ornt, ornt_transform
from nipype.interfaces.base import (
    BaseInterface,
    BaseInterfaceInputSpec,
    TraitedSpec,
    File,
    isdefined,
)


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
class ForceOrientInputSpec(BaseInterfaceInputSpec):
    in_file = File(exists=True, mandatory=True, desc="the input image")
    out_file = File(desc="the output image")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class ForceOrientOutputSpec(TraitedSpec):
    out_file = File(desc="the output image")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class ForceOrient(BaseInterface):
    """
    Converts an image in radiological convention and in RL PA IS orientation.

    """

    input_spec = ForceOrientInputSpec
    output_spec = ForceOrientOutputSpec

    def _run_interface(self, runtime):
        out_file = self._gen_outfilename()

        in_nii = nib.load(self.inputs.in_file)
        # radiological convention with RL PA IS axes is the LAS orientation.
        # Voxel data is only permuted/flipped, so dtype and scaling are
        # preserved as they are and the anatomy keeps its world coordinates
        transform = ornt_transform(
            io_orientation(in_nii.affine), axcodes2ornt(("L", "A", "S"))
        )
        nib.save(in_nii.as_reoriented(transform), out_file)

        return runtime

    def _gen_outfilename(self):
        out_file = self.inputs.out_file
        if not isdefined(out_file) and isdefined(self.inputs.in_file):
            out_file = os.path.basename(self.inputs.in_file)
        return abspath(out_file)

    def _list_outputs(self):
        outputs = self.output_spec().get()
        outputs["out_file"] = self._gen_outfilename()
        return outputs
