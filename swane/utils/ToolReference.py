from enum import Enum


class Package(Enum):
    FSL = "fsl"
    FREESURFER = "freesurfer"
    ANTS = "ants"
    NIPY = "nipy"
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
spatialimages_url = (
    "https://nipy.org/nibabel/reference/nibabel.spatialimages.html#spatialimage"
)
nibabel_reference = "https://doi.org/10.5281/zenodo.591597"

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
    "Eddy": ToolReference(
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
    "ProbTrackX2": ToolReference(
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
    "Cluster": ToolReference(
        command="fsl-cluster",
        package=Package.FSL,
        url="https://fsl.fmrib.ox.ac.uk/fsl/docs/statistics/cluster.html",
        references=[],
    ),
    # FSL Utilities
    "MERGE": ToolReference(
        command="fslmerge", package=Package.FSL, url=utilities_url, references=[]
    ),
    "ForceOrient": ToolReference(
        command="orientations [NiBabel]",
        package=Package.NIPY,
        url="https://nipy.org/nibabel/reference/nibabel.orientations.html",
        references=[nibabel_reference],
    ),
    "MathsCommand": ToolReference(
        command="fslmaths", package=Package.FSL, url=utilities_url, references=[]
    ),
    "NVols": ToolReference(
        command="spatialimages [NiBabel]",
        package=Package.NIPY,
        url=spatialimages_url,
        references=[nibabel_reference],
    ),
    "GetNiftiTR": ToolReference(
        command="spatialimages [NiBabel]",
        package=Package.NIPY,
        url=spatialimages_url,
        references=[nibabel_reference],
    ),
    "ExtractVolumes": ToolReference(
        command="spatialimages [NiBabel]",
        package=Package.NIPY,
        url=spatialimages_url,
        references=[nibabel_reference],
    ),
    "DeleteVolumes": ToolReference(
        command="spatialimages [NiBabel]",
        package=Package.NIPY,
        url=spatialimages_url,
        references=[nibabel_reference],
    ),
    "ImageStatistics": ToolReference(
        command="statistics [NumPy]",
        package=Package.OTHER,
        url="https://numpy.org/doc/stable/reference/routines.statistics.html",
        references=[
            "Harris CR, Millman KJ, van der Walt SJ, et al. Array programming with NumPy. Nature. 2020."
        ],
    ),
    "AsymmetryIndex": ToolReference(
        command="arithmetic [NumPy]",
        package=Package.OTHER,
        url="https://numpy.org/doc/stable/reference/routines.math.html",
        references=[
            "Harris CR, Millman KJ, van der Walt SJ, et al. Array programming with NumPy. Nature. 2020."
        ],
    ),
    "ArtifactDetect": ToolReference(
        command="rapidart [Nipype]",
        package=Package.OTHER,
        url="https://nipype.readthedocs.io/en/latest/api/generated/nipype.algorithms.rapidart.html",
        references=[],
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
    # ANTs (antspyx / antspynet)
    "AntsN4BiasFieldCorrection": ToolReference(
        command="N4BiasFieldCorrection [antspyx]",
        package=Package.ANTS,
        url="https://antspyx.readthedocs.io/en/latest/utils.html#ants.n4_bias_field_correction",
        references=[
            "Tustison NJ, Avants BB, Cook PA, et al. N4ITK: improved N3 bias correction. IEEE Trans Med Imaging. 2010;29(6):1310-1320."
        ],
    ),
    "AntsRegistration": ToolReference(
        command="antsRegistration",
        package=Package.ANTS,
        url="https://antspyx.readthedocs.io/en/latest/registration.html#ants.registration",
        references=[
            "Avants BB, Epstein CL, Grossman M, Gee JC. Symmetric diffeomorphic image registration with cross-correlation: evaluating automated labeling of elderly and neurodegenerative brain. Med Image Anal. 2008;12(1):26-41.",
            "Klein A, Andersson J, Ardekani BA, et al. Evaluation of 14 nonlinear deformation algorithms applied to human brain MRI registration. Neuroimage. 2009;46(3):786-802.",
            "Murphy K, van Ginneken B, Reinhardt JM, et al. Evaluation of registration methods on thoracic CT: the EMPIRE10 challenge. IEEE Trans Med Imaging. 2011;30(11):1901-1920.",
            "Avants BB, Tustison NJ, Stauffer M, Song G, Wu B, Gee JC. A reproducible evaluation of ANTs similarity metric performance in brain image registration. Neuroimage. 2011;54(3):2033-2044.",
        ],
    ),
    "AntsPyNetBrainExtraction": ToolReference(
        command="brain_extraction [antspynet]",
        package=Package.ANTS,
        url="https://github.com/ANTsX/ANTsPyNet/blob/master/antspynet/utilities/brain_extraction.py",
        references=[
            "Tustison NJ, Cook PA, Holbrook AJ, et al. The ANTsX ecosystem for quantitative biological and medical imaging. Sci Rep. 2021;11:9068."
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
    "ImageMaths": "MathsCommand",
    "BinaryMaths": "MathsCommand",
    "UnaryMaths": "MathsCommand",
    "SumMultiVols": "MathsCommand",
    "SumMultiTracks": "AsymmetryIndex",
    "SpatialFilter": "MathsCommand",
    "ApplyXFM": "FLIRT",
    "CustomSliceTimer": "FEAT",
    "FEATModel": "FEAT",
    "FILMGLS": "FEAT",
    "SmoothEstimate": "Cluster",
    "FeatureSpatialPrep": "AromaClassification",
    "FeatureTimeSeries": "AromaClassification",
    "FeatureFrequency": "AromaClassification",
    "FeatureSpatial": "AromaClassification",
    "SynthMorphApply": "SynthMorphReg",
    "EddyCorrect": "Eddy",
    "AntsApplyTransforms": "AntsRegistration",
}
