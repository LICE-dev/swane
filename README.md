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
- [Getting Started](#gettingstarted)
- [Troubleshots](#throubleshots)
- [SWANe on Windows](#swaneonwindows)
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

## Getting Started
**Ubuntu**: SWANe is developed and optimized for Ubuntu > 20.XX.

**macOS**: SWANe is developed and optimized for macOS > 12.5.XX.

### Mandatory Dependencies
| Software | Minimum Version | Recommended Version | Installation Guide |
| ------ | ------ | ------ | ------ |
| [python](https://www.python.org/) | [3.7](https://www.python.org/downloads/) | [3.10](https://www.python.org/downloads/) | |
| [dcm2niix](https://www.nitrc.org/plugins/mwiki/index.php/dcm2nii:MainPage) | [1.0.202111006](https://github.com/rordenlab/dcm2niix/tree/v1.0.20211006) | [1.0.20220720](https://github.com/rordenlab/dcm2niix/tree/v1.0.20220720) | [SWANe Wiki Page]() (Coming Soon) |
| [fsl](https://fsl.fmrib.ox.ac.uk/fsl/fslwiki/) | [6.0.0](https://fsl.fmrib.ox.ac.uk/fsl/fslwiki/FslInstallation) | [6.0.6](https://fsl.fmrib.ox.ac.uk/fsl/fslwiki/FslInstallation) | [SWANe Wiki Page]() (Coming Soon) |


### Optional Dependencies

| Software | Minimum Version | Recommended Version | Installation Guide |
| ------ | ------ | ------ | ------ |
| [FreeSurfer](https://surfer.nmr.mgh.harvard.edu/) | [7.0.0](https://github.com/freesurfer/freesurfer/tree/v7.0.0) | [7.3.2](https://github.com/freesurfer/freesurfer/tree/v7.3.2) | [SWANe Wiki Page]() (Coming Soon) |
| [3D Slicer](https://www.slicer.org/) | [5.0.0](https://www.slicer.org/wiki/Documentation/Nightly/FAQ/General#Where_can_I_download_Slicer.3F) | [5.2.1](https://download.slicer.org/bitstream/637f7a7f517443dc5dc7326e) | [SWANe Wiki Page]() (Coming Soon) |
| [graphviz](https://graphviz.org) | [0.2.0](https://github.com/graphp/graphviz/tree/v0.2.0) | [0.2.2](https://github.com/graphp/graphviz/tree/v0.2.2) | [SWANe Wiki Page]() (Coming Soon) |
> :warning: **Warning**
The installation of some of these dependencies can be tricky. If you're not handy with Mac or Linux OS we recommend you to use our Wiki (coming soon!) for a full installation guide of each one of these softwares.

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

### Ubuntu Freesurfer and tcsh
After the installation of FreeSurfer, the following error may occur at SWANe launching:
```
/usr/local/freesurfer/bin/recon-all: /bin/tcsh: badinterpreter: No such file or directory
```
To solve it, launch the following install command.
```
sudo apt install csh tcsh
```

### SWANe and Anaconda
Anaconda is a distribution of the Python and R programming languages for scientific computing.
Anaconda uses its own environment and its own python interpreter for the execution of packages and softwares, and it is often set as the default environment in the terminal window of the OS after its installation.
Currently there is no SWANe version compatible with the Anaconda environment, due a known issue with FSL and some of its functions (e.g.: the BET function).
We’re working on it, but in the meantime, to make sure SWANe can work properly, you can launch the SWANe installation command outside the Anaconda environment and without using its python interpreter.
To point the right python interpreter, you can specify its full path in the installation and launch command of SWANe.
After the installation you can also create a customized alias to make it easier to start SWANe.


### Missing libxml2
libxml2 is a C library and a direct and mandatory dependency for a wide range of other libraries.
If the installation of SWANe fails because this library is not present in your OS, you can easily solve the issue by installing the lxml toolkit.

**Ubuntu**
```
sudo apt-get install python3-lxml
```
**macOS**
```
sudo port install py27-lxml
```
You need Xcode installed on your OS.


## SWANe on Windows
SWANe can’t run on Windows due the fact some mandatory (such as FSL) and optional but recommended dependencies (such as FreeSurfer) does not have a compatible version with the Microsoft OS.

However, starting from Windows 10 (Build 19041) it is possible to use the Windows Subsystem for Linux (WSL) feature to run a Linux environment without the need for a separate virtual machine or dual booting.
> :warning: **Warning**
Keep in mind that, although WSL is a powerful and well-optimized tool and it is theoretically lighter in terms of resources used compared to a virtual machine, it is still a subsystem, and therefore less performing compared to a standalone Ubuntu.
This inevitably leads to a slowdown of SWANe and to an increment of memory and RAM usage by the analyses, which some less performing PCs could not handle.


## Authors
SWANe is designed and developed by [LICE Neuroimaging Commission](https://www.lice.it/), term 2021-2024, with the main contribution by [Power ICT Srls](https://powerictsoft.com/).


## Feedback
If you want to leave us your feedback on SWANe please fill the following [Google Form](https://forms.gle/ewUrNzwjQWanPxVF7).


## License

This project is licensed under the [MIT](LICENSE) License - see the [LICENSE](LICENSE) file for details
