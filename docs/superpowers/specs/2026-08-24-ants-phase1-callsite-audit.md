# ANTs Phase 1 — call-site audit (CP-C deliverable)

Date: 2026-08-24
Branch: `claude/ants-registration`
Scope: consumers of the two abstracted workflows'
(`linear_reg_workflow`, `nonlinear_reg_workflow`) **outputs**, classified as
either **(a) resampled-image use** — format-agnostic, safe under any engine — or
**(b) transform-field use** — reads an `out_matrix_file` / `fieldcoeff_file` /
`inverse_warp` output whose *content format* is backend-dependent (an FSL `.mat`
/ FNIRT warp today, an ANTs transform **list** when `engine == ANTS`).

This audit decides which of the two workflows may follow the ANTs default in
Group D and which must stay gated to FSL until a later phase ports its
consumers.

## Method

- Enumerated every `self.connect(<wf>, "outputnode.<field>", …)` in
  `MainWorkflow.py` sourced from a `linear_reg_workflow` instance
  (`self.flair`, `self.t2_cor`, `self.mdc`, `self.flair2d`) or a
  `nonlinear_reg_workflow` instance (`self.sym`, `self.mni1`).
- For each transform-field consumer, followed the field into the consuming
  workflow to see whether it is fed to an FSL `ApplyWarp`/`ApplyXFM`
  (FSL-specific) or merely re-saved / used as an image.
- Confirmed with `grep` that no `out_matrix_file` output of a linear_reg
  instance is connected or sinked anywhere.

## linear_reg_workflow

Output fields: `registered_file`, `registered_file_brain`, `out_matrix_file`,
`uncorrected_registered_file`, `uncorrected_registered_file_brain`.

| Consumer (MainWorkflow) | Output field | Kind | Verdict |
|---|---|---|---|
| `flat1.inputnode.flair_brain` ← `self.flair` | `uncorrected_registered_file_brain` | resampled image | (a) safe |
| `sink_result` of every `self.flair/t2_cor/mdc/flair2d` | `registered_file*`, `uncorrected_*` | resampled image (saved NIfTI) | (a) safe |
| — | `out_matrix_file` | transform | **not consumed** (no `connect`, no `sink_result`) |

**Result: linear_reg has NO transform-field consumer.** Its only downstream and
saved products are resampled images. It is **safe to default to ANTs** in Group
D — the ANTs transform list carried by `out_matrix_file` is produced but read by
nobody in Phase 1.

## nonlinear_reg_workflow

Output fields: `fieldcoeff_file`, `inverse_warp`, `warped_file`.

| Consumer (MainWorkflow → workflow) | Output field | Consuming call | Kind | Verdict |
|---|---|---|---|---|
| `self.mni1` → `flat1.ref_2_mni1_warp` | `fieldcoeff_file` | `apply_registration_node(non_linear=True)` → FSL `ApplyWarp.field_file` (×4: flair/restore/gm/wm) | transform-field, FSL | **(b) FSL-specific** |
| `self.mni1` → `flat1.ref_2_mni1_inverse_warp` | `inverse_warp` | FSL `ApplyWarp.field_file` (×3: extension/junction/binary) | transform-field, FSL | **(b) FSL-specific** |
| `self.sym` → `asl`/`pet` (`func_map`) `ref_2_sym_warp` | `fieldcoeff_file` | `func_map` `apply_registration_node(non_linear=True)` → FSL `ApplyWarp` | transform-field, FSL | **(b) FSL-specific** |
| `self.sym` → `asl`/`pet` (`func_map`) `ref_2_sym_invwarp` | `inverse_warp` | FSL `ApplyWarp` | transform-field, FSL | **(b) FSL-specific** |
| `self.mni1` → `tractography.mni2ref_warp` | `inverse_warp` | `tractography` `apply_registration_node(non_linear=True)` → FSL `ApplyWarp` | transform-field, FSL | **(b) FSL-specific** |
| `warped_file` | — | resampled image / sink only | (a) safe |

**Result: nonlinear_reg's `fieldcoeff_file` and `inverse_warp` are read
FSL-specifically** by `flat1`, `func_map` (ASL/PET AI) and `tractography`, each
of which passes the warp straight into an FSL `ApplyWarp` node (they resolve
their own engine with `allow_ants=False`, i.e. FSL/Synth, and never learned the
ANTs transform-list/`which_to_invert` contract). If `nonlinear_reg` emitted an
ANTs transform list under the ANTs default, those FSL `ApplyWarp` nodes would be
handed a file they cannot read — a **silent/hard cross-backend break**, not a
Phase-1 regression that any current test catches (the downstream workflows are
pinned to FSL, and their matrix snapshots stay green precisely because
nonlinear_reg is still pinned in the tests).

## Decision for Group D

- **linear_reg_workflow → may default to ANTs** (Group D flips it; its ANTs
  golden snapshots are added and reviewed in D3). No consumer gating needed.
- **nonlinear_reg_workflow → must stay on FSL in Phase 1.** Its warp outputs
  feed FSL `ApplyWarp` in `flat1`, `func_map` and `tractography`, none of which
  are ported in Phase 1. Two ways to honour this in D1:
  1. **(recommended, minimal)** the `MainWorkflow` engine resolver passes
     `linear_reg_workflow` the configured engine but pins
     `nonlinear_reg_workflow` to `RegistrationEngine.FSL` (an explicit Phase-1
     override), deferring its flip to the phase that ports flat1/func_map/
     tractography (Phase 2/3), where the ANTs-warp bridge is introduced; or
  2. build the ANTs→FSL warp bridge now for those three consumers — larger
     scope, explicitly deferred to Phase 3 by the spec ("probtrackx/FSL-only
     transform bridge (Phase 3)").

Option 1 keeps Phase 1 correct and matches the spec's phasing. Group D should
therefore flip **only** `linear_reg_workflow` to the ANTs default and keep
`nonlinear_reg_workflow` explicitly on FSL until its consumers are ported.

## Phase 2/3 feed-forward

The FSL-specific consumers to port (each needs its warp source expressed as an
ANTs transform list and applied via `AntsApplyTransforms` with the matching
`which_to_invert` flags):

- `flat1_workflow` (7 applies: flair/restore/gm/wm forward, extension/junction/
  binary inverse) — Phase 2.
- `func_map_workflow` (ASL/PET AI: `ref_2_sym_warp` forward, `ref_2_sym_invwarp`
  inverse) — Phase 2.
- `tractography_workflow` (`mni2ref_warp` inverse, ×4 seed/target/exclude/stop)
  — Phase 3.
- `dti_preproc_workflow` already special-cases the backend for the probtrackx
  `.mat` (`engine == SYNTH` → `LTAConvert`); the ANTs branch there is a Phase-3
  bridge target.
