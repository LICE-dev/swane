# Installing SWANe with the installer (Ubuntu/macOS)

The installer builds a complete, isolated SWANe environment with a single command.
You do not need Python beforehand: the installer creates a conda environment with Python 3.12.

## 1. Run it

From a terminal:

```
curl -fsSL https://raw.githubusercontent.com/LICE-dev/swane/main/installer/install_swane.sh | bash
```

> Run it from a terminal where **no** conda environment whose name starts with `swane` (e.g. `swane-env`) is active:
> otherwise it stops before changing anything and asks you to run `conda deactivate`.
> On a Mac, do not run it from a terminal running under Rosetta.

## 2. What it asks

Before changing anything the installer asks two questions:

1. **Which conda to use**: it lists every conda it finds (FSL's own excluded) plus *Download and install a new Miniforge*.
   Type `yes` for the first one or the number of another; for a new Miniforge it then asks where to install it.
2. **Where to put the SWANe environments**: it proposes the environments folder of the chosen conda; type `yes` or another folder.

Then, depending on your system:

- **FSL (optional)**: the installer shows the link to the FSL license (free for non-commercial use only) and installs FSL only if you type `yes`.
- **Ubuntu system packages**: on Linux with `apt`, it asks once for `sudo` to install the packages needed by 3D Slicer, `tcsh`, `unzip` and the `en_US.UTF-8` locale.
  If you answer no, nothing runs with `sudo` and the final summary lists the commands to run yourself.

## 3. What it installs

- **`swane-env`**: a conda environment with Python 3.12, SWANe and all its Python dependencies (dcm2niix included),
  Graphviz if not already available and, on Intel Macs, TensorFlow from conda-forge.
- **`swane-fsl`** (optional): a minimal FSL in its own conda environment, active only while `swane-env` is active.
- **`swane` launcher** in `~/.local/bin` (the folder is added to your `PATH` in your shell startup file if missing).

## 4. Options

Options are passed after `bash -s --`, for example:

```
curl -fsSL https://raw.githubusercontent.com/LICE-dev/swane/main/installer/install_swane.sh | bash -s -- --yes --no-fsl
```

| Option | Effect |
| --- | --- |
| `--yes` | Answer yes to every prompt except the FSL license (uses the proposed conda and folder). |
| `--conda-root DIR` | Use the conda installed in `DIR`, without asking. |
| `--accept-fsl-license` | Accept the FSL license without prompting. |
| `--no-fsl` | Do not install or configure FSL. |
| `--miniforge-prefix DIR` | Install Miniforge in `DIR` and use it, without asking. |
| `--install-dir DIR` | Folder for the `swane-env` and `swane-fsl` environments, without asking. |
| `-h`, `--help` | Show the help and exit. |

## 5. Launch

When it finishes, **open a new terminal** and run:

```
swane
```

You do not need to activate `swane-env`: the launcher does it for you.

## 6. What you still have to install by hand

The installer does **not** install the following programs. Install them separately, before or after SWANe,
following the [Dependencies Guides](https://github.com/LICE-dev/swane/wiki/04-Dependencies-Guides).

| Software | Recommended version | What it is used for |
| --- | --- | --- |
| [FreeSurfer](https://surfer.nmr.mgh.harvard.edu/fswiki/rel7downloads#A8.2.0_release/) | 8.2.0 | Surface-based analyses and segmentations |
| MATLAB Runtime for FreeSurfer (free) | the one FreeSurfer asks for (run `./checkMCR.sh` in `freesurfer/bin`) | Hippocampal/amygdala and brainstem segmentation modules |
| [3D Slicer](https://download.slicer.org/) | 5.12.4 | Viewing the results |

The SWANe Home tab shows which dependencies were detected.
