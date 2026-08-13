# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-

from os.path import abspath
import os
import nibabel as nib
from nipype.interfaces.base import (
    traits,
    BaseInterface,
    BaseInterfaceInputSpec,
    TraitedSpec,
    File,
    isdefined,
)
from swane.nipype_pipeline.nodes.ExtractVolumes import extract_volumes


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
class DeleteVolumesInputSpec(BaseInterfaceInputSpec):
    in_file = File(exists=True, mandatory=True, desc="the input image")
    nvols = traits.Int(mandatory=True, desc="original file volumes")
    del_start_vols = traits.Int(mandatory=True, desc="volumes to delete from start")
    del_end_vols = traits.Int(mandatory=True, desc="volumes to delete from end")
    out_file = File(desc="the output image")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class DeleteVolumesOutputSpec(TraitedSpec):
    out_file = File(desc="the output image")
    nvols = traits.Int(desc="new number of volumes")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class DeleteVolumes(BaseInterface):
    """
    Removes specified num. of volumes from start and end of a 4d NIFTI file.

    """

    input_spec = DeleteVolumesInputSpec
    output_spec = DeleteVolumesOutputSpec

    def _run_interface(self, runtime):
        out_file = self._gen_outfilename()

        in_nii = nib.load(self.inputs.in_file)
        nib.save(
            extract_volumes(in_nii, self.inputs.del_start_vols, self._new_nvols()),
            out_file,
        )

        return runtime

    def _new_nvols(self):
        return (
            self.inputs.nvols - self.inputs.del_start_vols - self.inputs.del_end_vols
        )

    def _gen_outfilename(self):
        out_file = self.inputs.out_file
        if not isdefined(out_file) and isdefined(self.inputs.in_file):
            out_file = os.path.basename(self.inputs.in_file)
        return abspath(out_file)

    def _list_outputs(self):
        outputs = self.output_spec().get()
        outputs["out_file"] = self._gen_outfilename()
        outputs["nvols"] = self._new_nvols()
        return outputs
