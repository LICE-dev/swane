# ANTs (antspyx) Registration — Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Each *session group* below runs in its **own separate Claude Code session**; the session that produced this plan is the **orchestrator** and reviews the feedback checkpoints between groups.

**Goal:** Lift the Phase-1 FSL pin on `nonlinear_reg_workflow` by porting its three boundary consumers (`flat1`, `func_map` AI, `tractography`) to ANTs, and move the cross-modality CT workflows (`venous_ct`, `seeg_ct`) off their FSL scientific pin, so the whole nonlinear + cross-modality surface follows the configured engine (ANTs by default).

**Architecture:** Approach A — the producer composes the ANTs ordered transform list `[warp, affine]` into a single directional displacement field per direction (new `AntsComposeTransform` node), so the MainWorkflow→consumer boundary stays 1:1 (one file per warp field) and `which_to_invert` is resolved once at the producer. The registration abstraction gains a single-field ANTs apply path so consumers keep passing `warp=[inputnode, field]` unchanged. CT workflows route their direct FLIRT/ApplyXFM through the abstraction; seeg's electrode weighting becomes an ANTs `moving_mask`.

**Tech Stack:** Python, Nipype 1.10.0, antspyx (Python import only — never ANTs binaries / `nipype.interfaces.ants`), nibabel, numpy 2.2.4, SimpleITK, pytest.

**Spec:** `docs/superpowers/specs/2026-08-25-ants-registration-phase2-design.md`

## Global Constraints

- Any Python command (tests/exploration/app) MUST use SWANe's env (conda `swane-env`) — never FSL's `fslpython` / FreeSurfer's `fspython`. Verify with `python -c "import sys; print(sys.executable)"`. Interpreter path: `/media/Dati/Installer_completi/Programmi/conda_env/swane-env/bin/python`. Run pytest with `-p no:datalad`.
- antspyx via the `ants` Python import only. Never ANTs binaries, never `nipype.interfaces.ants`. Do not vendor/copy antspyx or ANTs source.
- antspyx exact API (function signatures, return-dict keys, `compose=` return shape, `moving_mask` kwarg name, interpolator/`type_of_transform` names) MUST be verified against the installed antspyx before writing call bodies. Where this plan shows an antspyx call, treat it as *intended behavior to verify*, not confirmed syntax.
- Preserve stable contracts: persisted preference keys/section names, enum member names, workflow/node names, boundary output field names, deterministic result filenames, Slicer mappings.
- Preserve image header/affine/orientation/dtype unless a node explicitly transforms them (nibabel discipline: `header.copy()` + `set_data_dtype(float32)` where applicable).
- Terminology: "subject" not "patient"; no clinical/medical framing. English only.
- A passing test is software regression evidence only — never scientific/clinical validation.
- Code must run on both Ubuntu and macOS. Format changed Python with Black; do not reformat unrelated files.
- The comparative ANTs-vs-FSL oracle is a **local throwaway tool** (lives outside the repo). It is **never** committed to SWANe nor pushed to GitHub. Only software-regression tests are committed.
- Stay on branch `claude/ants-registration`. Never commit/push/merge/PR unless the user explicitly asks. Each session: `git pull`/rebase onto the latest orchestrator-merged state before starting, commit per task.

---

## Session orchestration

Seven session groups. **A** and **B** are independent (parallel). **C** depends on A+B. **D** depends on C. **E** depends on D. **F** depends on C+B (may run parallel with D+E). **G** depends on E+F. After each group, the executing session reports to the orchestrator at the named checkpoint and waits.

| Session | Scope | Depends on | Model | Why |
|---|---|---|---|---|
| **A — `AntsComposeTransform` node** | Task 1 | — | **Opus 5** | The one truly critical/hard part: composition direction/space + `which_to_invert` semantics + header discipline are silent-scientific-bug territory and need antspyx-API verification |
| **B — `AntsRegistration.moving_mask`** | Task 2 | — | **Sonnet 5** | Small, mechanical trait addition |
| **C — Abstraction** | Tasks 3–5 | A, B | **Opus 4.8** | Single-field ANTS apply path + `moving_mask` wiring + the round-trip correctness gate (risk #1) |
| **D — Producer (`nonlinear_reg`)** | Task 6 | C | **Opus 4.8** | Compose branch + pin lift; transform-space wiring |
| **E — Nonlinear-warp consumers** | Task 7 | D | **Sonnet 5** | Pattern-following pin lifts across flat1/func_map/tractography |
| **F — Cross-modality CT** | Task 8 | C (,B) | **Opus 4.8** | `venous_ct` MapNode routing + seeg `moving_mask` polarity are fiddly |
| **G — Snapshots + prerelease** | Tasks 9–10 | E, F | **Sonnet 5** | Golden-snapshot regen/review + prerelease smoke extension |

**Feedback checkpoints (report to orchestrator, then wait):**
- **CP-A:** `AntsComposeTransform` unit tests green; show the composed forward/inverse field outputs and how `which_to_invert` is applied. Orchestrator reviews composition semantics (highest risk) before C consumes it.
- **CP-B:** `moving_mask` trait test green; undefined leaves behavior unchanged.
- **CP-C:** abstraction tests green incl. the round-trip (compose→apply ≈ apply-via-list) correctness test. Orchestrator green-lights D/F.
- **CP-D:** `nonlinear_reg` graph test green; ANTS default builds the two compose nodes; FSL/SYNTH construction still green. Orchestrator confirms before consumers flip.
- **CP-E:** flat1/func_map/tractography construct under ANTS with `AntsApplyTransforms` fed the composed boundary field; FSL/SYNTH still green.
- **CP-F:** venous_ct/seeg_ct construct under all three engines; MapNode iteration preserved; seeg `moving_mask` wired on ANTS.
- **CP-G:** all matrix snapshots regenerated + reviewed by eye; prerelease smoke passes under ANTS default for nonlinear + CT. Orchestrator closes Phase 2 and plans Phase 3.

---

## File structure

**Create:**
- `swane/nipype_pipeline/nodes/AntsComposeTransform.py` (A)
- `swane/tests/nipype_pipeline/nodes/test_ants_compose_transform.py` (A)

**Modify:**
- `swane/nipype_pipeline/nodes/AntsRegistration.py` — `moving_mask` input (B)
- `swane/tests/nipype_pipeline/nodes/test_ants_registration.py` — `moving_mask` test (B)
- `swane/nipype_pipeline/nodes/utils.py` — single-field ANTS apply path; `get_registration_node` `moving_mask` param (C)
- `swane/tests/nipype_pipeline/nodes/test_registration_abstraction.py` — abstraction + round-trip tests (C)
- `swane/nipype_pipeline/workflows/nonlinear_reg_workflow.py` — compose branch + pin lift (D)
- `swane/tests/nipype_pipeline/matrix/test_nonlinear_reg_matrix.py` (+snapshots) (D/G)
- `swane/nipype_pipeline/workflows/flat1_workflow.py`, `func_map_workflow.py`, `tractography_workflow.py` — pin lift (E)
- `swane/nipype_pipeline/workflows/venous_ct_workflow.py`, `seeg_ct_workflow.py` — abstraction routing (F)
- matrix tests + snapshots for flat1/func_map/tractography/venous_ct/seeg_ct (G)
- `swane/tests/prerelease/plan.py` — ANTS nonlinear + CT smoke coverage (G)
- `swane/__init__.py` (or wherever `__version__` lives) — version bump (G)

---

## SESSION A — `AntsComposeTransform` node  (Opus 5)

> Before writing `_run_interface`: verify against the installed antspyx how to compose a `transformlist` (+ `whichtoinvert`) into a **single displacement field** written to disk. Candidate routes: `ants.apply_transforms(fixed=ref, moving=ref, transformlist=..., whichtoinvert=..., compose="<prefix>")` (returns a composite-transform path), or `ants.transform_to_displacement_field` / `ants.compose_ants_transforms`. Confirm the return shape and the on-disk file type before coding.

### Task 1: `AntsComposeTransform`

**Files:**
- Create: `swane/nipype_pipeline/nodes/AntsComposeTransform.py`
- Test: `swane/tests/nipype_pipeline/nodes/test_ants_compose_transform.py`

**Interfaces:**
- Produces: `AntsComposeTransform` (`BaseInterface`). Input spec: `transformlist` (`traits.List(File(exists=True))`, mandatory), `which_to_invert` (`traits.List(traits.Bool())`, optional), `reference_image` (File, exists, mandatory), `num_threads` (Int, nohash). Output spec: `out_field` (File — absolute path to the single composed displacement field).

- [ ] **Step 1: Write the failing spec tests** (Traits/output contract; antspyx mocked)

```python
# swane/tests/nipype_pipeline/nodes/test_ants_compose_transform.py
import pytest
from swane.nipype_pipeline.nodes.AntsComposeTransform import AntsComposeTransform


class TestAntsComposeTransformSpec:
    def test_outputs_declared(self):
        assert "out_field" in AntsComposeTransform().output_spec().get()

    def test_transformlist_mandatory(self):
        node = AntsComposeTransform()
        # reference set, transformlist missing -> mandatory error at run
        with pytest.raises(Exception):
            node.run()
```

- [ ] **Step 2: Run to verify fail**

Run: `/media/Dati/Installer_completi/Programmi/conda_env/swane-env/bin/python -m pytest -p no:datalad swane/tests/nipype_pipeline/nodes/test_ants_compose_transform.py -v`
Expected: FAIL (ImportError, `AntsComposeTransform` undefined).

- [ ] **Step 3: Implement the node** (mirror `AntsApplyTransforms` structure; VERIFY the antspyx compose call)

```python
import os
from nipype.interfaces.base import (
    BaseInterface, BaseInterfaceInputSpec, TraitedSpec, File, traits, isdefined,
)


class AntsComposeTransformInputSpec(BaseInterfaceInputSpec):
    transformlist = traits.List(
        File(exists=True), mandatory=True,
        desc="ordered ANTs transforms to compose (antspyx order)",
    )
    which_to_invert = traits.List(
        traits.Bool(), desc="per-transform invert flags (antspyx whichtoinvert)",
    )
    reference_image = File(
        exists=True, mandatory=True,
        desc="image defining the output displacement-field grid/space",
    )
    num_threads = traits.Int(nohash=True, desc="ITK threads")


class AntsComposeTransformOutputSpec(TraitedSpec):
    out_field = File(desc="single composed displacement field")


class AntsComposeTransform(BaseInterface):
    input_spec = AntsComposeTransformInputSpec
    output_spec = AntsComposeTransformOutputSpec

    def _run_interface(self, runtime):
        import ants
        if isdefined(self.inputs.num_threads):
            os.environ["ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS"] = str(
                self.inputs.num_threads
            )
        ref = ants.image_read(self.inputs.reference_image)
        kwargs = {}
        if isdefined(self.inputs.which_to_invert):
            kwargs["whichtoinvert"] = self.inputs.which_to_invert
        # VERIFY: compose= writes a composite transform and returns its path.
        composed = ants.apply_transforms(
            fixed=ref, moving=ref,
            transformlist=self.inputs.transformlist,
            compose=os.path.abspath("composed_"),
            **kwargs,
        )
        # `composed` is a path (str) when compose= is set. If antspyx returns a
        # different shape in the pinned version, adapt here and document it.
        self._out_field = os.path.abspath(composed)
        return runtime

    def _list_outputs(self):
        outputs = self._outputs().get()
        outputs["out_field"] = self._out_field
        return outputs
```

- [ ] **Step 4: Run to verify pass**

Run: same as Step 2. Expected: PASS (spec tests; the run-body path is exercised by Step 5).

- [ ] **Step 5: Real compose smoke test** (heavy-gated, antspyx installed)

```python
@pytest.mark.heavy
def test_compose_roundtrip(make_nifti, tmp_path):
    """Compose a real SyN forward list into one field; applying the composed
    field resamples the moving into fixed geometry identically (within tol) to
    applying the raw list. Confirms direction/space of the composition."""
    import numpy as np, nibabel as nib, ants
    from swane.nipype_pipeline.nodes.AntsRegistration import AntsRegistration
    from swane.nipype_pipeline.nodes.AntsApplyTransforms import AntsApplyTransforms
    from swane.nipype_pipeline.nodes.AntsComposeTransform import AntsComposeTransform
    # 1) run a tiny AntsRegistration (SyN) fixed<-moving
    # 2) apply raw fwd_transforms (+fwd_which_to_invert) to moving -> A
    # 3) compose fwd_transforms into one field (reference=fixed), apply -> B
    # 4) assert np.corrcoef(A,B) ~ 1.0 and identical geometry
    ...
```

Fill the body once the real `AntsRegistration` output shape is confirmed. Run: `... -m pytest -p no:datalad swane/tests/nipype_pipeline/nodes/test_ants_compose_transform.py -v -m heavy`.

- [ ] **Step 6: Commit**

```bash
git add swane/nipype_pipeline/nodes/AntsComposeTransform.py swane/tests/nipype_pipeline/nodes/test_ants_compose_transform.py
git commit -m "feat: add AntsComposeTransform node (compose transform list to single field)"
```

**→ CHECKPOINT CP-A.**

---

## SESSION B — `AntsRegistration.moving_mask`  (Sonnet 5)

### Task 2: optional `moving_mask` input

**Files:**
- Modify: `swane/nipype_pipeline/nodes/AntsRegistration.py`
- Test: `swane/tests/nipype_pipeline/nodes/test_ants_registration.py`

**Interfaces:**
- Produces: `AntsRegistration` gains input `moving_mask = File(exists=True)` (optional). When defined, `_run_interface` passes it to `ants.registration(moving_mask=...)` (VERIFY kwarg name). Undefined → unchanged behavior.

- [ ] **Step 1: Write failing tests**

```python
def test_moving_mask_optional_and_undefined_by_default():
    from nipype.interfaces.base import isdefined
    from swane.nipype_pipeline.nodes.AntsRegistration import AntsRegistration
    node = AntsRegistration()
    assert not isdefined(node.inputs.moving_mask)

def test_moving_mask_accepts_existing_file(make_nifti):
    from swane.nipype_pipeline.nodes.AntsRegistration import AntsRegistration
    node = AntsRegistration()
    node.inputs.moving_mask = make_nifti("mask.nii.gz", shape=(6, 6, 6))
    assert node.inputs.moving_mask.endswith("mask.nii.gz")
```

- [ ] **Step 2: Run to verify fail** — `... -m pytest -p no:datalad swane/tests/nipype_pipeline/nodes/test_ants_registration.py -k moving_mask -v`. Expected: FAIL (no such trait).

- [ ] **Step 3: Implement** — add to `AntsRegistrationInputSpec`:

```python
    moving_mask = File(exists=True, desc="binary mask in moving space "
                       "restricting the registration metric (ANTs moving_mask)")
```

In `_run_interface`, where `ants.registration(...)` is called, add (VERIFY kwarg):

```python
        if isdefined(self.inputs.moving_mask):
            reg_kwargs["moving_mask"] = ants.image_read(self.inputs.moving_mask)
```

(Adapt to how the existing node assembles its `ants.registration` kwargs.)

- [ ] **Step 4: Run to verify pass** — same as Step 2. Also run the full node test to confirm no regression: `... -m pytest -p no:datalad swane/tests/nipype_pipeline/nodes/test_ants_registration.py -v`.

- [ ] **Step 5: Commit**

```bash
git add swane/nipype_pipeline/nodes/AntsRegistration.py swane/tests/nipype_pipeline/nodes/test_ants_registration.py
git commit -m "feat: add optional moving_mask input to AntsRegistration"
```

**→ CHECKPOINT CP-B.**

---

## SESSION C — Abstraction  (Opus 4.8)

> Consumes A (`AntsComposeTransform`) and B (`AntsRegistration.moving_mask`). Read the real `utils.py` (`get_registration_node`, `apply_registration_node`, `wire_transforms`, `RegistrationNodeWrapper`) before editing.

### Task 3: single-field ANTS apply path in `apply_registration_node`

**Files:**
- Modify: `swane/nipype_pipeline/nodes/utils.py`
- Test: `swane/tests/nipype_pipeline/nodes/test_registration_abstraction.py`

**Interfaces:**
- Produces: `apply_registration_node(..., engine=ANTS, warp=[node, field], registration=None, ...)` builds `AntsApplyTransforms` with `transformlist=[warp]` and **no** `which_to_invert` (the composed field is directional). When `registration` (a `RegistrationNodeWrapper`) IS given, the existing `wire_transforms` path is used unchanged.

- [ ] **Step 1: Write failing test** — ANTS apply with a bare `warp=[node, field]` and `registration=None` produces an `AntsApplyTransforms` node whose `transformlist` is connected from `(node, field)` and whose `which_to_invert` is left unset; `labelmap=True` → `interpolator="nearestNeighbor"`. Build a throwaway `CustomWorkflow`, add a source `IdentityInterface` node, call `apply_registration_node`, and inspect the graph edges (mirror existing tests in this file).

```python
def test_ants_apply_single_field_from_boundary(make_workflow_with_source):
    from swane.config.config_enums import RegistrationEngine
    from swane.nipype_pipeline.nodes.utils import apply_registration_node
    wf, src = make_workflow_with_source(fields=["ref_2_sym_warp"])
    node = apply_registration_node(
        name="ai_2_sym", engine=RegistrationEngine.ANTS, workflow=wf,
        warp=[src, "ref_2_sym_warp"], moving="/tmp/m.nii.gz",
        reference="/tmp/r.nii.gz", non_linear=True, registration=None,
    )
    assert node.interface.__class__.__name__ == "AntsApplyTransforms"
    # transformlist edge wired from (src, "ref_2_sym_warp"); which_to_invert unset
    ...
```

- [ ] **Step 2: Run to verify fail** — `... -m pytest -p no:datalad swane/tests/nipype_pipeline/nodes/test_registration_abstraction.py -k single_field -v`. Expected: FAIL (current ANTS branch requires `registration`, calls `wire_transforms(None, ...)` → AttributeError).

- [ ] **Step 3: Implement** — in the `engine == RegistrationEngine.ANTS` branch of `apply_registration_node`, replace the unconditional `wire_transforms(registration, ...)` with:

```python
        if registration is not None:
            wire_transforms(registration, apply_node, workflow, inverse=inverse)
        else:
            # Single composed field crossing a workflow boundary: apply as a
            # one-element transformlist. The field is already directional, so
            # no which_to_invert is set.
            workflow.connect(warp[0], warp[1], apply_node, "transformlist")
```

Guard: `AntsApplyTransforms.transformlist` expects a list; if a scalar `(node,field)` cannot feed a List trait directly, wrap via a tiny `Merge(1)` node or a `Function` that returns `[x]`. VERIFY which is needed by running the test; document the choice.

- [ ] **Step 4: Run to verify pass** — same as Step 2, plus the whole abstraction file green: `... -m pytest -p no:datalad swane/tests/nipype_pipeline/nodes/test_registration_abstraction.py -v`.

- [ ] **Step 5: Commit** — `git commit -m "feat: single-field ANTS apply path for composed boundary warps"`

### Task 4: `moving_mask` param on `get_registration_node`

**Files:** Modify `swane/nipype_pipeline/nodes/utils.py`; Test `test_registration_abstraction.py`.

**Interfaces:**
- Produces: `get_registration_node(..., moving_mask: list[Node|str] | str | None = None, ...)`. On the ANTS branch, when provided, connects/sets `AntsRegistration.moving_mask`. FSL/Synth branches ignore it.

- [ ] **Step 1: Write failing test** — ANTS `get_registration_node(moving_mask=[src, "weight"])` wires `weight`→`AntsRegistration.moving_mask`; without it the input stays undefined.

- [ ] **Step 2: Run to verify fail.**

- [ ] **Step 3: Implement** — add the `moving_mask` parameter; in the ANTS branch, after building `ants_reg`:

```python
        if moving_mask is not None:
            if type(moving_mask) == str:
                ants_reg.inputs.moving_mask = moving_mask
            else:
                workflow.connect(moving_mask[0], moving_mask[1], ants_reg, "moving_mask")
```

- [ ] **Step 4: Run to verify pass.**

- [ ] **Step 5: Commit** — `git commit -m "feat: pass moving_mask through get_registration_node ANTS branch"`

### Task 5: round-trip correctness test (risk #1 guard)

**Files:** Test `swane/tests/nipype_pipeline/nodes/test_ants_compose_transform.py` (or the abstraction test file).

**Interfaces:** Consumes A + Task 3.

- [ ] **Step 1: Write the heavy-gated round-trip test** — on a synthetic phantom: run `AntsRegistration` (SyN), then (a) apply the raw `fwd_transforms` with `fwd_which_to_invert` via `AntsApplyTransforms`, and (b) compose `fwd_transforms` (reference=fixed) via `AntsComposeTransform` then apply the single field via the single-field path. Assert results match (`corrcoef ~ 1.0`, identical geometry). Repeat for the inverse (reference=moving). This is the guard that the composed field's direction/space equals the raw-list application.

- [ ] **Step 2: Run to verify** (heavy) — `... -m pytest -p no:datalad -m heavy -k roundtrip -v`. If it fails, the composition direction/`which_to_invert`/reference-space is wrong — fix in `AntsComposeTransform` (Session A) before proceeding; report to orchestrator.

- [ ] **Step 3: Commit** — `git commit -m "test: round-trip guard for composed vs raw-list transform application"`

**→ CHECKPOINT CP-C.**

---

## SESSION D — Producer: `nonlinear_reg_workflow`  (Opus 4.8)

> Consumes C. Read `nonlinear_reg_workflow.py` and the ANTS branch of `get_registration_node` first.

### Task 6: compose branch + lift pin

**Files:**
- Modify: `swane/nipype_pipeline/workflows/nonlinear_reg_workflow.py`
- Test: `swane/tests/nipype_pipeline/matrix/test_nonlinear_reg_matrix.py` (construction assertions; snapshot regen deferred to G)

**Interfaces:**
- Consumes: `AntsComposeTransform`, `get_registration_node` (wrapper with `fwd_transforms`/`inv_transforms`/`fwd_which_to_invert`/`inv_which_to_invert`).
- Produces: under ANTS, `outputnode.fieldcoeff_file`/`inverse_warp` are the **composed single fields**; field names/cardinality unchanged. FSL/Synth unchanged.

- [ ] **Step 1: Write failing test** — build `nonlinear_reg_workflow` with a synth_config whose `engine=ANTS`; assert the graph contains an `AntsRegistration` node and two `AntsComposeTransform` nodes, and that `outputnode.fieldcoeff_file`/`inverse_warp` are fed from the compose nodes (not directly from the registration list outputs). Also assert an `engine=FSL` config still builds FLIRT/FNIRT/InvWarp unchanged.

- [ ] **Step 2: Run to verify fail** — `... -m pytest -p no:datalad swane/tests/nipype_pipeline/matrix/test_nonlinear_reg_matrix.py -k ants -v`. Expected: FAIL (pin still forces FSL; no compose nodes).

- [ ] **Step 3: Implement**
  - Change `resolve_registration_engine(synth_config, allow_ants=False)` → `allow_ants=True`.
  - Keep the FSL/Synth output wiring as-is (guard on `engine`).
  - Under ANTS, after `reg_wrap = get_registration_node(...)`, build:

```python
    if engine == RegistrationEngine.ANTS:
        fwd_compose = Node(AntsComposeTransform(), name=name + "_fwd_compose")
        fwd_compose.long_name = "reference to atlas warp composition"
        workflow.connect(inputnode, "atlas", fwd_compose, "reference_image")
        _connect_list(workflow, reg_wrap.fwd_transforms, fwd_compose, "transformlist")
        workflow.connect(reg_wrap.fwd_which_to_invert[0], reg_wrap.fwd_which_to_invert[1],
                         fwd_compose, "which_to_invert")
        workflow.connect(fwd_compose, "out_field", outputnode, "fieldcoeff_file")

        inv_compose = Node(AntsComposeTransform(), name=name + "_inv_compose")
        inv_compose.long_name = "atlas to reference warp composition"
        workflow.connect(inputnode, "in_file", inv_compose, "reference_image")
        _connect_list(workflow, reg_wrap.inv_transforms, inv_compose, "transformlist")
        workflow.connect(reg_wrap.inv_which_to_invert[0], reg_wrap.inv_which_to_invert[1],
                         inv_compose, "which_to_invert")
        workflow.connect(inv_compose, "out_field", outputnode, "inverse_warp")
    else:
        # existing FSL/Synth wiring
        workflow.connect(reg_wrap.out_registered_node, reg_wrap.warp, outputnode, "fieldcoeff_file")
        workflow.connect(reg_wrap.inv_warp_node, reg_wrap.inv_warp, outputnode, "inverse_warp")
```

`reg_wrap.fwd_transforms` is a list of `(node, field)`; for a single ANTs node it has one entry, so `_connect_list` connects that entry to `transformlist` (reuse the same list-vs-scalar handling decided in Task 3 — factor it into a shared helper in `utils.py` if not already, and import it). `warped_file` wiring stays unchanged.

- [ ] **Step 4: Run to verify pass** — same as Step 2, plus FSL/SYNTH construction cases: `... -m pytest -p no:datalad swane/tests/nipype_pipeline/matrix/test_nonlinear_reg_matrix.py -v` (snapshot mismatches are EXPECTED here and regenerated in G — for now assert on node/edge structure, not snapshot bytes; if the file is snapshot-only, add explicit construction assertions in a new test function).

- [ ] **Step 5: Commit** — `git commit -m "feat: nonlinear_reg emits composed ANTs field; lift FSL pin"`

**→ CHECKPOINT CP-D.**

---

## SESSION E — Nonlinear-warp consumers  (Sonnet 5)

> Consumes D. Each consumer already calls `apply_registration_node(warp=[inputnode, "<field>"], engine=engine, non_linear=True, ...)`; Session C made that route to the single-field ANTS path. The change per file is the pin lift plus a construction test.

### Task 7: lift pins on flat1 / func_map / tractography

**Files:**
- Modify: `swane/nipype_pipeline/workflows/flat1_workflow.py`, `func_map_workflow.py`, `tractography_workflow.py`
- Test: `swane/tests/nipype_pipeline/matrix/test_flat1_matrix.py`, `test_func_map_matrix.py`, `test_tractography_matrix.py` (construction assertions; snapshot regen in G)

**Interfaces:** Consumes C+D. Produces: each workflow under ANTS builds `AntsApplyTransforms` fed the composed boundary field; boundary field names unchanged.

- [ ] **Step 1: Write failing tests** — for each of the three workflows, build under an `engine=ANTS` synth_config and assert the nonlinear applies are `AntsApplyTransforms` nodes (flat1: 7; func_map AI branch: fwd+inv; tractography: seed/target/[exclude]/[stop]), each with `transformlist` fed from the relevant `inputnode` field. Assert `engine=FSL` still builds `ApplyWarp`.

- [ ] **Step 2: Run to verify fail** — `... -m pytest -p no:datalad swane/tests/nipype_pipeline/matrix/test_flat1_matrix.py swane/tests/nipype_pipeline/matrix/test_func_map_matrix.py swane/tests/nipype_pipeline/matrix/test_tractography_matrix.py -k ants -v`. Expected: FAIL (pins force FSL).

- [ ] **Step 3: Implement** — in each file change `resolve_registration_engine(synth_config, allow_ants=False)` → `allow_ants=True`. No other change is required (the apply calls already pass `warp=[inputnode, field]`). Confirm `labelmap=True` paths in tractography still set `nearestNeighbor` under ANTS.

- [ ] **Step 4: Run to verify pass** — same as Step 2, plus FSL/SYNTH construction green.

- [ ] **Step 5: Commit** — `git commit -m "feat: port flat1/func_map/tractography nonlinear warp consumption to ANTs"`

**→ CHECKPOINT CP-E.**

---

## SESSION F — Cross-modality CT  (Opus 4.8)

> Consumes C (+B for `moving_mask`). May run in parallel with D+E. Read `venous_ct_workflow.py` and `seeg_ct_workflow.py` first; note `contrast_2_basal` is a `MapNode`.

### Task 8: route venous_ct + seeg_ct through the abstraction; remove the CT pin

**Files:**
- Modify: `swane/nipype_pipeline/workflows/venous_ct_workflow.py`, `swane/nipype_pipeline/workflows/seeg_ct_workflow.py`
- Test: `swane/tests/nipype_pipeline/matrix/test_venous_ct_matrix.py`, `test_seeg_ct_matrix.py` (construction; snapshot regen in G)

**Interfaces:** Produces: both workflows resolve `engine = resolve_registration_engine(synth_config, allow_ants=True)` and build registration/apply through the abstraction; the `# FLIRT performs better on CT` comment/pin is removed. `venous_ct` MapNode iteration preserved. `seeg_ct` passes the electrode weight map as `moving_mask` (ANTS) / `in_weight` (FSL).

> These workflows currently take a plain `config: SectionProxy` and do not receive `synth_config`. Add a `synth_config` parameter to each factory and thread it from `MainWorkflow` (see `launch_venous_ct_analysis`/`launch_seeg_ct_analysis`). Also pass `test_run`/`max_cpu`/`multicore_node_limit` if the abstraction needs them, matching how other workflows call `get_registration_node`.

- [ ] **Step 1: Write failing tests** — build each workflow under `engine=ANTS` and assert the reference registration is an `AntsRegistration` node (venous: basal→ref; seeg: seeg→ref) and the final resample is `AntsApplyTransforms`; assert `engine=FSL` still builds FLIRT/ApplyXFM. For seeg ANTS, assert the weight map is wired to `AntsRegistration.moving_mask`. For venous, assert `contrast_2_basal` remains a `MapNode` with its `iterfield` under both engines.

- [ ] **Step 2: Run to verify fail** — `... -m pytest -p no:datalad swane/tests/nipype_pipeline/matrix/test_venous_ct_matrix.py swane/tests/nipype_pipeline/matrix/test_seeg_ct_matrix.py -k ants -v`.

- [ ] **Step 3: Implement**
  - **venous_ct**: add `synth_config` param; resolve engine. Replace `basal_2_ref` (FLIRT) with `get_registration_node(non_linear=False, is_volumetric=True, flirt_cost="mutualinfo", flirt_search=90)`; replace `veins_2_ref` (ApplyXFM) with `apply_registration_node(non_linear=False, warp=<basal_2_ref forward>, ...)`. For `contrast_2_basal` (MapNode over `in_file`): the abstraction's `apply`/`get` helpers build `Node`, not `MapNode`. Keep `contrast_2_basal` as a direct-tool MapNode but make it engine-aware — build `FLIRT` MapNode on FSL/Synth and an `AntsRegistration` MapNode on ANTS (or, if the registration output is only used to resample the contrast onto basal and then subtract, evaluate whether an `AntsApplyTransforms` MapNode suffices). Choose the least-invasive shape that preserves the per-input iteration and the downstream subtraction; document the choice in a comment.
  - **seeg_ct**: add `synth_config` param; resolve engine. Replace `seeg_ct_2_ref_flirt` (FLIRT with `in_weight`) with `get_registration_node(non_linear=False, is_volumetric=True, flirt_cost="mutualinfo")`, passing the electrode weight map as `moving_mask` on ANTS and (on the FSL branch) preserving `in_weight`. Verify the binary weight map polarity (0 on electrodes) is correct for an ANTs metric mask (1 = region to register on) — if inverted, adjust the weight-map op_string or invert for the mask.
  - Remove the `# Do not use synthmorph, FLIRT performs better on CT` comments.
  - Update `MainWorkflow.launch_venous_ct_analysis`/`launch_seeg_ct_analysis` to pass `synth_config` (and any added params).

- [ ] **Step 4: Run to verify pass** — same as Step 2, plus FSL/SYNTH construction green.

- [ ] **Step 5: Commit** — `git commit -m "feat: route venous_ct/seeg_ct through registration abstraction; remove CT FSL pin"`

**→ CHECKPOINT CP-F.**

---

## SESSION G — Snapshots + prerelease  (Sonnet 5)

> Consumes E + F. All construction/graph tests are green; this session regenerates golden snapshots and reviews them by eye, then extends the prerelease smoke.

### Task 9: regenerate and review golden snapshots

**Files:**
- Modify: matrix SCENARIOS + snapshots for `nonlinear_reg`, `flat1`, `func_map`, `tractography`, `venous_ct`, `seeg_ct`.

- [ ] **Step 1: Add/confirm an `engine` dimension** in the SCENARIOS of each affected matrix test so all three engines stay covered at graph level, with the **default scenario per workflow** now ANTS (the Phase-2 flip) — mirror how Phase 1 did this for `linear_reg`/`nonlinear_reg`.
- [ ] **Step 2: Run** the affected matrix tests, expect FAIL (missing ANTS snapshots / changed defaults): `... -m pytest -p no:datalad swane/tests/nipype_pipeline/matrix -v`.
- [ ] **Step 3: Regenerate** — `SWANE_SNAPSHOT_UPDATE=1 /media/Dati/Installer_completi/Programmi/conda_env/swane-env/bin/python -m pytest -p no:datalad swane/tests/nipype_pipeline/matrix/test_nonlinear_reg_matrix.py swane/tests/nipype_pipeline/matrix/test_flat1_matrix.py swane/tests/nipype_pipeline/matrix/test_func_map_matrix.py swane/tests/nipype_pipeline/matrix/test_tractography_matrix.py swane/tests/nipype_pipeline/matrix/test_venous_ct_matrix.py swane/tests/nipype_pipeline/matrix/test_seeg_ct_matrix.py`.
- [ ] **Step 4: Review every diff by eye** — confirm ANTS nodes (`AntsRegistration`, `AntsApplyTransforms`, `AntsComposeTransform`), connections, `which_to_invert` absence at boundaries, `nearestNeighbor` on label maps, and deterministic filenames are correct — not merely present. This is a required orchestrator review, not auto-accept.
- [ ] **Step 5: Run** the full matrix suite green: `... -m pytest -p no:datalad swane/tests/nipype_pipeline/matrix -v`.
- [ ] **Step 6: Commit** — `git commit -m "test: regenerate golden snapshots for ANTs-default nonlinear + cross-modality CT"`

### Task 10: extend prerelease smoke + version bump

**Files:**
- Modify: `swane/tests/prerelease/plan.py`; `swane/__init__.py` (version).

- [ ] **Step 1:** Ensure the prerelease plan exercises, under the ANTS default, at least one pass that builds the nonlinear registration + a nonlinear consumer (flat1 or func_map or tractography) and the CT workflows end-to-end. Follow the existing `structural_ants` pattern and `_PASS_REQUIREMENTS`/capability gating (antspyx cap). Add named passes only where a backend must be forced; gate ANTS passes on the `antspyx` capability.
- [ ] **Step 2: Run** the prerelease integrity tests: `... -m pytest -p no:datalad swane/tests/prerelease -v`.
- [ ] **Step 3 (opt-in, real tools):** with antspyx installed and `~/test_swane/prerelease` verified, run the smoke pass(es) and confirm the ANTS nonlinear + CT paths execute end-to-end. Record failures; do not treat success as scientific validation.
- [ ] **Step 4:** Bump `__version__` (per the release convention in `swane/__init__.py`). No `force_pref_reset` change.
- [ ] **Step 5: Commit** — `git commit -m "test: prerelease smoke for ANTs nonlinear + CT; bump version"`

**→ CHECKPOINT CP-G:** all matrix snapshots reviewed; prerelease smoke green under ANTS default. Report explicitly what was NOT scientifically validated (ANTs-vs-FSL equivalence — that is the local oracle's job and the user's acceptance). Orchestrator closes Phase 2.

---

## Self-review

**Spec coverage:** `AntsComposeTransform` (Task 1) ↔ spec §1; `moving_mask` (Tasks 2,4) ↔ §2/§3; single-field apply path (Task 3) ↔ §3; producer compose + pin lift (Task 6) ↔ §4; consumer pin lifts (Task 7) ↔ §5; CT routing + pin removal (Task 8) ↔ §6; round-trip guard (Task 5) ↔ Testing "round-trip"; snapshots (Task 9) + prerelease (Task 10) ↔ Testing; version bump / no force_pref_reset (Task 10) ↔ Decisions §6. The comparative oracle is intentionally NOT a task (local, never committed). Phase-3 items (EPI, resting_state chain, probtrackx `.mat` bridge) are out of scope by the spec.

**Placeholder scan:** antspyx `_run_interface` bodies and the heavy round-trip/compose test bodies carry explicit "VERIFY against installed antspyx" / `...` markers — the project-mandated no-invention guardrail (as in Phase 1), each stating intended behavior + expected shape. The `contrast_2_basal` MapNode routing and the seeg weight-map polarity are flagged as implementer decisions with the exact options to choose between. All other steps carry runnable code or exact edits.

**Type consistency:** `AntsComposeTransform` inputs `transformlist`/`which_to_invert`/`reference_image` and output `out_field` (Task 1) are used identically in Task 6. `RegistrationNodeWrapper.fwd_transforms`/`inv_transforms`/`fwd_which_to_invert`/`inv_which_to_invert` (existing, from Phase 1) drive Task 6's compose wiring. `apply_registration_node(registration=None, warp=[node,field])` single-field path (Task 3) is what Tasks 7 and the consumers rely on. `get_registration_node(moving_mask=...)` (Task 4) is consumed by Task 8 (seeg). The list-vs-scalar `transformlist` helper decided in Task 3 is reused by Task 6.
