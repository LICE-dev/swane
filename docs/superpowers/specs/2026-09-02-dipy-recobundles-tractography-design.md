# dipy + RecoBundles tractography engine — design

Date: 2026-09-02
Branch: `claude/dipy-recobundles`
Status: design approved, pending implementation plan

## Goal

Add a second tractography engine to SWANe, based on `dipy` reconstruction plus
RecoBundles bundle recognition, selectable exactly the way the brain-extraction
and registration engines already are. The user-facing tract list must stay the
same across engines, with per-engine availability expressed through the existing
`pref_requirement` gating rather than through two different screens.

The dipy engine must not invoke FSL in any of its own steps. Steps that already
abstract an engine (brain extraction, registration) keep honouring the user's
global choice, FSL included.

## Non-goals

- Making SWANe FSL-free overall. FSL remains a hard global requirement today
  (`Subject.can_generate_workflow()` requires `is_fsl()`), and `ref_workflow`
  still uses FSL `RobustFOV` and `ApplyMask`. This change makes the *tractography
  path* FSL-free; it does not relax the global gate.
- Windows support. See "Strategic implications" below.
- Replacing or changing the existing FSL/XTRACT path in any way.

## Context: what the current pipeline does

`dti_preproc_workflow` runs dcm2niix → `ForceOrient` → b0 extraction →
deskull → FSL `eddy` → `dtifit` → diffusion↔reference registration → `bedpostx`.
`tractography_workflow` then runs one instance per tract, using XTRACT protocol
masks warped from MNI and `probtrackx2` in reference space.

Results land in `<Result_DIR>/dti/` as `r-<tract>_<side>.nii.gz` (a connectivity
density volume) plus `r-<tract>_<side>_waytotal`. `slicer_script_result.main_tract`
loads the volume and thresholds it at `waytotal * tractography_threshold` to build
a segmentation.

### Verified facts about the current state

- `ForceOrient` is pure nibabel, not FSL. It is reusable in the dipy branch.
- The real `TRACTS` dictionary has **16** entries, not 20. XTRACT ships `ac`,
  `fma`, `fmi` and `mcp` without `_l`/`_r` suffixes, and the `split[0][:-2]`
  parser in `preference_list.py` drops them at import. Confirmed against the
  local FSL 6.x `xtract_data/HUMAN` directory.
- The current pipeline is **probabilistic** (bedpostx estimates distributions on
  phi/theta; probtrackx2 samples them).
- Slicer here has no SlicerDMRI extension, so `.trk` is not natively loadable —
  but SWANe already installs Slicer extensions non-interactively via
  `DependencyManager.SLICER_MODULES` and `slicer_script_module_install.py`.

## Decisions

### 1. Engine selection

New enum in `config_enums.py`:

```python
class TractographyEngine(Enum):
    FSL_XTRACT = "FSL (XTRACT/probtrackx2)"
    DIPY_RECOBUNDLES = "dipy (CSD + RecoBundles)"
```

Exposed as `GLOBAL_PREFERENCES[GlobalPrefCategoryList.SYNTH]["tractography_engine"]`,
default `FSL_XTRACT` so existing users see no behaviour change, with
`option_dependency` on a new `DependencyManager.is_dipy()` following the
`is_antspynet` pattern.

### 2. Preference gating in the DTI section

| Preference | FSL | dipy |
|---|---|---|
| `tractography`, the 16 tract checkboxes | active | active |
| `atr` `str` `cbd` `cbp` `cbt` | active | greyed, "no RecoBundles atlas counterpart" |
| `cingulum` (new) | greyed | active |
| `tractography_threshold`, `track_procs` | active | greyed |
| `old_eddy_correct` | active | greyed |
| `seed_density`, `max_angle`, `step_size` (new) | greyed | active |

### 3. Bundle mapping (verified against the downloaded atlas)

Atlas: `fetch_bundle_atlas_hcp842()` → `Atlas_80_Bundles`, ICBM 2009a, 649 MB.

Available and bilateral (10): `af`→AF, `ar`→AR, `cst`→CST, `fa`→**AST**,
`ifo`→IFOF, `ilf`→ILF, `mdlf`→MdLF, `or`→OR, `uf`→UF, `vof`→VOF.

`fa`→AST was verified empirically, not assumed: `AST_L` spans x[-56,-8],
y[-17,+47], z[-2,+71] — entirely frontal and supratentorial, i.e. the Aslant
tract. The spinothalamic tract is `STT` (z[-53,+1], brainstem). Likewise `CB` is
the **cerebellum** (y[-86,-31], z[-48,-4]), not a cingulum subdivision; the
cingulum in this atlas is only `C_L`/`C_R`.

Unavailable, greyed on dipy (5): `atr`, `str`, `cbd`, `cbp`, `cbt`.

Special case: `fx`. The atlas ships `F_L_R.trk` with both sides in one file; the
README states they are separable. Recognise once, then split by sign of x to
produce `fx_lh`/`fx_rh`, preserving the side contract. This is anatomically sound
for a paired structure and would **not** be acceptable for a commissure.

Implementation trap: the atlas contains a misspelled duplicate `IF0F_R.trk`
(digit zero) alongside `IFOF_R.trk`. Bundles must be addressed by explicit name,
never by glob.

### 4. Workflow structure

Two parallel pairs. `dti_preproc_workflow` and `tractography_workflow` are left
untouched bit-for-bit; `dipy_dti_preproc_workflow` and `dipy_bundle_workflow` are
added, and `MainWorkflow.launch_dti_analysis` branches on the enum. The ~5-node
shared head is duplicated rather than extracted, so the validated FSL path needs
no re-validation and the golden matrix snapshots do not churn.

### 5. Phase 1 — `dipy_dti_preproc_workflow`

```
CustomDcm2niix -> ForceOrient -> ExtractVolumes(b0) -> get_deskull_node   [shared]
  -> DipyDenoise (mppca, patch_radius=1)
  -> DipyMotionCorrection (dipy.align, + bvec rotation)
  -> DwiBiasCorrection (N4 on mean b0, field applied to all volumes)
  -> DipyTensorFit -> FA -> apply_registration_node -> outputnode.FA
  -> DipyCsdFit (auto_response_ssst, adaptive sh_order_max)
  -> DipyTracking (pft_tracking, CmcStoppingCriterion) -> outputnode.tractogram
```

Side branch: `DipyTissueClassifier` (HMRF on the T1 `reference_brain`) → 3 PVE
maps → `apply_registration_node` ref→diff. The PVE maps serve **two** purposes:
the CMC stopping criterion and PFT's reinitialisation of implausible streamlines.

Tracking runs in diffusion space (no DWI interpolation); streamlines are moved to
reference space with `transform_streamlines` and the affine already produced by
`dif2ref`. No FSL `.mat` is needed — that was a probtrackx requirement only.

**Preprocessing order** is denoise → Gibbs → motion → bias, per MRtrix3/QSIPrep
convention, because denoising assumes i.i.d. noise and any interpolation
correlates neighbouring voxels. Gibbs unringing is **excluded**: on the
partial-Fourier acquisitions common in clinical practice it can introduce
artifacts rather than remove them.

**Adaptive `sh_order_max`**, since lmax needs `(lmax+1)(lmax+2)/2` coefficients:

| Directions | lmax | Coefficients |
|---|---|---|
| ≥45 | 8 | 45 |
| ≥28 | 6 | 28 |
| ≥15 | 4 | 15 |
| ≥6 | 2 | 6 |

### 6. Phase 2 — `dipy_bundle_workflow`

One instance per selected tract, mirroring the current per-tract workflow:

```
inputnode(tractogram_in_atlas_space, atlas_dir)
  -> DipyRecoBundles(model_bundle=<ATLAS>_L | _R)     # one per side
  -> transform back to reference space
  -> outputnode.bundle_lh / bundle_rh   (.trk)
```

**The whole-brain SLR against the atlas must run once, in phase 1**, with the
aligned tractogram and the inverse transform saved. Doing it inside each bundle
workflow would repeat the most expensive part of RecoBundles once per tract —
the difference between minutes and hours across 10 tracts.

### 7. Result contract and Slicer

Results in `<Result_DIR>/dti/`:

| Engine | Per tract and side |
|---|---|
| FSL | `r-<tract>_<side>.nii.gz` + `r-<tract>_<side>_waytotal` *(unchanged)* |
| dipy | `r-<tract>_<side>.trk` |

`SlicerDMRI` is added to `DependencyManager.SLICER_MODULES`, reusing the existing
non-interactive installer. `main_tract` gains a branch: `.trk` present → load as
fiber bundles and skip thresholding entirely; `.nii.gz` present → current
behaviour, unchanged.

An earlier draft proposed a hand-written VTK PolyData writer, because dipy's
`save_vtk_streamlines` is a tripwire requiring `fury`/VTK (~100 MB). That was
**withdrawn**: SWANe already had the extension-install mechanism, which is
strictly better.

### 8. Dependencies, atlas, licensing

- `setup.py`: `dipy==1.12.0` (pulls `trx-python`, `tqdm`, `typer`, `deepdiff`).
- `DependencyManager.is_dipy()` / `check_dipy()`, on the `check_antspynet` model.
- `LicenseReference`: new `DIPY` entry (BSD 3-clause) in `TOOL_IDS` and
  `LICENSES`, plus `swane/licenses/dipy.txt`, accepted like the others, and a
  dipy row on the home screen.
- **The atlas is licensed separately**: CC BY 4.0, © Eleftherios Garyfallidis —
  a data licence with an attribution obligation, distinct from dipy's BSD. By
  decision it gets **no license-acceptance entry**; the CC BY obligation is met
  through `NOTICE.md` and `ToolReference` citations (Garyfallidis 2017 for
  RecoBundles, Yeh 2018 for the atlas).
- `ToolReference`: entries for the new dipy nodes, citing Tournier 2007 (CSD),
  Veraart 2016 (MP-PCA), Girard 2014 (PFT), Garyfallidis 2017, Yeh 2018.
- `strings.py` `node_names`: readable labels for every new node.
- **Atlas download is silent on first use** (revisited later). Node requirements:
  a file lock, because SWANe processes subjects in parallel and two workflows
  finding `~/.dipy` empty would both fetch 649 MB into the same directory; a
  readable failure when offline rather than an opaque nipype traceback; and
  cleanup of a partial directory on retry.

### 9. Concurrency and resources

Per the project direction, `CoreLimit.NO_LIMIT` and `SOFT_CAP` are being removed:
**new nodes implement HARD_CAP only**, and the new workflow factories therefore
do not take a `multicore_node_limit` parameter at all.

| Node | Parallelism source | `n_procs` | `use_cuda` |
|---|---|---|---|
| `DipyDenoise` (mppca) | none — serial in dipy | 1 | no |
| `DipyMotionCorrection` | **our own pool over volumes** | `max_cpu` | no |
| `DipyCsdFit` | `peaks_from_model(num_processes)` | `max_cpu` | no |
| `DipyTracking` | `pft_tracking(nbr_threads)` | `max_cpu` | no |
| `DipyTissueClassifier` (HMRF) | none | 1 | no |
| `DipyRecoBundles` | `recognize(num_threads)` | `max_cpu` | no |
| N4 on b0 | ITK `num_threads` (existing node) | `max_cpu` | no |

**No dipy node declares `use_cuda`**: dipy core has no GPU path. GPU tracking
lives in `dipy/GPUStreamlines` (`cuslines`), a separate non-PyPI package needing
CUDA-toolkit compilation. This is the one asymmetry that cannot be closed against
the FSL branch, which does use the GPU for eddy, bedpostx and probtrackx.

`_mem_gb` must be measured **per node in isolation**, because nipype runs each
node in its own process. Chained measurements are not usable for this.

### 10. Phantom

`GENERATOR_VERSION` `"8"` → `"9"` (invalidates the cache; full regeneration for
everyone). `dwi_directions` 6 → 30. In `tissue.py`, AF and OR corridors alongside
the existing CST, plus a background white-matter direction field derived from the
fsaverage WM mask; `render_dwi` in `sequences.py` moves from "only the CST is
anisotropic" to a tensor field across the whole WM.

This is required, not cosmetic: RecoBundles runs a whole-brain SLR against
`whole_brain_MNI.trk` *before* recognising individual bundles. A tractogram
consisting of a single CST corridor would register arbitrarily, so even the CST
would fail — not just AF and OR.

## Validation

### Oracles

Two real subjects in `~/test_swane/dipy_test/` (local only, never committed) that
exercise opposite regimes:

| | subj1 | subj2 |
|---|---|---|
| Directions | 15 | 64 |
| DWI | 256×256×52 | 144×144×60 |
| Voxel | 0.94×0.94×2.5 | 1.56×1.56×2.2 |
| Resulting lmax | 4 (at the limit) | 6–8 (comfortable) |

They exercise different branches of the adaptive-lmax code, which is why both are
needed.

### `DipyMotionCorrection` equivalence

Hand-parallelising this node requires proof of equivalence. Three layers:

1. **Reassembly by index** — unit test with mocked registration returning
   identifiable per-volume payloads *out of order*; assert volume *i* lands at
   position *i*. This is the likeliest and most silent parallelisation bug:
   scrambled volumes crash nothing, they just corrupt the tensor.
2. **bvec rotation** — `register_dwi_series` uses `gtab` only for `b0s_mask` and
   returns `(image, affine_array)`. **It never rotates the bvecs**; the caller
   must. Forgetting this yields no crash, only wrong fibre orientations. Unit
   test: apply a known rigid rotation, assert the rotated bvec matches the
   analytic expectation, b0 rows stay `[0,0,0]`, norms preserved.
3. **Serial-vs-parallel oracle** (`@pytest.mark.heavy`) — each volume is
   registered independently by a deterministic optimiser, so the two must agree
   **bit for bit**, provided BLAS thread counts match on both sides. Pin
   `OMP_NUM_THREADS=1` on both and assert exact equality; loosening the tolerance
   would mask real bugs. Plus cheap guards: output volume count equals input, and
   no volume is entirely zero (catches a silently failed worker).

Method: implement the serial version calling dipy first, behind the final node
interface, so the oracle has a green baseline before the parallel version exists.
Keep the serial path reachable as a permanent reference and fallback.

### Streamline-order reproducibility

dipy's docstring guarantees the same trajectory per seed coordinate for a fixed
`random_seed`, but with multiple threads the **order** of streamlines in the
output may vary between runs. Trajectories would be identical, file bytes would
not. Two runs at equal seed must be compared, since bit-reproducible results are
a stated SWANe value.

### Other coverage

- **Matrix**: new golden snapshots `test_dipy_dti_matrix.py` /
  `test_dipy_bundle_matrix.py`. The existing FSL snapshots must stay
  **unchanged** — that is the proof the "two parallel pairs" choice isolated the
  new branch.
- **Nodes**: fornix split; explicit exclusion of `IF0F_R.trk`; non-finite
  sanitisation before motion correction.
- **Preferences**: per-engine gating enables and disables the right entries.
- **Prerelease**: sweep on phantom v9 asserting recovery of af/cst/or.

## Measurements

Measured on subj1 (256×256×52×16, brain bbox 158×193×52, 667k voxels),
deterministic tracking, whole-brain seeding, synthetic gradients:

| Step | Time | Cores |
|---|---|---|
| Brain mask | 21 s | 1 |
| MP-PCA denoise | 423 s | 1 *(measured instantaneously)* |
| `motion_correction` | 753 s | 1 *(pending confirmation)* |
| CSD lmax=4 | 244 s | 1 *(pending confirmation)* |
| `deterministic_tracking` | 625 s | **4** — `nbr_threads=0` means all threads |
| HMRF | 97 s | 1 *(pending confirmation)* |
| **Total** | **2162 s (36 min)** | |

Peak RSS reached 7.0 GB during tracking, on an 11 GB machine, with 662,889
streamlines from 667,146 whole-brain seeds.

Two consequences: **seeding must be restricted to the WM PVE mask**, not the whole
brain — seeding CSF and cortex only produces streamlines to prune — and the
tractogram must be written as `.trx` (memory-mappable, and `trx-python` already
arrives with dipy) rather than accumulating a Python list.

Tracking offers no further parallel gain; `motion_correction` is the only genuine
candidate for hand-parallelisation, 753 s → roughly 190 s on four cores.

**Pending**: PFT timings on real gradients with WM seeding and `.trx` output, for
both subjects, and per-node isolated `_mem_gb`. PFT is heavier than deterministic
on both time and memory, so the numbers above are a floor, not an estimate.

## Accepted risk

With ~15 directions, CSD lmax=4 is exactly determined: 15 coefficients for 15
measurements. The global tractogram will be poor in crossing regions, precisely
where bedpostx with `n_fibres=2` currently holds up, and RecoBundles can only
recognise what the tractogram contains. The dipy branch may therefore be
**scientifically inferior** to the FSL branch on typical clinical data while
being perfectly correct as software.

PFT (probabilistic, anatomically constrained) was chosen partly to mitigate this:
it samples the fODF instead of following its maximum, recovering branches that
deterministic tracking systematically drops in crossings, and it matches the
probabilistic nature of the existing FSL path.

The user has explicitly accepted this risk and chosen to proceed and test
afterwards. It is recorded here as an accepted risk, not a resolved question.

## Strategic implications

Everything selected has Windows support: `dipy`, `antspyx`, `dcm2niix`,
`tensorflow` and `PySide6` ship `win_amd64` wheels; `nibabel` and `nipype` ship
universal wheels; `antspynet` is sdist-only but pure Python. FSL and FreeSurfer
have no native Windows builds, so **the dipy branch is the only tractography path
that could ever run on native Windows** — a direct consequence of the FSL-free
constraint.

It is a first brick, not the finish line. `ref_workflow` still imports FSL
`RobustFOV` and `ApplyMask`, and `can_generate_workflow()` still hard-requires
FSL. Both FSL calls are shallow — a field-of-view crop and a mask multiply, both
trivial with nibabel/numpy or antspyx — so that blocker is far less deep than it
looks, if and when it is addressed.

## Corrections made during design

Recorded because the method matters as much as the result. Four claims were made
and then disproved by measurement or by the user:

1. An OOM during full-resolution MP-PCA — **never happened**; a wait loop broken
   by the sandbox was misread as a fact about the data.
2. A hand-written VTK writer — **unnecessary**; SWANe already installs Slicer
   extensions, so SlicerDMRI handles `.trk` natively.
3. `AST` read as the anterior spinothalamic tract — **wrong**; it is the Aslant
   tract, confirmed by its MNI coordinate extent.
4. "Everything ran on one core" — **wrong**; `ps -o %cpu` reports a lifetime
   average, and tracking had been using all four cores via `nbr_threads=0`.

Numbers entering this spec are measured. Those not yet measured are marked
pending rather than rounded into certainties.
