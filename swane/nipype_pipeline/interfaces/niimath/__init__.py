"""niimath-backed Nipype interfaces used across SWANe's workflows.

The maths drop-ins (:mod:`~swane.nipype_pipeline.interfaces.niimath.maths`) are
re-exported here so workflows can import them directly from the package, e.g.
``from swane.nipype_pipeline.interfaces.niimath import ImageMaths``. The custom
``ThrROI`` and ``SumMultiVols`` interfaces live in their own modules and are
imported from there, following the one-class-per-file convention.
"""

from swane.nipype_pipeline.interfaces.niimath.maths import (
    NIIMATH_CMD,
    ImageMaths,
    BinaryMaths,
    ApplyMask,
    Threshold,
    ErodeImage,
    DilateImage,
    IsotropicSmooth,
    SpatialFilter,
)
from swane.nipype_pipeline.interfaces.niimath.NiiMathRobustFov import (
    NiiMathRobustFov,
)

__all__ = [
    "NIIMATH_CMD",
    "NiiMathRobustFov",
    "ImageMaths",
    "BinaryMaths",
    "ApplyMask",
    "Threshold",
    "ErodeImage",
    "DilateImage",
    "IsotropicSmooth",
    "SpatialFilter",
]
