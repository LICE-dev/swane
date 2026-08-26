# ANTs (antspyx) Registration — Phase 3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Each *session* below runs in its **own separate Claude Code session**; the session that produced this plan is the **orchestrator** and reviews the feedback checkpoints between sessions.

**Goal:** Flip the EPI (`fMRI_preproc`/`fMRI_task`/`fMRI_resting_state`) and diffusion (`dti_preproc`) registrations off their FSL pins so the whole registration surface follows the configured engine (ANTs by default), replacing the probtrackx FSL-`.mat` dependency by externalizing probtrackx's transforms (register ROIs into diffusion space ourselves, run probtrackx natively there, warp results back to reference).

**Architecture:** EPI exposes its func→ref registration backend-agnostically (a `RegistrationNodeWrapper` attached to the shared workflow) so `task`/`resting` consume it via `registration=` (correct `which_to_invert`) instead of a hardcoded node-name + bare `.mat`. The resting func→ref→mni concatenation becomes a stacked ANTs `transformlist` (new ANTS-only multi-warp path in `apply_registration_node`); FSL keeps `ConvertWarp`. Diffusion flips fully to ANTs and drops the FSL-`.mat`/`LTAConvert` machinery because tractography is externalized from probtrackx.

**Tech Stack:** Python, Nipype 1.10.0, antspyx (Python import only — never ANTs binaries / `nipype.interfaces.ants`), nibabel, numpy 2.2.4, SimpleITK, FSL (probtrackx/bedpostx), pytest.

**Spec:** `docs/superpowers/specs/2026-08-26-ants-registration-phase3-design.md`

## Global Constraints

- Python (tests/exploration/app) ONLY via SWANe's env interpreter; run pytest with `-p no:datalad`. Verify with `python -c "import sys; print(sys.executable)"`. Never FSL's `fslpython` / FreeSurfer's `fspython`. The interpreter path is machine-specific — the orchestrator sets `$SWANE_PY` on the current system and each session uses that (see the orchestrator prompt / env recreation).
- antspyx via the `ants` Python import only. Never ANTs binaries, never `nipype.interfaces.ants`. Do not vendor/copy antspyx or ANTs source.
- antspyx exact API (apply / `transformlist` / `whichtoinvert` shapes, interpolator names) MUST be verified against the installed antspyx before writing call bodies. Where this plan shows an antspyx call, treat it as *intended behavior to verify*, not confirmed syntax.
- Preserve stable contracts: persisted preference keys/section names, enum member names, workflow/node names for sinked results, deterministic result filenames, Slicer mappings, and any `outputnode` field that is **sinked** (`FA`, `fdt_paths_*`, `waytotal_*`, fMRI thresholds, `thresh_zstat_files`, `mel_mix`). The diffusion diff↔ref `outputnode` fields (currently `.mat`) DO change format+name — they are internal MainWorkflow↔tractography wiring, updated atomically.
- Preserve image header/affine/orientation/dtype (nibabel discipline).
- Terminology: "subject" not "patient"; no clinical/medical framing. English only.
- A passing test is software-regression evidence only — never scientific/clinical validation.
- Code must run on both Ubuntu and macOS. Format changed Python with Black; do not reformat unrelated files.
- The comparative ANTs-vs-FSL oracle is a **local throwaway tool** (outside the repo). It is **never** committed to SWANe nor pushed to GitHub. Only software-regression tests are committed.
- Stay on branch `claude/ants-registration`. Never commit/push/merge/PR unless the user explicitly asks. Each session: rebase onto the latest orchestrator-merged state before starting; commit per task.

---

## Session orchestration

Six sessions. **A**, **B**, **D** are independent (parallel-capable). **C** depends on A+B. **E** depends on D. **F** depends on C+E. After each session the executing session reports to the orchestrator at the named checkpoint and waits.

| Session | Scope | Depends on | Model |
|---|---|---|---|
| **A — multi-warp ANTS apply path** | Task 1 | — | **Opus 5** |
| **B — `fMRI_preproc` exposure + flip** | Task 2 | — | **Opus 4.8** |
| **C — EPI consumers + resting concat** | Tasks 3–4 | A, B | **Opus 5** |
| **D — `dti_preproc` flip + outputnode** | Task 5 | — | **Opus 4.8** |
| **E — tractography externalization** | Task 6 | D | **Opus 4.8** |
| **F — snapshots + prerelease + version** | Tasks 7–8 | C, E | **Sonnet 5** |

**Checkpoints:** CP-A … CP-F as described per session below. The orchestrator reviews and green-lights the next dependent session.

---

## File structure

**Modify:**
- `swane/nipype_pipeline/nodes/utils.py` — ANTS multi-warp apply path (A)
- `swane/tests/nipype_pipeline/nodes/test_registration_abstraction.py` — multi-warp tests + round-trip guard (A)
- `swane/nipype_pipeline/workflows/fMRI_preproc_workflow.py` — expose func→ref, flip, thread `synth_config` (B)
- `swane/nipype_pipeline/workflows/fMRI_task_workflow.py` — consume `reg_2_ref` via `registration=`, flip (C)
- `swane/nipype_pipeline/workflows/fMRI_resting_state_workflow.py` — consumer flip + ANTS concat (C)
- `swane/nipype_pipeline/workflows/dti_preproc_workflow.py` — flip, outputnode transform-list, delete `LTAConvert`, expose b0 brain (D)
- `swane/nipype_pipeline/workflows/tractography_workflow.py` — externalization (E)
- `swane/nipype_pipeline/MainWorkflow.py` — thread `synth_config`/`max_cpu`/`multicore`/`test_run` into fMRI launches; update tractography connections (B for fMRI params, E for tractography)
- matrix tests + snapshots for fMRI_preproc / fMRI_task / fMRI_resting_state / dti_preproc / tractography (C, D, E construction asserts; F regen)
- `swane/tests/prerelease/plan.py` — EPI-ANTS + externalized DTI/tractography (F)
- `swane/__init__.py` — version bump (F)

---

## SESSION A — multi-warp ANTS apply path  (Opus 5)

> The EPI concat mechanism. `wire_transforms` today raises for >1 transform source (`utils.py:595`). Add an ANTS path that stacks an ordered list of registration wrappers into one `transformlist` + one `which_to_invert`, in output→input order. Read `utils.py` (`RegistrationNodeWrapper`, `wire_transforms`, `apply_registration_node` ANTS branch) first.

### Task 1: `registration_stack` on `apply_registration_node`

**Files:**
- Modify: `swane/nipype_pipeline/nodes/utils.py`
- Test: `swane/tests/nipype_pipeline/nodes/test_registration_abstraction.py`

**Interfaces:**
- Consumes: existing `RegistrationNodeWrapper` (`fwd_transforms`/`inv_transforms` = list of `(node, field)`; `fwd_which_to_invert`/`inv_which_to_invert` = single `(node, field)` whose field is a `List(Bool)` output, ANTs only).
- Produces: `apply_registration_node(..., registration_stack: list[RegistrationNodeWrapper] = None, inverse: bool = False)`. When `registration_stack` is given (ANTS engine only), the ANTS branch builds a `Merge(len(stack), ravel_inputs=True)` fed by each wrapper's `fwd_transforms[i]` (or `inv_transforms[i]` when `inverse`) — the stack order **is** the `transformlist` order (output→input, ANTs right-to-left) — and a parallel `Merge(len(stack), ravel_inputs=True)` fed by each wrapper's `fwd_which_to_invert` (or `inv_which_to_invert`), connected to `AntsApplyTransforms.transformlist` / `which_to_invert`. `registration_stack` is mutually exclusive with `registration` and the bare `warp=` boundary path.

- [ ] **Step 1: Write the failing test** (construction: two ANTS wrappers stack into ravel Merges)

```python
def test_ants_registration_stack_builds_ravel_merges(make_workflow):
    from swane.config.config_enums import RegistrationEngine
    from swane.nipype_pipeline.nodes.utils import (
        apply_registration_node, RegistrationNodeWrapper,
    )
    from nipype import Node, IdentityInterface
    wf = make_workflow()  # a bare CustomWorkflow (see existing fixtures)
    # two fake registration sources exposing ANTs-shaped transform outputs
    src_mni = Node(IdentityInterface(
        fields=["fwd_transforms", "fwd_which_to_invert"]), name="src_mni")
    src_ref = Node(IdentityInterface(
        fields=["fwd_transforms", "fwd_which_to_invert"]), name="src_ref")
    wf.add_nodes([src_mni, src_ref])
    reg_mni = RegistrationNodeWrapper(
        input_node=src_mni, out_registered_node=src_mni, warp="fwd_transforms",
        inv_warp_node=src_mni, inv_warp="fwd_transforms",
        engine=RegistrationEngine.ANTS,
        fwd_transforms=[(src_mni, "fwd_transforms")],
        fwd_which_to_invert=(src_mni, "fwd_which_to_invert"),
    )
    reg_ref = RegistrationNodeWrapper(
        input_node=src_ref, out_registered_node=src_ref, warp="fwd_transforms",
        inv_warp_node=src_ref, inv_warp="fwd_transforms",
        engine=RegistrationEngine.ANTS,
        fwd_transforms=[(src_ref, "fwd_transforms")],
        fwd_which_to_invert=(src_ref, "fwd_which_to_invert"),
    )
    apply_node = apply_registration_node(
        name="func_2_mni", engine=RegistrationEngine.ANTS, workflow=wf,
        warp=None, moving="/tmp/func.nii.gz", reference="/tmp/mni.nii.gz",
        non_linear=True, registration_stack=[reg_mni, reg_ref],
    )
    assert apply_node.interface.__class__.__name__ == "AntsApplyTransforms"
    # a ravel Merge(2) feeds transformlist, another feeds which_to_invert
    names = [n.name for n in wf._graph.nodes()]
    assert any("transformlist" in n for n in names)
    assert any("which_to_invert" in n for n in names)
    # order preserved: src_mni feeds in1, src_ref feeds in2 of the transformlist merge
```

- [ ] **Step 2: Run to verify fail**

Run: `$SWANE_PY -m pytest -p no:datalad swane/tests/nipype_pipeline/nodes/test_registration_abstraction.py -k registration_stack -v`
Expected: FAIL (`apply_registration_node` has no `registration_stack` param → TypeError).

- [ ] **Step 3: Implement** — in the ANTS branch of `apply_registration_node`, before the `registration is not None` check, add:

```python
        if registration_stack is not None:
            tl_merge = Node(
                Merge(len(registration_stack), ravel_inputs=True),
                name=name + "_transformlist",
            )
            wti_merge = Node(
                Merge(len(registration_stack), ravel_inputs=True),
                name=name + "_which_to_invert",
            )
            for i, reg in enumerate(registration_stack, start=1):
                transforms = reg.inv_transforms if inverse else reg.fwd_transforms
                which = reg.inv_which_to_invert if inverse else reg.fwd_which_to_invert
                # each wrapper contributes exactly one (node, field) list source
                src_node, src_field = transforms[0]
                workflow.connect(src_node, src_field, tl_merge, "in%d" % i)
                workflow.connect(which[0], which[1], wti_merge, "in%d" % i)
            workflow.connect(tl_merge, "out", apply_node, "transformlist")
            workflow.connect(wti_merge, "out", apply_node, "which_to_invert")
```

Add the signature params `registration_stack: list = None` and (if not already) `inverse: bool = False` is present. Ensure `Merge` is imported in `utils.py` (it already is, used by the boundary path). Keep `registration_stack` mutually exclusive: if both `registration` and `registration_stack` are given, raise `ValueError`.

> VERIFY against installed antspyx: `ravel_inputs=True` on nipype `Merge` flattens `[[warp, affine], [aff]] → [warp, affine, aff]`; confirm each wrapper's `fwd_transforms`/`fwd_which_to_invert` field is a `List` output so ravel produces a flat list in the intended order.

- [ ] **Step 4: Run to verify pass** — same as Step 2, plus the whole abstraction file green:
`$SWANE_PY -m pytest -p no:datalad swane/tests/nipype_pipeline/nodes/test_registration_abstraction.py -v`

- [ ] **Step 5: Commit**

```bash
git add swane/nipype_pipeline/nodes/utils.py swane/tests/nipype_pipeline/nodes/test_registration_abstraction.py
git commit -m "feat: ANTS multi-warp apply path (stack registration wrappers into one transformlist)"
```

- [ ] **Step 6: Heavy round-trip guard** (direction/order correctness — the #1 Phase-3 risk)

Write a `@pytest.mark.heavy` test on a synthetic phantom: build a linear `AntsRegistration` (func→ref) and a nonlinear `AntsRegistration` (ref→mni); (a) apply them **sequentially** (func→ref then ref→mni) to a moving image, and (b) apply the **stacked** `registration_stack=[reg_mni, reg_ref]` in one `AntsApplyTransforms` through the new path; assert the two resampled images match (`np.allclose(..., atol=1e-4)`, identical geometry). Fill the body once the real `AntsRegistration` output shape is confirmed (mirror the Phase-2 `test_registration_abstraction.py` heavy round-trip). Run:
`$SWANE_PY -m pytest -p no:datalad -m heavy -k stack_roundtrip -v` (outside sandbox if seccomp blocks the nipype run).

If it fails, the stack order / `which_to_invert` is wrong — fix here before C consumes it; report to orchestrator.

- [ ] **Step 7: Commit the guard** — `git commit -m "test: heavy round-trip guard for ANTS multi-warp stack ordering"`

**→ CHECKPOINT CP-A:** multi-warp path builds correct ravel Merges; round-trip guard green. Orchestrator reviews order/direction before C.

---

## SESSION B — `fMRI_preproc` exposure + flip  (Opus 4.8)

> Read `fMRI_preproc_workflow.py`, the `fMRI_task`/`resting` node-name lookups, and `MainWorkflow.launch_fMRI_task_analysis`/`launch_fMRI_resting_state_analysis` first. `fMRI_task`/`resting` build on the SAME workflow object returned here.

### Task 2: expose func→ref, flip engine, thread `synth_config`

**Files:**
- Modify: `swane/nipype_pipeline/workflows/fMRI_preproc_workflow.py`
- Modify: `swane/nipype_pipeline/MainWorkflow.py`
- Test: `swane/tests/nipype_pipeline/matrix/test_fmri_preproc_matrix.py` (or the existing fMRI matrix test file; construction asserts)

**Interfaces:**
- Produces: `fMRI_preproc_workflow(name, dicom_dir, TR, slice_timing, n_vols, del_start_vols, del_end_vols, hpcutoff, synth_config: SectionProxy, base_dir="/", max_cpu=0, multicore_node_limit=CoreLimit.SOFT_CAP, test_run=False)` returning a `CustomWorkflow` with the func→ref `RegistrationNodeWrapper` attached as `workflow.reg_2_ref`. Under the resolved engine (`resolve_registration_engine(synth_config, allow_ants=True)`, `SYNTH→FSL`), `reg_2_ref` is an ANTs/FLIRT registration; consumers pass it as `registration=workflow.reg_2_ref` to `apply_registration_node`.
- Consumes: `resolve_registration_engine`, `get_registration_node` (existing).

- [ ] **Step 1: Write failing test** — build `fMRI_preproc_workflow` with a `synth_config` whose `engine=ANTS`; assert `workflow.reg_2_ref` exists, is a `RegistrationNodeWrapper`, `engine == RegistrationEngine.ANTS`, and the registration node in the graph is an `AntsRegistration` (not `FLIRT`). Assert an `engine=FSL` config yields a `FLIRT` node and `engine=SYNTH` falls back to `FLIRT` (SYNTH→FSL).

```python
def test_fmri_preproc_exposes_reg_2_ref_ants(make_synth_config):
    from swane.config.config_enums import RegistrationEngine
    from swane.nipype_pipeline.nodes.utils import RegistrationNodeWrapper
    from swane.nipype_pipeline.workflows.fMRI_preproc_workflow import fMRI_preproc_workflow
    from swane.config.config_enums import SliceTiming
    wf = fMRI_preproc_workflow(
        name="fmri", dicom_dir="/tmp/dcm", TR=2.0,
        slice_timing=SliceTiming.UNKNOWN, n_vols=100,
        del_start_vols=0, del_end_vols=0, hpcutoff=100,
        synth_config=make_synth_config(engine=RegistrationEngine.ANTS),
    )
    assert isinstance(wf.reg_2_ref, RegistrationNodeWrapper)
    assert wf.reg_2_ref.engine == RegistrationEngine.ANTS
    node_types = {type(n.interface).__name__ for n in wf._graph.nodes()}
    assert "AntsRegistration" in node_types
```

- [ ] **Step 2: Run to verify fail** — `$SWANE_PY -m pytest -p no:datalad swane/tests/nipype_pipeline/matrix/test_fmri_preproc_matrix.py -k reg_2_ref -v`. Expected: FAIL (`synth_config` param missing / `reg_2_ref` absent).

- [ ] **Step 3: Implement**
  - Add imports: `resolve_registration_engine`, `RegistrationEngine`, `CoreLimit`, `SectionProxy`.
  - Add params `synth_config: SectionProxy`, `max_cpu: int = 0`, `multicore_node_limit: CoreLimit = CoreLimit.SOFT_CAP` to the factory signature (keep `test_run`).
  - Replace the `flirt_2_ref` block:

```python
    engine = resolve_registration_engine(synth_config, allow_ants=True)
    if engine == RegistrationEngine.SYNTH:
        engine = RegistrationEngine.FSL  # EPI: avoid SynthMorph (see spec §1)

    reg_2_ref = get_registration_node(
        name="%s_2_ref" % name,
        name_prefix=name,
        name_suffix="to reference space",
        engine=engine,
        workflow=workflow,
        moving=[meanfunc2, "out_file"],
        reference=[inputnode, "reference_brain"],
        non_linear=False,
        inverse=False,
        is_volumetric=True,
        flirt_cost="corratio",
        flirt_search=90,
        test_run=test_run,
        max_cpu=max_cpu,
        multicore_node_limit=multicore_node_limit,
        limit_synth_cores=synth_config.getboolean_safe("limit_cores"),
    )
    workflow.reg_2_ref = reg_2_ref
    return workflow
```
  Remove the "Stick to FSL intentionally avoiding synth for reproducibility reason" comment.
  > NOTE the node name: `get_registration_node` names the FSL node `<name>_2_ref_flirt` today (that is why the old lookup worked). Under ANTS the internal node name differs; consumers must NOT rely on it anymore — they use `workflow.reg_2_ref` (Task 3).
  - In `MainWorkflow.launch_fMRI_task_analysis` and `launch_fMRI_resting_state_analysis`, pass `synth_config=self.global_config[GlobalPrefCategoryList.SYNTH]`, `max_cpu=self.max_cpu`, `multicore_node_limit=self.multicore_node_limit`. (These launches currently omit them; `fMRI_task`/`resting` factories thread them down to `fMRI_preproc` — Task 3 adds the params there too.)

- [ ] **Step 4: Run to verify pass** — Step 2 command, plus FSL and SYNTH→FSL construction cases green.

- [ ] **Step 5: Commit** — `git commit -m "feat: fMRI_preproc exposes func->ref registration; follow engine (SYNTH->FSL)"`

**→ CHECKPOINT CP-B:** `fMRI_preproc` builds under all engines; `workflow.reg_2_ref` exposed; FSL construction unchanged.

---

## SESSION C — EPI consumers + resting concat  (Opus 5)

> Consumes A (`registration_stack`) and B (`workflow.reg_2_ref`). The resting func→ref→mni concat is the one truly critical Phase-3 part. Read `fMRI_task_workflow.py`, `fMRI_resting_state_workflow.py`, and the A/B as-built first.

### Task 3: `fMRI_task` + resting consumers use `registration=reg_2_ref`

**Files:**
- Modify: `swane/nipype_pipeline/workflows/fMRI_task_workflow.py`, `swane/nipype_pipeline/workflows/fMRI_resting_state_workflow.py`
- Test: `swane/tests/nipype_pipeline/matrix/test_fmri_task_matrix.py`, `test_fmri_resting_state_matrix.py` (construction)

**Interfaces:**
- Consumes: `workflow.reg_2_ref` (B), `apply_registration_node(registration=...)` (existing wrapper path).
- Produces: task `cluster_{1,2,3}_2_ref` and resting `zstats_2_ref` apply nodes use `registration=workflow.reg_2_ref` + the resolved EPI engine; no hardcoded `_flirt` lookup; boundary/output field names + filenames unchanged.

- [ ] **Step 1: Write failing tests** — under `engine=ANTS`, build `fMRI_task_workflow` and assert each `cluster_*_2_ref` is an `AntsApplyTransforms` whose `transformlist`/`which_to_invert` come from the func→ref registration node (via `wire_transforms`), NOT a bare `in_matrix_file`. Same for resting `zstats_2_ref`. Assert `engine=FSL` still builds `ApplyXFM`.

- [ ] **Step 2: Run to verify fail** — `$SWANE_PY -m pytest -p no:datalad swane/tests/nipype_pipeline/matrix/test_fmri_task_matrix.py swane/tests/nipype_pipeline/matrix/test_fmri_resting_state_matrix.py -k ants -v`.

- [ ] **Step 3: Implement**
  - Both factories: thread `synth_config`, `max_cpu`, `multicore_node_limit` into the `fMRI_preproc_workflow(...)` call (Task 2 added those params). Add `synth_config`/`max_cpu`/`multicore_node_limit` params to `fMRI_task_workflow`/`fMRI_resting_state_workflow` signatures (MainWorkflow passes them, Task 2 note).
  - `fMRI_task_workflow`: remove `flirt_2_ref = workflow.get_node("%s_2_ref_flirt" % name)`. For each of the six `cluster_*_2_ref` calls, replace `engine=RegistrationEngine.FSL, warp=[flirt_2_ref, "out_matrix_file"]` with `engine=<resolved EPI engine>, registration=workflow.reg_2_ref` (drop the `warp=` arg). Keep `non_linear=False`, `out_file`, `iterfield`, filenames, `outputnode` connections unchanged. Resolve the engine once at the top: `engine = resolve_registration_engine(synth_config, allow_ants=True); engine = FSL if engine==SYNTH else engine`.
  - `fMRI_resting_state_workflow`: remove `flirt_2_ref = workflow.get_node(...)`. Replace `zstats_2_ref`'s `engine=RegistrationEngine.FSL, warp=[flirt_2_ref, "out_matrix_file"]` with `engine=<resolved EPI engine>, registration=workflow.reg_2_ref`.

- [ ] **Step 4: Run to verify pass** — Step 2 command, plus FSL/SYNTH→FSL construction green.

- [ ] **Step 5: Commit** — `git commit -m "feat: EPI task/resting consume func->ref via registration= (follow engine)"`

### Task 4: resting func→ref→mni concat under ANTS

**Files:**
- Modify: `swane/nipype_pipeline/workflows/fMRI_resting_state_workflow.py`
- Test: `swane/tests/nipype_pipeline/matrix/test_fmri_resting_state_matrix.py`

**Interfaces:**
- Consumes: `registration_stack` (A), `workflow.reg_2_ref` (B), an in-workflow `ref_2_mni` `RegistrationNodeWrapper`.
- Produces: under ANTS, the AROMA-branch func→mni resample is a single `AntsApplyTransforms` fed a stacked `transformlist=[ref_2_mni fwd, reg_2_ref fwd]`; FSL/SYNTH→FSL keep `ConvertWarp` + `apply_registration_node(warp=[convert_warp,"out_file"])`.

- [ ] **Step 1: Write failing test** — under `engine=ANTS`, assert the AROMA branch has NO `ConvertWarp` node and the `func2mni` apply is an `AntsApplyTransforms` fed by a ravel `Merge` of the two registrations' transforms; under `engine=FSL`, assert `ConvertWarp` is present and feeds an `ApplyWarp`.

- [ ] **Step 2: Run to verify fail** — `$SWANE_PY -m pytest -p no:datalad swane/tests/nipype_pipeline/matrix/test_fmri_resting_state_matrix.py -k concat -v`.

- [ ] **Step 3: Implement** — in the `run_aroma` branch:
  - Change `reg_2_mni` to follow the engine: `get_registration_node(engine=<resolved EPI engine>, ..., non_linear=True, flirt_cost="corratio", flirt_search=90)` (it already returns a wrapper; keep the wrapper as `reg_2_mni`). Remove its "avoiding synth" comment.
  - Branch on engine:

```python
    if engine == RegistrationEngine.ANTS:
        # func -> mni in one shot: transformlist = [ref->mni fwd, func->ref fwd]
        # (output->input order; matches the FSL ConvertWarp premat=func->ref +
        # warp1=ref->mni semantics). Validated by CP-A's round-trip guard.
        apply_warp = apply_registration_node(
            name="func2mni",
            engine=RegistrationEngine.ANTS,
            workflow=workflow,
            warp=None,
            moving=[feature_spatial_prep, "out_file"],
            reference=mni2,
            non_linear=True,
            registration_stack=[reg_2_mni, workflow.reg_2_ref],
        )
    else:
        convert_warp = Node(ConvertWarp(), name="func_2_mni_warp")
        convert_warp.long_name = "func to atlas warp combination"
        convert_warp.inputs.reference = mni2
        workflow.connect(workflow.reg_2_ref.out_registered_node,
                         workflow.reg_2_ref.warp, convert_warp, "premat")
        workflow.connect(reg_2_mni.out_registered_node, reg_2_mni.warp,
                         convert_warp, "warp1")
        apply_warp = apply_registration_node(
            name="func2mni", engine=RegistrationEngine.FSL, workflow=workflow,
            warp=[convert_warp, "out_file"],
            moving=[feature_spatial_prep, "out_file"],
            reference=mni2, non_linear=True,
        )
```
  > NOTE: the FSL branch's `premat` used to read `flirt_2_ref.out_matrix_file`; now it reads `workflow.reg_2_ref.out_registered_node`/`.warp` (the FSL `.mat` view of the same wrapper — identical bytes on the FSL branch).

- [ ] **Step 4: Run to verify pass** — Step 2 command, plus FSL/SYNTH→FSL green.

- [ ] **Step 5: Commit** — `git commit -m "feat: resting func->ref->mni concat as ANTS transformlist stack (FSL keeps ConvertWarp)"`

**→ CHECKPOINT CP-C:** task/resting construct under ANTS with correct func→ref applies and the ANTS concat stack; FSL/SYNTH→FSL green.

---

## SESSION D — `dti_preproc` flip + outputnode  (Opus 4.8)

> Read `dti_preproc_workflow.py` first. The diff↔ref `.mat` outputs become the ANTs transform-list view; `LTAConvert` is deleted; the betted b0 (`b0_deskull` `out_file`) is exposed for probtrackx `seed_ref`.

### Task 5: flip engine, change outputnode, expose b0 brain

**Files:**
- Modify: `swane/nipype_pipeline/workflows/dti_preproc_workflow.py`
- Test: `swane/tests/nipype_pipeline/matrix/test_dti_preproc_matrix.py` (construction)

**Interfaces:**
- Produces: `dti_preproc` `outputnode` gains `diff2ref_transforms`, `diff2ref_which_to_invert`, `ref2diff_transforms`, `ref2diff_which_to_invert` (replacing `diff2ref_mat`/`ref2diff_mat`) and `nodif_brain` (the betted b0, diffusion space). `dif2ref` follows `resolve_registration_engine(synth_config, allow_ants=True)` (SYNTH→FSL). `LTAConvert` removed.
- Consumed by: tractography (E) and `MainWorkflow` (E).

> Field-name decision (open question #3): use the four names above. They describe the ANTs-space content and are internal wiring (not sinked, not prefs).

- [ ] **Step 1: Write failing test** — under `engine=ANTS`, assert `dif2ref` is an `AntsRegistration`, there is NO `LTAConvert` node, and `outputnode` exposes `diff2ref_transforms`/`ref2diff_transforms`/`nodif_brain`. Assert `engine=FSL` builds `FLIRT` and also exposes the new fields (list view of the FSL `.mat`). Assert `engine=SYNTH` falls back to FSL (no `LTAConvert`).

- [ ] **Step 2: Run to verify fail** — `$SWANE_PY -m pytest -p no:datalad swane/tests/nipype_pipeline/matrix/test_dti_preproc_matrix.py -k ants -v`.

- [ ] **Step 3: Implement**
  - `engine = resolve_registration_engine(synth_config, allow_ants=True); engine = FSL if engine==SYNTH else engine`.
  - `outputnode` fields: replace `diff2ref_mat`/`ref2diff_mat` with `diff2ref_transforms`, `diff2ref_which_to_invert`, `ref2diff_transforms`, `ref2diff_which_to_invert`; add `nodif_brain`.
  - Delete the `if engine == RegistrationEngine.SYNTH: LTAConvert ...` block and the `LTAConvert` import.
  - Wire the wrapper's list views:

```python
    # forward: diff -> ref ; inverse: ref -> diff
    fwd_node, fwd_field = dif2ref.fwd_transforms[0]
    workflow.connect(fwd_node, fwd_field, outputnode, "diff2ref_transforms")
    workflow.connect(dif2ref.fwd_which_to_invert[0], dif2ref.fwd_which_to_invert[1],
                     outputnode, "diff2ref_which_to_invert")
    inv_node, inv_field = dif2ref.inv_transforms[0]
    workflow.connect(inv_node, inv_field, outputnode, "ref2diff_transforms")
    workflow.connect(dif2ref.inv_which_to_invert[0], dif2ref.inv_which_to_invert[1],
                     outputnode, "ref2diff_which_to_invert")
    workflow.connect(b0_deskull, "out_file", outputnode, "nodif_brain")
```
  > VERIFY the FSL/SYNTH-branch wrappers also populate `fwd_transforms`/`fwd_which_to_invert` shaped so tractography's `registration=`-style stacking works uniformly. On FSL, `fwd_which_to_invert` is `None`; tractography's E-code must handle `None` (FSL/Synth never invert on apply) — see E.
  - `fa_2_ref` is unchanged (already uses the abstraction).

- [ ] **Step 4: Run to verify pass** — Step 2 command, plus FSL/SYNTH→FSL green.

- [ ] **Step 5: Commit** — `git commit -m "feat: dti_preproc follows engine; emit transform-list diff<->ref; drop LTAConvert; expose b0 brain"`

**→ CHECKPOINT CP-D:** dti_preproc constructs under all engines; new outputnode transform fields; `LTAConvert` gone; FA apply green.

---

## SESSION E — tractography externalization  (Opus 4.8)

> Consumes D. The big structural change: probtrackx runs in diffusion space, no `xfm`/`inv_xfm`; ROIs pre-warped MNI→diff (two sequential single-warp applies); summed results warped diff→ref. Read `tractography_workflow.py`, `CustomProbTrackX2.py`, and `MainWorkflow.launch_dti_analysis` first. Verify probtrackx behaviour with identity transform + diffusion-space `seed_ref` against the installed FSL.

### Task 6: externalize probtrackx transforms

**Files:**
- Modify: `swane/nipype_pipeline/workflows/tractography_workflow.py`, `swane/nipype_pipeline/MainWorkflow.py`
- Test: `swane/tests/nipype_pipeline/matrix/test_tractography_matrix.py` (construction) + heavy equivalence guard

**Interfaces:**
- Consumes: `dti_preproc` outputnode `diff2ref_transforms`/`ref2diff_transforms` (+ which_to_invert), `nodif_brain`, `mni2ref_warp` (ANTS from Phase 2).
- Produces: `tractography_workflow` runs probtrackx with no `xfm`/`inv_xfm`; ROIs in diffusion space; per-side summed `fdt_paths` warped diff→ref; sinked filenames unchanged.

- [ ] **Step 1: Write failing test** — under `engine=ANTS`, assert: (a) probtrackx MapNodes have no `xfm`/`inv_xfm` connections and `seed_ref` is fed from `nodif_brain`; (b) each ROI (seed/target/exclude/stop) is warped MNI→ref then ref→diff (two `AntsApplyTransforms`, both `nearestNeighbor`); (c) each side has a diff→ref `AntsApplyTransforms` (linear) after `SumMultiTracks`, preserving `r-<tract>_<side>.nii.gz`. Assert `engine=FSL` builds the analogous FSL nodes (no `xfm`/`inv_xfm`).

- [ ] **Step 2: Run to verify fail** — `$SWANE_PY -m pytest -p no:datalad swane/tests/nipype_pipeline/matrix/test_tractography_matrix.py -k ants -v`.

- [ ] **Step 3: Implement**
  - `inputnode`: replace `diff2ref_mat`/`ref2diff_mat` with `diff2ref_transforms`, `diff2ref_which_to_invert`, `ref2diff_transforms`, `ref2diff_which_to_invert`; add `nodif_brain`.
  - Build a `RegistrationNodeWrapper`-like handle (or reuse the abstraction) for ref→diff from the inputnode fields, so the ref→diff apply carries `which_to_invert`. Since these arrive as separate inputnode fields, construct the apply directly: for ANTS use `apply_registration_node(registration_stack=[<ref2diff wrapper built from inputnode>], ...)` OR add a small wrapper built inline:

```python
    from swane.nipype_pipeline.nodes.utils import RegistrationNodeWrapper
    ref2diff = RegistrationNodeWrapper(
        input_node=inputnode, out_registered_node=inputnode,
        warp="ref2diff_transforms", inv_warp_node=inputnode,
        inv_warp="ref2diff_transforms", engine=engine,
        fwd_transforms=[(inputnode, "ref2diff_transforms")],
        fwd_which_to_invert=(inputnode, "ref2diff_which_to_invert")
            if engine == RegistrationEngine.ANTS else None,
    )
```
  - For each ROI: keep the existing MNI→ref apply (`warp=[inputnode, "mni2ref_warp"]`, `non_linear=True`, `labelmap=True`), then add a second apply ref→diff: `apply_registration_node(non_linear=False, labelmap=True, registration=ref2diff, moving=[<mni2ref apply>, "out_file"], reference=[inputnode, "nodif_brain"])`. The ROI now lands in diffusion space.
  > On FSL, `registration=ref2diff` routes through `wire_transforms`? No — `wire_transforms` is ANTS-only. For FSL/Synth the ref→diff apply must use the single-file `warp=` path with the `.mat`/warp. Handle both: if `engine==ANTS` use `registration=ref2diff`; else use `warp=[inputnode, "ref2diff_transforms"]` (single-file view). Encapsulate this in a small local helper to avoid per-engine branching sprawl.
  - probtrackx: remove `workflow.connect(inputnode, "ref2diff_mat", probtrackx, "xfm")` and `... "diff2ref_mat", probtrackx, "inv_xfm"` (and the inverted-run equivalents). Change `seed_ref` from `reference_brain` to `nodif_brain`. Feed seed/waypoints/avoid_mp/stop_mask from the diffusion-space ROIs.
  - `SumMultiTracks` stays in diffusion space (its inputs are now diff-space `fdt_paths`). After it, add per-side `sum_2_ref = apply_registration_node(non_linear=False, engine=engine, warp/registration=<diff2ref>, moving=[sum_multi_tracks, "out_file"], reference=[inputnode, "reference_brain"], out_file="r-%s_%s.nii.gz")`; connect `sum_2_ref.out_file` → `outputnode.fdt_paths_%s`. `waytotal` unchanged.
  > Build a `diff2ref` wrapper analogous to `ref2diff` from `diff2ref_transforms`/`diff2ref_which_to_invert` for this final warp.
  - `MainWorkflow.launch_dti_analysis`: update the tractography connections — `outputnode.diff2ref_transforms`(+which)/`ref2diff_transforms`(+which)/`nodif_brain` → the new inputnode fields (replace the old `diff2ref_mat`/`ref2diff_mat` connects); `mni2ref_warp` unchanged; also connect `dti_preproc.outputnode.nodif_brain` → `tractography.inputnode.nodif_brain`.

- [ ] **Step 4: Run to verify pass** — Step 2 command, plus FSL/SYNTH→FSL construction green; full nipype+config suite green.

- [ ] **Step 5: Heavy equivalence guard** — `@pytest.mark.heavy`: on a phantom, confirm the externalized ROI (MNI→ref→diff) lands in the same diffusion voxels (within tolerance) as the prior single `.mat`-transform path would, for the FSL engine. Report to orchestrator.

- [ ] **Step 6: Commit** — `git commit -m "feat: externalize probtrackx transforms; tractography runs in diffusion space, results warped back to ref"`

**→ CHECKPOINT CP-E:** tractography constructs under all engines with diffusion-space probtrackx (no `xfm`/`inv_xfm`), MNI→diff ROI applies, diff→ref result warps; filenames preserved.

---

## SESSION F — snapshots + prerelease + version  (Sonnet 5)

> Consumes C + E. All construction/graph tests green; regenerate golden snapshots and review by eye, extend the prerelease smoke, bump the version.

### Task 7: regenerate and review golden snapshots

**Files:** matrix SCENARIOS + snapshots for `fMRI_preproc`, `fMRI_task`, `fMRI_resting_state`, `dti_preproc`, `tractography`.

- [ ] **Step 1: Add/confirm the `engine` dimension** in each affected matrix test's SCENARIOS so all three engines stay covered at graph level, with the default scenario now ANTS (SYNTH→FSL where applicable) — mirror how Phase 1/2 dimensioned `linear_reg`/`nonlinear_reg`/CT.
- [ ] **Step 2: Run** the affected matrix tests, expect FAIL (missing ANTS snapshots / changed defaults):
`$SWANE_PY -m pytest -p no:datalad swane/tests/nipype_pipeline/matrix -v`.
- [ ] **Step 3: Regenerate** —
`SWANE_SNAPSHOT_UPDATE=1 $SWANE_PY -m pytest -p no:datalad swane/tests/nipype_pipeline/matrix/test_fmri_preproc_matrix.py swane/tests/nipype_pipeline/matrix/test_fmri_task_matrix.py swane/tests/nipype_pipeline/matrix/test_fmri_resting_state_matrix.py swane/tests/nipype_pipeline/matrix/test_dti_preproc_matrix.py swane/tests/nipype_pipeline/matrix/test_tractography_matrix.py`.
- [ ] **Step 4: Review every diff by eye** — confirm ANTS nodes (`AntsRegistration`, `AntsApplyTransforms`, ravel `Merge` for the concat), absence of `xfm`/`inv_xfm` on probtrackx, `seed_ref`=`nodif_brain`, diff→ref result warps, `nearestNeighbor` on label ROIs, no `LTAConvert`/`ConvertWarp` under ANTS, and deterministic filenames — correct, not merely present. Required orchestrator review, not auto-accept.
- [ ] **Step 5: Run** the full matrix suite green.
- [ ] **Step 6: Commit** — `git commit -m "test: regenerate golden snapshots for ANTs-default EPI + externalized DTI/tractography"`

### Task 8: extend prerelease smoke + version bump

**Files:** `swane/tests/prerelease/plan.py`; `swane/__init__.py`.

- [ ] **Step 1:** Ensure the prerelease plan exercises, under the ANTS default, EPI (a task or resting pass) and the externalized DTI/tractography end-to-end. Follow the existing `structural_ants` pattern and `_PASS_REQUIREMENTS`/capability gating (`antspyx` cap). Add named passes only where a backend must be forced.
- [ ] **Step 2: Run** the prerelease integrity tests: `$SWANE_PY -m pytest -p no:datalad swane/tests/prerelease -v`.
- [ ] **Step 3 (opt-in, real tools):** with antspyx + FSL installed and `~/test_swane/prerelease` verified, run the smoke pass(es); confirm EPI + externalized tractography execute end-to-end. Record failures; do not treat success as scientific validation.
- [ ] **Step 4:** Bump `__version__` in `swane/__init__.py` (next patch per convention). No `force_pref_reset` change.
- [ ] **Step 5: Commit** — `git commit -m "test: prerelease smoke for ANTs EPI + externalized tractography; bump version"`

**→ CHECKPOINT CP-F:** all matrix snapshots reviewed by eye; prerelease smoke green under ANTS default for EPI + DTI/tractography. Report explicitly what was NOT scientifically validated (ANTs-vs-FSL / externalized-vs-native equivalence — the local oracle's job and the user's acceptance). Orchestrator closes Phase 3.

---

## Self-review

**Spec coverage:** §1 EPI exposure+flip ↔ Tasks 2,3; §2 resting concat ↔ Tasks 1,4; §3 dti flip+outputnode ↔ Task 5; §3 tractography externalization ↔ Task 6; §4 pins+version ↔ Tasks 2,3,4 (comment removal) + Task 8 (version); testing/oracle ↔ Tasks 1(step6),6(step5),7,8 + the local oracle (intentionally NOT a task — local, never committed); orchestration/models ↔ session table. The `.mat` bridge is intentionally absent (externalized). Open questions #2 (b0 brain) resolved in Task 5 (`nodif_brain`); #3 (field names) fixed in Task 5; #1/#4/#5 flagged as verify-in-implementation.

**Placeholder scan:** antspyx/probtrackx call shapes and the heavy round-trip/equivalence test bodies carry explicit "VERIFY against installed antspyx/FSL" / fill-body markers — the project-mandated no-invention guardrail (as in Phase 1/2). The per-engine ref→diff apply handling in Task 6 is flagged as an implementer decision with both branches specified. All other steps carry runnable code or exact edits.

**Type consistency:** `registration_stack: list[RegistrationNodeWrapper]` (Task 1) is consumed by Task 4 (`[reg_2_mni, workflow.reg_2_ref]`). `workflow.reg_2_ref` (Task 2) is consumed by Tasks 3,4. `dti_preproc` outputnode fields `diff2ref_transforms`/`diff2ref_which_to_invert`/`ref2diff_transforms`/`ref2diff_which_to_invert`/`nodif_brain` (Task 5) are consumed identically by Task 6 + MainWorkflow. `RegistrationNodeWrapper` fields (`fwd_transforms`/`inv_transforms`/`fwd_which_to_invert`/`inv_which_to_invert`) are used as defined in `utils.py`.
