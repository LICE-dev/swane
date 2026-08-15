# Workflow settings-matrix + snapshots

This area builds **every SWANe workflow factory under a matrix of configuration
settings** and records each resulting graph as a deterministic, human-readable
*golden snapshot*. It answers the question "what does SWANe actually assemble
for this combination of preferences?" — including the **CUDA on/off** axis — and
gives a reviewer plain-text artifacts to check by hand.

Nothing here *executes* FSL / FreeSurfer / Slicer / dcm2niix and no DICOM is
read: the builders only assemble a nipype graph, and the "DICOM" input is an
empty folder whose path is merely stored on the conversion node.

**Reference box = fully equipped.** The intended baseline is a machine with all
neuroimaging tools *and their data* installed (FSL + MNI templates + XTRACT
protocols): a handful of scenarios read those data files at construction
(`dti_preproc/new_eddy_tractography`, `tractography/cst_real_graph`,
`fmri_resting_state/aroma_on`) and are exercised there. On a box that lacks a
given data file (or FSL entirely) those scenarios **skip** — never fail — via
`conftest.require_fsl_data`, so the tool-free majority still runs green on a
plain Windows/CI box. The golden snapshots for the data-gated scenarios are
generated on an equipped box and committed (FSL paths rewritten to `<FSLDIR>`).

For the complementary *execution* work (real dcm2niix conversion of the
`paziente 0` series, FSL/FreeSurfer/Slicer runs, GPU `use_cuda`/`use_gpu`
equivalence), see `../TODO_dicom.md`.

## Layout

```
matrix/
├── conftest.py                # graph_snapshot fixture (compare / update)
├── _snapshot.py               # graph -> deterministic text renderer
├── generate_report.py         # build the MATRIX.md + HTML reports from snapshots
├── MATRIX.md                  # versioned overview rendered by GitHub (generated)
├── test_<workflow>_matrix.py  # one module per workflow factory
└── snapshots/
    └── <workflow>/<scenario>.txt   # committed golden files, reviewed by hand
```

Two reports are generated from the snapshots (never edited by hand):
`MATRIX.md` is a deterministic, committed overview GitHub renders as living
documentation (each scenario links to its golden `.txt`); `matrix_report.html`
is a richer local view that embeds the full snapshots and is git-ignored.

The construction fixtures (`subject_config`, `global_config`, `make_input_dir`,
`isolated_home`) are inherited from `../conftest.py` and shared with the
structural `../workflows/` tests.

## What each module covers

| Module | Builder | Main axes swept |
|--------|---------|-----------------|
| `test_ref_matrix` | `ref_workflow` (T13D) | BET vs SynthStrip, bias reduction, bet threshold |
| `test_linear_reg_matrix` | `linear_reg_workflow` (FLAIR3D/T2/MDC/2D) | volumetric, partial coverage, bias, Synth backend |
| `test_nonlinear_reg_matrix` | `nonlinear_reg_workflow` | FSL vs SynthMorph backend |
| `test_freesurfer_matrix` | `freesurfer_workflow` | step enum, hippo/amygdala, Synth recon-all |
| `test_func_map_matrix` | `func_map_workflow` (ASL/PET) | FreeSurfer step × asymmetry index |
| `test_venous_mr_matrix` | `venous_mr_workflow` | single/two series, detection mode, Synth backend |
| `test_venous_ct_matrix` | `venous_ct_workflow` | contrast series count, skull threshold |
| `test_seeg_ct_matrix` | `seeg_ct_workflow` | electrode threshold, erosion kernel |
| `test_flat1_matrix` | `flat1_workflow` | FSL vs SynthMorph backend |
| `test_dti_matrix` | `dti_preproc_workflow` | **CUDA on/off**, eddy backend, CPU core-limit, tractography (needs FSL data) |
| `test_fmri_preproc_matrix` | `fMRI_preproc_workflow` | slice timing, volume trimming |
| `test_fmri_resting_state_matrix` | `fMRI_resting_state_workflow` | MELODIC dim/threshold; AROMA on (needs FSL data) |
| `test_tractography_matrix` | `tractography_workflow` | real cst graph (needs XTRACT data) + unknown-name guard |
| `test_fmri_task_matrix` | `fMRI_task_workflow` | block design (RARA vs RARB) |

## Determinism

Golden files must match regardless of machine or OS, so the renderer:

* sorts nodes, input traits and connections;
* rewrites volatile absolute paths (`tmp_path`, home, `swane_supplement`,
  `$FSLDIR`, `site-packages`, cwd) to stable `<TOKEN>`s and normalises `\` to `/`;
* reduces resolved executables (e.g. the bundled `dcm2niix` binary) to a stem so
  neither the install path nor the Windows `.exe` suffix leaks.

Host-dependent values are kept out of snapshots on purpose: CPU thread counts are
pinned with an explicit `max_cpu` and the `SOFT_CAP`/`HARD_CAP` core-limit modes,
while `NO_LIMIT` (which falls back to `cpu_count()`) is covered by a plain
assertion instead of a snapshot.

## Running

### Prerequisites — no DICOM; neuroimaging tools optional

These tests need **no DICOM data**: each test creates its own empty temporary
"DICOM" folder. They also run without any **FSL / FreeSurfer / Slicer / dcm2niix
executable** — the few data-gated scenarios simply *skip* when the FSL data they
read is absent (see above); everything else runs. The only requirement is the
Python test environment:

```bash
pip install -e . pytest pytest-qt pytest-xdist
```

`pip install -e .` pulls in the `dcm2niix` **Python package** (a bundled binary),
which the workflow modules import at load time. Without it the `workflows/` and
`matrix/` tests do not even *collect* — this is the one and only gotcha.

To exercise (not just skip) the data-gated scenarios, run on a box with a real
FSL install whose `$FSLDIR/data` includes the MNI standard templates and the
XTRACT protocol data.

> The real `paziente 0` DICOM under the repo-root `dicom/` folder is **only** for
> the future execution/integration tests (real conversion + FSL/FreeSurfer/Slicer,
> marked `heavy`/`requires_*`). It is git-ignored and irrelevant to this suite —
> see `../TODO_dicom.md`.

### Commands

```bash
# compare against the committed golden snapshots (regression guard)
pytest swane/tests/nipype_pipeline/matrix

# regenerate the golden snapshots after an intentional change, then review the diff
SWANE_SNAPSHOT_UPDATE=1 pytest swane/tests/nipype_pipeline/matrix

# regenerate the reports (MATRIX.md + local HTML) after refreshing snapshots
python swane/tests/nipype_pipeline/matrix/generate_report.py
```

## Adding a workflow / scenario

1. Add a named scenario to the relevant `SCENARIOS` dict (or a new
   `test_<workflow>_matrix.py` following the same pattern).
2. Generate its golden file with `SWANE_SNAPSHOT_UPDATE=1`.
3. **Read the generated `snapshots/<workflow>/<scenario>.txt` by hand** and
   confirm the nodes, commands, flags and wiring are what you expect — the
   golden file is only as trustworthy as its first review.
4. Regenerate the reports (`python .../matrix/generate_report.py`) so `MATRIX.md`
   stays in sync, and commit the test, the golden file and `MATRIX.md` together.
