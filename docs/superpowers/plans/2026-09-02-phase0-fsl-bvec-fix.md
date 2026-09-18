# Phase 0 — FSL rotated-bvec fix and shared preprocessing flag

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Feed FSL `eddy`'s rotated b-vectors to `dtifit` and `bedpostx` instead of the unrotated dcm2niix ones.

**Status: COMPLETE (2026-09-02), uncommitted in the working tree.** Re-scoped
mid-flight: Task 1 was cancelled (see below), leaving Tasks 2-4. Verified by the
global orchestrator: 165 passed across `matrix`, `config` and the new
behavioural test; the snapshot diff is 14 lines, all of them the bvec edge.

**Architecture:** Two small, surgical changes inside `dti_preproc_workflow`, plus one preference rename. Both alter the output of the existing, validated FSL pipeline, so they are isolated in their own phase and their own golden snapshots, ahead of any dipy work.

**Tech Stack:** Python 3.12, nipype 1.12, FSL 6.x, pytest.

**Spec:** `docs/superpowers/specs/2026-09-02-dipy-recobundles-tractography-design.md` (sections 2 and 12)

## Global Constraints

- Start from branch `claude/dipy-recobundles`; do not commit, push, merge or open a PR unless explicitly asked.
- Every part of SWANe code and documentation is written in English.
- Never use "patient" — always "subject". SWANe is a research tool, never described as clinical or medical.
- Any Python command must use `/media/Dati/venv/bin/python`, never FSL's or FreeSurfer's bundled interpreter.
- Format changed Python with Black; do not reformat unrelated files.
- Preserve existing "derived from Nipype" disclaimer comments.
- Persisted preference keys, enum member names, workflow/node names, Traits fields, signals and result filenames are stable contracts.
- Real subject data, the HCP842 atlas and every derived artefact stay outside the repository. Before each commit, `git diff --name-only` must list only source, tests and docs — never a path under `test_swane`, never a binary imaging format.
- `CoreLimit.NO_LIMIT` and `SOFT_CAP` are being removed; do not add new behaviour branches for them.

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `swane/nipype_pipeline/workflows/dti_preproc_workflow.py` | DTI preprocessing graph | Modify: bvec source for `dtifit`/`bedpostx` |
| `swane/tests/nipype_pipeline/matrix/test_dti_matrix.py` | Golden graph snapshots | *(unchanged — the scenario rename was cancelled with Task 1)* |
| `swane/tests/nipype_pipeline/matrix/snapshots/dti_preproc/` | Golden snapshots | Regenerate |
| `swane/tests/nipype_pipeline/workflows/test_dti_bvec_source.py` | New behavioural test | Create |

| `swane/tests/nipype_pipeline/test_deskull_modality_wiring.py` | Deskull wiring test | Modify: writes the preference |
| `swane/tests/prerelease/plan.py` | Prerelease sweep definition | Modify: names the preference in its axis and scenarios |

Find every consumer before editing, rather than trusting this table:

```bash
grep -rn "old_eddy_correct" --include=*.py --include=*.md swane/ | grep -v docs/superpowers
```

The new workflow test sits under `swane/tests/nipype_pipeline/workflows/`, which
inherits the `subject_config`, `global_config` and `make_input_dir` fixtures from
`swane/tests/nipype_pipeline/conftest.py` — no new fixtures are needed.

---

### Task 1 (CANCELLED): Replace `old_eddy_correct` with `fast_dwi_preproc`

**Cancelled 2026-09-02 by the global orchestrator, before completion; any work
already done was reverted.** MP-PCA was dropped from the dipy engine after it
measured >54 minutes on a routine 64-direction acquisition, so dipy always uses
`nlmeans` + `estimate_sigma` and has no denoising choice to share. That removed
the reason for an engine-independent preference to exist.

`old_eddy_correct` therefore stays exactly as it is: same key, same FSL-only
meaning, greyed on the dipy engine. No new preference key, no persistence
question, no migration discussion. See "Denoising on dipy is always `nlmeans` +
`estimate_sigma`" in the spec's section 2.

The task body is removed rather than left struck through, because a detailed,
plausible, *wrong* set of instructions is exactly the kind of thing a later
executor follows by mistake.
---

### Task 2: `dtifit` and `bedpostx` consume eddy's rotated b-vectors

**Files:**
- Modify: `swane/nipype_pipeline/workflows/dti_preproc_workflow.py:228` and `:324`
- Test: `swane/tests/nipype_pipeline/workflows/test_dti_bvec_source.py` (create)

**Interfaces:**
- Consumes: the existing `old_eddy_correct` preference; `CustomEddy` output `out_rotated_bvecs` (verified present alongside `out_corrected`).
- Produces: nothing new for later tasks; this is a graph-wiring change.

**Context the implementer needs.** `dti_preproc_workflow` has two eddy branches. When `old_eddy_correct` is true it uses nipype's `EddyCorrect`, which produces **no** rotated bvecs; when false it uses `CustomEddy` (FSL `eddy`), which produces `out_rotated_bvecs`. Only the second branch can be fixed. The branch is already tracked by the local variable `eddy_output_name`, set to `"eddy_corrected"` in the old branch and `"out_corrected"` in the new one.

Why this matters: dipy's own docstring for `reorient_bvecs`, citing Leemans & Jones 2009, states that without reorientation the rotation applied to the volumes causes "systematic bias in rotationally invariant measures, such as FA and MD, and also characteristic biases in tractography". FSL `eddy` rotates the data and emits corrected gradients for exactly this reason; SWANe currently discards them.

- [ ] **Step 1: Write the failing test**

Create `swane/tests/nipype_pipeline/workflows/test_dti_bvec_source.py`:

```python
"""The FSL DTI branch must consume eddy's rotated b-vectors, not the raw ones.

Rotating the volumes without reorienting the gradients biases FA/MD and
tractography (Leemans & Jones 2009). FSL ``eddy`` emits ``out_rotated_bvecs``
for this purpose; ``eddy_correct`` does not, so the legacy branch keeps the
unrotated vectors because nothing better exists there.
"""

import pytest

from swane.config.config_enums import CoreLimit, DeskullModality


def _bvec_sources(workflow, consumer_name):
    """Return {(source node name, source field)} feeding ``consumer_name.bvecs``."""
    sources = set()
    for src, dst, data in workflow._graph.edges(data=True):
        if dst.name != consumer_name:
            continue
        for out_field, in_field in data.get("connect", []):
            if in_field == "bvecs":
                sources.add((src.name, out_field))
    return sources


def _build(subject_config, global_config, make_input_dir, fast):
    from swane.nipype_pipeline.workflows.dti_preproc_workflow import (
        dti_preproc_workflow,
    )
    from swane.utils.DataInputList import DataInputList

    subject_config[DataInputList.DTI]["old_eddy_correct"] = "true" if fast else "false"
    subject_config[DataInputList.DTI]["tractography"] = "true"
    subject_config[DataInputList.DTI]["cuda"] = "false"
    return dti_preproc_workflow(
        name="dti_preproc",
        dti_dir=str(make_input_dir("dti")),
        config=subject_config[DataInputList.DTI],
        synth_config=global_config[
            __import__(
                "swane.config.config_enums", fromlist=["GlobalPrefCategoryList"]
            ).GlobalPrefCategoryList.SYNTH
        ],
        deskull_modality=DeskullModality.NODIF,
        max_cpu=4,
        multicore_node_limit=CoreLimit.HARD_CAP,
    )


@pytest.mark.parametrize("consumer", ["dti_dtifit", "dti_bedpostx"])
def test_full_eddy_feeds_rotated_bvecs(
    consumer, subject_config, global_config, make_input_dir
):
    workflow = _build(subject_config, global_config, make_input_dir, fast=False)
    assert _bvec_sources(workflow, consumer) == {("dti_eddy", "out_rotated_bvecs")}


@pytest.mark.parametrize("consumer", ["dti_dtifit", "dti_bedpostx"])
def test_fast_path_keeps_conversion_bvecs(
    consumer, subject_config, global_config, make_input_dir
):
    """``eddy_correct`` emits no rotated bvecs, so the raw ones are correct here."""
    workflow = _build(subject_config, global_config, make_input_dir, fast=True)
    assert _bvec_sources(workflow, consumer) == {("dti_conv", "bvecs")}
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
/media/Dati/venv/bin/python -m pytest swane/tests/nipype_pipeline/workflows/test_dti_bvec_source.py -v
```

Expected: `test_full_eddy_feeds_rotated_bvecs` FAILS — the actual source is `("dti_conv", "bvecs")`. `test_fast_path_keeps_conversion_bvecs` passes already — that is the point: it is the regression guard for the branch that must *not* change.

- [ ] **Step 3: Wire the rotated bvecs on the full-eddy branch only**

In `dti_preproc_workflow.py`, just after the `if old_eddy_correct: ... else: ...` block that sets `eddy_output_name`, add a sibling variable, then use it at both consumers.

In the `if old_eddy_correct:` branch, after `eddy_output_name = "eddy_corrected"`:

```python
        # EddyCorrect emits no rotated b-vectors, so the raw ones stay.
        bvec_source, bvec_field = conversion, "bvecs"
```

In the `else:` branch, after `eddy_output_name = "out_corrected"`:

```python
        # eddy rotates the volumes, so the gradients must follow them, else FA,
        # MD and tractography carry a systematic bias (Leemans & Jones 2009).
        bvec_source, bvec_field = eddy, "out_rotated_bvecs"
```

Then replace line 228:

```python
    workflow.connect(bvec_source, bvec_field, dtifit, "bvecs")
```

and line 324:

```python
        workflow.connect(bvec_source, bvec_field, bedpostx, "bvecs")
```

Leave every `bvals` connection untouched: b-values are rotation-invariant.

- [ ] **Step 4: Run the test to verify it passes**

```bash
/media/Dati/venv/bin/python -m pytest swane/tests/nipype_pipeline/workflows/test_dti_bvec_source.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add swane/nipype_pipeline/workflows/dti_preproc_workflow.py swane/tests/nipype_pipeline/workflows/test_dti_bvec_source.py
git commit -m "fix: feed eddy's rotated b-vectors to dtifit and bedpostx

Rotating the DWI volumes without reorienting the gradients biases FA, MD
and tractography (Leemans & Jones 2009). FSL eddy emits out_rotated_bvecs
for this; SWANe was discarding them. The eddy_correct branch keeps the raw
vectors because it produces no rotated ones."
```

---

### Task 3: Update and regenerate the golden matrix snapshots

**Files:**
- Modify: `swane/tests/nipype_pipeline/matrix/test_dti_matrix.py:33-40` and the `_bool` wiring below it
- Regenerate: `swane/tests/nipype_pipeline/matrix/snapshots/dti_preproc/`

**Interfaces:**
- Consumes: the bvec wiring from Task 2.
- Produces: refreshed golden snapshots that later phases must not disturb.

**Why this task cannot be skipped or reordered.** Between Task 1 and this task the
matrix suite is in a silently wrong state: `test_dti_matrix.py` still writes
`old_eddy_correct`, a key that no longer exists, so the write lands nowhere and
the `old_eddy_correct` scenario stops exercising the `eddy_correct` branch — it
silently becomes a duplicate of the new-eddy scenario. Regenerating snapshots
before completing this task would bake that mistake into the golden files. Do not
run `SWANE_SNAPSHOT_UPDATE=1` until Step 1 below is done.

- [x] **Step 1: ~~Rename the scenario and its preference write~~ — CANCELLED**

Cancelled with Task 1. `test_dti_matrix.py` is **not** modified: the
`old_eddy_correct` scenario key and its preference write stay as they are. Go
straight to Step 2, where the only expected failures are snapshot content
changes from the bvec edge.

- [ ] **Step 2: Run the matrix suite and confirm it fails on content, not on errors**

```bash
/media/Dati/venv/bin/python -m pytest swane/tests/nipype_pipeline/matrix/test_dti_matrix.py -v
```

Expected: snapshot mismatches for the `dti_preproc` scenarios that include `dtifit`/`bedpostx`, because the bvec edge changed. Errors other than snapshot mismatch mean Task 1 or 2 is wrong — stop and fix before regenerating.

- [ ] **Step 3: Regenerate the snapshots**

```bash
SWANE_SNAPSHOT_UPDATE=1 /media/Dati/venv/bin/python -m pytest swane/tests/nipype_pipeline/matrix/test_dti_matrix.py
```

- [ ] **Step 4: Review the diff by eye before trusting it**

```bash
git diff --stat swane/tests/nipype_pipeline/matrix/snapshots/dti_preproc/
git diff swane/tests/nipype_pipeline/matrix/snapshots/dti_preproc/ | head -80
```

The only semantic change must be the bvec edge moving from `dti_conv` to `dti_eddy` in the full-eddy scenarios. There is no scenario rename. The `old_eddy_correct` scenario's snapshot must still show `dti_conv -> bvecs` and stay byte-identical. If anything else moved, a previous task overreached — investigate rather than accepting the regeneration.

- [ ] **Step 5: Re-run the whole matrix suite and the report**

```bash
/media/Dati/venv/bin/python -m pytest swane/tests/nipype_pipeline/matrix -v
/media/Dati/venv/bin/python swane/tests/nipype_pipeline/matrix/generate_report.py
```

Expected: all pass. Other workflows' snapshots must be untouched — confirm with `git status --short`.

- [ ] **Step 6: Commit**

```bash
git add swane/tests/nipype_pipeline/matrix/
git commit -m "test: regenerate DTI matrix snapshots for the rotated-bvec fix

The bvec edge moves from dti_conv to dti_eddy on the full-eddy scenarios;
the fast path keeps dti_conv."
```

---

### Task 4: Record the user-visible change

**Files:**
- Modify: `README.md` (changelog section, if one exists) and `NOTICE.md` only if attribution changed (it has not in this phase)

- [ ] **Step 1: Locate the changelog**

```bash
grep -n -i "changelog\|## 0\.\|## v" README.md | head
```

- [ ] **Step 2: Add the entry**

Add, in the style of the surrounding entries, wording to this effect:

> DTI: FSL `eddy`'s rotated b-vectors are now used for tensor fitting and bedpostx. Rotating the volumes without reorienting the gradients biased FA, MD and tractography in proportion to subject motion. Re-processing a subject will not reproduce results generated by earlier versions.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: note the rotated-bvec fix changes DTI results"
```

---

## Phase 0 completion report

Report back to the global orchestrator with:

- the exact output of `pytest swane/tests/nipype_pipeline/matrix` and of the new behavioural test;
- the reviewed snapshot diff — state explicitly that the only semantic change is the bvec edge, or describe what else moved;
- confirmation that `git diff --name-only` for this phase lists no path under `test_swane` and no binary imaging format;
- whether the `old_eddy_correct` local variable in `dti_preproc_workflow` was renamed or deliberately left (it was left unchanged);
- anything deliberately not done, and why.

A phase reported as "done" without the test output cannot be verified.
