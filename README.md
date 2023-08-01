<h1 align="center"> SWANe</h1><br>
**Standardized Workflow for Advanced Neuroimaging in Epilepsy**
<p align="center">
  <a href="#">
    <img alt="SWANi" title="SWANi" src="https://github.com/LICE-dev/swane_supplement/blob/main/swane_supplement/icons/swane.png">
  </a>
</p>
<p align="center">
  Standardized Workflow for Advanced Neuro-Imaging
</p>


## Table of Contents

- [Introduction](#introduction)
- [Features](#features)
- [Getting Started](#gettingstarted)
- [Contributors](#contributors)
- [Authors](#authors)
- [Acknowledgments](#acknowledgments)


## Introduction
SWANe is a software designed and developed to improve and simplify the management of a wide range of advanced neuroimaging analysis algorithms.
It consists of a library of predefinied workflows that can be managed through an user-friendly Graphical User Interface, which guides the users step by step to all the operations without any text-based command interface.
SWANe straightforward pipeline can be used to manage imaging for epileptic patients of all ages (including pediatric patients). Its structure in indipendent modules permits to be diffusely adopted overcoming the difficulties to collect advanced imaging (especially metabolic and functional) in small epileptic centers.
Each module is completely independent from the others and is dedicated to one imaging modality/analysis, starting from a 3D-T1 weighted image, which represent the “base image” for all the analysis.



## Features

A few of the analysis you can do with SWANi:
* **3D T1w**: generate T13D NIFTI files to use as reference;
* **3D Flair**: generate 3D Flair NIFTI files and perform linear registration to reference space;
* **2D Cor/Sag/Tra Flair**: generate 2D Flair NIFTI files and perform linear registration to reference space;
* **Post-contrast 3D T1w**: generate post-contrast 3D T1w NIFTI files and perform linear registration to T13D reference space.
* **FreeSurfer**: perform FreeSurfer cortical reconstruction and, if required, segmentation of the hippocampal substructures and the nuclei of the amygdala;
* **FLAT1**: create a junction and extension z-score map based on 3D T1w, 3D Flair and a mean template;
* **Diffusion Tensor Imaging processing**: DTI preprocessing workflow and fractinal anisotropy calculation;
* **Tractography**: tractography execution for chosen tract using FSL xtract protocols;
* **PET & Arterial Spin Analysis (ASL)**: analysis for registration to reference, z-score and asymmetry index maps, projection on FreeSurfer pial surface;
* **Task fMRI**: fMRI first level analysis for a single or double task with constant task-rest paradigm;
* **Venous MRA**: analysis of phase contrasts image (in single or two series) to obtain in-skull veins in reference space.

## Getting Started
**Ubuntu**: SWANe is developed and optimized for Ubuntu > 20.XX.

**macOS**: SWANe is developed and optimized for macOS > 12.5.XX.

### Mandatory Dependencies
| Software | Minimum Version | Recommended Version | Installation Guide |
| ------ | ------ | ------ | ------ |
| [python](https://www.python.org/) | [3.7](https://www.python.org/downloads/) | [3.10](https://www.python.org/downloads/) | |
| [dcm2niix](https://www.nitrc.org/plugins/mwiki/index.php/dcm2nii:MainPage) | [1.0.202111006](https://github.com/rordenlab/dcm2niix/tree/v1.0.20211006) | [1.0.20220720](https://github.com/rordenlab/dcm2niix/tree/v1.0.20220720) | [SWANi Wiki Page]() (Coming Soon) |
| [fsl](https://fsl.fmrib.ox.ac.uk/fsl/fslwiki/) | [6.0.0](https://fsl.fmrib.ox.ac.uk/fsl/fslwiki/FslInstallation) | [6.0.5](https://fsl.fmrib.ox.ac.uk/fsl/fslwiki/FslInstallation) | [SWANi Wiki Page]() (Coming Soon) |
> **Warning**
The installation of some of these dependencies can be tricky. If you're not handy with Mac or Linux OS we recommend you to use our Wiki (coming soon!)  or read the [Help](#help) section for a full installation guide of each one of these softwares.

### Optional Dependencies

| Software | Minimum Version | Recommended Version | Installation Guide |
| ------ | ------ | ------ | ------ |
| [FreeSurfer](https://surfer.nmr.mgh.harvard.edu/) | [7.0.0](https://github.com/freesurfer/freesurfer/tree/v7.0.0) | [7.3.2](https://github.com/freesurfer/freesurfer/tree/v7.3.2) | [SWANi Wiki Page]() (Coming Soon) |
| [3D Slicer](https://www.slicer.org/) | [5.0.0](https://www.slicer.org/wiki/Documentation/Nightly/FAQ/General#Where_can_I_download_Slicer.3F) | [5.2.1](https://download.slicer.org/bitstream/637f7a7f517443dc5dc7326e) | [SWANi Wiki Page]() (Coming Soon) |
| [graphviz](https://graphviz.org) | [0.2.0](https://github.com/graphp/graphviz/tree/v0.2.0) | [0.2.2](https://github.com/graphp/graphviz/tree/v0.2.2) | [SWANi Wiki Page]() (Coming Soon) |
> **Warning**
The installation of some of these dependencies can be tricky. If you're not handy with Mac or Linux OS we recommend you to use our Wiki (coming soon!) or read the  [Help](#help) section for a full installation guide of each one of these softwares.

### Package/Software Installation Order
Below the recommend software/package installation order to make sure SWANe works properly:
* Python;
* Dcm2niix;
* FSL;
* FreeSurfer;
* Matlab Runtime;
* 3D Slicer;
* Graphviz;
* SWANe

### Installation
```
python3 -m pip install swane
```

### Executing
```
python3 -m swane
```

### Updating
```
python3 install --upgrade swane
```

## Troubleshots
### FreeSurfer/FSL conflict with Python
A [known issue](https://github.com/freesurfer/freesurfer/pull/1072) with FSL >= 6.0.6 can cause the following error:
> SWANe has been executed using fsl Python instead of system Python.
This may depend on a conflict in FSL(>=6.0.6) and FreeSurfer(<=7.3.2) configurations in your /home/user/.bashrc file that impacts on correct functioning of SWANe and maybe other applications.
SWANe can try to fix your configuration file or to restart with system Python interpreter. Otherwise you can exit SWANe and fix your configuration manually adding this line to your configuration file.

To fix it, you can follow the instruction displayed in the alert window. We recommend you to use the automatic error fixing option.

### Scipy error with Apple Silicon mac
During SWANe installation with pip, the following error may occur on hardwares with Apple Silicon CPU:
```
pip3 install swane
[…]
error: metadata-generation-failed
```
To fix it, you can install Scipy manually with Homebrew before SWANe, using the following command:
```
brew install scipy
```

### Ubuntu Freesurfer bad interpreter
After the installation of FreeSurfer, the following error may occour at SWANe launching:
```
/usr/local/freesurfer/bin/recon-all: /bin/tcsh: badinterpreter: No such file or directory
```
To solve it, launch the following install command.
```
sudo apt install csh tcsh
```

## Authors
SWANe is designed and developed by [LICE Neuroimaging Commission](https://www.lice.it/), term 2021-2024, with the main contribution by [Power ICT Srls](https://powerictsoft.com/).


## Feedback
If you want to leave us your feedback on SWANe please fill the following [Google Form](https://forms.gle/ewUrNzwjQWanPxVF7).
For any advice on common problems or issues, please contact us at the following e-mail: [dev@lice.it](mailto:dev@lice.it).


## License

This project is licensed under the [MIT](LICENSE.md) License - see the [LICENSE.md](LICENSE.md) file for details