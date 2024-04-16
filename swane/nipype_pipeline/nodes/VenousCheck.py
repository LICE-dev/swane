# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-

import shutil
from nipype.interfaces.base import InputMultiObject
from nipype.interfaces.fsl import ImageStats
from os.path import abspath
from swane.config.config_enums import VEIN_DETECTION_MODE
from nipype.interfaces.base import traits
from nipype.interfaces.base import (BaseInterface, BaseInterfaceInputSpec, TraitedSpec, File)


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
class VenousCheckInputSpec(BaseInterfaceInputSpec):
    in_files = InputMultiObject(File(exists=True), desc="List of splitted file")
    detection_mode = traits.Enum(
        VEIN_DETECTION_MODE,
        argstr="-m %d",
        usedefault=True)
    out_file_veins = File(desc='the output venous image')
    out_file_anat = File(desc='the output anatomic image')


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class VenousCheckOutputSpec(TraitedSpec):
    out_file_veins = File(desc='the output venous image')
    out_file_anat = File(desc='the output anatomic image')


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class VenousCheck(BaseInterface):
    """
    Recognises the venous phase from the anatomic image of a phase contrast sequence based criteria specified by user.

    """
    
    input_spec = VenousCheckInputSpec
    output_spec = VenousCheckOutputSpec

    def _run_interface(self, runtime):
        self.inputs.out_file_veins = abspath("veins.nii.gz")
        self.inputs.out_file_anat = abspath("veins_anat.nii.gz")

        if self.inputs.detection_mode == VEIN_DETECTION_MODE.FIRST:
            # Always first
            shutil.copy(self.inputs.in_files[0], self.inputs.out_file_veins)
            shutil.copy(self.inputs.in_files[1], self.inputs.out_file_anat)
            return runtime
        elif self.inputs.detection_mode == VEIN_DETECTION_MODE.SECOND:
            # Always second
            shutil.copy(self.inputs.in_files[1], self.inputs.out_file_veins)
            shutil.copy(self.inputs.in_files[0], self.inputs.out_file_anat)
            return runtime
        elif self.inputs.detection_mode == VEIN_DETECTION_MODE.MEAN:
            # Mean value mode
            op_string = "-M"
        else:
            # Standard deviation mode (default)
            op_string = "-s"

        s0 = ImageStats()
        s0.inputs.in_file = self.inputs.in_files[0]
        s0.inputs.op_string = op_string
        res0 = s0.run()
        s1 = ImageStats()
        s1.inputs.in_file = self.inputs.in_files[1]
        s1.inputs.op_string = op_string
        res1 = s1.run()
        if res0.outputs.out_stat < res1.outputs.out_stat:
            shutil.copy(self.inputs.in_files[0], self.inputs.out_file_veins)
            shutil.copy(self.inputs.in_files[1], self.inputs.out_file_anat)
        else:
            shutil.copy(self.inputs.in_files[1], self.inputs.out_file_veins)
            shutil.copy(self.inputs.in_files[0], self.inputs.out_file_anat)

        return runtime

    def _list_outputs(self):
        outputs = self.output_spec().get()
        outputs['out_file_veins'] = abspath("veins.nii.gz")
        outputs['out_file_anat'] = abspath("veins_anat.nii.gz")
        return outputs
