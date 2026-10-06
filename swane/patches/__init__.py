"""SWANe monkeypatches for third-party libraries (Nipype, DIPY, SciPy)."""

# The pwd stub MUST be installed before anything imports nipype.pipeline.plugins
# (nipype_patches below does): on Windows that package fails on ``import pwd``.
from swane.patches.windows_compat import install_pwd_stub

install_pwd_stub()

# scipy_patches MUST be imported and applied FIRST because nipype_patches
# imports nipype which imports scipy, triggering the macOS crash we are trying to avoid.
from swane.patches.scipy_patches import apply_scipy_patches

apply_scipy_patches()

from swane.patches.nipype_patches import apply_patches, swane_run_node
from swane.patches.dipy_patches import dipy_slr_num_threads

# Ensure patches are active as soon as the package is imported.
apply_patches()

__all__ = [
    "apply_patches",
    "swane_run_node",
    "dipy_slr_num_threads",
    "apply_scipy_patches",
]
