# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-

from nipype.interfaces.fsl import BEDPOSTX5
from nipype.interfaces.fsl.dti import BEDPOSTX5InputSpec
from os.path import abspath
import os
from nipype.interfaces.base import (traits, isdefined)


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.fsl.dti.BEDPOSTX5InputSpec)  -*-
class CustomBEDPOSTX5InputSpec(BEDPOSTX5InputSpec):
    num_threads = traits.Int(argstr="")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.fsl.BEDPOSTX5)  -*-
class CustomBEDPOSTX5(BEDPOSTX5):
    """
    Custom implementation of BEDPOSTX subclass to ignore STDERR and multithreading management.

    """
    
    input_spec = CustomBEDPOSTX5InputSpec

    def _run_interface(self, runtime):
        from nipype.utils.filemanip import split_filename, copyfile
        from nipype.interfaces.fsl.dti import FSLXCommand
        subjectdir = abspath(self.inputs.out_dir)
        if not os.path.exists(subjectdir):
            os.makedirs(subjectdir)
        _, _, ext = split_filename(self.inputs.mask)
        copyfile(self.inputs.mask, os.path.join(subjectdir, "nodif_brain_mask" + ext))
        _, _, ext = split_filename(self.inputs.dwi)
        copyfile(self.inputs.dwi, os.path.join(subjectdir, "data" + ext))
        copyfile(self.inputs.bvals, os.path.join(subjectdir, "bvals"))
        copyfile(self.inputs.bvecs, os.path.join(subjectdir, "bvecs"))
        if isdefined(self.inputs.grad_dev):
            _, _, ext = split_filename(self.inputs.grad_dev)
            copyfile(self.inputs.grad_dev, os.path.join(subjectdir, "grad_dev" + ext))

        self._out_dir = os.getcwd()
        retval = super(FSLXCommand, self)._run_interface(runtime)

        self._out_dir = subjectdir + ".bedpostX"
        return retval

    def _parse_inputs(self, skip=None):
        """
        Custom implementation of _parse_inputs func to manage multithreading.

        """

        if isdefined(self.inputs.num_threads):
            skip = ["num_threads"]
            self.inputs.environ["FSLPARALLEL"] = "%d" % self.inputs.num_threads

        parse = super(CustomBEDPOSTX5, self)._parse_inputs(skip)
        return parse
