"""SWANe monkeypatches for third-party libraries (Nipype, DIPY)."""

from swane.patches.nipype_patches import apply_patches, swane_run_node
from swane.patches.dipy_patches import dipy_slr_num_threads

# Ensure patches are active as soon as the package is imported.
apply_patches()

__all__ = ["apply_patches", "swane_run_node", "dipy_slr_num_threads"]
