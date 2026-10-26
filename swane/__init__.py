__version__ = "0.2.6"
EXIT_CODE_REBOOT = -123

# Install lightweight platform shims that do NOT import third-party libraries:
# 1. Windows pwd stub (needed before nipype.pipeline.plugins is ever imported)
from swane.patches.windows_compat import install_pwd_stub

install_pwd_stub()

# 2. macOS SciPy propack dummy module (needed before scipy.sparse.linalg is ever imported)
from swane.patches.scipy_patches import apply_scipy_patches

apply_scipy_patches()
