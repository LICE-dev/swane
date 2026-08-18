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

### Re-run on a CUDA box, `--checks-only` confirmed (--ram 10, --with-reconall)
Second full run (this box now has a working FreeSurfer 8.2.0 + license, and a
CUDA GPU): 20 of 21 passes executed, **all 20 completed with zero failed
nodes and zero failed/warned checks** (`freesurfer_reconall_synth` skipped --
needs 20 GB, box has 10 GB allocated). Confirms both fixes from the previous
run: `dti_tractography`/`dti_synthmorph` now show non-zero `r-cst_lh` (171 and
30 respectively) and passing `dti.anisotropy_in_cst`; `freesurfer_reconall`
completed all 81 nodes with zero `node_errors` and every `asl_*`/`pet_*`
check green. First confirmation of the **CUDA path**: `dti_tractography_gpu`
completed 40/40 nodes with the same integrity/registration/CST checks as the
CPU pass.

### Resume was reusing passes stuck at a stale capability downgrade
Found by hand: a sweep run without the Matlab runtime downgrades
`hippo_amyg_labels` `true` -> `false` for `freesurfer_reconall` and completes
without the subfield labels; once Matlab became available, re-running the
sweep kept reusing that old "completed" record forever, since `_reusable()`
(`runner.py`) only checked `status == "completed"` and that `subject_dir`
still existed -- it never compared the axis values the *current* host
resolves the pass to against the ones the record was actually built with.
Any capability gate works the same way (RAM, GPU, Slicer, ...), so this was
general, not Matlab-specific. Fixed: `_reusable()` now also requires
`previous["values"] == dict(pass_item.values)`; a value that changed because
a requirement appeared (or disappeared) forces a re-run in the *same*
`subject_dir`, so nipype's per-node cache only executes the nodes whose
inputs actually changed (e.g. just `SegmentHA` and downstream) rather than
redoing the whole pass.

### Insufficient-resources signaling: tested at the right altitude, and a real bug found doing it
Originally scoped as "force it once in the sweep" -- redirected to a proper
unit test instead: `MonitoredMultiProcPlugin._prerun_check()` is where the
CPU/RAM/GPU budget gate and the `WORKFLOW_INSUFFICIENT_RESOURCES` signal
actually live, so it belongs in
`tests/nipype_pipeline/engine/test_monitored_multiproc_plugin.py`, exercised
directly against a minimal fake graph/node -- no phantom, no real workflow,
no hours-long sweep pass needed to hit three `if` branches. Covers all three
budgets (RAM, CPU threads, GPU slots) both over and within budget.

Writing it surfaced a real, previously silent bug: `WorkflowProcess.py`
built nipype's `plugin_args` with the key `"n_gpu_proc"` (missing the
trailing `s`); nipype's `MultiProcPlugin.__init__` reads `"n_gpu_procs"`, so
the typo'd key was simply never seen and it fell back to
`self.n_gpus_visible` (every GPU physically present) instead of the user's
configured `max_subj_gpu`. A user who deliberately capped or disabled GPU
use from SWANe's Performance settings had that limit silently ignored, and
`_prerun_check`'s GPU-over-budget gate could never fire against the
configured limit either. Fixed the key; added a regression test
(`test_workflow_process.py::test_workflow_run_worker_gpu_budget_reaches_the_plugin`)
that inspects the actual `plugin_args` dict built by `workflow_run_worker()`.

That regression test also exposed a pre-existing test-isolation bug:
`test_add_and_remove_handlers` called `WorkflowProcess.add_handlers()` and
`.remove_handlers()` with two *different* `DummyHandler()` instances, so the
removal was a silent no-op and the (attribute-less) added handler stayed on
the real `nipype.workflow`/`nipype.utils`/`nipype.filemanip`/`nipype.interface`
loggers for the rest of the pytest session -- any later `logger.warning(...)`
through those channels (exactly what `_prerun_check` does) crashed with
`AttributeError: 'DummyHandler' object has no attribute 'level'`. Fixed to
reuse one instance and assert it is actually gone afterward.

### Venous CT bilateral reconstruction now checked per hemisphere
`checks.py`'s only venous check was a combined centre-of-mass (`_check_feature`,
`veins.position`), which a one-sided reconstruction can pass: losing one
addend (`venous_ct2` right, or `venous_ct3` left, see `catalog.py`) only
nudges the overall centroid rather than zeroing it out. `GroundTruth.build()`
now also splits the phantom's `venous_sinus` mask into `venous_sinus_L`/`_R`
by world x sign (same convention the phantom generator itself uses to
one-side-opacify `venous_ct2`/`venous_ct3`, see
`helpers/phantom/sequences.py:_apply_side_override`). A new
`_check_venous_ct_bilateral()` reads the FINAL registered result (`r-veins*`,
on the reference/T1 grid) and counts above-half-max voxels on each side using
THAT image's own affine for the world x split -- not the phantom's native
grid -- so it is correct however registration reoriented the data. Gated on
`"venous_ct" in result.inputs`, so it does not fire for the venous MR passes
(different, non-bilateral reconstruction). `veins.bilateral_left` /
`veins.bilateral_right`, both severity `error`: a dropped addend now fails
the pass outright rather than only warning. Verified against real sweep
results (`venous_ct_slicer`, `venous_ct_fixed_threshold`): both sides detected
on the good data; zeroing the left hemisphere of a copy reproduces exactly
the "dropped addend" failure (`veins.bilateral_left` -> 0 voxels, fails).

### CPU vs GPU tractography equivalence: Dice on tracts, numeric on waytotal
New `checks.check_cpu_gpu_equivalence(cpu_result, gpu_result)`, called once
from `__main__.py` after the per-pass check loop and folded into the GPU
pass's own `checks` list (report structure stays per-pass). Pairs up every
`*_waytotal` file present under both `dti_tractography` and
`dti_tractography_gpu`'s results (extensionless, so needed a new
`_find_waytotal_files()` -- `_find_results()`'s image-extension glob never
sees them) and, for each, checks the waytotal counts' relative difference
and the Dice of the two tract density maps as any-positive-voxel masks.
WARNING severity throughout, deliberately: bedpostx's MCMC sampling is
stochastic and the CPU/GPU FSL implementations are not bit-identical, so
some divergence is real and expected, not a bug -- confirmed on this box:
measured `r-cst_lh` differed 2% (waytotal) / Dice 0.68, `r-cst_rh` 25% /
Dice 0.68; `GPU_WAYTOTAL_REL_TOLERANCE`/`GPU_TRACT_DICE_MIN` set generous
around those numbers so the check catches a real regression (e.g. an empty
or wildly displaced GPU tract) without flagging normal sampling noise.
Verified end to end against the real sweep's `--checks-only` results: both
tracts pass on both metrics.

### hippo/amygdala labels confirmed with the Matlab runtime now available
`hippo_amyg_labels=true` (`freesurfer_reconall`, SegmentHA) was only ever
run downgraded to `false` on this box for lack of the FreeSurfer Matlab
runtime. Runtime installed and the pass re-run (resume correctly picked it
up as a stale downgrade, see above, and only re-ran the newly-unblocked
nodes): passes.

### sEEG electrode position check, mirroring veins.position
The phantom's electrode geometry (`helpers/phantom/dataset.py`) was pure RAS
mm arithmetic private to the CT-stamping function -- no ground truth existed
to check against. Extracted it into public `seeg_trajectories()` (entry/target
pairs) and `seeg_contact_points()` (mm coordinates of every contact),
refactoring `_add_seeg_electrodes` to use them so rendering and ground truth
can never drift apart; verified byte-identical output against the pre-refactor
function on the same tissue model. `GroundTruth.build()` now sets a `"seeg"`
centre from the contacts' centroid (pure geometry, needs no affine/voxel
grid, unlike the tissue-model-derived centres). `_check_plausibility` now
also calls `_check_feature(files, truth, "seeg", "seeg")` -- the exact same
function `veins.position` uses, just a different token/truth key -- giving
`seeg.detected`/`seeg.position`. Verified end to end against the real
sweep's `structural_alt_settings` results: 367 voxels detected, 6.5 mm from
the phantom's known contacts (added to the `FEATURE_TOLERANCE_MM` margins
comment alongside the brain/CST/venous-sinus measurements).

## What is left

### 1. Coverage still not exercised end to end
- **recon-all on a 20 GB box**: `freesurfer_reconall_synth` (FS v8 synth path)
  still needs a bigger box than this one.

### 2. Check gaps
- **Geometry / interpolation**: assert affine/orientation/voxel size preserved
  where a node must not transform them, and masks/labels use nearest-neighbour.
- **Regression vs a committed baseline**: absolute thresholds catch "broken",
  not "changed"; a diff-against-previous-run mode would catch silent numeric
  drift between SWANe versions.

### 3. Robustness / operability
- **Resume**: the reuse-only-completed logic (including the stale-downgrade
  check above) is in; make an automated test (SIGINT → clean teardown →
  reused on re-run).

### 4. Calibration
`REGISTRATION_MIN_DICE` lowered to 0.85 (SynthStrip agrees with the reference
brainmask at ~0.88 by itself, so a correct SynthStrip registration lands ~0.89).
The other tolerances (`FEATURE_TOLERANCE_MM`, `NONLINEAR_*`, FA bounds) were set
from one box; confirm they hold across machines and FSL/atlas versions before
trusting them as gates; widen only with a measured reason.

### 5. CI / invocation
The light `test_plan_integrity.py` runs in CI. The heavy sweep is local/nightly
by nature (hours, real tools). Decide and document how it is launched — nightly
job, release gate — and where its report is published.
