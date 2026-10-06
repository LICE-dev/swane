# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-

"""niimath-backed drop-in replacements for the fslmaths-based Nipype interfaces.

niimath (https://github.com/rordenlab/niimath, BSD-2-Clause) is command-line
compatible with ``fslmaths``. Each class below subclasses the matching Nipype
FSL maths interface and only overrides ``_cmd`` to point at the niimath binary
shipped by the ``niimath`` pip package. Inputs, outputs and command-line
generation are otherwise inherited unchanged, so these classes are drop-in
substitutes: workflows import the same class names from this package instead of
from ``nipype.interfaces.fsl``.

Only the maths interfaces actually used by SWANe's workflows are provided here,
plus ``ImageMaths`` which the ``ThrROI`` and ``SumMultiVols`` interfaces extend.
"""

import niimath

from swane.patches.windows_compat import shell_executable
from nipype.interfaces.fsl import (
    ImageMaths as _ImageMaths,
    BinaryMaths as _BinaryMaths,
    ApplyMask as _ApplyMask,
    Threshold as _Threshold,
    ErodeImage as _ErodeImage,
    DilateImage as _DilateImage,
    IsotropicSmooth as _IsotropicSmooth,
    SpatialFilter as _SpatialFilter,
)

# Absolute path to the niimath binary bundled with the pip package. The package
# resolves the platform-specific binary name (e.g. ``niimath.exe`` on Windows),
# so pointing ``_cmd`` at it works on Linux, macOS and Windows. Nipype runs
# ``_cmd`` through a shell, so on Windows the path is quoted (it may contain
# spaces); elsewhere it is used unchanged.
NIIMATH_CMD = shell_executable(niimath.bin)

# Nipype's FSLCommand takes the default output type from the FSLOUTPUTTYPE
# environment variable set by the FSL setup, falling back to uncompressed NIFTI
# when it is unset. niimath does not need FSL, so pin the compressed NIFTI_GZ
# that SWANe's result filenames expect regardless of the FSL environment.
NIIMATH_OUTPUT_TYPE = "NIFTI_GZ"


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.fsl.ImageMaths)  -*-
class ImageMaths(_ImageMaths):
    """``fslmaths`` generic maths, executed through the niimath binary."""

    _cmd = NIIMATH_CMD
    _output_type = NIIMATH_OUTPUT_TYPE


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.fsl.BinaryMaths)  -*-
class BinaryMaths(_BinaryMaths):
    """``fslmaths`` binary maths, executed through the niimath binary."""

    _cmd = NIIMATH_CMD
    _output_type = NIIMATH_OUTPUT_TYPE


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.fsl.ApplyMask)  -*-
class ApplyMask(_ApplyMask):
    """``fslmaths -mas`` masking, executed through the niimath binary."""

    _cmd = NIIMATH_CMD
    _output_type = NIIMATH_OUTPUT_TYPE


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.fsl.Threshold)  -*-
class Threshold(_Threshold):
    """``fslmaths`` thresholding, executed through the niimath binary."""

    _cmd = NIIMATH_CMD
    _output_type = NIIMATH_OUTPUT_TYPE


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.fsl.ErodeImage)  -*-
class ErodeImage(_ErodeImage):
    """``fslmaths -ero`` erosion, executed through the niimath binary."""

    _cmd = NIIMATH_CMD
    _output_type = NIIMATH_OUTPUT_TYPE


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.fsl.DilateImage)  -*-
class DilateImage(_DilateImage):
    """``fslmaths`` dilation, executed through the niimath binary."""

    _cmd = NIIMATH_CMD
    _output_type = NIIMATH_OUTPUT_TYPE


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.fsl.IsotropicSmooth)  -*-
class IsotropicSmooth(_IsotropicSmooth):
    """``fslmaths -s`` Gaussian smoothing, executed through the niimath binary."""

    _cmd = NIIMATH_CMD
    _output_type = NIIMATH_OUTPUT_TYPE


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.fsl.SpatialFilter)  -*-
class SpatialFilter(_SpatialFilter):
    """``fslmaths`` spatial filtering, executed through the niimath binary."""

    _cmd = NIIMATH_CMD
    _output_type = NIIMATH_OUTPUT_TYPE
