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

It consists of a library of predefined workflows that can be managed through a user-friendly Graphical User Interface, 
which guides the users step by step to all the operations without any text-based command interface.

SWANe straightforward pipeline can be used to manage imaging for epileptic subjects of all ages.
Its structure in independent modules permits to be diffusely adopted overcoming the difficulties to collect advanced 
imaging (especially metabolic and functional) in small epilepsy centers.

Each module is completely independent of the others and is dedicated to one imaging modality/analysis, starting from 
a 3D-T1 weighted image, which represents the “base image” for all the analysis.



## Features

A few of the analyses you can do with SWANe:
* **3D T1w**: generates T13D NIFTI files to use as reference;
* **3D Flair**: generates 3D Flair NIFTI files and performs linear registration to reference space;
* **2D Cor/Sag/Tra Flair**: generates 2D Flair NIFTI files and performs linear registration to reference space;
* **Post-contrast 3D T1w**: generates post-contrast 3D T1w NIFTI files and perform linear registration to T13D reference space.
* **FreeSurfer**: performs FreeSurfer cortical reconstruction and, if required, segmentation of the hippocampal substructures and the nuclei of the amygdala;
* **FlaT1**: creates a junction and extension z-score map based on 3D T1w, 3D Flair and a mean template;
* **PET & Arterial Spin Analysis (ASL)**: analysis for registration to reference, z-score and asymmetry index maps, projection on FreeSurfer pial surface;
* **Diffusion Tensor Imaging processing**: performs DTI preprocessing workflow and fractional anisotropy calculation;
* **Tractography**: performs tractography execution for chosen tract using FSL xtract protocols;
* **Task fMRI**: performs fMRI first level analysis for a single or double task with constant task-rest paradigm;
* **Venous MRA**: performs analysis of phase contrasts image (in single or two series) to obtain in-skull veins in reference space.


## Wiki
**SWANe** comes with an extensive [Wiki](https://github.com/LICE-dev/swane/wiki) hosted on GitHub that covers all the aspects of the project.


## Getting Started
**Ubuntu**: SWANe is developed and optimized for Ubuntu > 20.XX.
