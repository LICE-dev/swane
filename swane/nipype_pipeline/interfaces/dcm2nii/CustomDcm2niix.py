# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-

import os
import platform
import re
from pathlib import Path
import dcm2niix
from nipype.interfaces.dcm2nii import Dcm2niix, Dcm2niixInputSpec
from nipype.pipeline.engine.nodes import NodeExecutionError
from nipype.interfaces.base import traits

from swane.patches import windows_compat
from swane.patches.windows_compat import shell_executable

# absolute path to the dcm2niix binary shipped by the pip package, so no
# system dcm2niix installation is required. The package exposes the path
# without the Windows suffix, so we add it ourselves when needed. Nipype runs
# ``_cmd`` through a shell, so on Windows the path is quoted (it may contain
# spaces); elsewhere it is used unchanged.
_dcm2niix_binary = Path(dcm2niix.bin)
if platform.system() == "Windows" and _dcm2niix_binary.suffix != ".exe":
    _dcm2niix_binary = _dcm2niix_binary.with_suffix(".exe")
DCM2NIIX_CMD = shell_executable(str(_dcm2niix_binary))

# dcm2niix reports each converted file as "Convert <n> DICOM as <path> (<dims>)".
# Nipype extracts <path> with ``\S+/\S+``, which needs a forward slash and no
# blank space; on Windows dcm2niix writes ``.\name`` and SWANe allows blank
# spaces in subject paths. This pattern takes everything between "as " and the
# final dimension group instead.
_CONVERT_LINE = re.compile(r"^Convert \d+ DICOM as (.+) \(\d+(?:x\d+)*\)\s*$")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.dcm2nii.Dcm2niixInputSpec)  -*-
class CustomDcm2niixInputSpec(Dcm2niixInputSpec):
    expected_files = traits.Int(default_value=1, usedefault=True)
    request_dti = traits.Bool(default_value=False, usedefault=True)


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.dcm2nii.Dcm2niix)  -*-
class CustomDcm2niix(Dcm2niix):
    """
    Custom implementation of Dcm2niix Nipype Interface to support crop and merge parameters.

    """

    _cmd = DCM2NIIX_CMD
    input_spec = CustomDcm2niixInputSpec

    def _parse_stdout(self, stdout):
        """Converted file names from the dcm2niix output.

        Nipype's parser on Linux/macOS (unchanged). On Windows the same
        semantics (absolute paths, in output order, from the "Convert ..."
        lines) with a pattern that accepts backslashes and blank spaces.
        """
        if not windows_compat.is_windows():
            return super()._parse_stdout(stdout)
        filenames = []
        for line in stdout.split("\n"):
            match = _CONVERT_LINE.match(line.rstrip("\r"))
            if match:
                filenames.append(os.path.abspath(match.group(1)))
        return filenames

    def _run_interface(self, runtime):
        runtime = super(CustomDcm2niix, self)._run_interface(runtime)

        # Expected files check
        if (
            self.inputs.expected_files > 0
            and len(self.output_files) != self.inputs.expected_files
        ):
            raise NodeExecutionError(
                "Dcm2niix generated %d nifti files while %s were expected"
                % (len(self.output_files), self.inputs.expected_files)
            )

        # Bvec and Bvals check
        if self.inputs.request_dti and (len(self.bvals) == 0 or len(self.bvecs) == 0):
            raise NodeExecutionError(
                "Dcm2niix could not generate requested bvals and bvecs files"
            )

        return runtime
