# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-

from nipype.interfaces.base import traits
from nipype.interfaces.fsl.epi import Eddy, EddyInputSpec
from nipype.utils.gpu_count import gpu_count
from shutil import which


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.fsl.epi.EddyInputSpec)  -*-
class CustomEddyInputSpec(EddyInputSpec):
    # The thread count only controls resource usage and must not invalidate
    # otherwise reusable Eddy results.
    args = traits.Str(
        argstr="%s",
        desc="Additional parameters to the command",
        nohash=True,
    )


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.epi.Eddy)  -*-
class CustomEddy(Eddy):
    """
    Custom implementation of Eddy subclass to support use_gpu input.

    """

    _cmd = "eddy_openmp"
    input_spec = CustomEddyInputSpec

    def _use_cuda(self):
        if self.inputs.use_cuda and gpu_count() > 0:
            self.inputs.num_threads = 1
            # eddy_cuda usually link to eddy_cudaX.X but some versions miss the symlink
            # anyway in newer fsl versions eddy automatically use cuda on cuda-capable systems
            self._cmd = "eddy_cuda" if which("eddy_cuda") else "eddy"
        else:
            self._cmd = "eddy_openmp"

    def _num_threads_update(self):
        if self.inputs.use_cuda:
            self.inputs.num_threads = 1
        super()._num_threads_update()

    def _run_interface(self, runtime):
        # Resolve the CPU binary at runtime (not at import time): newer FSL
        # versions ship 'eddy_cpu' instead of 'eddy_openmp'
        cmd = self._cmd
        if (
            self._cmd == "eddy_openmp"
            and not which("eddy_openmp")
            and which("eddy_cpu")
        ):
            self._cmd = "eddy_cpu"
        runtime = super()._run_interface(runtime)
        # Restore command to avoid side-effects (e.g. on hashing)
        self._cmd = cmd
        return runtime
