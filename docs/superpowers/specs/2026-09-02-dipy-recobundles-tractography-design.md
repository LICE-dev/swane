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
- Replacing or restructuring the existing FSL/XTRACT path. One targeted
  scientific fix to it *is* in scope: the rotated-bvec bug, section 12.

## Data handling — nothing but conclusions is committed

The oracles in this design run on **real subject data**. That data, and
everything derived from it, stays outside the repository. Only conclusions —
numbers, decisions, rationale, and the code they justify — are ever committed.

Stays local, under `~/test_swane/dipy_test/`, never added to git:

- the two real subjects (`dti.nii.gz`, `dti.bval`, `dti.bvec`, `t1.nii.gz`);
- the 649 MB HCP842 atlas, fetched into a local `DIPY_HOME` rather than a shared
  or repository path;
- every intermediate artefact: `.npy` denoise caches, `.trx`/`.trk` tractograms,
  PVE maps, probe scripts and their logs;
- any per-subject oracle output, including screenshots or renderings.

What may enter the repository:

- aggregate timings, memory figures, streamline counts and direction counts;
- the design decisions those measurements justify;
- synthetic fixtures only — the phantom generator produces its own data and never
  embeds anything subject-derived.

This is not a precaution specific to this change: `CLAUDE.md` forbids adding real
subject data, identifiers, private DICOM metadata, local subject paths, execution
logs or generated results to source control, and requires synthetic or
de-identified fixtures. Recorded explicitly here because this design leans on real
data far more than previous ones, and because the temptation to commit "just the
oracle output" is exactly how such data leaks.

Practical check before any commit on this branch: `git diff --name-only` against
the base should list source, tests and docs only — never a path under
`test_swane`, and never a binary imaging format.

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
default **`DIPY_RECOBUNDLES`**, with `option_dependency` on a new
`DependencyManager.is_dipy()` following the `is_antspynet` pattern.

The dipy engine is the default for every install, existing ones included. That
needs no migration code: `force_pref_reset` is a hidden global preference already
defaulting to `"true"`, and when `__version__` differs from the stored
`last_swane_version` the saved configuration is **not read at all** — defaults are
loaded and written over it. Shipping this change under a new version therefore
resets every configuration, and the new default simply applies.

Two consequences follow from that and must be stated in the release notes rather
than discovered: the 649 MB atlas will be fetched on the first DTI run of
essentially every user, and DTI results change format from thresholded `.nii.gz`
density maps to `.trk` bundles. Re-running an old subject will not reproduce its
previous output.

### 2. Preference gating in the DTI section

| Preference | FSL | dipy |
|---|---|---|
| `tractography`, the 16 tract checkboxes | active | active |
| `atr` `str` `cbd` `cbp` `cbt` | active | greyed, "no RecoBundles atlas counterpart" |
| `cingulum` (new) | greyed | active |
| `tractography_threshold`, `track_procs` | active | greyed |
| `old_eddy_correct` | active | greyed, "dipy always uses nlmeans" |
| `seed_density`, `max_angle`, `step_size` (new) | greyed | active |

#### Denoising on dipy is always `nlmeans` + `estimate_sigma`

**Decided 2026-09-02, on the measurement in "subj2 — MP-PCA does not scale".**
MP-PCA is not offered at all: it costs >54 minutes on a routine 64-direction
acquisition, roughly 27x more core-time than on the 15-direction subject for the
same data volume, and slab parallelism cannot rescue it because OpenBLAS already
saturates the cores there. A denoiser that costs the better part of an hour on a
routine acquisition is not defensible as either a default or an option.

The dipy branch therefore has **no denoising choice**: `nlmeans` with
`estimate_sigma`, always. It exposes `num_threads` and genuinely parallelises.

Consequences, all simplifications:

- `old_eddy_correct` **stays exactly as it is today** — an FSL-only preference
  selecting `eddy_correct` over `eddy`. It is not renamed, not made shared, and
  not given a dipy meaning. It is simply greyed on the dipy engine, like
  `tractography_threshold`.
- No new preference key is introduced, so there is no persistence question and
  no migration discussion to have.
- The adaptive `patch_radius` rule is **dropped**: it existed only to keep MP-PCA
  valid as the volume count grew. `nlmeans` has no such constraint.
- The MP-PCA slab-parallelism work — a hand-written pool and its bit-for-bit
  equivalence oracle — is **dropped entirely**. `DipyMotionCorrection` remains
  the only node needing that treatment.

An earlier draft made this a shared `fast_dwi_preproc` boolean spanning both
engines, with MP-PCA as the dipy "full quality" arm. That arm was measured and
found impractical, which removed the reason for the preference to exist.

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
  -> DipyDenoise (nlmeans + estimate_sigma)
  -> DipyMotionCorrection (dipy.align + reorient_bvecs)
  -> DwiBiasCorrection (N4 on mean b0, field applied to all volumes)
  -> DipyTensorFit -> FA -> apply_registration_node -> outputnode.FA
  -> DipyCsdFit (auto_response_ssst, adaptive sh_order_max)
  -> DipyTracking (probabilistic_tracking, CmcStoppingCriterion)
  -> DipyAtlasSLR (whole-brain SLR against the atlas, once)
```

Phase 1 publishes three outputs consumed by phase 2: `outputnode.tractogram`
(native/reference space), `outputnode.tractogram_atlas` (aligned to the atlas by
the single SLR) and `outputnode.atlas2native` (the inverse transform used to
bring recognised bundles back).

Side branch: `DipyTissueClassifier` (HMRF on the T1 `reference_brain`) → 3 PVE
maps → `apply_registration_node` ref→diff. The PVE maps feed the CMC stopping
criterion (`CmcStoppingCriterion.from_pve`), which constrains where streamlines
terminate.

**Tracker: `probabilistic_tracking`, not `pft_tracking`.** The design originally
specified particle-filtering tractography, but Task 11 measured it unusable on
the 8 GB / 4-core target (see Measurements and Accepted risk): PFT's `sh=` path
runs single-core (its OpenMP pool never engages) and precomputes a dense full-FOV
PMF of `X·Y·Z·362·8` bytes = 9.19 GB on subj1. `probabilistic_tracking` keeps the
same `CmcStoppingCriterion(PVE)` — so tracking stays probabilistic (it samples
the fODF) and anatomically constrained — while being genuinely multi-core and
~1.2 GB; the only capability lost is PFT's particle-filtering reinitialisation.
Streamline length is bounded to 10..250 mm (literature; module constants, so the
graph and golden snapshots are unchanged).

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
  Coupé 2008 (nlmeans), Girard 2014 (PFT), Garyfallidis 2017, Yeh 2018.
- `strings.py` `node_names`: readable labels for every new node.
- **Atlas download is silent on first use** (revisited later). Node requirements:
  a file lock, because SWANe processes subjects in parallel and two workflows
  finding `~/.dipy` empty would both fetch 649 MB into the same directory; a
  readable failure when offline rather than an opaque nipype traceback; and
  cleanup of a partial directory on retry.

### 9. Nipype-derived disclaimers in the new nodes

Every new node (`DipyDenoise`, `DipyMotionCorrection`, `DwiBiasCorrection`,
`DipyTensorFit`, `DipyCsdFit`, `DipyTracking`, `DipyTissueClassifier`,
`DipyAtlasSLR`, `DipyRecoBundles`) defines a custom Nipype interface and
therefore extends Nipype classes. Each one must carry the established
disclaimers, in the exact existing form:

```python
# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-
...
# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
```

This applies even though the *computation* inside these nodes is dipy's and not
Nipype's: the interface scaffolding is derived from Nipype, and `NOTICE.md`
already records that dependency (Apache 2.0, © 2009-2016 Nipype developers). The
disclaimers are kept when a node is rewritten against a new backend, never
dropped because the body changed.

`NOTICE.md` additionally needs the new third-party entries: dipy (BSD 3-clause)
and the HCP842 atlas (CC BY 4.0, © Eleftherios Garyfallidis), the latter being
the attribution route chosen instead of a license-acceptance entry.

### 10. Concurrency and resources

Per the project direction, `CoreLimit.NO_LIMIT` and `SOFT_CAP` are being removed:
**new nodes implement HARD_CAP only**, and the new workflow factories therefore
do not take a `multicore_node_limit` parameter at all.

| Node | Parallelism source | `n_procs` | `use_cuda` |
|---|---|---|---|
| `DipyDenoise` (`nlmeans`) | `num_threads` | `max_cpu` | no |
| `DipyMotionCorrection` | **our own pool over volumes** | `max_cpu` | no |
| `DipyTensorFit` (FA) | none needed — cheap | 1 | no |
| `DipyCsdFit` | `peaks_from_model(num_processes)` | `max_cpu` | no |
| `DipyTracking` | `probabilistic_tracking(nbr_threads)` | `max_cpu` | no |
| `DipyAtlasSLR` | none | 1 | no |
| `DipyTissueClassifier` (HMRF) | none | 1 | no |
| `DipyRecoBundles` | `recognize(num_threads)` | `max_cpu` | no |
| N4 on b0 | ITK `num_threads` (existing node) | `max_cpu` | no |

**Every dipy node must pin its BLAS thread count.** numpy here is linked against
scipy-openblas, which multithreads large decompositions on its own, invisibly to
nipype. Measured: `mppca` runs at 100% CPU on the 16-volume subject (27x16
matrices, below OpenBLAS's threshold) and at **340-360%** on the 65-volume one
(125x65 matrices). A node declared `n_procs=1` that silently consumes 3.5 cores
breaks the resource accounting the hard-cap direction requires, and the effect is
*data-dependent*, so it cannot be reasoned about per node in the abstract.

Each node therefore sets `OMP_NUM_THREADS`/`OPENBLAS_NUM_THREADS` explicitly to
the count it declares to nipype, rather than inheriting library defaults. This
applies to every numpy-heavy node — denoise, tensor fit, CSD fit, HMRF — not only
the ones with an explicit parallelism parameter.

**No dipy node declares `use_cuda`**: dipy core has no GPU path. GPU tracking
lives in `dipy/GPUStreamlines` (`cuslines`), a separate non-PyPI package needing
CUDA-toolkit compilation. This is the one asymmetry that cannot be closed against
the FSL branch, which does use the GPU for eddy, bedpostx and probtrackx.

`_mem_gb` must be measured **per node in isolation**, because nipype runs each
node in its own process. Chained measurements are not usable for this.

### 11. Phantom

`GENERATOR_VERSION` `"8"` → `"9"` (invalidates the cache; full regeneration for
everyone). `dwi_directions` 6 → 30. In `tissue.py`, AF and OR corridors alongside
the existing CST, plus a background white-matter direction field derived from the
fsaverage WM mask; `render_dwi` in `sequences.py` moves from "only the CST is
anisotropic" to a tensor field across the whole WM.

This is required, not cosmetic: RecoBundles runs a whole-brain SLR against
`whole_brain_MNI.trk` *before* recognising individual bundles. A tractogram
consisting of a single CST corridor would register arbitrarily, so even the CST
would fail — not just AF and OR.

### 12. Fixing the FSL rotated-bvec bug (in scope)

FSL `eddy` produces `out_rotated_bvecs`, and nipype exposes it, but
`dti_preproc_workflow` passes the original dcm2niix bvecs to both `dtifit`
(line 228) and `bedpostx` (line 324). By the same Leemans & Jones 2009 argument
that makes `reorient_bvecs` mandatory on the dipy branch, the current FSL branch
carries a systematic bias in FA and tractography proportional to subject rotation.

Found while designing the dipy branch and, by decision, **fixed as part of this
work** since the same code is being touched.

The fix: connect `eddy` → `out_rotated_bvecs` to `dtifit.bvecs` and
`bedpostx.bvecs` in place of `conversion.bvecs`.

Two constraints:

- It applies **only to the full `eddy` path**. `EddyCorrect`, used when
  `old_eddy_correct` is true, produces no rotated bvecs, so that path keeps the
  original ones — there is nothing better available.
- It **changes the output of the existing, validated FSL pipeline**. FA maps and
  tractography will differ from previously produced results, by the amount of
  subject rotation. The golden matrix snapshots change, and this is a scientific
  correction rather than a refactor: it needs its own validation and a note in
  the changelog, so that users understand why re-running an old subject no longer
  reproduces the old numbers.

## Implementation phasing

The work splits along the same seam as the two workflows, and phase 2 should not
start before phase 1 has been looked at on real data:

- **Phase 0** — the FSL rotated-bvec fix (section 12) alone. It touches the
  existing path and changes its snapshots, and is far easier to review on its own
  than mixed into a new engine. The `old_eddy_correct` → `fast_dwi_preproc`
  replacement that this phase originally also carried was **cancelled** on
  2026-09-02: see "Denoising on dipy is always nlmeans" in section 2.
- **Phase 1** — engine preference and gating, dependency/licence plumbing, the
  new preprocessing/reconstruction/tracking nodes, `dipy_dti_preproc_workflow`,
  the `MainWorkflow` branch, and matrix snapshots. Deliverable: a global
  tractogram for both oracle subjects.
- **Phase 2** — `DipyRecoBundles`, `dipy_bundle_workflow`, the fornix split, the
  Slicer/SlicerDMRI branch, and the result contract.
- **Phase 3** — phantom v9 and the prerelease sweep, which can only assert bundle
  recovery once phase 2 exists.

## How this gets executed

The plan is delivered in the shape it is run in, not as a flat checklist:

```
global orchestrator  (holds this design and the cross-phase contracts)
  └─ phase orchestrator      one session per phase
       └─ executors          several per phase, each labelled Sonnet 5 or Opus 4.8
```

For each phase, the deliverable is a ready-to-paste **orchestrator prompt**. That
orchestrator splits its phase into independent executor tasks, writes their
prompts, and assigns each a model. Model choice follows the nature of the work:
**Opus 4.8** for anything needing real reasoning — scientific correctness, the
equivalence oracles, adaptive `lmax` logic, RecoBundles
integration, the phantom geometry — and **Sonnet 5** for well-specified
mechanical work such as preference plumbing, licence and `strings.py` entries, or
snapshot regeneration.

At the end of each phase the result is reported back to the global orchestrator,
so every orchestrator prompt must close with a **report-back contract**: tests run
and their actual output, contracts touched, deviations from the plan, numbers
measured, and what was deliberately not done. A phase reported as "done" without
that evidence cannot be verified, and under `CLAUDE.md` a change is not complete
until its tests have been run *and reviewed for correctness*.

## Validation

### Oracles

Two real subjects in `~/test_swane/dipy_test/` (local only — see "Data handling"
above; neither they nor anything derived from them is ever committed) that
exercise opposite regimes:

| | subj1 | subj2 |
|---|---|---|
| Directions | 15 | 64 |
| DWI | 256×256×52 | 144×144×60 |
| Voxel | 0.94×0.94×2.5 | 1.56×1.56×2.2 |
| Resulting lmax | 4 (supported floor) | 6–8 (comfortable) |

They exercise different branches of the adaptive-lmax code, which is why both are
needed: subj1 covers the lowest angular resolution SWANe accepts, subj2 a routine
one. Neither is "the typical case" on its own.

### `DipyDenoise` (nlmeans)

No equivalence oracle is needed: `nlmeans` exposes `num_threads` and parallelises
itself, so there is no hand-written pool to prove equivalent. This section
previously specified a slab-parallel MP-PCA implementation and its bit-for-bit
oracle; both were dropped with MP-PCA itself.

Coverage reduces to the ordinary node contract: `estimate_sigma` is called on the
data actually passed to `nlmeans`, the output preserves shape, affine and volume
count, and `OMP_NUM_THREADS` is pinned to the declared `n_procs`.

### `DipyMotionCorrection` equivalence

Hand-parallelising this node requires proof of equivalence. Three layers:

1. **Reassembly by index** — unit test with mocked registration returning
   identifiable per-volume payloads *out of order*; assert volume *i* lands at
   position *i*. This is the likeliest and most silent parallelisation bug:
   scrambled volumes crash nothing, they just corrupt the tensor.
2. **bvec reorientation** — `motion_correction` does not reorient the gradients
   itself; it returns `(image, affine_array)` and leaves that to the caller. Use
   dipy's official helper, `dipy.core.gradients.reorient_bvecs(gtab, affines)`,
   not a hand-rolled rotation.

   This is not optional. dipy's own docstring, citing Leemans & Jones 2009,
   states that without reorientation the rotation of the volumes causes
   "systematic bias in rotationally invariant measures, such as FA and MD, and
   also characteristic biases in tractography".

   **Indexing trap**: `reorient_bvecs` expects affines ordered as
   `gtab.bvecs[~gtab.b0s_mask]` — the non-b0 volumes only — while
   `motion_correction` returns an affine array covering *all* volumes including
   b0s. The correct call passes `affines[..., ~gtab.b0s_mask]`. Passing the full
   array silently misaligns every gradient. Unit test: apply a known rigid
   rotation, assert the reoriented bvec matches the analytic expectation, that
   b0 rows stay `[0,0,0]`, and that norms are preserved.
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
| MP-PCA denoise | 423 s | 1 *(historical: MP-PCA was later dropped)* |
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

### subj1, real gradients, WM seeding, PFT

| Step | Time | delta RSS |
|---|---|---|
| Brain mask | 16.5 s | +0.22 GB |
| MP-PCA (`patch_radius=1`) | 404.4 s | +0.01 GB |
| `motion_correction` (serial) | 663.7 s | +0.30 GB |
| `reorient_bvecs` | 0.0 s | — |
| CSD lmax=4 | 172.6 s | +0.32 GB |
| HMRF -> PVE | 10.7 s | +0.04 GB |
| **PFT, WM seeding** | **136.8 s** | +0.03 GB |
| `.trx` save | 1.7 s | +0.10 GB |
| **Total** | **1406 s (23.4 min)** | **peak 1.2 GB** |

160,644 streamlines from 56,934 WM seeds; the WM mask is 8% of the 667,146 brain
voxels. `motion_correction` alone is 47% of the total, which is why it is the
parallelisation target.

Note this corrects the earlier deterministic/whole-brain figures: PFT with WM
seeding is *cheaper* than deterministic tracking with whole-brain seeding (137 s
vs 625 s, +0.03 GB vs a 7.0 GB peak). The 7 GB came from seeding 667k voxels, not
from the tracker.

### subj1 — Task 11 isolated node run overturned PFT (tracker swap)

The isolated per-node measurement mandated by Task 11 (each node run in its own
process, tree-peak RSS = parent + workers) contradicted the figures above and
forced the tracker change. Two facts about `pft_tracking(sh=)` came out:

* **It is single-core.** An exhaustive thread bench (`nbr_threads` 1/4/8, all
  `seed_buffer_fraction` values, `nbr_threads=0`, `OMP_NUM_THREADS` set at
  process start) held `avg_cores = 1.0` throughout — the `sh=` path never engages
  the OpenMP pool. So density=2 is ~88–100 min single-core on subj1.
* **It precomputes a dense full-FOV PMF** — the fODF sampled over `default_sphere`
  (362 vertices), float64, for every voxel of the passed SH volume:
  `256·256·52·362·8` bytes = **9.19 GB** on subj1. The measured peak matched this
  exactly and was independent of seed/thread count. (The earlier 1.2 GB PFT probe
  was low only because it cropped the SH; the node passed the full FOV.)

Both facts make PFT unusable on the 8 GB / 4-core target. `probabilistic_tracking`
with the *same* `CmcStoppingCriterion(PVE)` has neither problem — the dense PMF is
specific to PFT's `sh=` path — while keeping the anatomical CMC stop:

| tracker + criterion (subj1, density=1) | wall | avg_cores | RAM |
|---|---|---|---|
| `pft_tracking` + CMC (old node) | 673 s | 1.0 | 7.87 GB (needs SH crop) |
| `probabilistic_tracking` + CMC (new node) | 74.5 s | 2.62 | 1.17 GB |

Multiprocessing PFT was rejected (each worker rebuilds the ~4.8 GB PMF → ~19 GB on
four cores). At matched density=2, `probabilistic_tracking` + CMC recovers the
CST/AF bundles at least as well as PFT (RecoBundles counts equal or higher on all
four), so the swap is not a quality regression in the throwaway comparison —
though that comparison carries its own caveat (below).

### subj1 — tractogram save: materialise-then-save vs streaming

`probabilistic_tracking` at density=2 yields **623,794 streamlines** (1.16M WM
seeds). Two write paths were measured on subj1 (4 threads, real node code, tree-peak
RSS; the tracker's own peak sits around 4.8–5.0 GB regardless of the write path):

| write path | density | peak RSS |
|---|---|---|
| materialise `Streamlines()` → `StatefulTractogram` → `save_tractogram(.trx)` | 2 | **6.18 GB** |
| stream generator → `TrxFile.from_lazy_tractogram(LazyTractogram)` → `.trx` | 1 | 1.82 GB |
| stream generator → `TrxFile.from_lazy_tractogram(LazyTractogram)` → `.trx` | 2 | ~5 GB |

The materialise path holds the whole set while the transform + `StatefulTractogram`
+ save each duplicate it — a spike that scales with streamline count and clears the
~6 GB comfort threshold on an 8 GB box. **The node therefore streams**: each
streamline is moved to reference space and handed straight to a memmap-backed
`.trx` in chunks, so the write never holds the full set and the peak is bounded by
the tracker itself, not by the tractogram size. No SH crop is needed
(`probabilistic_tracking` has no full-FOV PMF). Streamline length is bounded to
10–250 mm (`MIN_LEN_MM`/`MAX_LEN_MM`, module constants).

**⚠️ Quality caveat.** The RecoBundles CST/AF comparison that backs "not a quality
regression" was run on throwaway tractograms in diffusion space with approximate
PVE (HMRF on the low-contrast b0, not the T1) and no diff→T1/MNI registration;
default RecoBundles params recovered zero, so the loose params partly measure
SLR-alignment quality, not tracker quality. The engineering case for the swap is
conclusive; the quality confirmation on the realistic path (T1-HMRF PVE + ANTs
diff→T1) is prepared but not yet run.

### subj2 — MP-PCA does not scale (this decided against MP-PCA)

The 64-direction probe was **interrupted after 54 minutes still inside MP-PCA**,
at 335% CPU. The two subjects carry near-identical data volumes (25.4M vs 29.9M
voxel-volumes), yet:

| | subj1 | subj2 |
|---|---|---|
| Per-patch matrix | 27x16 | 125x65 |
| MP-PCA wall clock | 6.7 min | **>54 min** |
| Cores used | 1 | 3.35 |
| **Core-minutes** | **6.7** | **>180** |

Roughly **27x more expensive in core-time for the same amount of data**. The
mechanism: eigendecomposition cost grows as `min(m,n)^2 * max(m,n)`, so ~7k
operations per patch becomes ~528k, and the direction count enters *twice* — it
enlarges the matrix and forces a larger `patch_radius`, which enlarges the patch.
Cost grows roughly with the cube of the direction count.

**Resolved, 2026-09-02: MP-PCA is dropped entirely.** A 64-direction
acquisition is routine, not extreme, and denoising alone costing the better part
of an hour cannot be defended as a default or offered as an option. Slab
parallelism does **not** rescue it: OpenBLAS already uses 3.35 of 4 cores, so the
headroom is spent, and the gain it would buy lands on low-direction data rather
than on the case that actually hurts.

An intermediate proposal — keep both and invert the default above a volume
threshold — was considered and rejected as carrying the cost of a preference, a
threshold and a second code path for an arm nobody should pick. The dipy engine
now always uses `nlmeans` + `estimate_sigma`; see section 2. This measurement is
what decided it, so it is kept here rather than deleted with the feature.

### Task 11 final — isolated per-node `_mem_gb`, both subjects (2026-09-03)

Both oracle subjects were run through the isolated per-node harness (each node in
its own process, tree-peak RSS = parent + workers) with the **shipped** node code:
brain-bbox-cropped `probabilistic_tracking`+CMC and **rigid-only** motion. subj2
(64-dir, 144×144×60) reached the end for the first time. Reservations are the max
across the two subjects, rounded to the nearest integer GB (min 1). The full
regressor table (RAM vs T1 voxels, DWI 4D size, SH coeffs, streamline count, with
provisional estimator slopes) is in `2026-09-03-phase1-dipy-node-ram-report.md`.

| node | subj1 GB | subj2 GB | reserv | streamlines / regressor |
|---|---|---|---|---|
| DipyDenoise | 1.11 | 1.37 | 1 | DWI 4D samples |
| DipyMotionCorrection | 7.11 | **8.44** | **8** | pool ceiling (4 workers) |
| DwiBiasCorrection | 0.85 | 0.99 | 1 | |
| DipyTensorFit | 0.89 | 1.16 | 1 | |
| DipyCsdFit | 3.57 | 3.05 | 4 | DWI spatial voxels |
| DipyTissueClassifier | 2.58 | 5.17 | 5 | T1 voxels (subj2 T1 is 2×) |
| AffineToRAS | 0.11 | 0.11 | 1 | trivial |
| DipyTracking (crop+stream) | 5.09 | 2.04 | 5 | streamlines (409k / 35k) |
| DipyAtlasSLR | 4.75 | 0.98 | 5 | streamline count |

subj1 tractogram 409,155 streamlines (15 dir), subj2 34,818 (64 dir), both at
`seed_density=2`. Sequential per-node time (isolated): subj1 ≈ 35 min, subj2 ≈ 39
min; the real workflow overlaps the T1 tissue branch with the diffusion stream.

**Motion — rigid-only applied.** Dropping the trailing `affine` stage was validated
on subj2 (64-dir, where eddy shows most): series correlation **0.9997**, max
reoriented-bvec diff **0.0034** (subj1 was 0.9995 / 0.0044) — equivalent. The one
localised divergence (a brain-edge voxel spike, larger on 64-dir data) is the eddy
distortion the affine stage was partially correcting, now **left uncorrected — a
declared asymmetry vs the FSL eddy path** (section 5). `DEFAULT_PIPELINE` is now
`[center_of_mass, translation, rigid]`; the serial path was fixed to pass it
explicitly and the serial-vs-parallel equivalence oracle re-passes bit-for-bit.
Rigid-only saves ~30% of motion time but does **not** lower its RAM — the 8.44 GB
is the 4-worker process pool, not the pipeline.

**Motion parallelization.** dipy's `motion_correction` is serial over volumes;
serial + `OPENBLAS_NUM_THREADS=4` measured **1.01 avg_cores** (BLAS does not engage
`affine_registration`) at 0.91 GB, while our process pool gives **3.88 avg_cores**
at 8.48 GB. The pool is what delivers multicore, at ~9× the RAM. Decision (user):
keep the pool, reserve motion at 8 GB.

**RAM floor.** `tractography_engine = DIPY_RECOBUNDLES` now carries an
`option_pref_requirement` of **8 GB** on `ram_gb` (`ResourceManager.
dipy_tractography_ram_requirements`), from the motion ceiling; macOS is unmeasured
and carries the same 8 GB pending a macOS run.

## Accepted risk

The risk is **confined to the bottom of the supported range**, and it should not
be read as a general reservation about the dipy engine.

SWANe supports acquisitions down to 15 directions for inclusiveness, not because
that is the expected input. At that floor, CSD lmax=4 is exactly determined — 15
coefficients for 15 measurements — so the fODF has no regularisation headroom,
crossing regions are poorly resolved, and RecoBundles can only recognise what the
tractogram actually contains. On such data the dipy engine may reconstruct fewer
or thinner bundles than bedpostx with `n_fibres=2`, which is a parsimonious
Bayesian model built precisely for sparse angular sampling.

From roughly 28 directions upward the picture changes: lmax=6 becomes comfortable,
and there is no structural reason to expect the dipy engine to underperform. The
two oracle subjects were chosen to straddle this boundary — 15 and 64 directions —
so the difference between the two regimes is measured rather than assumed.

Two design choices already mitigate the low end: the adaptive `sh_order_max`,
which never fits more coefficients than the data supports, and probabilistic
tracking (`probabilistic_tracking`), which samples the fODF instead of following
its maximum and so recovers branches that deterministic tracking systematically
drops in crossings — matching the probabilistic nature of the existing FSL path.
This is the tracker that replaced PFT (see Measurements): the anatomical
constraint is unchanged (the same `CmcStoppingCriterion`); what is given up is
PFT's particle-filtering reinitialisation of implausible streamlines, which is a
refinement on top of the same probabilistic sampling, not the probabilistic
nature itself. Whether that loss is visible on real data is folded into the
already-open quantitative comparison below — the tracker swap is an engineering
decision (it makes the dipy path run at all on 8 GB / 4 cores), ratified by the
user, with quality confirmation still pending.

What remains open is a quantitative comparison against the FSL branch on real
data. The user has chosen to proceed and measure afterwards. Recorded here as a
bounded, accepted risk at the low-direction end, not as a general caveat and not
as a resolved question.

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
5. "PFT will be heavier than deterministic tracking" — **wrong on both time and
   memory**: 137 s and +0.03 GB against 625 s and a 7.0 GB peak. The peak came
   from whole-brain seeding, not from the tracker.
6. "`mppca` is single-core" — **only on small data**; it inherits OpenBLAS
   threading and reaches 340-360% CPU on the 65-volume subject.

Numbers entering this spec are measured. Those not yet measured are marked
pending rather than rounded into certainties.
