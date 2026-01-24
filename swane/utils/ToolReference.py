from enum import Enum

class Package(Enum):
    FSL = "fsl"
    FREESURFER = "freesurfer"
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
        return tool_reference_list[key]
    except KeyError:
        raise ValueError(f"Comando '{key}' non trovato nel database")

tool_reference_list= {
    # Structural
    "BET": ToolReference(
        command="bet",
        package=Package.FSL,
        url="https://fsl.fmrib.ox.ac.uk/fsl/docs/structural/bet.html",
        references=[
            "S.M. Smith. Fast robust automated brain extraction. Human Brain Mapping, 17(3):143-155, November 2002"
        ]
    ),
    "FAST": ToolReference(
        command="fast",
        package=Package.FSL,
        url="https://fsl.fmrib.ox.ac.uk/fsl/docs/structural/fast.html",
        references=[
            "Zhang, Y., Brady, M., Smith, S. Segmentation of brain MR images through a hidden Markov random field model and the expectation-maximization algorithm. IEEE Trans Med Imag, 20(1):45-57, 2001"
        ]
    ),

    # fMRI
    "FEAT": ToolReference(
        command="feat",
        package=Package.FSL,
        url="https://fsl.fmrib.ox.ac.uk/fsl/docs/task_fmri/feat/index.html",
        references=[
            "Woolrich, M. W., Ripley, B. D., Brady, M., & Smith, S. M. (2001). Temporal Autocorrelation in Univariate Linear Modeling of FMRI Data. NeuroImage, 14(6), 1370–1386. http://doi.org/10.1006/nimg.2001.0931"
        ]
    ),
    "MELODIC": ToolReference(
        command="melodic",
        package=Package.FSL,
        url="https://fsl.fmrib.ox.ac.uk/fsl/docs/resting_state/melodic.html",
        references=[
            "Beckmann CF, Smith SM. Probabilistic independent component analysis for functional magnetic resonance imaging. IEEE Trans Med Imaging. 2004 Feb;23(2):137-52. doi: 10.1109/TMI.2003.822821. PMID: 14964560."
        ]
    ),

    # Diffusion / Tractography
    "EDDY": ToolReference(
        command="eddy",
        package=Package.FSL,
        url="https://fsl.fmrib.ox.ac.uk/fsl/docs/eddy/eddy.html",
        references=[
            "Andersson JLR, Sotiropoulos SN. An integrated approach to correction for off-resonance effects and subject movement in diffusion MR imaging. Neuroimage. 2016 Jan 15;125:1063-1078. doi: 10.1016/j.neuroimage.2015.10.019. Epub 2015 Oct 20. PMID: 26481672; PMCID: PMC4692656."
        ]
    ),
    "BEDPOSTX": ToolReference(
        command="bedpostx",
        package=Package.FSL,
        url="https://fsl.fmrib.ox.ac.uk/fsl/docs/diffusion/bedpostx.html",
        references=[
            "Behrens TE, Berg HJ, Jbabdi S, Rushworth MF, Woolrich MW. Probabilistic diffusion tractography with multiple fibre orientations: What can we gain? NeuroImage. 2007 Jan 1;34(1):144-55. doi: 10.1016/j.neuroimage.2006.09.018. Epub 2006 Oct 27. PMID: 17070705; PMCID: PMC7116582."
        ]
    ),
    "PROBTRACKX": ToolReference(
        command="probtrackx",
        package=Package.FSL,
        url="https://fsl.fmrib.ox.ac.uk/fsl/docs/diffusion/probtrackx.html",
        references=[
            "Behrens TE, Berg HJ, Jbabdi S, Rushworth MF, Woolrich MW. Probabilistic diffusion tractography with multiple fibre orientations: What can we gain? NeuroImage. 2007 Jan 1;34(1):144-55. doi: 10.1016/j.neuroimage.2006.09.018. Epub 2006 Oct 27. PMID: 17070705; PMCID: PMC7116582."
        ]
    ),
    "XTRACT": ToolReference(
        command="xtract",
        package=Package.FSL,
        url="https://fsl.fmrib.ox.ac.uk/fsl/docs/diffusion/xtract.html",
        references=[
            "Warrington S., Bryant K., Khrapitchev A., Sallet J., Charquero-Ballester M., Douaud G., Jbabdi S.*, Mars R.*, Sotiropoulos S.N.* (2020) XTRACT - Standardised protocols for automated tractography and connectivity blueprints in the human and macaque brain. NeuroImage, 217(116923). DOI: 10.1016/j.neuroimage.2020.116923",
            "Warrington S.*, Thompson E.*, Bastiani M., Dubois J., Baxter L., Slater R., Jbabdi S., Mars R.B., Sotiropoulos S.N. (2022) Concurrent mapping of brain ontogeny and phylogeny within a common space: Standardized tractography and applications. Science Advances, 8(42). DOI: 10.1126/sciadv.abq2022",
            "de Groot M., Vernooij M.W., Klein S., Ikram M.A., Vos F.M., Smith S.M., Niessen W.J., Andersson J.L.R. (2013) Improving alignment in Tract-based spatial statistics: Evaluation and optimization of image registration. NeuroImage, 76(1), 400-411. DOI: 10.1016/j.neuroimage.2013.03.015"
        ]
    ),

    # Registration
    "FLIRT": ToolReference(
        command="flirt",
        package=Package.FSL,
        url="https://fsl.fmrib.ox.ac.uk/fsl/docs/registration/flirt/index.html",
        references=[
            "Jenkinson, M., Bannister, P., Brady, J. M. and Smith, S. M. Improved Optimisation for the Robust and Accurate Linear Registration and Motion Correction of Brain Images. NeuroImage, 17(2), 825-841, 2002.",
            "Jenkinson, M. and Smith, S. M. A Global Optimisation Method for Robust Affine Registration of Brain Images. Medical Image Analysis, 5(2), 143-156, 2001.",
            "Greve, D.N. and Fischl, B. Accurate and robust brain image alignment using boundary-based registration. NeuroImage, 48(1):63-72, 2009."
        ]
    ),
    "FNIRT": ToolReference(
        command="fnirt",
        package=Package.FSL,
        url="https://fsl.fmrib.ox.ac.uk/fsl/docs/registration/fnirt/index.html",
        references=[
            "Andersson JLR, Jenkinson M, Smith S (2010) Non-linear registration, aka spatial normalisation. FMRIB technical report TR07JA2"
        ]
    ),
    "MCFLIRT": ToolReference(
        command="mcflirt",
        package=Package.FSL,
        url="https://fsl.fmrib.ox.ac.uk/fsl/docs/registration/mcflirt.html",
        references=[
            "Jenkinson, M., Bannister, P., Brady, J. M. and Smith, S. M. Improved Optimisation for the Robust and Accurate Linear Registration and Motion Correction of Brain Images. NeuroImage, 17(2), 825-841, 2002."
        ]
    ),
    "SUSAN": ToolReference(
        command="susan",
        package=Package.FSL,
        url="https://fsl.fmrib.ox.ac.uk/fsl/docs/registration/susan.html",
        references=[
            "S.M. Smith and J.M. Brady. SUSAN - a new approach to low level image processing. International Journal of Computer Vision, 23(1):45–78, May 1997."
        ]
    )
}

# Utility FSL senza reference → stesso URL
utilities_url = "https://fsl.fmrib.ox.ac.uk/fsl/docs/utilities/fslutils.html"

tool_reference_list.update({
    "MERGE": ToolReference(
        command="fslmerge",
        package=Package.FSL,
        url=utilities_url,
        references=[]
    ),
    "EXTRACTROI": ToolReference(
        command="fslroi",
        package=Package.FSL,
        url=utilities_url,
        references=[]
    ),
    "MATHSCMD": ToolReference(
        command="fslmaths",
        package=Package.FSL,
        url=utilities_url,
        references=[]
    ),
    "STATISTICS": ToolReference(
        command="fslstats",
        package=Package.FSL,
        url=utilities_url,
        references=[]
    ),
    "FSLORIENT": ToolReference(
        command="fslorient",
        package=Package.FSL,
        url=utilities_url,
        references=[]
    ),
    "SWAPDIM": ToolReference(
        command="fslswapdim",
        package=Package.FSL,
        url=utilities_url,
        references=[]
    ),
    "NVOLS": ToolReference(
        command="fslnvols",
        package=Package.FSL,
        url=utilities_url,
        references=[]
    ),
    "FSLHD": ToolReference(
        command="fslhd",
        package=Package.FSL,
        url=utilities_url,
        references=[]
    )
})


# TODO AGGIORNARE NOME
tool_reference_list["SEGMENTE"] = ToolReference(
    command="segmente",
    package=Package.FREESURFER,
    url="https://surfer.nmr.mgh.harvard.edu/fswiki/HippocampalSubfieldsAndNucleiOfAmygdala",
    references=[
        "Iglesias, J.E., Augustinack, J.C., Nguyen, K., Player, C.M., Player, A., Wright, M., Roy, N., Frosch, M.P., Mc Kee, A.C., Wald, L.L., Fischl, B., and Van Leemput, K. A computational atlas of the hippocampal formation using ex vivo, ultra-high resolution MRI: Application to adaptive segmentation of in vivo MRI. Neuroimage, 115, July 2015, 117-137.",
        "Saygin ZM & Kliemann D (joint 1st authors), Iglesias JE, van der Kouwe AJW, Boyd E, Reuter M, Stevens A, Van Leemput K, Mc Kee A, Frosch MP, Fischl B, Augustinack JC. High-resolution magnetic resonance imaging reveals nuclei of the human amygdala: manual segmentation to automatic atlas. Neuroimage, 155, July 2017, 370-382."
    ]
)

tool_reference_list["MRI_SYNTHSEG"] = ToolReference(
    command="mri_synthseg",
    package=Package.FREESURFER,
    url="https://surfer.nmr.mgh.harvard.edu/fswiki/SynthSeg",
    references=[
        "Billot, B., Greve, D.N., Puonti, O., Thielscher, A., Van Leemput, K., Fischl, B., Dalca, A.V., Iglesias, J.E. SynthSeg: Segmentation of brain MRI scans of any contrast and resolution without retraining. Medical Image Analysis, 83, 102789 (2023).",
        "Billot, B., Magdamo, C., Arnold, S.E., Das, S., Iglesias, J.E. Robust machine learning segmentation for large-scale analysis of heterogeneous clinical brain MRI datasets. PNAS, 120(9), e2216399120 (2023)."
    ]
)


tool_reference_list["MRI_SYNTHMORPH"] = ToolReference(
    command="mri_synthmorph",
    package=Package.FREESURFER,
    url="https://martinos.org/malte/synthmorph/",
    references=[
        "Hoffmann M, Hoopes A, Greve DN, Fischl B, Dalca AV. Anatomy-aware and acquisition-agnostic joint registration with SynthMorph. Imaging Neuroscience, 2, pp 1-33, 2024.",
        "Hoffmann M, Hoopes A, Fischl B, Dalca AV. Anatomy-specific acquisition-agnostic affine registration learned from fictitious images. SPIE Medical Imaging: Image Processing, 12464, p 1246402, 2023."
    ]
)

tool_reference_list["MRI_SYNTHSTRIP"] = ToolReference(
    command="mri_synthstrip",
    package=Package.FREESURFER,
    url="https://surfer.nmr.mgh.harvard.edu/docs/synthstrip/",
    references=[
        "Andrew Hoopes, Jocelyn S. Mora, Adrian V. Dalca, Bruce Fischl*, Malte Hoffmann* (*equal contribution). NeuroImage 260, 2022, 119474. https://doi.org/10.1016/j.neuroimage.2022.119474"
    ]
)


tool_reference_list["DCM2NIIX"] = ToolReference(
    command="dcm2niix",
    package=Package.OTHER,
    url="https://www.nitrc.org/plugins/mwiki/index.php/dcm2nii:MainPage",
    references=[
        "Li X, Morgan PS, Ashburner J, Smith J, Rorden C. The first step for neuroimaging data analysis: DICOM to NIfTI conversion. J Neurosci Methods. 2016 May 1;264:47-56. doi: 10.1016/j.jneumeth.2016.03.001. Epub 2016 Mar 2. PMID: 26945974."
    ]
)


