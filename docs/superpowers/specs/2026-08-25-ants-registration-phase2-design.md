# ANTs (antspyx) registration backend — Phase 2 design

Status: draft for review
Date: 2026-08-25
Branch: `claude/ants-registration`

## Context

Phase 1 added antspyx as a third registration backend (`engine` enum
`{FSL, SYNTH, ANTS}`, default `ANTS`) and flipped **only** `linear_reg_workflow`
to the ANTs default. `nonlinear_reg_workflow` and every cross-modality / EPI /
DTI workflow stayed pinned to FSL via `resolve_registration_engine(..., allow_ants=False)`,
because their transform consumers had not been ported to ANTs.

The Phase 1 call-site audit
(`docs/superpowers/specs/2026-08-24-ants-phase1-callsite-audit.md`) established
the reason the nonlinear pin exists: `nonlinear_reg`'s `fieldcoeff_file` /
`inverse_warp` outputs are read **FSL-specifically** by `flat1`, `func_map`
(ASL/PET AI) and `tractography`, each feeding the warp straight into an FSL
`ApplyWarp` node. Flipping `nonlinear_reg` to ANTs without porting those
consumers would hand FSL `ApplyWarp` a file it cannot read — a silent, hard
cross-backend break.

**Phase 2 lifts the nonlinear FSL pin** by porting those three consumers, and
**moves the cross-modality CT workflows off their FSL scientific pin** so the
whole cross-modality / nonlinear surface follows the configured engine (ANTs by
default).

### Scope (this spec)

In scope:

- **Nonlinear-warp boundary port:** `nonlinear_reg_workflow` (producer) and its
  three boundary consumers `flat1_workflow`, `func_map_workflow` (ASL/PET AI
  branch), `tractography_workflow` (`mni2ref_warp`). Lift `allow_ants=False` →
  `True` on all four; they flip to the ANTs default together (atomic flip).
- **Cross-modality CT:** `venous_ct_workflow`, `seeg_ct_workflow`. Route their
  direct FLIRT / ApplyXFM through the registration abstraction and remove the
  `# FLIRT performs better on CT` scientific pin, so CT follows the global
  engine (ANTs default). Confirmed research decision (user, 2026-08-25).
- **Abstraction:** `AntsComposeTransform` node + a single-field ANTs apply path
  in `apply_registration_node`; optional `moving_mask` on `AntsRegistration`.

Out of scope (deferred to Phase 3):

- EPI (`fMRI_preproc`/`fMRI_task`/`fMRI_resting_state`) and DTI
  (`dti_preproc`) registration remain FSL. In particular
  `fMRI_resting_state`'s func→ref→mni concatenation (FSL `ConvertWarp`) and the
  probtrackx FSL `.mat` bridge (`dti_preproc`'s `diff2ref_mat`/`ref2diff_mat`)
  stay on FSL. Tractography still flips its `mni2ref_warp` consumption to ANTs;
  it only *passes through* the diffusion `.mat` (produced by `dti_preproc`) into
  probtrackx, so it does not need the ANTs→FSL `.mat` bridge.
- The ANTs affine → FSL `.mat` bridge (`AntsAffineToFSL`; antspyx exposes
  `ants.fsl2antstransform` and the inverse direction for it) — Phase 3.
- No ANTs-based brain extraction. `get_deskull_node` is unchanged.

### Non-goals

- No claim of scientific/clinical validation. Committed tests are software
  regression evidence only; the real-data ANTs-vs-FSL comparison (see
  "Comparative oracle") is quality evidence for the user's own scientific
  acceptance decision, never clinical validation.

## Decisions already made (with the user)

1. **Boundary representation: Approach A — composed single field.** The producer
   composes the ANTs ordered transform list `[warp, affine]` into a single
   directional displacement field per direction, so the workflow boundary stays
   1:1 with today (one file per warp field). `which_to_invert` is resolved once
   at the producer and never crosses the boundary. Rationale and compatibility
   check with dti/tractography/fmri chains recorded below.
2. **Nonlinear default flips to ANTS** (atomic with its three consumers).
3. **CT follows the global engine** (ANTs default); the `# FLIRT performs better
   on CT` pin is removed. The comparative oracle validates this on real data.
4. **seeg_ct electrode weighting → ANTs `moving_mask`.** The existing binary
   electrode weight map (0 on electrodes, 1 elsewhere, in moving/seeg space)
   maps to `ants.registration(moving_mask=...)`; there is no antspyx analogue of
   FSL `FLIRT.in_weight`.
5. **Comparative oracle is a local, throwaway tool** — never committed to SWANe
   nor pushed to GitHub. It tunes parameters and validates ANTs-vs-FSL quality
   locally; the committed suite carries only software-regression tests.
6. **No new `force_pref_reset`.** The `engine` preference already exists and
   defaults ANTS since Phase 1; Phase 2 changes no preference default, it only
   makes more workflows honour the existing one. Users who explicitly chose FSL
   keep it. `__version__` is bumped for the release.

## Why Approach A stays compatible with chained workflows

The only transform *concatenation* in the affected surface is inside
`fMRI_resting_state_workflow` (func→ref linear `.mat` as `premat` + ref→mni
nonlinear warp as `warp1`, combined by FSL `ConvertWarp`). It is self-contained
(the workflow builds both registrations itself, both hardcoded FSL) and **does
not consume the MainWorkflow nonlinear-warp boundary**; it is Phase 3. Composing
the nonlinear warp into a single field does not prevent later stacking: a
composed displacement field is itself a valid transform and can be placed in an
`AntsApplyTransforms.transformlist` alongside other transforms when Phase 3
ports EPI. Every Phase-2 boundary consumer applies the nonlinear warp **alone**
(flat1, func_map AI, tractography), so a single composed field is exactly right.
No consumer needs the nonlinear registration's affine component in isolation
(the affine concatenated in resting_state comes from a *separate* linear
registration, not from `nonlinear_reg`).

## Architecture

### 1. New node: `AntsComposeTransform`

`swane/nipype_pipeline/nodes/AntsComposeTransform.py`, a native `BaseInterface`
wrapping antspyx (Python import only; never ANTs binaries / `nipype.interfaces.ants`).

- Inputs: `transformlist` (List of File, mandatory, ordered as antspyx expects),
  `which_to_invert` (List of Bool, optional), `reference_image` (File, exists,
  mandatory — defines the output field grid/space), `num_threads` (Int, nohash).
- Output: `out_field` (File, absolute path — a single displacement field).
- `_run_interface`: composes the list into one displacement field via
  `ants.apply_transforms(fixed=reference, moving=reference, transformlist=...,
  whichtoinvert=..., compose=<prefix>)` (exact call/return verified against the
  installed antspyx before writing the body — the compose route returns a
  composite-transform path). Preserve header/affine/orientation/dtype
  discipline (nibabel) for any image written.

> API note: the antspyx `compose=` return shape, and whether
> `transform_to_displacement_field` / `compose_ants_transforms` is the cleaner
> primitive, MUST be verified against the pinned antspyx during implementation.
> This spec states intended behavior, not verified call syntax.

### 2. `AntsRegistration` gains an optional `moving_mask`

`swane/nipype_pipeline/nodes/AntsRegistration.py`: add `moving_mask` (File,
exists, optional). When defined, pass it to `ants.registration(moving_mask=...)`
(verify the exact kwarg name against the installed antspyx). Undefined leaves
current behavior byte-identical (no golden-snapshot churn for existing ANTs
scenarios). Used only by `seeg_ct`.

### 3. Abstraction (`swane/nipype_pipeline/nodes/utils.py`)

- **`get_registration_node`** gains an optional `moving_mask: list[Node|str]`
  parameter; on the ANTS branch it connects/sets `AntsRegistration.moving_mask`.
  FSL/Synth ignore it (FSL's equivalent, `FLIRT.in_weight`, stays wired only on
  the FSL branch if a caller needs it — see seeg_ct below).
- **`apply_registration_node`** ANTS branch accepts a bare `warp=[node, field]`
  (a single composed field crossing a workflow boundary) with **no**
  `registration` wrapper: it builds `AntsApplyTransforms(transformlist=[warp])`
  and sets **no** `which_to_invert` (the composed field is already directional).
  The existing wrapper path (`wire_transforms`, used for same-workflow
  multi-transform cases such as `linear_reg` internals and future Phase-3
  chains) is preserved unchanged. Selection: if `registration` is provided use
  the wrapper path; else use the single-field path.
- No signature change for FSL/Synth branches.

### 4. Producer: `nonlinear_reg_workflow`

- `resolve_registration_engine(synth_config, allow_ants=True)` (pin lifted).
- FSL/Synth branches: unchanged (still emit `fieldcoeff_file` / `inverse_warp`
  as single FNIRT/SynthMorph warps).
- ANTS branch: after `get_registration_node` (which yields the wrapper with the
  ordered transform lists + `which_to_invert` in scope), add two
  `AntsComposeTransform` nodes:
  - forward: `reference_image = atlas` (inputnode `atlas`), `transformlist` /
    `which_to_invert` from `reg_wrap.fwd_transforms` / `fwd_which_to_invert`
    → `outputnode.fieldcoeff_file`.
  - inverse: `reference_image = in_file` (inputnode `in_file`), from
    `reg_wrap.inv_transforms` / `inv_which_to_invert`
    → `outputnode.inverse_warp`.
- Outputnode field **names and cardinality preserved** (`fieldcoeff_file`,
  `inverse_warp`, `warped_file`); only the file *format* changes under ANTS.

### 5. Consumers (nonlinear-warp boundary)

Each: `allow_ants=False` → `True`. Their existing apply calls already pass
`warp=[inputnode, "<field>"]`; via §3 those now route to
`AntsApplyTransforms(transformlist=[warp])` under ANTS. No MainWorkflow
connection changes (boundary fields keep name + single-file cardinality).

- **`flat1_workflow`**: 7 applies (flair/restore/gm/wm forward via
  `ref_2_mni1_warp`; extension/junction/binary inverse via
  `ref_2_mni1_inverse_warp`).
- **`func_map_workflow`** (AI branch): `ref_2_sym_warp` forward,
  `ref_2_sym_invwarp` inverse. The func→ref linear reg already flows through the
  abstraction; lifting the pin lets it and the AI applies follow ANTs together.
- **`tractography_workflow`**: `mni2ref_warp` applied to seed/target/exclude/stop
  ROIs, `labelmap=True` → `nearestNeighbor`. The diffusion `.mat`
  (`diff2ref_mat`/`ref2diff_mat`) is untouched and still flows FSL-format into
  probtrackx (Phase 3 owns that bridge).

### 6. Cross-modality CT

Route direct FLIRT/ApplyXFM through the abstraction with
`engine = resolve_registration_engine(synth_config, allow_ants=True)`; remove the
`# FLIRT performs better on CT` pin.

- **`venous_ct_workflow`**:
  - `basal_2_ref` (basal→reference, volumetric linear, dof=6, cost mutualinfo)
    → `get_registration_node(non_linear=False, is_volumetric=True)`.
  - `contrast_2_basal` (contrast→basal) is a **MapNode** (iterfield `in_file`):
    routing through the abstraction must preserve the per-input iteration.
    Either keep it a direct FLIRT MapNode on the FSL branch and add an ANTS
    MapNode branch, or extend the abstraction to build a MapNode; the plan
    picks the least-invasive option that preserves iteration and the reused
    `.mat`/transform downstream.
  - final `veins_2_ref` (`ApplyXFM`) → `apply_registration_node(non_linear=False)`
    fed by the `basal_2_ref` forward transform.
- **`seeg_ct_workflow`**:
  - `seeg_ct_2_ref_flirt` (seeg→reference, volumetric linear) →
    `get_registration_node`, passing the electrode weight map as `moving_mask`
    on the ANTS branch (§2/§3) and as `in_weight` on the FSL branch. Verify the
    binary weight map (0 on electrodes) is the correct polarity for an ANTs
    metric mask (mask = region to register on).

Preserve every workflow/node name, deterministic result filename, boundary
field, Slicer mapping, and preference key.

## Comparative oracle (local, never committed)

A throwaway local script (lives outside the repo — e.g. `~/test_swane/` or a
scratchpad — and is **never** added to SWANe or GitHub). It reads the real,
pre-converted volumes in `~/test_swane/ant_phase2_data/` (real data, never in
source control) and, per modality→T1 pair present (ct veins, ct seeg, pet, asl;
dti/fmri present but Phase 3):

- registers moving→T1 with both FSL and ANTs,
- computes an overlap/similarity metric in the common region (brain-mask Dice /
  correlation, consistent with the Phase-1 `registration.overlap.*` 0.90 gate),
- reports the per-modality metric ANTs vs FSL.

Purpose: tune parameters (metric mapping, `transform_type` choices, composition
correctness) and give the user quality evidence for the CT-pin removal and the
nonlinear flip. This is real-data comparison + software evidence, **not clinical
validation**; scientific acceptance is the user's.

## Testing (committed — software regression only)

- **Node unit tests**: `AntsComposeTransform` (traits/defaults, `_list_outputs`
  absolute path, direction/`which_to_invert` handling, header preservation, with
  antspyx mocked; one `heavy`-gated real compose smoke). `AntsRegistration`
  `moving_mask` (accepted, undefined → unchanged behavior).
- **Abstraction tests**: `apply_registration_node` ANTS with bare
  `warp=[node,field]` → `AntsApplyTransforms(transformlist=[warp])`, no
  `which_to_invert`; wrapper path still builds. `get_registration_node`
  `moving_mask` wiring on ANTS.
- **Round-trip correctness test** (the #1 risk): for a synthetic phantom,
  compose the nonlinear forward/inverse transforms then apply the composed field,
  and assert it matches applying the raw transform list with the correct
  `which_to_invert` (within tolerance). Guards composition direction/space.
- **Graph/snapshot (matrix)**: `nonlinear_reg` default scenario flips FSL→ANTS
  (with the two compose nodes); `flat1`/`func_map`/`tractography`/`venous_ct`/
  `seeg_ct` get ANTS default scenarios; regenerate and **review every diff by
  eye** for correct nodes/connections/filenames. Keep FSL/SYNTH construction
  coverage for all.
- **Prerelease smoke** (opt-in, real tools incl. antspyx, disposable
  `~/test_swane/prerelease`): extend the plan so the ANTS-default passes now
  exercise nonlinear + CT end-to-end; keep the synthetic-phantom overlap gates.

State explicitly in results what was **not** validated (scientific/clinical
equivalence of ANTs vs prior backends).

## Cross-platform

OS-agnostic Python; format changed files with Black; RAM floors route through
`get_os_type()`. macOS is not runnable in the dev environment here; changes must
stay OS-neutral and be reviewed for macOS correctness.

## Open questions / to confirm during implementation

1. antspyx `compose=` return shape and the cleanest composition primitive
   (`apply_transforms(compose=)` vs `transform_to_displacement_field` /
   `compose_ants_transforms`); exact `moving_mask` kwarg name.
2. `venous_ct` `contrast_2_basal` MapNode routing that preserves iteration.
3. seeg electrode weight-map polarity as an ANTs metric mask.
4. Composed-field direction/space correctness (fwd fixed=atlas, inv
   fixed=in_file) — validated by the round-trip test and the oracle.
