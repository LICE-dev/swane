# ANTs (antspyx) Registration — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Each *session group* below is meant to run in its **own separate Claude Code session**; the session that produced this plan is the **orchestrator** and reviews the feedback checkpoints between groups.

**Goal:** Add antspyx as a third, default image-registration backend (engine enum FSL/SYNTH/ANTS) and wire it through the two abstracted registration workflows, without touching EPI/cross-modality workflows or downstream FSL-format consumers.

**Architecture:** A new pair of native Nipype `BaseInterface` nodes wraps the antspyx Python library (never ANTs binaries, never `nipype.interfaces.ants`). The existing `utils.py` registration abstraction becomes backend-aware and carries an ordered transform list. Backend choice moves from the `morph` boolean to an `engine` enum preference (default ANTS) with per-option RAM/dependency gating; existing configs reset to defaults via the existing `force_pref_reset` version mechanism.

**Tech Stack:** Python, Nipype 1.10.0, antspyx (new), nibabel, numpy 2.2.4, SimpleITK, PyQt (wizard), pytest.

**Spec:** `docs/superpowers/specs/2026-08-24-ants-registration-phase1-design.md`

## Global Constraints

- Any Python command (tests/exploration/app) MUST use SWANe's environment (conda `swane-env`), never FSL's `fslpython`/FreeSurfer's `fspython`. Verify with `python -c "import sys; print(sys.executable)"`. Run pytest with `-p no:datalad`.
- Never use the ANTs binaries or `nipype.interfaces.ants`; use the `antspyx` Python import only. Do not vendor/copy antspyx or ANTs source.
- Preserve stable contracts: persisted preference keys/section names, enum member names, workflow/node names, boundary field names, deterministic result filenames, Slicer mappings.
- Preserve image header/affine/orientation/dtype unless a node explicitly transforms them (nibabel discipline: `header.copy()` + `set_data_dtype(float32)` where applicable).
- Terminology: "subject" not "patient"; no clinical/medical framing. English only.
- A passing test is software regression evidence only — never scientific/clinical validation.
- Code must run on both Ubuntu and macOS. Format changed Python with Black; do not reformat unrelated files.
- antspyx exact API (function signatures, return-dict keys `fwdtransforms`/`invtransforms`/`warpedmovout`, `type_of_transform` names, interpolator names) MUST be verified against the installed antspyx version before writing call bodies. Where this plan shows an antspyx call, treat it as *intended behavior to verify*, not confirmed syntax.

---

## Session orchestration (the execution groups)

Four session groups. **A** and **B** are independent and may run in parallel. **C** depends on both A and B. **D** depends on C. After each group, the executing session reports back to this orchestrator session at the named checkpoint before the next group starts.

| Group | Scope | Depends on | Suggested model | Why |
|---|---|---|---|---|
| **A — Config & packaging foundation** | `RegistrationEngine` enum, `engine` preference (replaces `morph`) with per-option gating, `DependencyManager.is_antspyx`, `ResourceManager` ANTs RAM, `setup.py` dep, `force_pref_reset` bump, config tests | — | **Sonnet 5** | Mechanical, pattern-following; mirrors existing `freesurfer_step` enum + synth gating |
| **B — ANTs Nipype nodes** | `AntsRegistration`, `AntsApplyTransforms` + unit tests | — | **Opus 5** | The genuinely hard part: transform-list ordering, forward/inverse semantics, interpolation and header preservation are silent-scientific-bug territory and need antspyx-API verification |
| **C — Backend-aware abstraction + call-site migration** | Generalize CPU helpers, transform-list `RegistrationNodeWrapper`, `engine` branch in `get_registration_node`/`apply_registration_node`, `use_synth`→`engine` signature change across **all** callers, call-site audit | A, B | **Opus 4.8** | Cross-cutting refactor touching every registration call site; needs judgment but not novel difficulty |
| **D — Wire abstracted workflows + wizard + graph/snapshot tests** | `linear_reg_workflow`/`nonlinear_reg_workflow` on resolved engine, `MainWorkflow` resolver, wizard sets `engine`, graph tests, golden-snapshot update, optional prerelease smoke | C | **Sonnet 5** | Integration + test wiring, pattern-following |

**Feedback checkpoints (report to orchestrator, then wait):**
- **CP-A:** config tests green; show that `engine` default is ANTS and SYNTH/ANTS option gating behaves. Orchestrator confirms enum/pref shape before C consumes it.
- **CP-B:** node unit tests green; show `AntsRegistration` forward/inverse transform-list outputs and `AntsApplyTransforms` interpolation handling. Orchestrator reviews transform semantics (highest-risk item) before C consumes the node interfaces.
- **CP-C:** abstraction + call-site tests green; **deliver the call-site audit table** (which consumers of the two abstracted workflows read transform fields FSL-specifically). Orchestrator decides any gating needed and green-lights D. This audit also feeds Phase 2/3 planning.
- **CP-D:** graph tests green + golden-snapshot diff reviewed for correctness; report what was NOT scientifically validated. Orchestrator closes Phase 1.

Each session: create/checkout the shared branch `claude/ants-registration`, `git pull`/rebase onto the latest orchestrator-merged state before starting, and commit per task. The orchestrator merges/reviews between groups.

---

## File structure

**Create:**
- `swane/nipype_pipeline/nodes/AntsRegistration.py` — antspyx registration interface (Group B)
- `swane/nipype_pipeline/nodes/AntsApplyTransforms.py` — antspyx resampling interface (Group B)
- `swane/tests/nipype_pipeline/nodes/test_ants_registration.py` (Group B)
- `swane/tests/nipype_pipeline/nodes/test_ants_apply_transforms.py` (Group B)
- `swane/tests/config/test_registration_engine_pref.py` (Group A)

**Modify:**
- `swane/config/config_enums.py` — `RegistrationEngine` enum (Group A)
- `swane/config/preference_list.py` — `engine` entry replaces `morph`; `force_pref_reset` bump (Group A)
- `swane/utils/DependencyManager.py` — `is_antspyx()` (Group A)
- `swane/utils/ResourceManager.py` — `ants_ram_requirements()` / min-RAM helper (Group A)
- `setup.py` — add `antspyx` (Group A)
- `swane/nipype_pipeline/nodes/utils.py` — CPU-helper generalization, wrapper, engine branches, signature change (Group C)
- every caller of `get_registration_node`/`apply_registration_node`: `linear_reg_workflow.py`, `nonlinear_reg_workflow.py`, `dti_preproc_workflow.py`, `fMRI_preproc_workflow.py`, `fMRI_resting_state_workflow.py`, `fMRI_task_workflow.py`, `func_map_workflow.py` (audit which actually call it) — `use_synth`→`engine` (Group C)
- `swane/nipype_pipeline/MainWorkflow.py` — engine resolver + pass to the two workflows (Groups C/D)
- `swane/ui/PreferenceWizardWindow.py` — set `engine` instead of `morph` (Group D)
- `swane/tests/nipype_pipeline/matrix/test_linear_reg_matrix.py`, `test_nonlinear_reg_matrix.py` + snapshots (Group D)

---

## GROUP A — Config & packaging foundation  (Sonnet 5)

### Task A1: `RegistrationEngine` enum

**Files:**
- Modify: `swane/config/config_enums.py`
- Test: `swane/tests/config/test_registration_engine_pref.py`

**Interfaces:**
- Produces: `RegistrationEngine` enum with members `FSL`, `SYNTH`, `ANTS`; each member `.value` is a human-readable label (used by the ENUM preference UI, following `FreesurferStep`/`CoreLimit` convention in the same file).

- [ ] **Step 1: Write the failing test**

```python
# swane/tests/config/test_registration_engine_pref.py
from swane.config.config_enums import RegistrationEngine


class TestRegistrationEngineEnum:
    def test_members_exist(self):
        assert {m.name for m in RegistrationEngine} == {"FSL", "SYNTH", "ANTS"}

    def test_values_are_human_labels(self):
        # values are user-facing strings, not the bare member names
        assert all(isinstance(m.value, str) and m.value for m in RegistrationEngine)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -c "import sys; print(sys.executable)"` (confirm swane-env), then
`pytest -p no:datalad swane/tests/config/test_registration_engine_pref.py::TestRegistrationEngineEnum -v`
Expected: FAIL with ImportError (`RegistrationEngine` not defined).

- [ ] **Step 3: Implement the enum**

Add to `swane/config/config_enums.py`, following the existing enum style in that file (match how `FreesurferStep`/`CoreLimit` are declared — same base class and `__str__` convention if present):

```python
class RegistrationEngine(Enum):
    FSL = "FSL (FLIRT/FNIRT)"
    SYNTH = "FreeSurfer SynthMorph"
    ANTS = "ANTs (antspyx)"
```

If the file's enums subclass a custom base or define `__str__`/serialization used by the preference system, mirror that exactly (check `FreesurferStep` in the same file before writing).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest -p no:datalad swane/tests/config/test_registration_engine_pref.py::TestRegistrationEngineEnum -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add swane/config/config_enums.py swane/tests/config/test_registration_engine_pref.py
git commit -m "Add RegistrationEngine enum (FSL/SYNTH/ANTS)"
```

### Task A2: antspyx dependency detection + RAM requirement

**Files:**
- Modify: `swane/utils/DependencyManager.py`, `swane/utils/ResourceManager.py`, `setup.py`
- Test: `swane/tests/config/test_registration_engine_pref.py`

**Interfaces:**
- Produces: `DependencyManager.is_antspyx() -> bool` (import-based check); `ResourceManager.ants_ram_requirements() -> float` and, if the wizard needs a combined floor, extend the existing `get_min_synth_ram_requirement`-style helper analogously.

- [ ] **Step 1: Write failing tests**

```python
def test_is_antspyx_returns_bool():
    from swane.utils.DependencyManager import DependencyManager
    assert isinstance(DependencyManager.is_antspyx(), bool)

def test_ants_ram_requirement_positive():
    from swane.utils.ResourceManager import ResourceManager
    assert ResourceManager.ants_ram_requirements() > 0
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest -p no:datalad swane/tests/config/test_registration_engine_pref.py -k "antspyx or ram_requirement" -v`
Expected: FAIL (AttributeError).

- [ ] **Step 3: Implement**

- In `DependencyManager`, follow the existing `is_freesurfer_synth`/importability patterns. antspyx is a pure import:

```python
@staticmethod
def is_antspyx() -> bool:
    try:
        import ants  # noqa: F401
        return True
    except Exception:
        return False
```

(Match whether neighbors use `@staticmethod`/instance methods and how they cache; mirror the closest existing check.)

- In `ResourceManager`, add `ants_ram_requirements()` next to `synth_morph_ram_requirements()`; pick an initial value consistent with the synth helpers' style. **Value to confirm at CP-A** — start from the same magnitude as `synth_morph_ram_requirements()` and record the choice.

- In `setup.py` `install_requires`, add `antspyx` with a pinned version verified importable alongside `numpy==2.2.4` and `SimpleITK>=2.5.0`. Record the exact pin and confirm a wheel exists for Linux and macOS.

- [ ] **Step 4: Run to verify pass**

Run: `pytest -p no:datalad swane/tests/config/test_registration_engine_pref.py -k "antspyx or ram_requirement" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add swane/utils/DependencyManager.py swane/utils/ResourceManager.py setup.py swane/tests/config/test_registration_engine_pref.py
git commit -m "Detect antspyx dependency and declare ANTs RAM requirement"
```

### Task A3: `engine` preference replaces `morph`

**Files:**
- Modify: `swane/config/preference_list.py`
- Test: `swane/tests/config/test_registration_engine_pref.py`

**Interfaces:**
- Produces: `GLOBAL_PREFERENCES[GlobalPrefCategoryList.SYNTH]["engine"]` — an `InputTypes.ENUM` `PreferenceEntry`, `value_enum=RegistrationEngine`, `default=RegistrationEngine.ANTS`, with `option_dependency`/`option_pref_requirement` per option. The `morph` key is removed. `strip` and `reconall` are unchanged.

- [ ] **Step 1: Write failing tests**

```python
def test_engine_pref_defaults_to_ants():
    from swane.config.preference_list import GLOBAL_PREFERENCES
    from swane.config.config_enums import GlobalPrefCategoryList, RegistrationEngine
    entry = GLOBAL_PREFERENCES[GlobalPrefCategoryList.SYNTH]["engine"]
    assert entry.default == RegistrationEngine.ANTS

def test_morph_key_removed():
    from swane.config.preference_list import GLOBAL_PREFERENCES
    from swane.config.config_enums import GlobalPrefCategoryList
    assert "morph" not in GLOBAL_PREFERENCES[GlobalPrefCategoryList.SYNTH]

def test_synth_option_gated_on_ram_and_freesurfer():
    from swane.config.preference_list import GLOBAL_PREFERENCES
    from swane.config.config_enums import GlobalPrefCategoryList, RegistrationEngine
    entry = GLOBAL_PREFERENCES[GlobalPrefCategoryList.SYNTH]["engine"]
    # SYNTH option keeps the SynthMorph RAM gate and FreeSurfer-Synth dependency
    assert RegistrationEngine.SYNTH in entry.option_pref_requirement
    assert RegistrationEngine.SYNTH in entry.option_dependency

def test_ants_option_gated_on_antspyx_and_ram():
    from swane.config.preference_list import GLOBAL_PREFERENCES
    from swane.config.config_enums import GlobalPrefCategoryList, RegistrationEngine
    entry = GLOBAL_PREFERENCES[GlobalPrefCategoryList.SYNTH]["engine"]
    assert RegistrationEngine.ANTS in entry.option_pref_requirement
    assert RegistrationEngine.ANTS in entry.option_dependency
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest -p no:datalad swane/tests/config/test_registration_engine_pref.py -v`
Expected: FAIL (KeyError `engine` / `morph` still present).

- [ ] **Step 3: Implement**

Replace the `morph` block in `preference_list.py` (currently lines ~642-655) with an ENUM entry, following the `freesurfer_step` entry (lines ~104-129) for the per-option gating mechanism. `option_dependency` values are `[check_name, fail_tooltip]`; `option_pref_requirement` maps the option to `{category: [(key, required_value)]}`:

```python
GLOBAL_PREFERENCES[category]["engine"] = PreferenceEntry(
    input_type=InputTypes.ENUM,
    label="Registration engine",
    value_enum=RegistrationEngine,
    default=RegistrationEngine.ANTS,
    option_dependency={
        RegistrationEngine.SYNTH: [
            "is_freesurfer_synth",
            "SynthMorph requires FreeSurfer 8.1.0",
        ],
        RegistrationEngine.ANTS: [
            "is_antspyx",
            "ANTs registration requires the antspyx package",
        ],
    },
    option_pref_requirement={
        RegistrationEngine.SYNTH: {
            GlobalPrefCategoryList.PERFORMANCE: [
                ("ram_gb", ResourceManager.synth_morph_ram_requirements())
            ]
        },
        RegistrationEngine.ANTS: {
            GlobalPrefCategoryList.PERFORMANCE: [
                ("ram_gb", ResourceManager.ants_ram_requirements())
            ]
        },
    },
    option_pref_requirement_fail_tooltip={
        RegistrationEngine.SYNTH: "SynthMorph requires at least %.1f GB RAM"
        % ResourceManager.synth_morph_ram_requirements(),
        RegistrationEngine.ANTS: "ANTs registration requires at least %.1f GB RAM"
        % ResourceManager.ants_ram_requirements(),
    },
    section=True,
)
```

Verify `is_antspyx` is a valid dependency-check name in whatever registry `option_dependency` resolves against (the same place `is_freesurfer_synth` resolves). Add `is_antspyx` there if that registry is explicit.

- [ ] **Step 4: Run to verify pass**

Run: `pytest -p no:datalad swane/tests/config/test_registration_engine_pref.py -v`
Expected: PASS.

- [ ] **Step 5: Grep for stale `morph` readers**

Run: `grep -rn '"morph"\|getboolean_safe("morph")\|\[.morph.\]' swane/`
Expected: only workflow call sites remain (handled in Group C/D). Record them; do not edit here.

- [ ] **Step 6: Commit**

```bash
git add swane/config/preference_list.py swane/tests/config/test_registration_engine_pref.py
git commit -m "Replace morph boolean with engine enum preference (default ANTS)"
```

### Task A4: `force_pref_reset` version bump (migration)

**Files:**
- Modify: `swane/config/preference_list.py` (the `force_pref_reset` MAIN entry, ~line 529) and/or `swane/__init__.py` version, per how the mechanism keys off `last_swane_version`.
- Test: `swane/tests/config/` (add to an existing ConfigManager test module if one exists; otherwise extend the engine pref test).

**Interfaces:**
- Consumes: `ConfigManager` reset logic (`force_pref_reset` / `last_swane_version`, `ConfigManager.py:66-104`).
- Produces: on load, a config whose `last_swane_version` predates this release is reset to defaults (engine=ANTS).

- [ ] **Step 1: Write failing test** — construct a `ConfigManager` pointed at a `tmp_path` config file carrying an old `last_swane_version` with `force_pref_reset=true` and `engine` (or legacy `morph`) set to a non-default, load it, and assert `engine` is back to `RegistrationEngine.ANTS`. Model the fixture on existing ConfigManager tests under `swane/tests/config/`.

- [ ] **Step 2: Run to verify fail.**

- [ ] **Step 3: Implement** — set `force_pref_reset` default to trigger for this upgrade following exactly how the existing mechanism is toggled per release (inspect the current value and comment in `preference_list.py` ~529 and `ConfigManager.py:66-85`). Do not invent a new mechanism.

- [ ] **Step 4: Run to verify pass.**

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "Reset preferences on upgrade so engine defaults to ANTS"
```

**→ CHECKPOINT CP-A:** report config tests green; show engine default + option gating. Wait for orchestrator confirmation of the enum/pref shape before Group C starts.

---

## GROUP B — ANTs Nipype nodes  (Opus 5)

> Before writing any `_run_interface` body: install antspyx in swane-env and verify `ants.registration`, `ants.apply_transforms` signatures, their return-dict keys, valid `type_of_transform` and `interpolator` names. The code blocks below state intended behavior; correct them to the real API.

### Task B1: `AntsRegistration` node

**Files:**
- Create: `swane/nipype_pipeline/nodes/AntsRegistration.py`
- Test: `swane/tests/nipype_pipeline/nodes/test_ants_registration.py`

**Interfaces:**
- Produces: `AntsRegistration` (`BaseInterface`). Input spec: `moving` (File, exists, mandatory), `fixed` (File, exists, mandatory), `transform_type` (Enum, mandatory — e.g. `"Rigid"`, `"Affine"`, `"SyN"`, `"SyNRA"`), `metric` (Enum, usedefault), `num_threads` (Int, nohash), `initial_transform` (File, optional). Output spec: `fwd_transforms` (OutputMultiObject/List of File — ordered as antspyx returns), `inv_transforms` (List of File), `warped_file` (File), `affine_transform` (File — the affine component), `warp_field` (File, defined only for nonlinear).

- [ ] **Step 1: Write failing tests** (Traits/output contract; antspyx run mocked)

```python
# swane/tests/nipype_pipeline/nodes/test_ants_registration.py
import pytest
from swane.nipype_pipeline.nodes.AntsRegistration import AntsRegistration


class TestAntsRegistrationSpec:
    def test_transform_type_is_constrained(self):
        node = AntsRegistration()
        with pytest.raises(Exception):
            node.inputs.transform_type = "not-a-real-transform"

    def test_outputs_declared(self):
        out = AntsRegistration().output_spec().get()
        for field in ["fwd_transforms", "inv_transforms", "warped_file",
                      "affine_transform", "warp_field"]:
            assert field in out

    def test_linear_run_lists_single_affine(self, monkeypatch, make_nifti, tmp_path):
        """A Rigid/Affine run advertises exactly one forward transform (the affine)."""
        node = AntsRegistration()
        node.inputs.moving = make_nifti("m.nii.gz", shape=(6, 6, 6))
        node.inputs.fixed = make_nifti("f.nii.gz", shape=(6, 6, 6))
        node.inputs.transform_type = "Affine"
        # monkeypatch ants.registration to return deterministic fake transform paths
        # written into tmp_path, then assert _list_outputs maps them to
        # fwd_transforms == [affine] and warp_field is undefined.
        ...
```

Fill the monkeypatch body once the real `ants.registration` return shape is confirmed (a dict with `fwdtransforms`, `invtransforms`, `warpedmovout`).

- [ ] **Step 2: Run to verify fail**

Run: `pytest -p no:datalad swane/tests/nipype_pipeline/nodes/test_ants_registration.py -v`
Expected: FAIL (ImportError).

- [ ] **Step 3: Implement the node**

Follow the `SynthMorphReg` structure for spec/`_list_outputs`, but as a Python `BaseInterface`:

```python
import os
import nibabel as nib
from nipype.interfaces.base import (
    BaseInterface, BaseInterfaceInputSpec, TraitedSpec, File, traits, isdefined,
)
from nipype.utils.filemanip import fname_presuffix


class AntsRegistrationInputSpec(BaseInterfaceInputSpec):
    moving = File(exists=True, mandatory=True, desc="the moving image")
    fixed = File(exists=True, mandatory=True, desc="the reference image")
    transform_type = traits.Enum(
        "Rigid", "Affine", "SyN", "SyNRA",
        mandatory=True, desc="antspyx type_of_transform",
    )
    metric = traits.Enum(
        "mattes", "meansquares", "CC", "MI",
        usedefault=True, desc="registration metric",
    )
    num_threads = traits.Int(nohash=True, desc="ITK threads")
    initial_transform = File(exists=True, desc="initial moving transform")


class AntsRegistrationOutputSpec(TraitedSpec):
    fwd_transforms = traits.List(File(exists=True), desc="ordered forward transforms")
    inv_transforms = traits.List(File(exists=True), desc="ordered inverse transforms")
    warped_file = File(desc="moving resampled into fixed space")
    affine_transform = File(desc="affine component")
    warp_field = File(desc="nonlinear warp component (nonlinear only)")


class AntsRegistration(BaseInterface):
    input_spec = AntsRegistrationInputSpec
    output_spec = AntsRegistrationOutputSpec

    def _run_interface(self, runtime):
        import ants
        if isdefined(self.inputs.num_threads):
            os.environ["ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS"] = str(self.inputs.num_threads)
        fixed = ants.image_read(self.inputs.fixed)
        moving = ants.image_read(self.inputs.moving)
        # VERIFY: exact kwarg names/return keys against installed antspyx
        result = ants.registration(
            fixed=fixed, moving=moving,
            type_of_transform=self.inputs.transform_type,
            aff_metric=self.inputs.metric,
        )
        self._fwd = [os.path.abspath(p) for p in result["fwdtransforms"]]
        self._inv = [os.path.abspath(p) for p in result["invtransforms"]]
        warped_path = os.path.abspath("warped.nii.gz")
        ants.image_write(result["warpedmovout"], warped_path)
        self._warped = warped_path
        return runtime

    def _list_outputs(self):
        outputs = self._outputs().get()
        outputs["fwd_transforms"] = self._fwd
        outputs["inv_transforms"] = self._inv
        outputs["warped_file"] = self._warped
        # antspyx forward order for SyN is [warp, affine]; the affine is the
        # .mat, the warp is the displacement field. Classify by extension.
        affine = [p for p in self._fwd if p.endswith(".mat")]
        warp = [p for p in self._fwd if not p.endswith(".mat")]
        if affine:
            outputs["affine_transform"] = affine[0]
        if warp:
            outputs["warp_field"] = warp[0]
        return outputs
```

Confirm the `.mat`-vs-warp classification against real antspyx output filenames; if antspyx uses a different suffix convention, key off that instead.

- [ ] **Step 4: Run to verify pass**

Run: `pytest -p no:datalad swane/tests/nipype_pipeline/nodes/test_ants_registration.py -v`
Expected: PASS.

- [ ] **Step 5: (heavy, optional) real smoke test** behind `@pytest.mark.heavy` — a tiny real `ants.registration` on two synthetic volumes, asserting the transform files exist and `warped_file` matches fixed geometry. Run only with antspyx installed.

- [ ] **Step 6: Commit**

```bash
git add swane/nipype_pipeline/nodes/AntsRegistration.py swane/tests/nipype_pipeline/nodes/test_ants_registration.py
git commit -m "Add AntsRegistration antspyx node"
```

### Task B2: `AntsApplyTransforms` node

**Files:**
- Create: `swane/nipype_pipeline/nodes/AntsApplyTransforms.py`
- Test: `swane/tests/nipype_pipeline/nodes/test_ants_apply_transforms.py`

**Interfaces:**
- Produces: `AntsApplyTransforms` (`BaseInterface`). Input spec: `input_image` (File, exists, mandatory), `reference_image` (File, exists, mandatory), `transformlist` (List of File, mandatory — ordered as antspyx expects, right-applied-first), `interpolator` (Enum, usedefault: `"linear"`, `"nearestNeighbor"`), `whichtoinvert` (List of Bool, optional), `out_file` (File, genfile). Output: `out_file` (File, abspath).

- [ ] **Step 1: Write failing tests**

```python
# swane/tests/nipype_pipeline/nodes/test_ants_apply_transforms.py
import pytest
from swane.nipype_pipeline.nodes.AntsApplyTransforms import AntsApplyTransforms


class TestAntsApplyTransformsSpec:
    def test_interpolator_constrained(self):
        node = AntsApplyTransforms()
        with pytest.raises(Exception):
            node.inputs.interpolator = "bogus"

    def test_default_interpolator_is_linear(self):
        assert AntsApplyTransforms().inputs.interpolator == "linear"

    def test_out_file_is_absolute(self, monkeypatch, make_nifti, tmp_path):
        node = AntsApplyTransforms()
        node.inputs.input_image = make_nifti("in.nii.gz", shape=(6, 6, 6))
        node.inputs.reference_image = make_nifti("ref.nii.gz", shape=(6, 6, 6))
        node.inputs.transformlist = []
        # monkeypatch ants.apply_transforms to write a deterministic file;
        # assert outputs.out_file == os.path.abspath(node.inputs.out_file or genfile)
        ...
```

- [ ] **Step 2: Run to verify fail.** Expected: ImportError.

- [ ] **Step 3: Implement** — mirror B1's structure:

```python
import os
from nipype.interfaces.base import (
    BaseInterface, BaseInterfaceInputSpec, TraitedSpec, File, traits, isdefined,
)


class AntsApplyTransformsInputSpec(BaseInterfaceInputSpec):
    input_image = File(exists=True, mandatory=True)
    reference_image = File(exists=True, mandatory=True)
    transformlist = traits.List(File(exists=True), mandatory=True)
    interpolator = traits.Enum("linear", "nearestNeighbor", usedefault=True)
    whichtoinvert = traits.List(traits.Bool())
    out_file = File(genfile=True, hash_files=False)


class AntsApplyTransformsOutputSpec(TraitedSpec):
    out_file = File(desc="resampled image")


class AntsApplyTransforms(BaseInterface):
    input_spec = AntsApplyTransformsInputSpec
    output_spec = AntsApplyTransformsOutputSpec

    def _run_interface(self, runtime):
        import ants
        fixed = ants.image_read(self.inputs.reference_image)
        moving = ants.image_read(self.inputs.input_image)
        kwargs = {}
        if isdefined(self.inputs.whichtoinvert):
            kwargs["whichtoinvert"] = self.inputs.whichtoinvert
        # VERIFY kwarg names against installed antspyx
        out = ants.apply_transforms(
            fixed=fixed, moving=moving,
            transformlist=self.inputs.transformlist,
            interpolator=self.inputs.interpolator,
            **kwargs,
        )
        ants.image_write(out, os.path.abspath(self._gen_outfilename()))
        return runtime

    def _gen_outfilename(self):
        if isdefined(self.inputs.out_file):
            return self.inputs.out_file
        return "ants_resampled.nii.gz"

    def _gen_filename(self, name):
        if name == "out_file":
            return os.path.abspath(self._gen_outfilename())
        return None

    def _list_outputs(self):
        outputs = self._outputs().get()
        outputs["out_file"] = os.path.abspath(self._gen_outfilename())
        return outputs
```

- [ ] **Step 4: Run to verify pass.**

- [ ] **Step 5: Commit**

```bash
git add swane/nipype_pipeline/nodes/AntsApplyTransforms.py swane/tests/nipype_pipeline/nodes/test_ants_apply_transforms.py
git commit -m "Add AntsApplyTransforms antspyx node"
```

**→ CHECKPOINT CP-B:** report node unit tests green; show forward/inverse transform-list outputs and interpolation handling. Orchestrator reviews transform semantics before Group C consumes these interfaces.

---

## GROUP C — Backend-aware abstraction + call-site migration  (Opus 4.8)

> Consumes A (`RegistrationEngine`) and B (`AntsRegistration`/`AntsApplyTransforms` interfaces above).

> **AS-BUILT interfaces from Group B (commits 06fc9e5, e11e12c) — these override the B code sketch above where they differ. Verify against the real node files before coding C.**
>
> `AntsRegistration` outputs: `fwd_transforms` (list), `inv_transforms` (list),
> **`fwd_which_to_invert` (list[bool])**, **`inv_which_to_invert` (list[bool])**,
> `warped_file`, `affine_transform`, `warp_field`, `inverse_warp_field`.
> Inputs include `transform_type`, **`aff_metric`** and **`syn_metric`** (the plan's
> single `metric` enum was wrong — antspyx splits them, and "MI" is invalid in both),
> `num_threads`, `initial_transform`, `out_prefix`.
>
> `AntsApplyTransforms` inputs: `input_image`, `reference_image`, `transformlist` (list),
> `interpolator` (`"linear"`/`"nearestNeighbor"` — note the antspyx spelling, NOT FSL's
> `nearestneighbour`), **`which_to_invert` (list[bool])**, `out_file`. Output: `out_file`.
>
> **CRITICAL (silent-bug guard):** antspyx's `which_to_invert` default is only correct for
> `[matrix, warp]`. A linear inverse `[affine.mat]` needs `which_to_invert=[True]`; relying on
> the default silently gives a wrong result (measured corr 0.108 vs 0.997, no error raised).
> Therefore Group B publishes the flags on the registration node and **C MUST wire
> `fwd_which_to_invert`/`inv_which_to_invert` into `AntsApplyTransforms.which_to_invert`** —
> never re-derive or rely on the antspyx default.

### Task C1: Generalize the CPU-config helpers to be tool-neutral

**Files:**
- Modify: `swane/nipype_pipeline/nodes/utils.py`
- Test: `swane/tests/utils/` (add a focused test module, or extend the nearest existing utils test)

**Interfaces:**
- Produces: `get_tool_cpu_config(...)` and `apply_tool_num_threads(...)` — the current `get_synth_cpu_config`/`apply_synth_num_threads` renamed/generalized so the ANTs node can reuse them with `soft_env_vars=("ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS",)`. Keep the old names as thin aliases if any caller imports them by name (grep first).

- [ ] **Step 1: Write failing test** asserting `apply_tool_num_threads` sets `ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS` in the soft path and `num_threads`/`n_procs` in the hard path (mirror the semantics documented in `utils.py:62-87`).
- [ ] **Step 2: Run to verify fail.**
- [ ] **Step 3: Implement** the rename/generalization; update the two existing internal call sites. Preserve behavior for Synth exactly.
- [ ] **Step 4: Run to verify pass** + run existing utils tests to confirm no regression.
- [ ] **Step 5: Commit** `git commit -m "Generalize Synth CPU-config helpers to tool-neutral helpers"`

### Task C2: Transform-list `RegistrationNodeWrapper` + `engine` branch in `get_registration_node`

**Files:**
- Modify: `swane/nipype_pipeline/nodes/utils.py`
- Test: `swane/tests/utils/test_registration_abstraction.py` (new)

**Interfaces:**
- Consumes: `RegistrationEngine`, `AntsRegistration`.
- Produces: `RegistrationNodeWrapper` extended with `fwd_transforms: list[(node, field)]`, `inv_transforms: list[(node, field)]`, **`fwd_which_to_invert: (node, field)`**, **`inv_which_to_invert: (node, field)`**, and `engine`. `get_registration_node(..., engine: RegistrationEngine, ...)` replaces the `use_synth: bool` parameter and gains an `engine == RegistrationEngine.ANTS` branch. FSL/Synth branches map from `engine` (SYNTH↔ old `use_synth=True`, FSL↔ `False`). For ANTS the wrapper's `fwd_transforms`/`inv_transforms` point at the node's `fwd_transforms`/`inv_transforms` list outputs and the which-to-invert fields at `fwd_which_to_invert`/`inv_which_to_invert` (so C3 can wire them). FSL/Synth set the which-to-invert fields to `None`.

- [ ] **Step 1: Write failing tests** — for each engine, `get_registration_node` returns a wrapper whose node types match (FSL→FLIRT/FNIRT, SYNTH→SynthMorphReg, ANTS→AntsRegistration) and whose `fwd_transforms`/`inv_transforms` are populated (ANTS linear → 1 forward transform; ANTS nonlinear → 2). Build a throwaway `CustomWorkflow` and inspect nodes.
- [ ] **Step 2: Run to verify fail.**
- [ ] **Step 3: Implement** the `engine` parameter and ANTS branch. For ANTS: `transform_type = "Affine" if not non_linear else "SyN"` (rigid vs deformable — confirm the linear default matches the FSL `dof` intent: FSL linear uses dof=6 rigid in the volumetric non-linear-affine step and dof=12 for the pre-FNIRT affine; pick `Rigid`/`Affine` accordingly and document). Set `aff_metric`/`syn_metric` mapping the prior FSL cost intent (document the mapping; "MI" is not a valid antspyx metric). Populate the wrapper's `fwd_transforms`/`inv_transforms` and `fwd_which_to_invert`/`inv_which_to_invert` from the node's list outputs. Keep `warp`/`inv_warp` set for FSL/Synth compatibility; set the which-to-invert fields to `None` on the FSL/Synth branches.
- [ ] **Step 4: Run to verify pass.**
- [ ] **Step 5: Commit** `git commit -m "Add ANTs branch and transform-list wrapper to get_registration_node"`

### Task C3: `engine` branch in `apply_registration_node`

**Files:**
- Modify: `swane/nipype_pipeline/nodes/utils.py`
- Test: `swane/tests/utils/test_registration_abstraction.py`

**Interfaces:**
- Produces: `apply_registration_node(..., engine, ...)` builds `AntsApplyTransforms` for ANTS with the ordered `transformlist` **and its paired `which_to_invert` flags**; `labelmap=True` → `interpolator="nearestNeighbor"`. FSL/Synth branches unchanged (still keyed off `engine`).

- [ ] **Step 1: Write failing test** — ANTS apply produces an `AntsApplyTransforms` node with `interpolator` correct for `labelmap` True/False, `transformlist` wired from a wrapper's `fwd_transforms` (or `inv_transforms` when `inverse=True`), **and `which_to_invert` wired from the matching `fwd_which_to_invert`/`inv_which_to_invert`**. Add a regression test proving a linear-inverse apply carries `which_to_invert=[True]`, not the wrong antspyx default `[False]`.
- [ ] **Step 2: Run to verify fail.**
- [ ] **Step 3: Implement** the ANTS branch via a helper `wire_transforms(wrapper, apply_node, workflow, inverse=False)` that connects BOTH the transform list AND its which-to-invert flags (forward or inverse set, per `inverse`). Never leave `which_to_invert` to the antspyx default for ANTS.
- [ ] **Step 4: Run to verify pass.**
- [ ] **Step 5: Commit** `git commit -m "Add ANTs branch to apply_registration_node"`

### Task C4: Migrate all `use_synth` call sites to `engine` (behavior-preserving) + call-site audit

**Files:**
- Modify: `linear_reg_workflow.py`, `nonlinear_reg_workflow.py`, `dti_preproc_workflow.py`, `fMRI_preproc_workflow.py`, `fMRI_resting_state_workflow.py`, `fMRI_task_workflow.py`, `func_map_workflow.py` (grep-confirm the exact set), and `MainWorkflow.py` where these factories are called.
- Test: existing matrix tests must still pass (unchanged snapshots for the workflows NOT retargeted in Phase 1).

**Interfaces:**
- Consumes: C2/C3 signatures.
- Produces: every caller passes an explicit `engine`. Phase-1 rule: sites currently hardcoded `use_synth=False` pass `engine=RegistrationEngine.FSL` (identical behavior — their pins are removed only in Phases 2/3); sites currently `use_synth=synth_config.getboolean_safe("morph")` pass an engine resolved from the new preference (see D-resolver), which for the two abstracted workflows becomes ANTS by default (that behavior change is validated by D's snapshot update; for **other** workflows in this task keep them on their current backend by resolving to FSL/SYNTH exactly as before — do NOT flip EPI/DTI to ANTS here).

- [ ] **Step 1:** Grep the exact call-site set: `grep -rn "use_synth" swane/nipype_pipeline/`.
- [ ] **Step 2: Write/adjust failing tests** — run the full matrix suite; the signature change will break construction. Expected: FAIL at import/call for the changed signature.
- [ ] **Step 3: Implement** the `use_synth=`→`engine=` change at every site, preserving each site's current backend (FSL stays FSL, `morph` sites stay Synth-or-FSL per preference). Only `linear_reg_workflow`/`nonlinear_reg_workflow` are allowed to follow the ANTS default — and that flip is finalized in Group D.
- [ ] **Step 4: Run** `pytest -p no:datalad swane/tests/nipype_pipeline/matrix -v` — every non-retargeted workflow snapshot must be unchanged (behavior preserved). Fix until green.
- [ ] **Step 5: Produce the call-site audit** — a table listing every consumer (in `MainWorkflow` and downstream) of `linear_reg_workflow`/`nonlinear_reg_workflow` outputs, classifying each as (a) resampled-image use (format-agnostic, safe) or (b) transform-field use (FSL-specific, must be gated/deferred). Save it as `docs/superpowers/specs/2026-08-24-ants-phase1-callsite-audit.md`.
- [ ] **Step 6: Commit** `git commit -m "Migrate registration call sites from use_synth to engine (behavior-preserving) + call-site audit"`

**→ CHECKPOINT CP-C:** report abstraction + matrix tests green; deliver the call-site audit. Orchestrator decides gating and green-lights Group D. Audit also feeds Phase 2/3 planning.

---

## GROUP D — Wire abstracted workflows to ANTS + wizard + graph/snapshot tests  (Sonnet 5)

> Consumes C. This is where the two abstracted workflows actually default to ANTS.

### Task D1: Engine resolver in `MainWorkflow`

**Files:**
- Modify: `swane/nipype_pipeline/MainWorkflow.py`
- Test: `swane/tests/nipype_pipeline/` (graph-level; or a focused resolver unit test)

**Interfaces:**
- Produces: a single helper that reads `GlobalPrefCategoryList.SYNTH["engine"]` → `RegistrationEngine` and passes it to `linear_reg_workflow`/`nonlinear_reg_workflow`. (Keeps a place for Phase 2/3 per-site overrides.)

- [ ] **Step 1: Write failing test** — with the config `engine=ANTS`, `MainWorkflow` constructs the two workflows with `engine=RegistrationEngine.ANTS`.
- [ ] **Step 2–4:** implement resolver; pass into the two factories; run.
- [ ] **Step 5: Commit** `git commit -m "Resolve registration engine in MainWorkflow for abstracted workflows"`

### Task D2: Wizard sets `engine`

**Files:**
- Modify: `swane/ui/PreferenceWizardWindow.py` (lines ~1017-1029 and the availability/summary text ~188-189, ~768-769)
- Test: `swane/tests/ui/` (pytest-qt) — mirror existing wizard tests.

**Interfaces:**
- Produces: wizard writes `GlobalPrefCategoryList.SYNTH["engine"]` = ANTS when antspyx available and RAM ≥ ANTs requirement; SYNTH only when FreeSurfer-Synth available and RAM ≥ `synth_morph_ram_requirements()` under the "advanced models" opt-in; else FSL. `morph` is no longer written.

- [ ] **Step 1: Write failing test** — advanced-models + sufficient RAM + antspyx available → wizard sets `engine == ANTS`; the `morph` key is never written.
- [ ] **Step 2–4:** implement; update the SynthMorph availability/summary strings (in `swane/strings.py` if the text lives there) to speak of the engine choice.
- [ ] **Step 5: Commit** `git commit -m "Wizard configures registration engine instead of morph"`

### Task D3: Retarget the two workflows' golden snapshots to ANTS

**Files:**
- Modify: `swane/tests/nipype_pipeline/matrix/test_linear_reg_matrix.py`, `test_nonlinear_reg_matrix.py` (add an `engine` dimension to SCENARIOS, replacing the `synth` bool where these two builders are exercised) + regenerate snapshots under `snapshots/linear_reg/`, `snapshots/nonlinear_reg/`.

**Interfaces:**
- Consumes: D1 (default engine flows into construction).

- [ ] **Step 1:** Extend SCENARIOS to cover `engine` ∈ {FSL, SYNTH, ANTS} for these two builders (keep FSL/SYNTH scenarios so all three backends stay tested).
- [ ] **Step 2: Run** the two matrix tests, expect FAIL (missing ANTS snapshots / changed default).
- [ ] **Step 3: Regenerate** `SWANE_SNAPSHOT_UPDATE=1 pytest -p no:datalad swane/tests/nipype_pipeline/matrix/test_linear_reg_matrix.py swane/tests/nipype_pipeline/matrix/test_nonlinear_reg_matrix.py`.
- [ ] **Step 4: Review the snapshot diff by eye** — confirm ANTS nodes/connections/filenames are correct (not merely present). This is a required human/orchestrator review, not an auto-accept.
- [ ] **Step 5: Run** the full matrix suite green.
- [ ] **Step 6: Commit** `git commit -m "Add ANTS-default golden snapshots for linear/nonlinear registration"`

### Task D4: (opt-in) prerelease smoke

**Files:** none (execution only).

- [ ] With antspyx installed and the disposable root `~/test_swane/prerelease` verified, run `python -m swane.tests.prerelease` and confirm the two abstracted workflows execute end-to-end under the ANTS default. Record failures; do not treat success as scientific validation.

**→ CHECKPOINT CP-D:** graph tests green + snapshot diff reviewed; report explicitly what was NOT scientifically validated. Orchestrator closes Phase 1 and plans Phase 2 from the CP-C audit.

---

## Self-review

**Spec coverage:** nodes (B1/B2) ↔ spec §1; abstraction (C1–C4) ↔ §2; config/enum/migration/gating (A1–A4) ↔ §3; dependency/resources/packaging (A2) ↔ §4; wizard (D2) ↔ §5; call-site audit (C4) ↔ spec "Call-site audit"; testing (all task test steps + D3/D4) ↔ spec "Testing"; cross-platform (A2 wheel check, Global Constraints) ↔ spec "Cross-platform". No orphan spec section.

**Placeholder scan:** the antspyx `_run_interface` bodies and two mocked test bodies are marked "VERIFY against installed antspyx"/`...` deliberately — this is a project-mandated no-invention guardrail (antspyx is not yet installed), not a lazy TODO; each states the intended call and expected return shape. All other steps carry runnable code or exact edits. RAM magnitude in A2 and the `force_pref_reset` toggle in A4 are flagged for confirmation against live values at their checkpoints.

**Type consistency:** `RegistrationEngine` members `FSL`/`SYNTH`/`ANTS` used identically in A1/A3/C2/C4/D1/D2. Node output fields `fwd_transforms`/`inv_transforms`/`affine_transform`/`warp_field` (B1) match the wrapper population in C2 and the `transformlist` consumption in C3. Helper rename `get_tool_cpu_config`/`apply_tool_num_threads` (C1) is the name reused by B via the soft-env-var path.
