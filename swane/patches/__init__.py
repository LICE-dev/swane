"""SWANe monkeypatches for third-party libraries (Nipype)."""

from swane.patches.nipype_patches import apply_patches, swane_run_node

# Ensure patches are active as soon as the package is imported.
apply_patches()

__all__ = ["apply_patches", "swane_run_node"]
