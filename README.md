<h1 align="center"> SWANe</h1><br>
<p align="center">
  <a href="#">
    <img alt="SWANe" title="SWANe" src="https://github.com/LICE-dev/swane_supplement/blob/main/swane_supplement/icons/swane.png">
  </a>
</p>
<h3 align="center"> Standardized Workflow for Advanced Neuroimaging in Epilepsy</h3>


## Table of Contents

- [Introduction](#introduction)
- [Features](#features)
- [Wiki](#wiki)
- [Getting Started](#getting-started)
- [Authors](#authors)
- [Feedback](#feedback)
- [License](#license)


## Introduction
SWANe is a software designed and developed to improve and simplify the management of a wide range of advanced neuroimaging analysis algorithms.

It consists of a library of predefinied workflows that can be managed through an user-friendly Graphical User Interface, which guides the users step by step to all the operations without any text-based command interface.

SWANe straightforward pipeline can be used to manage imaging for epileptic patients of all ages (including pediatric patients). Its structure in indipendent modules permits to be diffusely adopted overcoming the difficulties to collect advanced imaging (especially metabolic and functional) in small epileptic centers.

Each module is completely independent from the others and is dedicated to one imaging modality/analysis, starting from a 3D-T1 weighted image, which represent the “base image” for all the analysis.



## Features

A few of the analyses you can do with SWANe:
* **3D T1w**: generates T13D NIFTI files to use as reference;
* **3D Flair**: generates 3D Flair NIFTI files and perform linear registration to reference space;
* **2D Cor/Sag/Tra Flair**: generates 2D Flair NIFTI files and perform linear registration to reference space;
* **Post-contrast 3D T1w**: generates post-contrast 3D T1w NIFTI files and perform linear registration to T13D reference space.
* **FreeSurfer**: performs FreeSurfer cortical reconstruction and, if required, segmentation of the hippocampal substructures and the nuclei of the amygdala;
* **FlaT1**: creates a junction and extension z-score map based on 3D T1w, 3D Flair and a mean template;
* **PET & Arterial Spin Analysis (ASL)**: analysis for registration to reference, z-score and asymmetry index maps, projection on FreeSurfer pial surface;
* **Diffusion Tensor Imaging processing**: performs DTI preprocessing workflow and fractinal anisotropy calculation;
* **Tractography**: perrforms tractography execution for chosen tract using FSL xtract protocols;
* **Task fMRI**: performs fMRI first level analysis for a single or double task with constant task-rest paradigm;
* **Venous MRA**: performs analysis of phase contrasts image (in single or two series) to obtain in-skull veins in reference space.


## Wiki
**SWANe** comes with an extensive [Wiki](https://github.com/LICE-dev/swane/wiki) hosted on GitHub that covers all the aspects of the project.


## Getting Started
**Ubuntu**: SWANe is developed and optimized for Ubuntu > 20.XX.

**macOS**: SWANe is developed and optimized for macOS > 12.5.XX.

### Mandatory Dependencies
| **Software** | **Minimum Version** | **Official Installation Guide** |
| --- | --- | --- |
| [python](https://www.python.org/) | [3.10](https://www.python.org/downloads/) |   |
| [dcm2niix](https://github.com/rordenlab/dcm2niix) | [1.0.20220720](https://github.com/rordenlab/dcm2niix/tree/v1.0.20220720) | [Link](https://github.com/rordenlab/dcm2niix#install) |
| [fsl](https://fsl.fmrib.ox.ac.uk/fsl/fslwiki/) | [6.0.6](https://fsl.fmrib.ox.ac.uk/fsl/fslwiki/FslInstallation) | [Link](https://fsl.fmrib.ox.ac.uk/fsl/fslwiki/FslInstallation#Installing_FSL) |

> [!WARNING]
The installation of some of these dependencies can be tricky. If you're not handy with Mac or Linux OS we recommend you to use our Wiki (coming soon!)  or read the [Wiki](https://github.com/LICE-dev/swane/wiki) section for a full installation guide of each one of these softwares.

### Optional Dependencies

| **Software** | **Minimum Version** | **Official Installation Guide** |
| --- | --- | --- |
| [FreeSurfer](https://surfer.nmr.mgh.harvard.edu/) | [7.3.2](https://github.com/freesurfer/freesurfer/tree/v7.3.2) | [Linux](https://surfer.nmr.mgh.harvard.edu/fswiki/FS7_linux) - [macOS](https://surfer.nmr.mgh.harvard.edu/fswiki/FS7_mac) |
| [3D Slicer](https://www.slicer.org/) | [5.2.1](https://www.slicer.org/wiki/Documentation/Nightly/FAQ/General#Where_can_I_download_Slicer.3F) | [Linux](https://slicer.readthedocs.io/en/latest/user_guide/getting_started.html#linux) - [macOS](https://slicer.readthedocs.io/en/latest/user_guide/getting_started.html#mac) |
| [graphviz](https://graphviz.org/) | [0.2.2](https://github.com/graphp/graphviz/tree/v0.2.2) | [Linux](https://graphviz.org/download/#linux) - [macOS](https://graphviz.org/download/#mac) |

> [!WARNING]
The installation of some of these dependencies can be tricky. If you're not handy with Mac or Linux OS we recommend you to use our Wiki (coming soon!) or read the [Wiki](https://github.com/LICE-dev/swane/wiki) for a full installation guide of each one of these softwares.

### Package/Software Installation Order
Below the recommend software/package installation order to make sure SWANe works properly:
* Python;
* Pip
* Dcm2niix;
* FSL;
* FreeSurfer;
* Matlab Runtime;
* 3D Slicer;
* Graphviz;
* SWANe

### Installation
```
pip3 install swane
```
> :information_source: **Info**
Starting from Ubuntu 23.04 apt is the default package manager for python libraries.
SWANe is published only on PyPi, therefore it's necessary to allow the pip installation command with the argument --break-system-packages.
This is not necessary for previous Ubuntu versions.
### Executing
```
python3 -m swane
```

### Updating
```
pip3 install --upgrade swane
```

## Authors
SWANe is designed and developed by [LICE Neuroimaging Commission](https://www.lice.it/), term 2021-2024, with the main contribution by [Power ICT Srls](https://powerictsoft.com/).


## Feedback
If you want to leave us your feedback on **SWANe** please fill the following [**Google Form**](https://forms.gle/ewUrNzwjQWanPxVF7).

For any advice on common problems or issues, please open an [Issue](https://github.com/LICE-dev/swane/issues) on our GitHub. Pull requests are welcomed.

You can contact us at the following e-mail: [dev@lice.it](mailto:dev@lice.it).


## License

This project is licensed under the [MIT](LICENSE) License - see the [LICENSE](LICENSE) file for details
