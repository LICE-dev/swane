# TODO — pre-release execution sweep

State of the `swane/tests/prerelease/` module and what is left to finish it.
This replaces the old `nipype_pipeline/TODO_dicom.md`: that file planned running
the workflows on synthetic DICOM (its §1) and validating the output (its §4);
both are now realised here, on top of the phantom in `helpers/phantom/`. The
graph-*construction* coverage it also tracked lives in `nipype_pipeline/matrix/`.

## Done

- **Capability probe** (`capabilities.py`): FSL / dcm2niix / FreeSurfer (+ Synth
  RAM thresholds from the dependency manager) / Slicer (read from the user's
  real `~/.SWANe`) / CUDA / XTRACT / MNI templates, plus a user-set core/RAM
  budget for the `MonitoredMultiProcPlugin`.
- **Plan** (`plan.py`): a covering array over the same axes as the matrix,
  degrading or skipping per host capability, never silently dropping coverage.
  Guarded by `test_plan_integrity.py` in the light suite.
- **Runner** (`runner.py`): strictly sequential, through the real
  `WorkflowProcess`, resumable via an on-disk state file. Default work dir
  `~/test_swane/prerelease` is persistent (survives `/tmp` cleanup / reboot).
- **Checks** (`checks.py`): execution, expected outputs, integrity, reference
  position, **linear registration goodness** (before/after COM + brain-mask
  Dice vs the reference), **non-linear registration goodness** (warp present /
  non-trivial + alignment of the warped subject to the real MNI/sym target read
  at run time), DTI FA range + CST localisation, fMRI activation, venous/vein
  localisation. Calibrated once against a real run on this box.
- **Phantom deformation** (`helpers/phantom/deformation.py`): a fixed smooth
  non-linear warp so FNIRT/SynthMorph have real work; the subject differs
  non-linearly from the atlas while series stay rigid to each other.
- **fMRI config follows the phantom**: task/rest durations and dummy trimming
  are taken from the manifest; TR and volume count stay on auto-detect.
- **Reporting/CLI** (`report.py`, `__main__.py`): JSON + self-contained HTML,
  `--dry-run`, `--only`, `--checks-only`, `--with-reconall`, `--cores/--ram`.

Verified end to end on this box (FSL + FreeSurfer, 11.6 GB, GPU present):
`structural_fsl`, `structural_synthstrip`, `structural_alt_settings`,
`dti_classic`, `venous_ct_slicer`, `venous_mr_*`, `fmri_task_and_rest`.

## What is left

### 1. Coverage never exercised yet

No full sweep has been run start to finish; only the passes above, one at a
time. Still unexercised **on any box so far**:

- **Full run** of the whole plan in one go, and a `--with-reconall` run
  (recon-all passes are opt-in and slow, never run).
- **Synth family** (`structural_synthmorph`, `func_map_synthseg`, synth
  recon-all): need ≥14–20 GB RAM; this box has 11.6, so they *skip* here. Run on
  a bigger box to cover `synth_morph`/`synth_seg`/`synth_reconall=true`.
- **CUDA paths** (eddy `cuda`, bedpostx/probtrackx `use_gpu` via
  `dti_tractography`): some CUDA tools reportedly fail on this machine, so these
  need a box with a working CUDA/FSL GPU build. Until then treat CUDA passes as
  unverified.
- **hippo/amygdala labels** (`hippo_amyg_labels=true`): needs the FreeSurfer
  Matlab runtime, absent here.
- Remaining single-axis variants not yet run: `fmri_alt_settings` (aroma off,
  alt slice timing, `del_vols=none`), `venous_ct_fixed_threshold`,
  `venous_mr_detection_modes`.

### 2. Check gaps

- **sEEG electrode localisation**: the phantom stamps electrodes on known
  trajectories, but there is still no `seeg.*` position check (only presence +
  integrity). Add one, mirroring `veins.position`, against the known contacts.
- **Venous CT bilateral reconstruction**: confirm the check actually verifies
  the subtract-then-sum recovers *both* sinus sides (the phantom opacifies one
  side per contrast); a dropped addend must fail.
- **CPU vs GPU equivalence** (from the old §4): the `use_cuda`/`use_gpu`
  outputs of eddy / bedpostx / probtrackx must be equivalent to the CPU path at
  the contract level, not merely both terminate. Needs a GPU box.
- **Geometry / interpolation** (from the old §4): assert affine, orientation and
  voxel size are preserved where a node must not transform them, and that masks/
  labels use nearest-neighbour (no interpolation-smeared labels).
- **Regression vs a committed baseline** (from the old §4): the checks are
  absolute thresholds, which catch "broken", not "changed". A mode that diffs an
  output against a previous verified run (kept out of the repo) would catch a
  silent numeric drift between SWANe versions — separate from clinical validity,
  which stays a human call.

### 3. Robustness / operability

- **Resume** was verified once by hand (SIGINT → clean teardown, reused on
  re-run); make it an automated test.
- **Out-of-memory / insufficient-resources** path is recorded but has never
  actually been triggered — force it once to confirm the sweep records and
  continues rather than dying.
- **Per-pass timeout**: a hung workflow currently blocks the whole sweep.
- Review the **HTML report** on a full run for legibility.

### 4. Calibration

Tolerances (`FEATURE_TOLERANCE_MM`, `REGISTRATION_MIN_DICE`,
`NONLINEAR_*`, FA bounds) were set from a single run on one box. Confirm they
hold across machines and FSL/atlas versions before trusting them as gates;
widen only with a measured reason.

### 5. CI / invocation

The light `test_plan_integrity.py` runs in CI. The heavy sweep is local/nightly
by nature (hours, real tools). Decide and document how it is meant to be
launched — nightly job, release gate — and where its report is published.
