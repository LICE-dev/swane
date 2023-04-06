# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-

import shutil
from nipype.interfaces.fsl import ExtractROI
from nipype import Node
from os.path import abspath
import os
from nipype.interfaces.base import (traits, TraitedSpec, BaseInterface, BaseInterfaceInputSpec, File)


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
class DeleteVolumesInputSpec(BaseInterfaceInputSpec):
    in_file = File(exists=True, mandatory=True, desc='the input image')
    nvols = traits.Int(mandatory=True, desc='original file volumes')
    del_start_vols = traits.Int(mandatory=True, desc='volumes to delete from start')
    del_end_vols = traits.Int(mandatory=True, desc='volumes to delete from end')


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class DeleteVolumesOutputSpec(TraitedSpec):
    out_file = File(desc='the output image')
    nvols = traits.Int(desc='new number of volumes')


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class DeleteVolumes(BaseInterface):
    """
    Removes specified num. of volumes from start and end of a 4d NIFTI file.

    """
    
    input_spec = DeleteVolumesInputSpec
    output_spec = DeleteVolumesOutputSpec

    def _run_interface(self, runtime):
        out_file = self._gen_outfilename()
        if self.inputs.del_start_vols == 0 and self.inputs.del_end_vols == 0:
            shutil.copy(self.inputs.in_file, out_file)
        else:
            fmri_delete_volumes = Node(ExtractROI(), name="fMRI_delete_volumes")
            fmri_delete_volumes.inputs.in_file = self.inputs.in_file
            fmri_delete_volumes.inputs.t_min = self.inputs.del_start_vols
            fmri_delete_volumes.inputs.t_size = self.inputs.nvols - self.inputs.del_start_vols - self.inputs.del_end_vols
            fmri_delete_volumes.inputs.roi_file = out_file

            fmri_delete_volumes.run()

        return runtime

    def _gen_outfilename(self):
        out_file = os.path.basename(self.inputs.in_file)
        return abspath(out_file)

    def _list_outputs(self):
        outputs = self.output_spec().get()
        outputs['out_file'] = self._gen_outfilename()
        outputs['nvols'] = self.inputs.nvols - self.inputs.del_start_vols - self.inputs.del_end_vols
        return outputs
