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
| `--yes` | Answer yes to every prompt except the FSL licence (including the Linux `sudo` question). |
| `--accept-fsl-license` | Accept the FSL licence without prompting. |
| `--no-fsl` | Do not install or configure FSL (an FSL already wired into `swane-env` is kept). |
| `--swane-spec SPEC` | What to install as SWANe, passed verbatim to `pip install -U` (default: `swane`, the latest release on PyPI). SWANe 0.2.5 or newer is required. Accepted forms: a PyPI version (`swane==0.2.5`), a local checkout (`/path/to/swane`), a git URL (`git+https://github.com/LICE-dev/swane.git@<branch>`), a wheel file (`/path/to/swane-0.2.5-py3-none-any.whl`). |
| `--miniforge-prefix DIR` | Where to install Miniforge when no conda is found (default: `~/miniforge3`). |
| `--install-dir DIR` | Directory for the conda environments the installer creates: `DIR/swane-env` and, when FSL is installed, `DIR/swane-fsl` (default: the environments directory of conda). With this option only `DIR` is searched: environments already in conda's default location are left alone, a rerun without the option keeps the directory of the previous run (the one the `swane` launcher points to), and a different `DIR` creates new environments there, leaving the old ones untouched. |
| `-h`, `--help` | Show the help and exit. |

What it installs and where:
* conda: your existing one, or Miniforge in `~/miniforge3` (a fixed Miniforge release, checked against the SHA-256 written in the installer; no `conda init`, `~/.condarc` untouched, the conda `defaults` channel is never used);
* `swane-env`: Python 3.12, SWANe from PyPI (or `--swane-spec`) with its pip dependencies (dcm2niix included), Graphviz only when no `dot` is already available, and TensorFlow from conda-forge on Intel Macs;
* `swane-fsl` (optional): a minimal FSL, the oldest release supported by SWANe, in its own conda environment, with FSL's command wrappers in `$FSLDIR/share/fsl/bin`. FSL is wired into `swane-env` only through its activation hook, and only while `swane-env` is active: it sets `FSLDIR` and `FSLOUTPUTTYPE`, and makes sure `$FSLDIR/share/fsl/bin` comes before the `bin` of `swane-env` on `PATH` (never `$FSLDIR/bin`, which holds a whole conda environment with its own `python`). If your shell already has that entry ahead of `swane-env`, it is left as it is; otherwise the hook puts it first (a copy, when your shell has it further down). Nothing else on your `PATH` is changed. Deactivation removes only the entry the hook added and restores both variables. If you activate `swane-env` by hand (`conda activate swane-env`), run `conda deactivate` before activating another environment in that shell: otherwise FSL's wrappers stay on its `PATH`. An FSL already installed is reused instead when it is recent enough and has those wrappers (`bet`, `flirt` and `fsl-cluster` in `$FSLDIR/share/fsl/bin`);
* on Linux with `apt`, the system packages needed by 3D Slicer (plus `tcsh` and `unzip`, which FreeSurfer's `recon-all` and `fs_install_mcr` need) and the `en_US.UTF-8` locale. These are the only steps that use `sudo`, and the installer asks once before running them, listing what will run (`apt-get update` and `apt-get install`; `locale-gen en_US.UTF-8` only when the locale is missing). If you answer no, nothing runs with `sudo` and the final summary lists the commands to run yourself; when everything is already installed, nothing is asked. The installer never edits files under `/etc`: if `locale-gen` does not make the locale available (on Debian it generates only the locales enabled in the system's configuration), enable `en_US.UTF-8` in your system's locale configuration yourself. Without `apt` (or without `sudo`) it only prints what to install. A failure only prints a warning;
* `~/.local/bin/swane`, the launcher (on Linux it starts SWANe with `QT_QPA_PLATFORM=xcb`, i.e. X11 or XWayland, unless you set `QT_QPA_PLATFORM` yourself; no shell startup file is changed for this), and, when `~/.local/bin` is not on your `PATH`, a block delimited by `# >>> SWANe installer >>>` in one startup file of your shell: `~/.zshrc` for zsh, `~/.bashrc` for bash on Linux, `~/.bash_profile` for bash on macOS (or your existing `~/.bash_login` or `~/.profile` when there is no `~/.bash_profile`), `~/.profile` for sh/dash. An existing `~/.local/bin/swane` not written by the installer (e.g. from an old `pip install --user swane`) is first moved to `~/.local/bin/swane.bk` (or `swane.bk.1`, `swane.bk.2`, ...), and the summary names it. No other file is changed. Open a new terminal, then run `swane` (or run the launcher by its full path, printed at the end).

FreeSurfer, the MATLAB Runtime and 3D Slicer are not installed by the installer: install them separately (see [Optional Dependencies](#optional-dependencies) and the [Wiki](https://github.com/LICE-dev/swane/wiki)).

Every prompt is read from the terminal, so the command also works through `curl | bash`. Running the installer again updates the existing installation. Run it from a shell where no conda environment whose name starts with `swane` (`swane-env`, `swane-fsl`, ...) is active, not even one stacked below another: otherwise it stops before changing anything and asks you to run `conda deactivate` until none is active (or to open a new terminal).

> [!NOTE]
FSL is free for non-commercial use only, under its own licence (https://fsl.fmrib.ox.ac.uk/fsl/docs/license.html): installing it means accepting that licence. Before installing FSL the installer says so and links the licence, and it installs FSL only if you type `yes`. `--yes` does not accept the FSL licence: use `--accept-fsl-license` (or `--no-fsl` to skip FSL).

To remove everything the installer created, use the conda printed on the `SWANe installer: conda` line of the summary (here the default Miniforge one):
```
~/miniforge3/bin/conda env remove -n swane-env
~/miniforge3/bin/conda env remove -n swane-fsl
rm ~/.local/bin/swane
rm -f ~/.local/share/applications/swane.desktop ~/.local/share/swane/swane-launcher.sh
```
(if you used `--install-dir DIR`, remove them by prefix instead: `conda env remove -p DIR/swane-env` and `conda env remove -p DIR/swane-fsl`) then delete the block from `# >>> SWANe installer >>>` to `# <<< SWANe installer <<<` in your shell's startup file (`~/.zshrc`, `~/.bashrc`, `~/.bash_profile`, `~/.bash_login` or `~/.profile`) and, if you no longer need it, the Miniforge directory (`~/miniforge3`).

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
To update a SWANe installation created with the quick installer, run the installer command again:
```
curl -fsSL https://raw.githubusercontent.com/LICE-dev/swane/main/installer/install_swane.sh | bash
```

For manual installations:
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

### [0.3.1] - Unreleased

#### Added

- **Experimental native Windows support**: SWANe can be installed on Windows 10/11 with pip and run with the processing engines that do not need FSL and FreeSurfer (see [SWANe on Windows](https://github.com/LICE-dev/swane/wiki/05-SWANe-on-Windows)).

#### Changed

- **FSL** is now a **recommended** dependency: SWANe runs all the analyses except the Resting State fMRI with the new default processing engines, which do not need FSL. The FSL engines can still be selected when FSL is installed; a stored FSL engine choice falls back to the default if FSL is not detected.
- **New default processing engines**: ANTs (antspynet) for brain extraction, dipy (CSD + RecoBundles) for tractography, ANTs (antspyx Atropos) for tissue segmentation and Python (nilearn/scikit-learn) for task fMRI. Registration still runs with ANTs (antspyx).
- **Resting State fMRI** requires FSL: without FSL the Resting State fMRI optional series cannot be enabled.

### [0.3] - Unreleased

#### Added

- **SWANe installer** for Ubuntu and macOS: a single command creates a dedicated conda environment (`swane-env`) with Python 3.12 and SWANe, optionally installs a minimal FSL, installs the Ubuntu system packages and adds a `swane` launcher. It is now the recommended installation method (see [Getting Started](https://github.com/LICE-dev/swane/wiki/03-Getting-Started#quick-install-ubuntumacos)).
- **Processing engines**: the former *Synth Tools* section of the Application Settings is now called **Processing engines** and lets the user choose the tool used for each processing step:
  - **Brain extraction engine**: FSL BET (default), ANTs (antspynet) or FreeSurfer SynthStrip;
  - **Registration engine**: ANTs (antspyx, default), FSL (FLIRT/FNIRT) or FreeSurfer SynthMorph;
  - **Tractography engine**: FSL (XTRACT/probtrackx2, default) or dipy (CSD + RecoBundles, experimental);
  - **Segmentation engine**: FSL (FAST, default) or ANTs (antspyx Atropos);
  - **Task fMRI engine**: FSL (FEAT, default) or Python (nilearn/scikit-learn, experimental).
- **ANTs registration**: linear and nonlinear registrations run by default with ANTs (antspyx), for every workflow.
- **antspynet brain extraction** as an alternative to FSL BET, with a new *antspynet brain-extraction threshold* workflow preference.
- **dipy tractography engine** (experimental, untested): constrained spherical deconvolution, probabilistic tracking and bundle recognition with RecoBundles and the HCP842 bundle atlas. New DTI preferences: *Cingulum*, *Seed density for tractography*, *Maximum tracking angle*, *Tracking step size*. Results are exported as streamline bundles; bundles poorly matched to the atlas are flagged as **(LOW CONFIDENCE)** in 3D Slicer.
- **ANTs Atropos tissue segmentation** as an alternative to FSL FAST. The tissue segmentation is computed once on the 3D T1w and shared by the analyses that need it.
- **Python task fMRI engine** (nilearn/scikit-learn, experimental, untested) as an alternative to FSL FEAT.
- **FreeSurfer analysis step** workflow preference: *Disabled*, *SynthSeg Cortical Parcellation only*, *Surfaces + Cortical Parcellation*, *Complete Recon-all*.
- **SynthSeg fast mode** workflow preference.
- **Limit Synth tools CPU cores** application setting.
- **Estimated RAM allocation per subject** and **Enable resource monitor** application settings.
- **Third-party license consent**: at the first launch, and whenever the version of a detected tool changes, SWANe shows the licenses of the external tools (FSL, FreeSurfer, 3D Slicer, dcm2niix, antspyx, antspynet, dipy) and requires their acceptance.
- **Home tab**: each detected dependency shows a link to its license, and a new **Atlases** column lists the atlases and templates used by SWANe with their licenses.
- **Resting State fMRI**: the independent component time courses are saved as `ica_mix` and shown in 3D Slicer next to the component maps.
- **Kurtosis** venous volume detection mode for Venous MRA, now the default.
- Progress messages while the processing modules load and while templates, antspynet models and the dipy atlas are downloaded at workflow generation.
- SWANe icon in the Linux taskbar/dock and Linux desktop entry.
- Link to the FreeSurfer recon-all log in the subject log folder.

#### Changed

- **Python requirement**: from >=3.10 to >=3.12.
- **FSL requirement**: from >=6.0.6 to >=6.0.7.8. FSL remains a mandatory dependency: in the next releases it will be possible to choose directly whether to use SWANe with or without FSL.
- **dcm2niix** and **niimath** are now installed automatically as Python packages together with SWANe: a separate dcm2niix installation is no longer needed.
- Image maths steps now run with niimath instead of fslmaths.
- **Nipype** updated to 1.12; other Python package requirements updated.
- The MNI and symmetric atlases are now downloaded from TemplateFlow at the first workflow generation; the `swane_supplement` package is no longer needed.
- Bias field correction of the reference image with ANTs N4.
- **Configuration Wizard** redesigned: the user chooses the share of the computer SWANe can use (Light, Balanced, High) and how many subjects can be analysed at the same time, then the processing engines, the GPU acceleration and the FreeSurfer outputs.
- All the subject tabs together cannot use more than 90% of the RAM; the number of parallel subjects is also limited by the CPU cores.
- ANTs registration RAM requirement lowered to 4 GB.
- **Resting State fMRI** always runs on FSL MELODIC. The *Melodic dimensionality* preference is renamed **Independent Components to estimate** (existing configurations are migrated automatically).
- **Resting State fMRI with ICA-AROMA**: decomposition and denoising use the data before the temporal high-pass filter, which is applied after denoising.
- Venous CT and Stereo-EEG CT registrations follow the selected registration engine.
- *FLIRT between modalities cost function* (ASL/PET) is used only with the FSL registration engine.
- Preferences that cannot be used with the selected engines are hidden or disabled, with a tooltip explaining why.
- Faster startup: dependency checks and processing modules are loaded in background.
- The 3D Slicer installation is checked again at every startup.

#### Removed

- *CPU management for multicore steps* and *Exclude FreeSurfer Synth tools* application settings, replaced by the processing engine choices and the *Limit Synth tools CPU cores* setting.
- fsaverage atlas references.

#### Fixed

- DTI: the b-vectors rotated by FSL `eddy` are now used by `dtifit` and `bedpostx`. Re-processing a subject will not reproduce the results of previous versions.
- Changing the DTI CPU allocation no longer invalidates the cached Eddy results.
- ASL/PET surface sampling no longer starts before recon-all completes.
- Resting state model order estimation.
- IC time course viewer with a single independent component.
- Occasional 3D Slicer process hang.
- Preference wizard window placement and FreeSurfer Synth checkbox availability on low-RAM computers.

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
