"""Workflow constants shared with GUI-side code.

This module must stay free of Nipype/scientific imports: the configuration and
GUI layers import it at startup (importing the workflow modules that use these
constants would load Nipype on the GUI thread).
"""

# Subject results directory name (MainWorkflow.Result_DIR).
RESULT_DIR = "results"

# FreeSurfer subject directory name inside the subject workflow base dir.
FS_DIR = "FS"

# The SWANe tract key -> the atlas model-bundle basename (spec section 3,
# verified against the downloaded HCP842 atlas). Every value is bilateral: the
# per-side model file is ``<base>_L`` / ``<base>_R``. ``fx`` maps to ``F`` and is
# the one tract processed as a single bilateral bundle (the atlas ships F_L_R
# combined); ``cingulum`` is dipy-only. Tracts with no atlas counterpart
# (``atr``/``str``/``cbd``/``cbp``/``cbt`` -- greyed on dipy -- and the
# non-bilateral ``fma``/``fmi``/``mcp``/``ac``) are deliberately absent, so
# :func:`dipy_bundle_workflow` returns ``None`` for them. ``ar`` (acoustic
# radiation) *has* an atlas counterpart (``AR_L``/``AR_R``) but is excluded too:
# RecoBundles has poor performance on acoustic radiation, so it is FSL-only.
DIPY_TRACT_ATLAS = {
    "af": "AF",
    "cst": "CST",
    "fa": "AST",
    "ifo": "IFOF",
    "ilf": "ILF",
    "mdlf": "MdLF",
    "or": "OR",
    "uf": "UF",
    "vof": "VOF",
    "fx": "F",
    "cingulum": "C",
}
