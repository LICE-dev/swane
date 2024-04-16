# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-

from nibabel import (load, save)
from nibabel.processing import conform

from os.path import abspath
import os
import shutil

from nipype.interfaces.base import (traits, BaseInterface, BaseInterfaceInputSpec, TraitedSpec, File, isdefined)


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
class CropFovInputSpec(BaseInterfaceInputSpec):
    in_file = File(exists=True, mandatory=True, desc='the input image')
    max_dim = traits.Int(mandatory=True)
    out_file = File(desc='the output image')


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class CropFovOutputSpec(TraitedSpec):
    out_file = File(desc='the output image')


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class CropFov(BaseInterface):
    """
    If FOV exceeds 250mm, crop the borders.

    """

    input_spec = CropFovInputSpec
    output_spec = CropFovOutputSpec

    def _run_interface(self, runtime):
        self.inputs.out_file = self._gen_outfilename()

        # Calculate current fov in mm
        img = load(self.inputs.in_file)
        dim1, dim2, dim3 = img.header.get_data_shape()
        vox1, vox2, vox3 = img.header.get_zooms()
        fov = [dim1*vox1, dim2*vox2, dim3*vox3]
        current_max_dim = max(fov)

        if current_max_dim <= self.inputs.max_dim:
            shutil.copyfile(self.inputs.in_file, self.inputs.out_file)
        else:

            rescale_factor = (self.inputs.max_dim-1)/current_max_dim

            t_dim1 = dim1 if fov[0] <= self.inputs.max_dim else int(dim1*rescale_factor)
            t_dim2 = dim2 if fov[1] <= self.inputs.max_dim else int(dim2*rescale_factor)
            t_dim3 = dim3 if fov[2] <= self.inputs.max_dim else int(dim3*rescale_factor)

            scaled_img = conform(img, (t_dim1, t_dim2, t_dim3), img.header.get_zooms())

            save(scaled_img, self.inputs.out_file)

        return runtime

    def _gen_outfilename(self):
        out_file = self.inputs.out_file
        if not isdefined(out_file) and isdefined(self.inputs.in_file):
            out_file = "cropped_" + os.path.basename(self.inputs.in_file)
        return abspath(out_file)

    def _list_outputs(self):
        outputs = self.output_spec().get()
        outputs['out_file'] = self._gen_outfilename()
        return outputs
