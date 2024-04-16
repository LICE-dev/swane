# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-

from nipype.interfaces.base import (TraitedSpec, File, BaseInterfaceInputSpec, BaseInterface)
import os


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.fsl.base.FSLCommandInputSpec)  -*-
class GenEddyFilesInputSpec(BaseInterfaceInputSpec):
    bval = File(exists=True, mandatory=True, desc='the bval file')


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class GenEddyFilesOutputSpec(TraitedSpec):
    index = File(desc="Volume index file for Eddy")
    acqp = File(desc="Acquisition parameters file for Eddy")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.fsl.base.FSLCommand)  -*-
class GenEddyFiles(BaseInterface):
    """
    Generates index and acqp files for eddy. Does not support topup

    """

    input_spec = GenEddyFilesInputSpec
    output_spec = GenEddyFilesOutputSpec

    def _run_interface(self, runtime):
        bval_file = open(self.inputs.bval, "r")
        bvals = bval_file.read().split()
        bval_file.close()
        self.index_file = os.path.abspath("index")
        with open(self.index_file, "w") as file:
            for val in bvals:
                file.write("1 ")
        self.acqp_file = os.path.abspath("acqp")
        with open(self.acqp_file, "w") as file:
            file.write("0 1 0 0.05")

    def _list_outputs(self):
        outputs = self.output_spec().get()
        outputs['index'] = self.index_file
        outputs['acqp'] = self.acqp_file
        return outputs
