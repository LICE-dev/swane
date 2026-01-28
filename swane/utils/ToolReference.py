from enum import Enum


class Package(Enum):
    FSL = "fsl"
    FREESURFER = "freesurfer"
    SLICER = "slicer"
    OTHER = "Other"


from dataclasses import dataclass
from typing import List


@dataclass
class ToolReference:
    command: str
    package: Package
    url: str
    references: List[str]


def get_command_info(key: str) -> ToolReference:
    try:
        if key in equivalent_command_list:
            key = equivalent_command_list[key]
        return tool_reference_list[key]
    except KeyError:
        return None


utilities_url = "https://fsl.fmrib.ox.ac.uk/fsl/docs/utilities/fslutils.html#"

tool_reference_list = {
    # Structural
    "BET": ToolReference(
        command="bet",
        package=Package.FSL,
        url="https://fsl.fmrib.ox.ac.uk/fsl/docs/structural/bet.html",
        references=[
            "Smith SM, et al. Fast robust automated brain extraction. Hum Brain Mapp. 2002."
        ],
    ),
    "FAST": ToolReference(
        command="fast",
        package=Package.FSL,
        url="https://fsl.fmrib.ox.ac.uk/fsl/docs/structural/fast.html",
        references=[
            "Zhang Y, Brady M, Smith S, et al. Segmentation of brain MR images through a hidden Markov random field model and the expectation-maximization algorithm. IEEE Trans Med Imaging. 2001."
        ],
    ),
    # fMRI
    "FEAT": ToolReference(
        command="feat",
        package=Package.FSL,
        url="https://fsl.fmrib.ox.ac.uk/fsl/docs/task_fmri/feat/index.html",
        references=[
            "Woolrich MW, Ripley BD, Brady M, et al. Temporal autocorrelation in univariate linear modeling of fMRI data. NeuroImage. 2001."
        ],
    ),
    "MELODIC": ToolReference(
        command="melodic",
        package=Package.FSL,
        url="https://fsl.fmrib.ox.ac.uk/fsl/docs/resting_state/melodic.html",
        references=[
            "Beckmann CF, Smith SM, et al. Probabilistic independent component analysis for functional magnetic resonance imaging. IEEE Trans Med Imaging. 2004."
        ],
    ),
    "FilterRegressor": ToolReference(
        command="fsl_regfilt",
        package=Package.FSL,
        url="https://fsl.fmrib.ox.ac.uk/fsl/docs/resting_state/melodic.html",
        references=[
            "Beckmann CF, Smith SM, et al. Probabilistic independent component analysis for functional magnetic resonance imaging. IEEE Trans Med Imaging. 2004."
        ],
    ),
    "AromaClassification": ToolReference(
        command="aroma",
        package=Package.OTHER,
        url="https://github.com/maartenmennes/ICA-AROMA",
        references=[
            "Pruim RHR, Mennes M, van Rooij D, et al. ICA-AROMA: A robust ICA-based strategy for removing motion artifacts from fMRI data. NeuroImage. 2015.",
            "Pruim RHR, Mennes M, Buitelaar JK, et al. Evaluation of ICA-AROMA and alternative strategies for motion artifact removal in resting-state fMRI. NeuroImage. 2015.",
        ],
    ),
    # Diffusion / Tractography
    "CustomEddy": ToolReference(
        command="eddy",
        package=Package.FSL,
        url="https://fsl.fmrib.ox.ac.uk/fsl/docs/eddy/eddy.html",
        references=[
            "Andersson JLR, Sotiropoulos SN, et al. An integrated approach to correction for off-resonance effects and subject movement in diffusion MR imaging. NeuroImage. 2016."
        ],
    ),
    "DTIFit": ToolReference(
        command="dtifit",
        package=Package.FSL,
        url="https://fsl.fmrib.ox.ac.uk/fsl/docs/diffusion/dtifit.html",
        references=[
            "Andersson JLR, Sotiropoulos SN, et al. An integrated approach to correction for off-resonance effects and subject movement in diffusion MR imaging. NeuroImage. 2016."
        ],
    ),
    "BEDPOSTX5": ToolReference(
        command="bedpostx",
        package=Package.FSL,
        url="https://fsl.fmrib.ox.ac.uk/fsl/docs/diffusion/bedpostx.html",
        references=[
            "Behrens TEJ, Woolrich MW, Jenkinson M, et al. Characterization and propagation of uncertainty in diffusion-weighted MR imaging. Magn Reson Med. 2003.",
            "Behrens TEJ, Johansen-Berg H, Jbabdi S, et al. Probabilistic diffusion tractography with multiple fibre orientations. NeuroImage. 2007.",
            "Sotiropoulos SN, Hernandez-Fernandez M, Vu AT, et al. Fusion in diffusion MRI for improved fibre orientation estimation. NeuroImage. 2016.",
            "Hernandez M, Guerrero GD, Cecilia JM, et al. Accelerating fibre orientation estimation from diffusion MRI using GPUs. PLoS One. 2013.",
        ],
    ),
    "CustomProbTrackX2": ToolReference(
        command="probtrackx",
        package=Package.FSL,
        url="https://fsl.fmrib.ox.ac.uk/fsl/docs/diffusion/probtrackx.html",
        references=[
            "Behrens TEJ, Woolrich MW, Jenkinson M, et al. Characterization and propagation of uncertainty in diffusion-weighted MR imaging. Magn Reson Med. 2003.",
            "Behrens TEJ, Johansen-Berg H, Jbabdi S, et al. Probabilistic diffusion tractography with multiple fibre orientations. NeuroImage. 2007.",
            "Hernandez-Fernandez M, Reguly I, Jbabdi S, et al. Using GPUs to accelerate computational diffusion MRI. NeuroImage. 2019.",
        ],
    ),
    "XTRACT": ToolReference(
        command="xtract",
        package=Package.FSL,
        url="https://fsl.fmrib.ox.ac.uk/fsl/docs/diffusion/xtract.html",
        references=[
            "Warrington S, Bryant K, Khrapitchev A, et al. XTRACT: Standardised protocols for automated tractography. NeuroImage. 2020.",
            "Warrington S, Thompson E, Bastiani M, et al. Concurrent mapping of brain ontogeny and phylogeny. Sci Adv. 2022.",
            "de Groot M, Vernooij MW, Klein S, et al. Improving alignment in tract-based spatial statistics. NeuroImage. 2013.",
        ],
    ),
    # Registration
    "FLIRT": ToolReference(
        command="flirt",
        package=Package.FSL,
        url="https://fsl.fmrib.ox.ac.uk/fsl/docs/registration/flirt/index.html",
        references=[
            "Jenkinson M, Bannister P, Brady JM, et al. Improved optimisation for robust linear registration. NeuroImage. 2002.",
            "Jenkinson M, Smith SM, et al. A global optimisation method for affine registration. Med Image Anal. 2001.",
            "Greve DN, Fischl B, et al. Accurate and robust brain image alignment using boundary-based registration. NeuroImage. 2009.",
        ],
    ),
    "FNIRT": ToolReference(
        command="fnirt",
        package=Package.FSL,
        url="https://fsl.fmrib.ox.ac.uk/fsl/docs/registration/fnirt/index.html",
        references=[
            "Andersson JLR, Jenkinson M, Smith SM, et al. Non-linear registration, aka spatial normalisation. FMRIB Tech Rep. 2010."
        ],
    ),
    "ApplyWarp": ToolReference(
        command="applywarp",
        package=Package.FSL,
        url="https://fsl.fmrib.ox.ac.uk/fsl/docs/registration/fnirt/user_guide.html",
        references=[
            "Andersson JLR, Jenkinson M, Smith SM, et al. Non-linear registration, aka spatial normalisation. FMRIB Tech Rep. 2010."
        ],
    ),
    "MCFLIRT": ToolReference(
        command="mcflirt",
        package=Package.FSL,
        url="https://fsl.fmrib.ox.ac.uk/fsl/docs/registration/mcflirt.html",
        references=[
            "Jenkinson M, Bannister P, Brady JM, et al. Improved optimisation for motion correction. NeuroImage. 2002."
        ],
    ),
    "SUSAN": ToolReference(
        command="susan",
        package=Package.FSL,
        url="https://fsl.fmrib.ox.ac.uk/fsl/docs/registration/susan.html",
        references=[
            "Smith SM, Brady JM, et al. SUSAN: A new approach to low level image processing. Int J Comput Vis. 1997."
        ],
    ),
    "RobustFOV": ToolReference(
        command="robustfov",
        package=Package.FSL,
        url="https://fsl.fmrib.ox.ac.uk/fsl/docs/structural/fsl_anat.html",
        references=[],
    ),
    # FSL Utilities
    "MERGE": ToolReference(
        command="fslmerge", package=Package.FSL, url=utilities_url, references=[]
    ),
    "ForceOrient": ToolReference(
        command="fslorient", package=Package.FSL, url=utilities_url, references=[]
    ),
    "MathsCommand": ToolReference(
        command="fslmaths", package=Package.FSL, url=utilities_url, references=[]
    ),
    "FslNVols": ToolReference(
        command="fslnvols", package=Package.FSL, url=utilities_url, references=[]
    ),
    "Split": ToolReference(
        command="fslsplit", package=Package.FSL, url=utilities_url, references=[]
    ),
    "GetNiftiTR": ToolReference(
        command="fslval", package=Package.FSL, url=utilities_url, references=[]
    ),
    "ExtractROI": ToolReference(
        command="fslroi", package=Package.FSL, url=utilities_url, references=[]
    ),
    "ImageStats": ToolReference(
        command="fslstats", package=Package.FSL, url=utilities_url, references=[]
    ),
    # FreeSurfer
    "SynthSeg": ToolReference(
        command="mri_synthseg",
        package=Package.FREESURFER,
        url="https://surfer.nmr.mgh.harvard.edu/fswiki/SynthSeg",
        references=[
            "Billot B, Greve DN, Puonti O, et al. SynthSeg: Segmentation of brain MRI scans of any contrast and resolution without retraining. Med Image Anal. 2023.",
            "Billot B, Magdamo C, Arnold SE, et al. Robust machine learning segmentation for heterogeneous clinical MRI datasets. Proc Natl Acad Sci USA. 2023.",
        ],
    ),
    "SynthMorphReg": ToolReference(
        command="mri_synthmorph",
        package=Package.FREESURFER,
        url="https://martinos.org/malte/synthmorph/",
        references=[
            "Hoffmann M, Hoopes A, Greve DN, et al. Anatomy-aware and acquisition-agnostic joint registration with SynthMorph. Imaging Neurosci. 2024.",
            "Hoffmann M, Hoopes A, Fischl B, et al. Anatomy-specific acquisition-agnostic affine registration. Proc SPIE Med Imaging. 2023.",
        ],
    ),
    "SynthStrip": ToolReference(
        command="mri_synthstrip",
        package=Package.FREESURFER,
        url="https://surfer.nmr.mgh.harvard.edu/docs/synthstrip/",
        references=[
            "Hoopes A, Mora JS, Dalca AV, et al. SynthStrip: Skull-stripping for brain MRI. NeuroImage. 2022."
        ],
    ),
    "SegmentHA": ToolReference(
        command="segmentHA_T1",
        package=Package.FREESURFER,
        url="https://surfer.nmr.mgh.harvard.edu/fswiki/HippocampalSubfieldsAndNucleiOfAmygdala",
        references=[
            "Iglesias JE, Augustinack JC, Nguyen K, et al. A computational atlas of the hippocampal formation. NeuroImage. 2015.",
            "Saygin ZM, Kliemann D, Iglesias JE, et al. High-resolution MRI reveals nuclei of the human amygdala. NeuroImage. 2017.",
        ],
    ),
    "LTAConvert": ToolReference(
        command="lta_convert",
        package=Package.FREESURFER,
        url="https://ftp.nmr.mgh.harvard.edu/pub/docs/html/lta_convert.help.xml.html",
        references=[],
    ),
    "ApplyVolTransform": ToolReference(
        command="mri_vol2vol",
        package=Package.FREESURFER,
        url="https://surfer.nmr.mgh.harvard.edu/fswiki/mri_vol2vol",
        references=[],
    ),
    "ReconAll": ToolReference(
        command="recon-all",
        package=Package.FREESURFER,
        url="https://surfer.nmr.mgh.harvard.edu/fswiki/recon-all",
        references=[
            "Dale AM, Fischl B, Sereno MI, et al. Cortical surface-based analysis I: Segmentation and surface reconstruction. NeuroImage. 1999.",
            "Fischl B, Sereno MI, Dale AM, et al. Cortical surface-based analysis II: Inflation and surface-based coordinate system. NeuroImage. 1999.",
            "Fischl B, Salat DH, Busa E, et al. Whole brain segmentation: Automated labeling of neuroanatomical structures. Neuron. 2002.",
            "Fischl B, van der Kouwe A, Destrieux C, et al. Automatically parcellating the human cerebral cortex. Cereb Cortex. 2004.",
        ],
    ),
    # Other
    "CustomDcm2niix": ToolReference(
        command="dcm2niix",
        package=Package.OTHER,
        url="https://www.nitrc.org/plugins/mwiki/index.php/dcm2nii:MainPage",
        references=[
            "Li X, Morgan PS, Ashburner J, et al. The first step for neuroimaging data analysis: DICOM to NIfTI conversion. J Neurosci Methods. 2016."
        ],
    ),
    "SegmentEndocranium": ToolReference(
        command="SegmentEndocranium [SlicerMorph]",
        package=Package.OTHER,
        url="https://slicermorph.github.io/Endocast_creation.html#automatic-method",
        references=[
            "Rolfe S, Pieper S, Porto A, et al. SlicerMorph: An open and extensible platform to retrieve, visualize and analyze 3D morphology. Methods Ecol Evol. 2021."
        ],
    ),
}

# Update url finishing with #
for tool_reference in tool_reference_list.values():
    if tool_reference.url.endswith("#"):
        tool_reference.url += tool_reference.command

# Equivalent command list
equivalent_command_list = {
    "IsotropicSmooth": "MathsCommand",
    "DilateImage": "MathsCommand",
    "ErodeImage": "MathsCommand",
    "MeanImage": "MathsCommand",
    "Threshold": "MathsCommand",
    "ThrROI": "MathsCommand",
    "ApplyMask": "MathsCommand",
    "DeleteVolumes": "MathsCommand",
    "ImageMaths": "MathsCommand",
    "BinaryMaths": "MathsCommand",
    "UnaryMaths": "MathsCommand",
    "SumMultiVols": "MathsCommand",
    "SumMultiTracks": "MathsCommand",
    "ApplyXFM": "FLIRT",
    "CustomSliceTimer": "FEAT",
    "FeatureSpatialPrep": "AromaClassification",
    "FeatureTimeSeries": "AromaClassification",
    "FeatureFrequency": "AromaClassification",
    "FeatureSpatial": "AromaClassification",
    "SynthMorphApply": "SynthMorphReg",
    "EddyCorrect": "Eddy",
}
