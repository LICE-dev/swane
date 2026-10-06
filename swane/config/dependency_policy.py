from swane.config.config_enums import (
    DeskullEngine,
    FmriEngine,
    RegistrationEngine,
    SegmentationEngine,
    TractographyEngine,
)

# Build-time policy: when True, FSL is a mandatory dependency (workflows cannot
# be generated without it) and the FSL tools are the default engines for brain
# extraction, tractography, segmentation and fMRI. When False, FSL is only a
# recommended dependency and the FSL-free engines are the defaults. Registration
# defaults to ANTs either way.
FSL_MANDATORY = False


def default_engines(fsl_mandatory: bool) -> dict:
    """
    Default engine for each Synth-tools engine preference.

    Parameters
    ----------
    fsl_mandatory: bool
        The FSL dependency policy, see FSL_MANDATORY.

    Returns
    -------
    A dict mapping each engine preference key to its default enum member.
    """
    if fsl_mandatory:
        return {
            "deskull_engine": DeskullEngine.BET,
            "engine": RegistrationEngine.ANTS,
            "tractography_engine": TractographyEngine.FSL_XTRACT,
            "segmentation_engine": SegmentationEngine.FSL,
            "fmri_engine": FmriEngine.FSL,
        }
    return {
        "deskull_engine": DeskullEngine.ANTSPYNET,
        "engine": RegistrationEngine.ANTS,
        "tractography_engine": TractographyEngine.DIPY_RECOBUNDLES,
        "segmentation_engine": SegmentationEngine.ANTS,
        "fmri_engine": FmriEngine.NILEARN,
    }
