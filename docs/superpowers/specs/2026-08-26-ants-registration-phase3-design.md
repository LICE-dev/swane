# ANTs (antspyx) registration backend — Phase 3 design

Status: draft for review
Date: 2026-08-26
Branch: `claude/ants-registration`

## Context

Phase 1 added antspyx as a third registration backend (`engine` enum
`{FSL, SYNTH, ANTS}`, default `ANTS`) and flipped `linear_reg_workflow`.
Phase 2 lifted the nonlinear FSL pin (`nonlinear_reg_workflow` + its consumers
`flat1`, `func_map`, `tractography`'s `mni2ref_warp`) and moved the
cross-modality CT workflows (`venous_ct`, `seeg_ct`) off their FSL pin, using
Approach A (the producer composes the ordered ANTs transform list into a single
directional displacement field per direction via `AntsComposeTransform`).

After Phase 2 the only workflows still pinned to FSL are the **EPI** family
(`fMRI_preproc`, `fMRI_task`, `fMRI_resting_state`) and the **diffusion**
producer (`dti_preproc`). Phase 3 ports both so the whole registration surface
follows the configured engine (ANTs by default).

### Scope (this spec)

In scope:

1. **EPI linear registration.** `fMRI_preproc_workflow` builds `flirt_2_ref`
   (func→ref, hardcoded `engine=RegistrationEngine.FSL`, "avoiding synth for
   reproducibility"). `fMRI_task_workflow` and `fMRI_resting_state_workflow`
   build **on the same workflow object** and today reach back into it by the
   hardcoded node name `"%s_2_ref_flirt"`, reusing its `out_matrix_file` as a
   bare `warp=[node, field]`. Expose the func→ref registration
   backend-agnostically, flip it to the configured engine, and fix the bare-warp
   linear applies so they carry `which_to_invert` under ANTS.

2. **resting_state func→ref→mni concatenation.** The AROMA branch combines the
   func→ref linear `.mat` (premat) and the ref→mni nonlinear warp (warp1) with
   FSL `ConvertWarp`, then resamples func→mni. Under ANTS this becomes a stacked
   `AntsApplyTransforms.transformlist` applied in one shot; the FSL branch keeps
   `ConvertWarp` verbatim.

3. **Diffusion + tractography, transforms externalized from probtrackx.**
   `dti_preproc_workflow` is pinned FSL because its `diff2ref_mat`/`ref2diff_mat`
   outputs must be **FSL `.mat`** for `probtrackx` (`xfm`/`inv_xfm`). Rather than
   build an ANTs-affine→FSL-`.mat` bridge (see "The bridge that does not exist"
   below), **externalize the transforms out of probtrackx**: pre-warp all ROIs
   into diffusion space ourselves, run probtrackx natively in diffusion space
   (no `xfm`/`inv_xfm`), and warp the summed result back to reference space
   ourselves. `dti_preproc` then flips fully to the configured engine and emits
   its diff↔ref transform as the abstraction's transform-list (not an FSL
   `.mat`), and the `LTAConvert` SYNTH special-case is deleted.

4. Remove the EPI "reproducibility" FSL pins; bump `__version__`.

Out of scope / non-goals:

- No ANTs-based brain extraction. `get_deskull_node` is unchanged.
- No new `AntsAffineToFSL` node (the externalization removes the need for it).
- No claim of scientific/clinical validation. Committed tests are software
  regression evidence only. The real-data ANTs-vs-FSL comparison (local oracle)
  is quality evidence for the user's own scientific acceptance, never clinical
  validation. EPI is the weakest-evidence modality (rigid EPI→T1 is intrinsically
  limited by susceptibility distortion that no backend corrects); its flip needs
  the user's scientific acceptance most and the local oracle re-run on more cases.

## The bridge that does not exist

The Phase-2 feed-forward assumed `ants.fsl2antstransform` could power an
`AntsAffineToFSL` bridge. Verified against the installed antspyx: it converts
**FSL→ANTs**, the *opposite* direction; its math lives in compiled C++
(`fsl2antstransformF3`), not invertible in Python; there is no `ants2fsltransform`;
and a numeric probe shows the FSL→ANTs map is **not** cleanly affine-linear in the
matrix entries, so "numerically invert the trusted primitive" is not reliable. A
genuine ANTs-affine→FSL-`.mat` conversion is c3d `-ras2fsl` coordinate-convention
territory (LPS/RAS, radiological determinant flip, transform direction) — real
silent-scientific-bug risk. **Decision: do not build the bridge.** Externalize
probtrackx's transforms instead (§3), which also aligns with the project-wide
"everything in ANTs transform space" decision and lets the diffusion registration
be fully ANTS.

## Decisions already made (with the user)

1. **EPI engine policy:** lift the pins to
   `resolve_registration_engine(synth_config, allow_ants=True)` but fall back
   `SYNTH → FSL` (mirrors the Phase-2 CT decision — SynthMorph is the
   non-deterministic/worse backend; ANTS is deterministic and becomes the
   default). Applies to `fMRI_preproc` (`flirt_2_ref`) and the
   `resting_state` `ref_2_mni` registration.
2. **probtrackx transforms externalized** (no `.mat` bridge). Pre-warp ROIs to
   diffusion space, run probtrackx in diffusion space, warp results back to ref.
3. **Tractography stays engine-independent:** externalize **uniformly for all
   engines** (FSL/SYNTH/ANTS), not only ANTS. This changes the FSL tract output
   too (diffusion-space accumulation + one diff→ref resample of the density map),
   which the local DTI oracle must validate for both FSL and ANTS.
4. **No new `force_pref_reset`.** The `engine` preference already defaults ANTS
   since Phase 1; Phase 3 changes no persisted default. Internal outputnode field
   changes (diffusion transform list) are MainWorkflow↔workflow wiring updated
   atomically, not persisted preferences. `__version__` is bumped for the release.
5. **Comparative oracle is a local, throwaway tool** — never committed to SWANe
   nor pushed to GitHub. Re-run the fMRI→T1 oracle on more cases; add a DTI oracle.
6. **Each implementation session runs in its own separate Claude Code session**;
   the orchestrator reviews checkpoints between sessions. The user runs on a new
   system, so the orchestrator recreates the swane env there (see Plan).

## Architecture

### §1 — EPI: expose func→ref backend-agnostically + flip

`fMRI_task_workflow` and `fMRI_resting_state_workflow` call
`workflow = fMRI_preproc_workflow(...)` and then extend that **same**
`CustomWorkflow`. So the func→ref registration nodes already live in the shared
graph; the only problems are (a) the hardcoded node-name lookup
`"%s_2_ref_flirt"` (wrong under ANTS) and (b) reusing `out_matrix_file` as a bare
`warp=`, which drops `which_to_invert` and mis-lists the transform under ANTS
(the exact `func_map` `smooth_2_ref` latent bug fixed in Phase 2).

- **`fMRI_preproc_workflow`:**
  - Add parameters `synth_config: SectionProxy`, `max_cpu`,
    `multicore_node_limit`, and keep `test_run` (needed for the ANTS node), and
    thread them into `get_registration_node`.
  - `flirt_2_ref` → `engine = resolve_registration_engine(synth_config,
    allow_ants=True)`; `SYNTH → FSL`. Remove the "avoiding synth for
    reproducibility" comment. Keep `flirt_cost="corratio"`, `flirt_search=90`,
    `non_linear=False`, `is_volumetric=True`.
  - **Expose the func→ref registration** to consumers by attaching the returned
    `RegistrationNodeWrapper` to the workflow object (e.g.
    `workflow.reg_2_ref = <wrapper>`), documented in the factory docstring.
    Consumers read `workflow.reg_2_ref` instead of `get_node("..._flirt")`.
    (Rationale: task/resting share the same `CustomWorkflow`, so the wrapper's
    `(node, field)` references remain valid; this realizes §1's "expose
    backend-agnostically" without changing the factory return type and without an
    extra `IdentityInterface`. If attaching an attribute to `CustomWorkflow`
    proves unsafe, fall back to a stable `reg_outputnode` `IdentityInterface`
    carrying the transform list + `which_to_invert`.)

- **`fMRI_task_workflow`** (`cluster_{1,2,3}_2_ref`, three thresholds × up to two
  contrasts): replace `warp=[flirt_2_ref, "out_matrix_file"]` with
  `registration=workflow.reg_2_ref` on each `apply_registration_node`
  (the `wire_transforms` path — correct `which_to_invert`). The engine passed to
  each apply is the resolved EPI engine (no longer hardcoded FSL). Keep
  `non_linear=False`, the per-iteration `out_file`/`iterfield`, filenames, and
  `outputnode` fields unchanged.

- **`fMRI_resting_state_workflow`** (`zstats_2_ref`): same change —
  `registration=workflow.reg_2_ref`, resolved engine, unchanged filenames.

- **`MainWorkflow`:** thread `synth_config`
  (`self.global_config[GlobalPrefCategoryList.SYNTH]`), `max_cpu`,
  `multicore_node_limit`, `test_run` into `launch_fMRI_task_analysis` and
  `launch_fMRI_resting_state_analysis` calls (dti already passes these).

### §2 — resting_state func→ref→mni concatenation under ANTS

The AROMA branch resamples the `feature_spatial_prep` func image into MNI space.

- **FSL / SYNTH→FSL branch:** unchanged — `ConvertWarp` combines
  `reg_2_ref.out_matrix_file` (premat) + `ref_2_mni` warp (warp1), then
  `apply_registration_node(engine=FSL, non_linear=True, warp=[convert_warp,
  "out_file"], ...)`.

- **ANTS branch:** no `ConvertWarp`. Stack an ordered `transformlist` and apply
  once. ANTs applies a list right-to-left and each transform maps output→input,
  so to resample the moving func image into MNI output space the order is
  ref→mni first, then func→ref:

  ```
  transformlist   = [ <ref→mni forward: warp, affine>, <func→ref affine> ]
  which_to_invert = [ <ref→mni fwd flags...>,          <func→ref flag>    ]
  ```

  - `ref_2_mni` is a **nonlinear** `AntsRegistration` built in this workflow → its
    wrapper exposes `fwd_transforms` (`[warp, affine]`) + `fwd_which_to_invert`.
    Feed the **raw list** directly into the stack (no `AntsComposeTransform`
    needed — it is not a MainWorkflow boundary; raw-list stacking avoids an extra
    node). `ref_2_mni` → `resolve_registration_engine(allow_ants=True)`,
    `SYNTH → FSL`; keep `flirt_cost="corratio"`, `flirt_search=90`,
    `non_linear=True`.
  - `reg_2_ref` (§1) is **linear** → its wrapper's affine + `which_to_invert`.

- **Abstraction support (multi-warp apply path):** extend
  `apply_registration_node` with an ANTS multi-warp path that accepts an ordered
  list of warp sources `[(node, field), ...]` plus their invert-flag sources and
  builds the `Merge`→`transformlist` + `which_to_invert` wiring internally, so the
  workflow stays declarative and the ordering is tested once in the abstraction.
  This multi-warp path is **ANTS-only** (used solely by the resting concat); the
  existing single-field boundary path and wrapper (`registration=`) paths are
  unchanged. This is the one order/direction-sensitive spot — it gets a heavy
  round-trip guard.

### §3 — Diffusion flip + tractography externalization

#### `dti_preproc_workflow`

- Lift the pin: `engine = resolve_registration_engine(synth_config,
  allow_ants=True)`; `SYNTH → FSL`.
- `dif2ref` (diff→ref, linear, `inverse=True`) → under any engine yields the
  diff↔ref transform via the abstraction wrapper (forward + inverse transform
  lists + `which_to_invert`).
- **Delete the `if engine == RegistrationEngine.SYNTH: LTAConvert` block.** No
  consumer needs an FSL `.mat` anymore (probtrackx transforms are externalized).
- **Change the `outputnode` diff↔ref contract** from FSL `.mat`
  (`diff2ref_mat`, `ref2diff_mat`) to the abstraction transform representation for
  each direction — the ordered transform list + `which_to_invert` (forward:
  diff→ref; inverse: ref→diff). Suggested fields: `diff2ref_transforms`,
  `diff2ref_which_to_invert`, `ref2diff_transforms`, `ref2diff_which_to_invert`
  (final field names decided in the plan; keep names descriptive of the ANTs-space
  content). `fa_2_ref` already applies via the abstraction and flips cleanly.
- `bedpostx` is unaffected (runs in diffusion space).

#### `tractography_workflow` (externalize uniformly, all engines)

- **`inputnode`:** replace `diff2ref_mat`/`ref2diff_mat` with the ref↔diff
  transform fields matching `dti_preproc`'s new `outputnode`. Keep `mni2ref_warp`
  (already ANTS from Phase 2).
- **ROIs MNI→diff (two sequential single-warp applies, engine-uniform):** each ROI
  (seed / target / exclude / stop) currently warps MNI→ref via `mni2ref_warp`
  (`apply_registration_node(non_linear=True, labelmap=True)`). Add a **second**
  single-warp apply ref→diff using the ref→diff transform from `dti_preproc`
  (`non_linear=False`, `labelmap=True`, nearestNeighbor). Two NN resamples of a
  label mask ≈ one (sub-voxel). Both applies are already supported on all three
  engines by the existing abstraction, so **no cross-engine multi-warp stacker is
  needed here** (the §2 multi-warp path is ANTS-only and unrelated).
- **probtrackx in diffusion space:** drop the `xfm`/`inv_xfm` connections; set
  `seed_ref` to the diffusion b0 brain (`nodif_brain`, diffusion space) instead of
  `reference_brain`. All seed / waypoint / avoid_mp / stop_mask inputs are now the
  diffusion-space ROIs. bedpostx samples are already diffusion-space. probtrackx
  is handed no matrix (identity transform).
- **Results back to reference:** `SumMultiTracks` sums `fdt_paths` **in diffusion
  space** (per side / per direct+inverted), then **one** `apply_registration_node`
  per side warps the summed density diff→ref (`non_linear=False`, linear
  interpolation — a probabilistic density, not a label map). `waytotal` is a
  space-independent scalar count, unchanged. Preserve output filenames
  (`r-<tract>_<side>.nii.gz`) and `outputnode` field names.
- **New `inputnode` need:** the diffusion b0 brain (`nodif_brain`) as `seed_ref`,
  and possibly the diffusion reference for the diff→ref result warp — thread from
  `dti_preproc` (it already outputs `nodiff_mask_file`; add the b0 brain image if
  not already exposed).
- **`MainWorkflow`:** update the tractography connections
  (`inputnode.diff2ref_mat`/`ref2diff_mat` → the new transform fields;
  `mni2ref_warp` unchanged) and add the diffusion-space `seed_ref` source, all
  atomically.

### §4 — Pins + version

- Remove the "Stick to FSL intentionally avoiding synth for reproducibility
  reason" comments at the three EPI sites.
- Bump `__version__` (per `swane/__init__.py`). No `force_pref_reset` change.

## Data flow (preserved contracts)

- Result filenames (`r-FA.nii.gz`, `r-<tract>_<side>.nii.gz`, fMRI cluster /
  zstat names), Slicer mappings, preference keys, workflow/node names for sinked
  results, and `outputnode` result fields that are **sinked** (`FA`,
  `fdt_paths_*`, `waytotal_*`, fMRI thresholds, `thresh_zstat_files`, `mel_mix`)
  are preserved.
- The diffusion diff↔ref `outputnode` fields change **format and name** (FSL
  `.mat` → ANTs transform list); they are internal MainWorkflow↔tractography
  wiring, updated atomically in this phase (mirrors Phase 2 changing
  `nonlinear_reg`'s `fieldcoeff_file` format). They are not sinked and not
  persisted preferences.

## Testing (committed — software regression only)

- **Abstraction/node tests:** the ANTS multi-warp apply path (transformlist order
  + `which_to_invert` assembly, `Merge` wiring); `fMRI_preproc` func→ref exposure
  (`workflow.reg_2_ref` present and of the right shape per engine).
- **Graph/matrix (all three engines, ANTS default):** `fMRI_preproc`,
  `fMRI_task`, `fMRI_resting_state` (incl. the ANTS concat stack vs. FSL
  `ConvertWarp`), `dti_preproc` (externalized, no `LTAConvert`), `tractography`
  (externalized: no `xfm`/`inv_xfm`, diffusion-space probtrackx, diff→ref result
  warp). Regenerate goldens and **review every diff by eye**.
- **Heavy direction guards:** round-trip for the resting concat transformlist
  (composed/stacked apply ≈ sequential apply); equivalence guard that externalized
  tractography ROIs land in the same diffusion voxels as the prior `.mat` path.
- **Local throwaway oracle (never committed):**
  - Re-run the **fMRI→T1** oracle on more cases than the two used in Phase 2
    (user directive; EPI is weakest evidence). Faithful to
    `fMRI_preproc.flirt_2_ref` (RobustFOV on the T1 reference only).
  - New **DTI** oracle: externalized tracts ≈ current `.mat`-path tracts (the
    `fdt_paths`-resample concern) for **both** FSL and ANTS.
- **Prerelease `plan.py`:** extend so the ANTS default exercises EPI + externalized
  DTI/tractography end-to-end; gate ANTS passes on the `antspyx` capability.
- **State explicitly** in results what was NOT scientifically validated
  (ANTs-vs-FSL / externalized-vs-native equivalence — the oracle's job and the
  user's acceptance).

## Cross-platform

OS-agnostic Python; format changed files with Black; RAM floors route through
`get_os_type()`. macOS is not runnable in the dev environment; changes must stay
OS-neutral and be reviewed for macOS correctness.

## Session orchestration + models

Six separate sessions. **A**, **B**, **D** are independent (parallel-capable).
**C** depends on A+B. **E** depends on D. **F** depends on C+E. After each session
the executing session reports to the orchestrator at the named checkpoint and
waits.

| Session | Scope | Depends on | Model | Why |
|---|---|---|---|---|
| **A — multi-warp apply path** in `apply_registration_node` + round-trip guard | abstraction | — | **Opus 5** | The EPI-concat mechanism: transformlist order / direction / `which_to_invert` — silent-scientific-bug territory |
| **B — `fMRI_preproc`** func→ref exposure + flip + thread `synth_config` | EPI producer | — | **Opus 4.8** | Exposure refactor + pin lift |
| **C — `fMRI_task` + `fMRI_resting_state`** consumer flips; resting concat via A | EPI consumers | A, B | **Opus 5** | The EPI transformlist concat (the one truly critical Phase-3 part) |
| **D — `dti_preproc`** flip + outputnode→transform-list + delete `LTAConvert` | DTI producer | — | **Opus 4.8** | Contract change + pin lift |
| **E — tractography externalization** (diffusion-space probtrackx, diff→ref warp-back) | DTI consumer | D | **Opus 4.8** | Fiddly ROI/space restructure; oracle-guarded |
| **F — snapshots + prerelease + version** | tests | C, E | **Sonnet 5** | Golden regen/review + prerelease + version bump |

**Feedback checkpoints (report to orchestrator, then wait):**

- **CP-A:** multi-warp apply path builds the correct `Merge`/`transformlist`/
  `which_to_invert`; round-trip guard green. Orchestrator reviews order/direction
  before C consumes it.
- **CP-B:** `fMRI_preproc` builds under all engines (SYNTH→FSL); `workflow.reg_2_ref`
  exposed; FSL construction unchanged.
- **CP-C:** `fMRI_task`/`resting` construct under ANTS with correct func→ref applies
  and the ANTS concat stack; FSL/SYNTH→FSL still green.
- **CP-D:** `dti_preproc` constructs under all engines; new outputnode transform
  fields; `LTAConvert` gone; FA apply green.
- **CP-E:** tractography constructs under all engines with diffusion-space probtrackx
  (no `xfm`/`inv_xfm`), MNI→diff ROI applies, and diff→ref result warps; filenames
  preserved.
- **CP-F:** all matrix snapshots regenerated + reviewed by eye; prerelease smoke
  green under ANTS default for EPI + DTI/tractography. Orchestrator closes Phase 3.

## Global constraints (unchanged from Phase 1/2)

- Python only via the SWANe env interpreter; `pytest -p no:datalad`. Verify with
  `python -c "import sys; print(sys.executable)"`. Never FSL's `fslpython` /
  FreeSurfer's `fspython`. On the new system the env must be recreated first
  (orchestrator prompt covers this).
- antspyx via the `ants` Python import only. Never ANTs binaries, never
  `nipype.interfaces.ants`. Do not vendor/copy antspyx or ANTs source. Exact
  antspyx API verified against the installed version before writing call bodies.
- Preserve stable contracts: persisted preference keys/section names, enum member
  names, workflow/node names, sinked result field names, deterministic result
  filenames, Slicer mappings.
- Preserve image header/affine/orientation/dtype (nibabel discipline).
- "subject" not "patient"; no clinical/medical framing; English only.
- A passing test is software-regression evidence only, never scientific/clinical
  validation. The comparative oracle is a local throwaway tool, never committed.
- Code runs on Ubuntu and macOS; format changed Python with Black.
- Stay on branch `claude/ants-registration`; never commit/push/merge/PR unless the
  user explicitly asks. Each session rebases onto the latest orchestrator-merged
  state before starting; commit per task.

## Open questions / to confirm during implementation

1. Exact antspyx apply / transformlist / `whichtoinvert` call shapes for the
   multi-warp stack (§2), verified against the installed antspyx.
2. Whether `dti_preproc` already exposes a diffusion b0 brain image suitable as
   probtrackx `seed_ref`, or a new outputnode field is needed (§3).
3. Final `outputnode` field names for the diffusion diff↔ref transform lists.
4. probtrackx behavior with no `xfm`/`inv_xfm` (identity) and `seed_ref` in
   diffusion space — confirmed against the installed FSL probtrackx during E.
5. Whether attaching `reg_2_ref` as an attribute on `CustomWorkflow` is safe, or
   the `reg_outputnode` `IdentityInterface` fallback is needed (§1).
