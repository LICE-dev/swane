# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-

from nipype.interfaces.fsl.epi import Eddy, EddyInputSpec
from nipype.interfaces.base import (traits, isdefined)
from nipype.utils.gpu_count import gpu_count
from shutil import which
import os


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.fsl.dti.EddyInputSpec)  -*-
class CustomEddyInputSpec(EddyInputSpec):
    use_gpu = traits.Bool(argstr="", mandatory=True)


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.epi.Eddy)  -*-
class CustomEddy(Eddy):
    """
    Custom implementation of Eddy subclass to support use_gpu input.

    """
    
    input_spec = CustomEddyInputSpec
    _cmd = "eddy_openmp" if which("eddy_openmp") else "eddy_cpu"

    def __init__(self, **inputs):
        super().__init__(**inputs)
        self.inputs.on_trait_change(self._cuda_update, "use_gpu")

    def _cuda_update(self):
        if (self.inputs.use_cuda or self.inputs.use_gpu) and gpu_count()>0:
            self.inputs.num_threads = 1
            # eddy_cuda usually link to eddy_cudaX.X but some versions miss the symlink
            # anyway in newer fsl versions eddy automatically use cuda on cuda-capable systems
            self._cmd = "eddy_cuda" if which("eddy_cuda") else "eddy"
        else:
            # older fsl versions has cuda_openmp, newer versions has eddy_cpu
            _cmd = "eddy_openmp" if which("eddy_openmp") else "eddy_cpu"

    def _num_threads_update(self):
        if self.inputs.use_cuda or self.inputs.use_gpu:
            self.inputs.num_threads = 1
        super()._num_threads_update()

    def _run_interface(self, runtime):
        # If selected command is missing, use generic 'eddy'

        FSLDIR = os.getenv("FSLDIR", "")
        cmd = self._cmd
        if all(
            (
                FSLDIR != "",
                not os.path.exists(os.path.join(FSLDIR, "bin", self._cmd)),
            )
        ):
            self._cmd = "eddy"
        runtime = super()._run_interface(runtime)

        # Restore command to avoid side-effects
        self._cmd = cmd
        return runtime



