# ANTs (antspyx) registration backend — Phase 1 design

Status: draft for review
Date: 2026-08-24
Branch: `claude/ants-registration`

## Context

SWANe performs image registration through two interchangeable backends,
selected inside `swane/nipype_pipeline/nodes/utils.py` by the boolean
`use_synth`:

- **FSL**: `FLIRT` (linear), `FLIRT`+`FNIRT` (nonlinear), `InvWarp`/`ConvertXFM`
  for the inverse transform, `ApplyWarp`/`ApplyXFM` to resample.
- **Synth**: `SynthMorphReg`/`SynthMorphApply` (plus `SynthStrip` for brain
  extraction).

The abstraction exposes three helpers — `get_registration_node`,
`apply_registration_node`, `get_deskull_node` — returning a
`RegistrationNodeWrapper` carrying a single forward `warp` and a single
`inv_warp`. Only two workflows consume this abstraction today:
`linear_reg_workflow` and `nonlinear_reg_workflow`. Other workflows
(EPI: fMRI/DTI; cross-modality: venous_ct, seeg_ct, mdc) call FSL directly
and concatenate transforms in FSL-native formats.

This project adds a **third backend based on antspyx** (the Python library,
**never** the ANTs binaries and **never** `nipype.interfaces.ants`, which
shells out to those binaries) and makes it the **default** for both linear
and nonlinear registration, preserving the existing direct/inverse logic and
transform concatenation semantics.

The work is decomposed into phases. **This spec covers Phase 1 only.**

### Overall phasing (context, not all in scope here)

- **Phase 1 (this spec):** antspyx Nipype nodes, backend-aware abstraction in
  `utils.py`, the `engine` preference enum + dependency/RAM gating + config
  reset + wizard update + `setup.py`/`DependencyManager`/`ResourceManager`
  wiring, and conversion of the two abstracted workflows
  (`linear_reg_workflow`, `nonlinear_reg_workflow`). No probtrackx bridge yet.
- **Phase 2:** cross-modality PET/CT (`venous_ct`, `seeg_ct`, `mdc`, `flat1`,
  `func_map`) — remove the CT→FLIRT scientific pin, express concatenations in
  ANTs transform space.
- **Phase 3:** EPI (`fMRI_preproc`/`resting_state`/`task`, `dti_preproc`) —
  remove the reproducibility pin, express `func→ref→mni` chains in ANTs space,
  add the ANTs-affine→FSL-mat bridge for probtrackx and other FSL-only
  consumers.

Each phase gets its own spec → plan → implementation → test cycle.

## Decisions already made (with the user)

1. Transform interop: **everything in ANTs transform space** — concatenations
   stack an ordered transform list via ANTs `apply_transforms` rather than
   summing FSL matrices. (Applies fully from Phase 2 onward; Phase 1 only needs
   the list-shaped abstraction to exist.)
2. Scope: **all** registrations eventually move to ANTs (default). Existing
   scientific pins to FSL follow the engine and are removed in the phase that
   touches them (Phases 2–3). Phase 1 does not remove any pin.
3. Backend selection: a single **`engine` enum** `{FSL, SYNTH, ANTS}`,
   default `ANTS`. Replaces only the `morph` boolean. `strip` (brain
   extraction) and `reconall` are unchanged.
4. Brain extraction is **unchanged** (BET/SynthStrip). `get_deskull_node` is
   not modified.
5. Migration: reuse the existing **`force_pref_reset` version mechanism** —
   bump the reset so existing configs reset to defaults (engine=ANTS on
   upgrade). No bespoke `morph`→`engine` value mapping. The setup wizard is
   updated to set `engine` instead of `morph`.
6. SynthMorph's RAM selectability requirement must be **preserved** in the new
   enum, via `option_pref_requirement`.

## Non-goals (Phase 1)

- No changes to EPI or cross-modality workflows.
- No probtrackx/FSL-only transform bridge (Phase 3).
- No ANTs-based brain extraction / antspynet.
- No claim of scientific/clinical validation. Tests are software regression
  evidence only; real-data scientific comparison of ANTs vs FSL/Synth output
  is out of scope and remains the user's responsibility.

## Architecture

### 1. New Nipype nodes (`swane/nipype_pipeline/nodes/`)

Native `BaseInterface` interfaces wrapping antspyx (Python), mirroring the
role of `SynthMorphReg`/`SynthMorphApply` but implemented in Python rather
than as `CommandLine`.

> API note: exact antspyx function signatures, return-dict keys
> (`fwdtransforms`, `invtransforms`, `warpedmovout`) and `type_of_transform`
> names must be **verified against the antspyx version pinned in `setup.py`**
> during implementation. This spec states intended behavior, not verified
> call syntax.

- **`AntsRegistration`**
  - Inputs: `moving` (File, exists, mandatory), `fixed` (File, exists,
    mandatory), `transform_type` (Enum — e.g. `Rigid`/`Affine` for linear,
    `SyN`/`SyNRA` for nonlinear), `metric`/cost (Enum, defaulted to preserve
    current cost intent — `mutualinfo`/`corratio` FSL costs map to ANTs
    `Mattes`/`CC`/`MI`; exact mapping decided in implementation and
    documented), `num_threads` (Int, nohash), optional `initial_transform`.
  - Outputs: `fwd_transforms` (list — for SyN `[warp, affine]`, ANTs order),
    `inv_transforms` (list), `warped_file`, and convenience scalars
    `affine_transform` / `warp_field` for callers that need one component.
  - `_run_interface` calls `ants.registration(...)`; `_list_outputs` returns
    absolute paths for the produced transform files. Preserve header/affine/
    orientation/dtype of images written (nibabel discipline).
- **`AntsApplyTransforms`**
  - Inputs: `input_image`, `reference_image`, `transformlist` (List, ordered),
    `interpolator` (Enum — `linear` default, `nearestNeighbor` for label maps),
    `whichtoinvert` (List[bool], optional), `out_file`.
  - Output: `out_file` (absolute path).
  - Wraps `ants.apply_transforms(...)`.

`AntsAffineToFSL` (ANTs affine → FSL `.mat`) is **not** built in Phase 1; it
belongs to Phase 3 (probtrackx bridge). Named here only to reserve the
boundary.

Threading: generalize the existing `get_synth_cpu_config` /
`apply_synth_num_threads` helpers into tool-neutral helpers so the ANTs nodes
reuse the same hard/soft CPU-cap logic, driving
`ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS` (and `num_threads`/`n_procs` for the
hard cap). RAM: static `mem_gb` plus a RAM estimator if input-size sensitive
(mirror the FLIRT/FNIRT estimators).

### 2. Backend-aware abstraction (`swane/nipype_pipeline/nodes/utils.py`)

- `RegistrationNodeWrapper` gains an ordered **transform list** representation
  and an `engine` tag while keeping `warp`/`inv_warp` for the FSL/Synth
  single-file case (a 1-element list). New attributes: `fwd_transforms`
  (node, field) list and `inv_transforms` (node, field) list. A small helper
  wires a wrapper's transforms into an apply node regardless of backend.
- `get_registration_node(...)`:
  - Signature changes from `use_synth: bool` to `engine: RegistrationEngine`.
  - Adds an `engine == ANTS` branch building `AntsRegistration` with
    `transform_type` derived from `non_linear`, and populating the wrapper's
    forward/inverse transform lists. FSL and Synth branches are preserved
    behaviorally (they now key off `engine` instead of the boolean).
  - `inverse=True` uses ANTs `invtransforms` directly (no separate InvWarp/
    ConvertXFM node needed).
- `apply_registration_node(...)`:
  - Becomes backend-aware. For `engine == ANTS`, builds `AntsApplyTransforms`
    with the ordered `transformlist`; `labelmap=True` selects
    `nearestNeighbor`. FSL/Synth branches unchanged.
- All existing callers that pass `use_synth=synth_config.getboolean_safe(...)`
  are updated to pass a resolved `RegistrationEngine`. A single resolver reads
  the `engine` preference (and honors any per-site pin argument, so Phases 2–3
  can pass explicit overrides — Phase 1 introduces the pin parameter but every
  Phase-1 call site simply follows the preference).

### 3. Configuration (`swane/config/`)

- `config_enums.py`: new `RegistrationEngine` enum with members `FSL`,
  `SYNTH`, `ANTS` and human-readable values.
- `preference_list.py`: under the existing `GlobalPrefCategoryList.SYNTH`
  category, replace the `morph` `PreferenceEntry` with an `engine` entry:
  - `input_type=InputTypes.ENUM`, `value_enum=RegistrationEngine`,
    `default=RegistrationEngine.ANTS`.
  - `option_dependency`: `ANTS` → antspyx-importable dependency check;
    `SYNTH` → `is_freesurfer_synth` (as today).
  - `option_pref_requirement`: `SYNTH` →
    `("ram_gb", synth_morph_ram_requirements())` (preserves current gating);
    `ANTS` → `("ram_gb", ants_ram_requirements())`.
  - `option_pref_requirement_fail_tooltip` for both.
  - The `strip` and `reconall` entries are untouched.
  - Category *label* stays `"Synth tools"` (its serialized key `synth` is a
    persistence contract); relabeling is cosmetic and deferred.
- Migration: bump the version-keyed `force_pref_reset` so existing global and
  subject configs reset to defaults on this upgrade. Confirm the mechanism in
  `ConfigManager` (`force_pref_reset` / `last_swane_version`) triggers as
  intended for `__version__` `0.2.1.1` → next.

### 4. Dependency, resources, packaging

- `setup.py`: add `antspyx` with a pinned version compatible with the existing
  `numpy==2.2.4` and `SimpleITK>=2.5.0`. Verify wheel availability for the
  supported Linux and macOS targets.
- `DependencyManager`: add an `is_antspyx()` (importability) check used by the
  `engine` option-dependency and by wizard availability. antspyx is a pure
  Python import, not a system executable — no version-of-binary detection.
- `ResourceManager`: add `ants_ram_requirements()` (and any min-RAM helper the
  wizard needs), analogous to the synth RAM helpers.
- Licensing: antspyx is Apache-2.0 and is a runtime dependency only (imported,
  never embedded/copied). No `NOTICE.md` change is required for depending on
  it; no ANTs/antspyx source is vendored.

### 5. Setup wizard (`swane/ui/PreferenceWizardWindow.py`)

- Where the wizard currently sets `GlobalPrefCategoryList.SYNTH["morph"]` from
  `use_advanced_models` + RAM, it instead sets `engine`:
  - Default target `ANTS` when antspyx is available and RAM meets the ANTs
    requirement.
  - `SYNTH` remains selectable only when FreeSurfer Synth is available and RAM
    meets `synth_morph_ram_requirements()` (preserved gating), gated behind the
    same "advanced models" opt-in.
  - Fall back to `FSL` otherwise.
- Update the wizard availability/summary text that references SynthMorph so it
  reflects the engine choice. `strip`/`reconall` wizard logic is unchanged.

## Data flow (unchanged contracts)

`linear_reg_workflow` and `nonlinear_reg_workflow` keep their factory
signatures, boundary node names, output field names
(`registered_file`, `registered_file_brain`, `out_matrix_file`,
`fieldcoeff_file`, `inverse_warp`, `warped_file`, …), and deterministic
filenames. Internally, the transform carried by `out_matrix_file` /
`fieldcoeff_file` becomes an ANTs transform when `engine == ANTS`. Because
Phase 1 does not touch downstream FSL-format consumers, and both abstracted
workflows sink their outputs as images (resampled files) plus a transform
output, the transform-output *field names* are preserved but their *format*
is backend-dependent — any Phase-2/3 consumer that reads those transform
fields must handle the ANTs format (tracked as a Phase 2/3 boundary, not a
Phase 1 regression, because current consumers of these two workflows use the
resampled image outputs, to be confirmed in the call-site audit below).

### Call-site audit (Phase 1 acceptance sub-task)

Before implementation, enumerate every consumer of
`linear_reg_workflow`/`nonlinear_reg_workflow` outputs in `MainWorkflow` and
downstream, and classify each output use as (a) resampled image (format-
agnostic, safe in Phase 1) or (b) transform-format-dependent (must be deferred
to the phase that handles its consumer, or gated so Phase 1 doesn't ship a
broken cross-backend path). If any current consumer of these two workflows
reads a transform field in an FSL-specific way, the affected connection is
listed and its resolution decided (bridge now vs. keep that specific site on
FSL until its phase). This audit is part of Phase 1 and its result is recorded
in the implementation plan.

## Testing (Phase 1)

- **Node unit tests**: Traits defaults/validation, generated output paths, and
  `_list_outputs` for `AntsRegistration`/`AntsApplyTransforms`, with antspyx
  calls mocked where a real run is unavailable; one real-tool smoke test gated
  behind `--run-heavy` when antspyx is installed.
- **Abstraction tests**: `get_registration_node`/`apply_registration_node`
  produce the expected node types and wrapper transform lists for each of the
  three engines; FSL/Synth branches unchanged.
- **Graph tests**: construct `linear_reg_workflow` and `nonlinear_reg_workflow`
  with `engine=ANTS` and assert node identities, connections, boundary fields,
  and deterministic output names; keep the FSL/Synth constructions green.
- **Config tests**: `engine` default is `ANTS`; option dependency/RAM gating
  behaves (SYNTH gated on FreeSurfer Synth + RAM; ANTS gated on antspyx + RAM);
  `force_pref_reset` resets an old-version config.
- **Golden snapshots**: update `swane/tests/nipype_pipeline/matrix` snapshots
  for the two workflows under the new default
  (`SWANE_SNAPSHOT_UPDATE=1 pytest swane/tests/nipype_pipeline/matrix`) and
  review the diff for correctness, not just green.
- **Prerelease** (`python -m swane.tests.prerelease`, opt-in, real tools incl.
  antspyx, disposable `~/test_swane/prerelease`): run once the nodes exist to
  confirm the two workflows execute end-to-end with the ANTs default.

State explicitly in the results what was **not** validated (scientific/clinical
equivalence of ANTs vs prior backends).

## Cross-platform

- Verify antspyx installs and imports on the supported Ubuntu and macOS
  targets; make thread-env handling platform-neutral. Run the light suite on
  both where possible, per the project's Linux+macOS requirement.

## Open questions / to confirm during implementation

1. Exact antspyx `type_of_transform` values and cost/metric mapping from the
   current FSL `mutualinfo`/`corratio` intent (documented in code once chosen).
2. antspyx pinned version and its numpy/SimpleITK compatibility on both OSes.
3. Result of the call-site audit (which, if any, transform-field consumers of
   the two abstracted workflows must be handled or gated in Phase 1).
