"""SWANe monkeypatches for third-party libraries (Nipype, DIPY, SciPy)."""

from typing import TYPE_CHECKING

# The pwd stub MUST be installed before anything imports nipype.pipeline.plugins
# (nipype_patches below does): on Windows that package fails on ``import pwd``.
from swane.patches.windows_compat import install_pwd_stub

install_pwd_stub()

# scipy_patches MUST be imported and applied FIRST because nipype_patches
# imports nipype which imports scipy, triggering the macOS crash we are trying to avoid.
from swane.patches.scipy_patches import apply_scipy_patches

apply_scipy_patches()

if TYPE_CHECKING:
    from swane.patches.nipype_patches import apply_patches, swane_run_node
    from swane.patches.dipy_patches import (
        dipy_slr_num_threads,
        dipy_reco_bundles_num_threads,
    )

__all__ = [
    "apply_patches",
    "swane_run_node",
    "dipy_slr_num_threads",
    "dipy_reco_bundles_num_threads",
    "apply_scipy_patches",
    "install_pwd_stub",
]


def __getattr__(name: str):
    if name in ("apply_patches", "swane_run_node"):
        from swane.patches import nipype_patches

        return getattr(nipype_patches, name)
    if name in ("dipy_slr_num_threads", "dipy_reco_bundles_num_threads"):
        from swane.patches import dipy_patches

        return getattr(dipy_patches, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return sorted(list(globals().keys()) + __all__)
