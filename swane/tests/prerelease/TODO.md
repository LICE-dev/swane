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
  at 1900 HU; `fmri_0` padded with dummy volumes, `fmri_1` with none (generator
  v7). **fMRI config follows the phantom.**
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

### fMRI dummy-volume trimming
- **Baked into the phantom instead of a `del_vols` axis toggle**: `fmri_0` is
  generated with dummy padding (subject.py trims it), `fmri_1` with none (so
  del=0 is the correct declaration). Every fMRI pass exercises both "trim real
  padding" and "correctly declare none" at once. Replaces the old
  `fmri0_del_vols=none` config, which asked the workflow not to trim padding the
  data still had — desyncing the GLM and emptying the activation maps. Removed
  the `fmri0_del_vols` axis; `subject.py` now always uses the manifest's real
  per-series dummy counts. (Resting state was never trimmed and never will be —
  MELODIC is data-driven, not onset-locked — so it is unaffected.)

### test_run RAM
- **Synth RAM floor lowered 30% in test_run** for SynthSeg/SynthMorph only
  (they do less work under `--fast`/`robust=False`/`steps=5`), applied to BOTH
  the capability gate and the per-node `mem_gb` reservation together, so the
  plugin's prerun check does not abort a pass the gate admitted. SynthStrip and
  Synth recon-all are unchanged. Lets an ~11.6 GB box run the synth passes at
  `--ram 10`.

### FreeSurfer recon-all -expert bugs (two found; one patched, one worked around)
Unpatched FreeSurfer 8.x `recon-all` mishandles the `-expert` path in its
surface-registration stage (`if($XOptsFile)` instead of `if($#XOptsFile ...)`),
aborting with "if: Expression Syntax." whenever an expert file is present (and,
once copied into the subject's scripts dir, on later nodes too). FreeSurfer
fixed it in `fs820_updates.sh` (mid-2026). We keep the expert speedups and
detect the buggy build (`capabilities.reconall_expert`), gating the recon-all
passes on it in test_run so they are skipped with an "apply the patch" message
instead of failing hours in. `--full-accuracy` passes no expert file. Confirmed
on this box: unpatched -> skipped with the message; patched -> passes run.

After patching, a **second, separate, still-unpatched** bug surfaced:
`rca-surfreg` (untouched by `fs820_updates.sh`, last modified 3/24 vs
`recon-all`'s 3/29) splices the `mris_register` xopts override BETWEEN the
first positional arg and the rest (`mris_register ... lh.sphere -N 10
target.tif out.reg`), which `mris_register` cannot parse -- it reads "-N"
itself as the target filename. `mris_inflate`/`mris_fix_topology`/`mri_synthseg`
all place their xopts safely elsewhere in the command, so only the
`mris_register -N 10` line is affected. Dropped it from
`RECONALL_TEST_EXPERT` in `freesurfer_workflow.py` (kept the other three
lines). **Re-add `"mris_register -N 10\n"` once FreeSurfer fixes rca-surfreg's
argument ordering** -- it was the single biggest speed lever for the surface
steps. (`fsr-getxopts`'s own comments date the current xopts-merging behaviour
to 10/16/24, so this whole mechanism is young -- expect more rough edges.)

### BEDPOSTX test_run cut was breaking the left CST — bisected, fixed
`dti_tractography` completed but `r-cst_lh` was all-zero (waytotal 0; right was
a thin 118). Isolated to the BEDPOSTX5 MCMC reduction (NOT the warp: full-res
FNIRT still gave 0; NOT ProbTrackX `n_samples`: full still gave 0; NOT
seed/FA/fibre direction: free tracking gives 87 000 streamlines both sides).
Bisected the MCMC cut directly: n_fibres=2 with the *cheap* test_run MCMC
settings (`n_jumps=200 burn_in=100 sample_every=5`) recovers the left CST
(waytotal 463, 683s) -- but n_fibres=1 stays at 0 even with much heavier MCMC
(`n_jumps=800 burn_in=500 sample_every=15`, ~13k iterations/voxel, still 0). The
lever that matters is n_fibres, not MCMC depth: a single-fibre model can't
represent the crossing along the left CST's path, no matter how well-sampled.
Set `n_fibres=2` in test_run (`dti_preproc_workflow.py`), matching the
full-accuracy path; MCMC stays cheap.

### ASL/PET surface sampling race condition (production bug, found via freesurfer_reconall)
`freesurfer_reconall` failed on `asl_surf_lh/rh`/`pet_surf_lh/rh` (`mri_vol2surf`
couldn't find `lh.white`) even though recon-all itself completed cleanly and
the file existed on disk 23 minutes later. Root cause: `MainWorkflow` connects
ASL/PET's surface sampling to `self.freesurfer`'s `outputnode.subjects_dir`/
`subject_id` -- plain strings FreeSurfer tools use to *locate* `lh.white`/
`lh.pial` on disk by convention, not a tracked nipype dependency on the node
that writes them. `freesurfer_workflow.py`'s `outputnode` sourced those two
fields from `recon_all_recon1` (the FIRST node), so nipype considered ASL/PET
surface sampling "ready" as soon as recon1 finished, regardless of whether
recon2/recon_pial/recon3 (which actually write the surfaces) had run yet. This
mostly went unnoticed because timing usually left enough slack; a resumed,
multi-hour recon2 (9195s here) removed it, causing a real, deterministic crash.
Fixed: `outputnode.subject_id`/`subjects_dir` now connect from the chain's
*actual last node* (`recon_all_recon_pial`, or `recon_all_recon3` when
`step == RECONALL`) via a `final_recon` variable, so nipype has a real edge to
wait on. Verified both `AUTORECON_PIAL` and `RECONALL` build correctly (no
`NameError` when stopping at the earlier step). `SegmentHA` (hippo/amygdala)
was already wired correctly from `recon_all_recon_pial`, unaffected.

### Full sweep run start to finish, --checks-only confirmed (--ram 10, --with-reconall)
First complete run of the whole plan in one go, overnight (19 run, 2 skipped
[CUDA / synth recon-all, both need hardware this box lacks], 6h00m). A
`--checks-only` pass (execution + integrity + full anatomical plausibility,
ground truth rebuilt) came back green for **16 of 19** passes: `structural_fsl`,
`structural_alt_settings`, `structural_synthstrip`, `structural_synthmorph`,
`venous_ct_slicer`, `venous_ct_fixed_threshold`, `func_map_synthseg`,
`func_map_no_freesurfer`, `func_map_synthmorph`, `dti_classic`,
`fmri_task_and_rest`, `fmri_alt_settings`, `venous_mr_detection_modes`,
`venous_mr_second_phase`, `venous_mr_synth`, `freesurfer_autorecon_pial`. This
is the first full-checks confirmation of: the Synth family end to end, the
`mris_register` recon-all fix, the SegmentEndocranium fix (on the regenerated
v7 phantom), and -- notably -- **the fMRI `del_vols` fix**: both
`fmri_task_and_rest` and `fmri_alt_settings` show no activation errors, so
`fmri_1`'s no-dummy-padding redesign is confirmed working, not just
theoretically sound.

The remaining 3 all have an **already-committed** fix that landed after this
run's process had imported the old code, so they only show pre-fix symptoms:
- `dti_tractography`, `dti_synthmorph`: `integrity.r-cst_lh` constant zero --
  the BEDPOSTX `n_fibres=1` bug, fixed to `n_fibres=2` (see above).
- `freesurfer_reconall`: `asl_surf_lh/rh`, `pet_surf_lh/rh` node failures --
  the ASL/PET race condition, fixed (see above).

## What is left

### 1. Re-run to confirm this session's fixes (cheap: nipype resumes from the
first changed/failed node, not a full re-run)
- `freesurfer_reconall` -- ASL/PET race-condition fix.
- `dti_tractography`, `dti_synthmorph` -- BEDPOSTX `n_fibres=2` fix (left CST).

### 2. Coverage still not exercised end to end
- **recon-all on a 20 GB box**: `freesurfer_reconall_synth` (FS v8 synth path)
  still needs a bigger box than this one.
- **CUDA paths** (`dti_tractography_gpu`, eddy `cuda`): need a working CUDA/FSL
  box; unverified here.
- **hippo/amygdala labels** (`hippo_amyg_labels=true`): needs the FreeSurfer
  Matlab runtime, absent here.
- Once `freesurfer_reconall` passes cleanly: confirm usable pial/white
  surfaces + aparc+aseg, and measure time saved vs accuracy lost on the expert
  values (`-no-fix-with-ga` vs `mris_fix_topology -niters 2` overlap, drop one
  if redundant).

### 3. Check gaps
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

### 4. Robustness / operability
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

### 5. Calibration
`REGISTRATION_MIN_DICE` lowered to 0.85 (SynthStrip agrees with the reference
brainmask at ~0.88 by itself, so a correct SynthStrip registration lands ~0.89).
The other tolerances (`FEATURE_TOLERANCE_MM`, `NONLINEAR_*`, FA bounds) were set
from one box; confirm they hold across machines and FSL/atlas versions before
trusting them as gates; widen only with a measured reason.

### 6. CI / invocation
The light `test_plan_integrity.py` runs in CI. The heavy sweep is local/nightly
by nature (hours, real tools). Decide and document how it is launched — nightly
job, release gate — and where its report is published.
