__version__ = "0.2.5"
EXIT_CODE_REBOOT = -123

# Ensure all monkeypatches (SciPy, Nipype, DIPY) are active as soon as SWANe is imported
import swane.patches  # noqa: F401
