# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-

from nipype.interfaces.fsl.epi import Eddy, EddyInputSpec
from nipype.utils.gpu_count import gpu_count
from shutil import which

# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.epi.Eddy)  -*-
class CustomEddy(Eddy):
    """
    Custom implementation of Eddy subclass to support use_gpu input.

    """

    _cmd = "eddy_openmp" if which("eddy_openmp") else "eddy_cpu"

    def _use_cuda(self):
        if self.inputs.use_cuda and gpu_count()>0:
            self.inputs.num_threads = 1
            # eddy_cuda usually link to eddy_cudaX.X but some versions miss the symlink
            # anyway in newer fsl versions eddy automatically use cuda on cuda-capable systems
            self._cmd = "eddy_cuda" if which("eddy_cuda") else "eddy"
        else:
            # older fsl versions has cuda_openmp, newer versions has eddy_cpu
            self._cmd = "eddy_openmp" if which("eddy_openmp") else "eddy_cpu"

    def _num_threads_update(self):
        if self.inputs.use_cuda:
            self.inputs.num_threads = 1
        super()._num_threads_update()