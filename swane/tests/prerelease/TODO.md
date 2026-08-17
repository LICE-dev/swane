# TODO — pre-release execution sweep

State of the `swane/tests/prerelease/` module and what is left to finish it.
This replaces the old `nipype_pipeline/TODO_dicom.md`: that file planned running
the workflows on synthetic DICOM (its §1) and validating the output (its §4);
both are now realised here, on top of the phantom in `helpers/phantom/`. The
graph-*construction* coverage it also tracked lives in `nipype_pipeline/matrix/`.

## Done

### Infrastructure
- **Capability probe** (`capabilities.py`): FSL / dcm2niix / FreeSurfer (+ Synth
  RAM thresholds) / Slicer (from the user's real `~/.SWANe`) / CUDA / XTRACT /
  MNI templates / `reconall_expert` (see below), plus a user-set core/RAM budget.
- **Plan** (`plan.py`): a covering array over the same axes as the matrix,
  degrading or skipping per host capability, never silently dropping coverage.
  Guarded by `test_plan_integrity.py` in the light suite.
- **Runner** (`runner.py`): strictly sequential, through the real
  `WorkflowProcess`, resumable. Reuses only *completed* passes; skipped and
  failed passes are re-evaluated/retried on the next run (so raising `--ram`
  runs the Synth passes, and a fix makes a failed pass retry — cheaply, since
  nipype's per-node cache resumes from the first failed node).
- **Checks** (`checks.py`): execution, expected outputs, integrity, reference
  position, linear/non-linear registration goodness, DTI FA + CST localisation,
  fMRI activation, venous localisation.
- **Phantom** (`helpers/phantom/`): fixed smooth non-linear deformation; CT bone
  at 1900 HU (generator v6). **fMRI config follows the phantom.**
- **Reporting/CLI** (`report.py`, `__main__.py`): JSON + HTML, `--dry-run`,
  `--only`, `--checks-only`, `--with-reconall`, `--cores/--ram`, `--no-cuda`,
  `--full-accuracy`, `--view PASS` (open a pass's result scene in Slicer without
  saving a scene.mrb).

### Plan coverage added
- **CPU/GPU tractography split**: `dti_tractography` (CPU baseline, always runs)
  + `dti_tractography_gpu` (needs a GPU), so a CUDA box exercises both.
- **Synth in every workflow that uses it** (except fMRI, which avoids synth by
  design; venous_ct/seeg use FLIRT by design): `func_map_synthmorph`,
  `dti_synthmorph`, `venous_mr_synth`, and `structural_synthmorph` with flat1.
- **recon-all RAM split**: `freesurfer_reconall` (classic ~5 GB) +
  `freesurfer_reconall_synth` (FS v8 synth ~20 GB), so a big box tests both.
- **SYNTHSEG** gated on `synth_seg` (RAM/version), and `asl_ai`/`pet_ai=true`
  moved to `func_map_no_freesurfer` so the asymmetry index is covered in the
  fast sweep, not tied to a 14 GB SynthSeg pass.

### test_run fixes (were crashing / hanging)
- **FNIRT** test_run scheme was invalid (2-level lists, per-level length
  mismatch → "Expression Syntax" abort). Fixed to a length-4 coarse schedule
  `subsampling_scheme=[4,4,4,2]`, `max_nonlin_iter=[5,5,5,3]` (never full
  resolution). Nonlinear target-alignment check still clears with margin
  (Dice 0.94, NCC 0.79).
- **InvWarp** `niter=5` removed: FSL `invwarp` has no such option (crashed every
  inverse warp). No iteration knob exists on that tool.
- **CustomEddy** `--nthr` removed (pre-existing bug, not test_run): recent FSL's
  `eddy_cpu` has no `--nthr`; `OMP_NUM_THREADS` already sets the thread count.
- **SegmentEndocranium** hang: an empty bone segment (skull_threshold above the
  scan's max HU) made Wrap Solidify hang forever. Now fails fast with a clear
  error and actually exits Slicer (`slicer.util.exit`). Phantom CT bone raised
  1100→1900 HU so the fixed `skull_threshold=1500` test value has bone.

### test_run RAM
- **Synth RAM floor lowered 30% in test_run** for SynthSeg/SynthMorph only
  (they do less work under `--fast`/`robust=False`/`steps=5`), applied to BOTH
  the capability gate and the per-node `mem_gb` reservation together, so the
  plugin's prerun check does not abort a pass the gate admitted. SynthStrip and
  Synth recon-all are unchanged. Lets an ~11.6 GB box run the synth passes at
  `--ram 10`.

### FreeSurfer recon-all -expert bug (found + handled)
Unpatched FreeSurfer 8.x `recon-all` mishandles the `-expert` path in its
surface-registration stage (`if($XOptsFile)` instead of `if($#XOptsFile ...)`),
aborting with "if: Expression Syntax." whenever an expert file is present (and,
once copied into the subject's scripts dir, on later nodes too). FreeSurfer
fixed it in `fs820_updates.sh` (mid-2026). We keep the expert speedups and
detect the buggy build (`capabilities.reconall_expert`), gating the recon-all
passes on it in test_run so they are skipped with an "apply the patch" message
instead of failing hours in. `--full-accuracy` passes no expert file.

### Passes verified end to end this box (FSL + patched FS 8.2.0, --ram 10)
execution + integrity + anatomical plausibility all green: `structural_fsl`,
`structural_alt_settings`, `structural_synthstrip`, `venous_ct_slicer`,
`func_map_synthseg`, `func_map_no_freesurfer`, `dti_classic`,
`fmri_task_and_rest`, `venous_mr_detection_modes`, `venous_mr_second_phase`.
This validates the test_run cuts they exercise: FAST (`flat1`), the FNIRT
schedule, MCFLIRT `stages=1`, SynthSeg `--fast`, CustomEddy `niter=1` (FA range).

## What is left

### 1. bedpostx test_run cut breaks the left CST — TUNE (priority)
`dti_tractography` completes but `r-cst_lh` is all-zero (waytotal 0; right is a
thin 118). Root cause isolated this session: NOT the warp (full-res FNIRT still
0), NOT ProbTrackX `n_samples` (full still 0), NOT the seed/FA/fibre direction
(free tracking gives 87 000 streamlines both sides), NOT the phantom↔protocol
geometry. It is the **BEDPOSTX5 MCMC reduction** (`n_fibres=1 n_jumps=200
burn_in=100 sample_every=5`): re-running bedpostx at full accuracy recovers the
left CST (waytotal 432). Find the *minimal* relaxation (bisect n_fibres / n_jumps
/ burn_in) that recovers the left CST at least cost, and set it in
`dti_preproc_workflow.py`.

### 2. fMRI `del_vols=none` empties activation — DECISION
`fmri_alt_settings` completes but both task contrasts have empty activation
clusters. Cause: the phantom always pads dummy volumes, and `FMRIGenSpec`
computes block onsets from volume 0 of the *used* series; with `del_vols=none`
the dummies are not trimmed, so the whole block design is shifted and the GLM
decorrelates. This is arguably expected for that config on this data, not a
SWANe bug. Decide: exempt tract/activation for the `del_vols=none` pass, drop
that pass, or give the phantom a no-dummy variant for it.

### 3. venous_ct_fixed_threshold — re-run on the fresh phantom
The endocranium fix (fail-fast + bone 1900 HU) was never actually exercised: the
overnight run reused stale nipype intermediates built from the old 1100 HU
phantom (see §"phantom cache" below). Delete the pass dir and re-run with the v6
phantom to confirm the venous-CT vein-localisation check passes with the coarse
test_run endocranium params.

### 4. Coverage still not exercised end to end
- **Full sweep** start to finish in one go.
- **Synth family**: now runnable at `--ram 10` (30% reduction) but not yet
  executed — confirm `structural_synthmorph` / `func_map_synthmorph` /
  `dti_synthmorph` / `venous_mr_synth` actually pass, and watch real RAM vs the
  9.8 GB estimate (swap is the cushion).
- **recon-all**: now runnable with the FS patch. Run end to end (classic and,
  on a 20 GB box, synth), confirm usable pial/white surfaces + aparc+aseg, and
  measure time saved vs accuracy lost — tune the expert values (`mris_register
  -N 10` is the biggest lever; `-no-fix-with-ga` vs `mris_fix_topology -niters 2`
  overlap, drop one if redundant).
- **CUDA paths** (`dti_tractography_gpu`, eddy `cuda`): need a working CUDA/FSL
  box; unverified here.
- **hippo/amygdala labels** (`hippo_amyg_labels=true`): needs the FreeSurfer
  Matlab runtime, absent here.

### 5. Check gaps
- **sEEG electrode localisation**: no `seeg.*` position check yet (only presence
  + integrity). Add one mirroring `veins.position` against the known contacts.
- **Venous CT bilateral reconstruction**: confirm the check verifies the
  subtract-then-sum recovers *both* sinus sides; a dropped addend must fail.
- **CPU vs GPU equivalence**: eddy/bedpostx/probtrackx GPU output must be
  equivalent to CPU at the contract level. Needs a GPU box.
- **Geometry / interpolation**: assert affine/orientation/voxel size preserved
  where a node must not transform them, and masks/labels use nearest-neighbour.
- **Regression vs a committed baseline**: absolute thresholds catch "broken",
  not "changed"; a diff-against-previous-run mode would catch silent numeric
  drift between SWANe versions.

### 6. Robustness / operability
- **Phantom cache staleness**: nipype hashes the DICOM *directory path*, not its
  recursive content, so regenerating the phantom (bumped `GENERATOR_VERSION`)
  is NOT picked up by pass dirs that already exist — the stale intermediates are
  reused and the new data never reaches the workflow. Today the only fix is to
  delete the affected pass dir. Document, or force-invalidate on a version bump.
- **Resume**: the reuse-only-completed logic is in; make an automated test
  (SIGINT → clean teardown → reused on re-run).
- **Out-of-memory / insufficient-resources** path is recorded but never actually
  triggered — force it once to confirm the sweep records and continues.
- **Per-pass timeout**: a hung workflow currently blocks the whole sweep (we hit
  exactly this with the endocranium hang; the fail-fast fixed that instance, but
  a generic timeout is still missing).
- Review the **HTML report** on a full run for legibility.

### 7. Calibration
`REGISTRATION_MIN_DICE` lowered to 0.85 (SynthStrip agrees with the reference
brainmask at ~0.88 by itself, so a correct SynthStrip registration lands ~0.89).
The other tolerances (`FEATURE_TOLERANCE_MM`, `NONLINEAR_*`, FA bounds) were set
from one box; confirm they hold across machines and FSL/atlas versions before
trusting them as gates; widen only with a measured reason.

### 8. CI / invocation
The light `test_plan_integrity.py` runs in CI. The heavy sweep is local/nightly
by nature (hours, real tools). Decide and document how it is launched — nightly
job, release gate — and where its report is published.
