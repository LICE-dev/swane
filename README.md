<h1 align="center"> SWANe</h1><br>
<p align="center">
  <a href="#">
    <img alt="SWANe" title="SWANe" src="swane/resources/icons/swane.png">
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
- [Changelog](#changelog)


## Introduction
SWANe is a software designed and developed to improve and simplify the management of a wide range of advanced neuroimaging analysis algorithms.

It consists of a library of predefinied workflows that can be managed through a user-friendly Graphical User Interface, which guides the users step by step to all the operations without any text-based command interface.

SWANe is a research tool, not a medical device. Its straightforward pipeline can process imaging data of subjects of all ages, including pediatric subjects. Its structure in independent modules allows wide adoption, also by small research groups that find it difficult to run advanced imaging analyses (especially metabolic and functional).

Each module is completely independent from the others and is dedicated to one imaging modality/analysis, starting from a 3D-T1 weighted image, which represent the “base image” for all the analysis.


## Features

A few of the analyses you can do with SWANe:
* **3D T1w**: generates T13D NIFTI files to use as reference;
* **3D Flair**: generates 3D Flair NIFTI files and perform linear registration to reference space;
* **2D Cor/Sag/Tra Flair**: generates 2D Flair NIFTI files and perform linear registration to reference space;
* **2D 2T Coronal**: generates 2D 2T Coronal NIFTI files and perform linear registration to reference space;
* **Post-contrast 3D T1w**: generates post-contrast 3D T1w NIFTI files and perform linear registration to T13D reference space.
* **FreeSurfer**: performs FreeSurfer cortical reconstruction and, if required, segmentation of the hippocampal substructures and the nuclei of the amygdala;
* **FlaT1**: creates a junction and extension z-score map based on 3D T1w, 3D Flair and a mean template;
* **PET & Arterial Spin Analysis (ASL)**: analysis for registration to reference, z-score and asymmetry index maps, projection on FreeSurfer pial surface;
* **Diffusion Tensor Imaging processing**: performs DTI preprocessing workflow and fractinal anisotropy calculation;
* **Tractography**: perrforms tractography execution for chosen tract using FSL xtract protocols;
* **dipy Tractography**: performs CSD tractography and bundle recognition using dipy and the HCP842 atlas (RecoBundles);
* **Task fMRI**: performs fMRI first level analysis for a single or double task with constant task-rest paradigm;
* **Resting State fMRI**: performs single-subject spatial ICA with optional ICA-AROMA denoising, with a Python engine (nilearn/scikit-learn) or FSL MELODIC, and returns the thresholded component maps in reference space;
* **Venous MRA**: performs analysis of phase contrasts image (in single or two series) to obtain in-skull veins in reference space.


## Wiki
**SWANe** comes with an extensive [Wiki](https://github.com/LICE-dev/swane/wiki) hosted on GitHub that covers all the aspects of the project.


## Getting Started
**Ubuntu**: SWANe is developed and optimized for Ubuntu > 20.XX.

**macOS**: SWANe is developed and optimized for macOS > 12.5.XX.

**Windows (experimental)**: FSL-free pipelines only; FSL and FreeSurfer are not available natively; 3D Slicer integration is best-effort.

### Mandatory Dependencies
| **Software** | **Minimum Version** | **Official Installation Guide** |
| --- | --- | --- |
| [python](https://www.python.org/) | [3.10](https://www.python.org/downloads/) |   |
| [dcm2niix](https://github.com/rordenlab/dcm2niix) | [1.0.20220720](https://github.com/rordenlab/dcm2niix/tree/v1.0.20220720) | [Link](https://github.com/rordenlab/dcm2niix#install) |

> [!WARNING]
The installation of some of these dependencies can be tricky. If you're not handy with Mac or Linux OS we recommend you to read our [Wiki](https://github.com/LICE-dev/swane/wiki) for a full installation guide of each one of these softwares.

### Optional Dependencies

| **Software** | **Minimum Version** | **Official Installation Guide** |
| --- | --- | --- |
| [fsl](https://fsl.fmrib.ox.ac.uk/fsl/fslwiki/) | [6.0.7.8](https://fsl.fmrib.ox.ac.uk/fsl/fslwiki/FslInstallation) | [Link](https://fsl.fmrib.ox.ac.uk/fsl/fslwiki/FslInstallation#Installing_FSL) |
| [FreeSurfer](https://surfer.nmr.mgh.harvard.edu/) | [7.3.2](https://github.com/freesurfer/freesurfer/tree/v7.3.2) | [Linux](https://surfer.nmr.mgh.harvard.edu/fswiki/FS7_linux) - [macOS](https://surfer.nmr.mgh.harvard.edu/fswiki/FS7_mac) |
| [3D Slicer](https://www.slicer.org/) | [5.2.1](https://www.slicer.org/wiki/Documentation/Nightly/FAQ/General#Where_can_I_download_Slicer.3F) | [Linux](https://slicer.readthedocs.io/en/latest/user_guide/getting_started.html#linux) - [macOS](https://slicer.readthedocs.io/en/latest/user_guide/getting_started.html#mac) |
| [graphviz](https://graphviz.org/) | [0.2.2](https://github.com/graphp/graphviz/tree/v0.2.2) | [Linux](https://graphviz.org/download/#linux) - [macOS](https://graphviz.org/download/#mac) |

> [!WARNING]
The installation of some of these dependencies can be tricky. If you're not handy with Mac or Linux OS we recommend you read our [Wiki](https://github.com/LICE-dev/swane/wiki) for a full installation guide of each one of these softwares.

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

#### Quick install (Linux/macOS)
A single command builds a working SWANe environment: it reuses an existing conda (otherwise it installs Miniforge in `~/miniforge3`), creates a Python 3.12 environment named `swane-env`, installs SWANe in it (with Graphviz when no `dot` is already available), optionally installs a minimal FSL, and adds a `swane` launcher in `~/.local/bin`. The installer needs SWANe 0.2.5 or newer: it stops with an error if the SWANe it installed is older.
```
curl -fsSL https://raw.githubusercontent.com/LICE-dev/swane/main/installer/install_swane.sh | bash
```
Options can be passed after `bash -s --`, for example `curl -fsSL <url> | bash -s -- --yes --no-fsl`:

| Option | Effect |
| --- | --- |
| `--yes` | Answer yes to every prompt except the FSL licence. |
| `--accept-fsl-license` | Accept the FSL licence without prompting. |
| `--no-fsl` | Do not install or configure FSL (an FSL already wired into `swane-env` is kept). |
| `--swane-spec SPEC` | pip requirement or local path to install (default: `swane`). |
| `--miniforge-prefix DIR` | Where to install Miniforge when no conda is found (default: `~/miniforge3`). |
| `-h`, `--help` | Show the help and exit. |

What it installs and where:
* conda: your existing one, or Miniforge in `~/miniforge3` (no `conda init`, `~/.condarc` untouched, the conda `defaults` channel is never used);
* `swane-env`: Python 3.12, SWANe from PyPI (or `--swane-spec`) with its pip dependencies (dcm2niix included), Graphviz only when no `dot` is already available, and TensorFlow from conda-forge on Intel Macs;
* `swane-fsl` (optional): a minimal FSL, the oldest release supported by SWANe, in its own conda environment, with FSL's command wrappers in `$FSLDIR/share/fsl/bin`. FSL is wired into `swane-env` only through its activation hook, and only while `swane-env` is active: it sets `FSLDIR` and `FSLOUTPUTTYPE`, and makes sure `$FSLDIR/share/fsl/bin` comes before the `bin` of `swane-env` on `PATH` (never `$FSLDIR/bin`, which holds a whole conda environment with its own `python`). If your shell already has that entry ahead of `swane-env`, it is left as it is; otherwise the hook puts it first (a copy, when your shell has it further down). Nothing else on your `PATH` is changed. Deactivation removes only the entry the hook added and restores both variables. An FSL already installed is reused instead when it is recent enough and has those wrappers (`bet`, `flirt` and `fsl-cluster` in `$FSLDIR/share/fsl/bin`);
* on Linux, the system libraries needed by 3D Slicer and a `en_US.UTF-8` locale, through `sudo` (a failure only prints a warning);
* `~/.local/bin/swane`, the launcher, and, when `~/.local/bin` is not on your `PATH`, a block delimited by `# >>> SWANe installer >>>` in your login profile (`~/.zprofile`, `~/.bash_profile` or `~/.profile`) and, for bash and zsh, in `~/.bashrc` or `~/.zshrc`. Open a new terminal, then run `swane` (or run the launcher by its full path, printed at the end).

FreeSurfer, the MATLAB Runtime and 3D Slicer are not installed by the installer: install them separately (see [Optional Dependencies](#optional-dependencies) and the [Wiki](https://github.com/LICE-dev/swane/wiki)).

Every prompt is read from the terminal, so the command also works through `curl | bash`. Running the installer again updates the existing installation.

> [!NOTE]
FSL is free for non-commercial use only, under its own licence (https://fsl.fmrib.ox.ac.uk/fsl/docs/license.html): installing it means accepting that licence. Before installing FSL the installer says so and links the licence, and it installs FSL only if you type `yes`. `--yes` does not accept the FSL licence: use `--accept-fsl-license` (or `--no-fsl` to skip FSL).

To remove everything the installer created, use the conda printed on the `SWANe installer: conda` line of the summary (here the default Miniforge one):
```
~/miniforge3/bin/conda env remove -n swane-env
~/miniforge3/bin/conda env remove -n swane-fsl
rm ~/.local/bin/swane
rm -f ~/.local/share/applications/swane.desktop ~/.local/share/swane/swane-launcher.sh
```
then delete the block from `# >>> SWANe installer >>>` to `# <<< SWANe installer <<<` in your login profile (`~/.zprofile`, `~/.bash_profile` or `~/.profile`) and in `~/.bashrc` or `~/.zshrc` and, if you no longer need it, the Miniforge directory (`~/miniforge3`).

#### Manual installation
```
pip3 install swane
```
> [!NOTE]
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
This project includes subsection derived from other software, which licenses can be found in the [NOTICE](NOTICE.md) file


## Changelog

### [Unreleased]

#### Added

- License consent gate: on startup (after the setup wizard) SWANe shows and requires acceptance of the licenses of the detected external tools (FSL, FreeSurfer, 3D Slicer, dcm2niix, ANTs/antspyx). Acceptance is stored per tool and re-prompted only when a tool's version changes.
- Home dependency labels now include an inline link to each detected tool's license, opening the locally installed license file when available, otherwise the official source.
- dipy tractography engine: added a CSD and RecoBundles tractography engine as an alternative to FSL XTRACT. A new global `tractography_engine` preference selects the engine (dipy is the default only when FSL is not mandatory).
- On the first DTI tractography run, the ~649 MB HCP842 bundle atlas (`Atlas_80_Bundles` via dipy) is automatically downloaded into the local dipy directory.
- dipy tractography results are exported as `.vtp` streamline bundle models in reference space rather than thresholded `.nii.gz` density maps; re-running an old subject will not reproduce its previous output.
- Tracking defaults updated to use percentile-based FA stopping (`FA_STOP_PERCENTILE = 10%`, floored at 0.10) and volume-based seeding (`REFERENCE_VOXEL_MM3 = 2.2 mm³`) for consistent tracking across differing voxel sizes and contrasts.
- Acoustic radiation (`ar`) produces no dipy bundle and remains FSL-only.
- Low-confidence bundles are flagged rather than hidden: bundles that remain poorly matched to the atlas model after recovery retry generate a `r-<tract>_<side>.lowconf.json` sidecar (or `r-fx.lowconf.json` for fornix) and are labeled with `(LOW CONFIDENCE)` in 3D Slicer.
- The dipy tractography engine requires a 6 GB RAM floor (`DIPY_TRACTOGRAPHY_RAM_REQUIREMENT`).

#### Changed

- Resting state fMRI requires FSL: it always runs on FSL MELODIC, whatever the fMRI engine preference (now labelled "Task fMRI engine", which only selects the task fMRI engine). Without FSL the "Resting State fMRI" optional series cannot be enabled, and a stored choice is turned off.
- Resting state preference `melodic_dim` renamed `ic_dim`; existing configurations are migrated automatically.
- Resting state results: the component time courses are saved as `ica_mix` (FSL results used `melodic_mix`); 3D Slicer still loads older result folders. Component maps remain `r-thresh_zstatNN.nii.gz`.
- Resting state, FSL engine with ICA-AROMA: the ICA-AROMA decomposition and the denoising now use the data before the temporal high-pass, and the high-pass is applied after denoising, before the final MELODIC.
- Python task fMRI engine: motion correction now uses a fixed random seed and a single thread, so the same input always gives the same output. It is slower, and results of earlier versions are not reproduced.
- The FSL license is always shown at first launch, also when FSL is not installed, because it covers the MNI152NLin6Asym template used by SWANe.
- FSL remains a mandatory dependency, and the FSL tools are the default brain extraction, tractography, segmentation and task fMRI engines (registration defaults to ANTs). SWANe can also run without FSL using the FSL-free engines (ANTs, antspynet, dipy, nilearn): a build-time flag (`FSL_MANDATORY` in `swane/config/dependency_policy.py`, currently `True`) set to `False` makes FSL a recommended dependency and the FSL-free engines the defaults. The FSL engines are disabled in the preferences when FSL is not installed, and stored FSL engine choices fall back to the default.

#### Fixed

- Without the FSL XTRACT data, the tracts supported by the dipy tractography engine are no longer removed from the DTI preferences.
- niimath-based nodes always write compressed `.nii.gz` images, also when the FSL environment (`FSLOUTPUTTYPE`) is not set.
- License consent preparation no longer repeats dependency detection on the GUI thread and keeps the interface responsive while license texts are resolved.
- Changing the DTI CPU allocation no longer invalidates cached Eddy results.
- DTI: FSL `eddy`'s rotated b-vectors are now used for tensor fitting (dtifit)
  and bedpostx. Previously the unrotated vectors were used; rotating the volumes
  without reorienting the gradients biased FA, MD and tractography in proportion
  to subject motion (Leemans & Jones 2009). Re-processing a subject will not
  reproduce results from earlier versions.

### [0.2.1.1] - 2026-08-08

#### Hotfix

* Added a `filelock` version constraint to avoid a multiprocessing issue with Nipype 1.10.0.

#### Changed

* Minor layout improvements in `ToolReferenceWindow`.

### [0.2.1] - 2026-07-20

#### Changed

- Improved linear and nonlinear registration output handling by explicitly applying the computed transforms to unstripped images
- DTI preprocessing registration now uses the brain-extracted reference image
- Improved the readability of DICOM series labels and automatic series-association prompts
- Updated `dicom-sequence-classifier` from `1.0.4` to `1.0.5`

#### Fixed

- False multiple-instance detection by validating process creation time in addition to PID
- FLIRT registration now searches both negative and positive x-axis ranges
- N4 bias correction now handles minimal geometric differences between input-image and mask origins while rejecting larger mismatches

### [0.2] - 2026-03-14

#### Added

- **Venous CT Workflow**
- **Stereo-EEG CT Workflow**
- **Resting State fMRI Workflow**
- information window for running and completed workflow steps
- FreeSurfer Synth tools support

#### Changed

- **Venous MRA** and **Task fMRI** now flagged as optional analyses
- Recon-all core management improved
- Preferences window layout improved

#### Fixed

- Result tab now correctly refreshes the file list after workflow fresh execution.

### [0.1.5.2] - 2025-12-11

#### Changed

- **Flat1 Workflow**: outliers removal improvement.

#### Changed

- **Python requirement**: from >=3.7 to >=3.10.
- **nibabel requirement**: from <=5.3.0 to >=5.3.0,<6.
- **fMRI Delete Start Volumes preference**: from range[1,500] to range[0,500].
- DICON scan improved

### [0.1.5.1] - 2025-12-04

#### Changed

- **Python requirement**: from >=3.7 to >=3.10.
- **nibabel requirement**: from <=5.3.0 to >=5.3.0,<6.
- **fMRI Delete Start Volumes preference**: from range[1,500] to range[0,500].

### [0.1.5] - 2025-11-22

#### Added

- **ImageType series error shown after DICOM folder scan**: the error is shown only if no valid series are found into the folder and list all the wrong ImageType found in the path.
- **Shutdown SWANe at Analysis End**: if enabled, it turns off the OS when SWANe ends all the started analyses without error.
- **Automatic series classification**: if enabled, activates a new module that automatically classifies subject series at their load in Data Load Subtab.
- **SWANe Assistant GPTs link**: added a button into the client footer that links to SWANe Assistant GPTs.
- **UBUNTU ONLY**: check xclip dependency existance.

#### Changed

- multiframe series reading improved
- networkx version requisites
- nipype version requisites
- using typing package to ensure SWANe compatibility with older python versions

#### Fixed

- Minor bug in subject workflow status tracing.

### [0.1.4] - 2025-02-18

#### Added

- setuptools dependency for GPUtils Series
- fMRI cluster outputs with different thresholds (3.1, 5.1, 7.1)
- Threshold for 3DSlicer DTI Tract in Workflow Preferences
- Threshold (%) for 3DSlicer Vein Segment in Workflow Preferences
- Cost Function for ASL/PET in Workflow Preferences

#### Changed

- PySide6 QSpinBox & QDoubleSpinBox implementation in App & Workflow Preferences

### [0.1.3] - 2024-11-28

#### Fixed

- PySide6 ThreadPool handing bug on python3.10

### [0.1.2] - 2024-11-25

#### Added

- Multiframe Series reading function

#### Changed

- FLAT1 Outliers Mask restored
- DICOM Tree analyze worker improved

#### Fixed

- fMRI Task names conflict in nypipe command
- numpy >= 2 conflict with nypipe: numpy version forced to < 2 waiting for nypipe upgrade

### [0.1.1] - 2024-10-18

#### Added

- Mail Settings for mail report at the workflow completion
- 2D Cor T2 workflow (in Optional Series)
- Unbetted series saved into workflow results
- New dependency checks in Home

#### Changed

- Various python packages dependency requirement updated
- FSL robustfov for neck cropping
- 3D Slicer **setMasterVolumeNode** replaced with **setSourceVolumeNode**
- pydicom **read_file** replaced with **dcmread**
- ASL Flirt cost function param **Mutual Information** replaced with **Normalized Mutual Information**

#### Fixed

- SWANe compatibility with FSL ver. >= 7.0.0
- fMRI Task B name setting field unlocked for rArB block design
- Various typos
