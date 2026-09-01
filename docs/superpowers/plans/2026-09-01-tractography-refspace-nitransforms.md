# Reference-space tractography with nitransforms — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make probtrackx track and accumulate in high-resolution reference space again (pre-`34890d2` behaviour) for every registration engine, by converting the diffusion↔reference affine to an FSL `.mat` via nitransforms instead of running probtrackx natively in diffusion space and trilinearly upsampling the density.

**Architecture:** Add a small `AffineToFSL` nipype node (nitransforms-backed) that turns a diff→ref affine (ITK for ANTs, LTA for FreeSurfer/synth) into an FSL forward+inverse `.mat`. `dti_preproc` emits FSL `diff2ref_mat`/`ref2diff_mat` per engine (FSL passthrough, ANTs via `AffineToFSL`). `tractography_workflow` reverts the diffusion-space externalisation: ROIs stay in reference space (MNI→ref nonlinear kept), and `CustomProbTrackX2` runs with `seed_ref=reference_brain` and `xfm`/`inv_xfm` FSL matrices. `MainWorkflow` rewires the two workflows.

**Tech Stack:** Python, nipype 1.10, nitransforms ≥25.1.0, nibabel, numpy, FSL probtrackx2, antspyx (ANTs), pytest snapshot matrix tests.

**Spec:** `docs/superpowers/specs/2026-09-01-tractography-refspace-nitransforms-design.md`

## Global Constraints

- Python `>=3.10`; `numpy==2.2.4`, `nibabel>=5.3.0,<6`, `antspyx==0.6.3` are pinned in `setup.py` — do not change these pins.
- Add `nitransforms` with a floor of `>=25.1.0` (installed with `--no-deps` in the dev venv `/media/Dati/venv` so it does not upgrade numpy/scipy).
- Do NOT use CUDA on the dev machine (driver broken); `use_gpu` stays wired but is never exercised here.
- `dif2ref` is `non_linear=False` on every engine and SYNTH is downgraded to FSL for the diffusion registration (`dti_preproc_workflow.py`), so `dif2ref` runs only as FSL or ANTS. The `AffineToFSL` `"fs"` format is future-ready but has no live consumer in this plan.
- Keep existing "derived from Nipype" disclaimer comments intact where present.
- Preserve sinked result filenames: `r-<tract>_<side>.nii.gz` and `r-<tract>_<side>_waytotal`.

---

## File structure

- **Create** `swane/nipype_pipeline/nodes/AffineToFSL.py` — one nipype interface: affine (ITK/LTA) → FSL forward+inverse `.mat`. Sole responsibility: format conversion.
- **Create** `swane/tests/nipype_pipeline/nodes/test_affine_to_fsl.py` — unit test for the node.
- **Modify** `setup.py:32-55` — add `nitransforms` to `install_requires`.
- **Modify** `swane/nipype_pipeline/workflows/dti_preproc_workflow.py` — outputnode fields + per-engine FSL `.mat` emission.
- **Modify** `swane/nipype_pipeline/workflows/tractography_workflow.py` — revert diffusion-space externalisation; ref-space `CustomProbTrackX2`.
- **Modify** `swane/nipype_pipeline/MainWorkflow.py:1069-1100` — rewire dti_preproc→tractography.
- **Regenerate** snapshots under `swane/tests/nipype_pipeline/matrix/snapshots/dti/` and `.../tractography/`, updating `test_dti_matrix.py` / `test_tractography_matrix.py` docstrings/assertions as needed.

---

## Task 1: `AffineToFSL` node + nitransforms dependency

**Files:**
- Create: `swane/nipype_pipeline/nodes/AffineToFSL.py`
- Test: `swane/tests/nipype_pipeline/nodes/test_affine_to_fsl.py`
- Modify: `setup.py:32-55`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: class `AffineToFSL(BaseInterface)` with inputs `in_transform` (File or List[File]), `in_fmt` (Enum `"itk"`/`"fs"`, default `"itk"`), `source_file` (File, the registration moving image), `reference_file` (File, the registration fixed image), `out_file` (Str, default `"diff2ref.mat"`), `out_file_inverse` (Str, default `"ref2diff.mat"`); outputs `out_fsl` (File, diff→ref) and `out_fsl_inverse` (File, ref→diff).

- [ ] **Step 1: Write the failing test**

`swane/tests/nipype_pipeline/nodes/test_affine_to_fsl.py`:

```python
import numpy as np
import nibabel as nib
import pytest

from swane.nipype_pipeline.nodes.AffineToFSL import AffineToFSL


def _write_img(path, shape, zooms):
    aff = np.diag(list(zooms) + [1.0])
    nib.Nifti1Image(np.zeros(shape, "float32"), aff).to_filename(str(path))
    return str(path)


def test_affine_to_fsl_emits_forward_and_inverse(tmp_path):
    pytest.importorskip("nitransforms")
    from nitransforms.linear import Affine

    mov = _write_img(tmp_path / "mov.nii.gz", (10, 10, 10), (2, 2, 2))
    ref = _write_img(tmp_path / "ref.nii.gz", (20, 20, 20), (1, 1, 1))
    itk = tmp_path / "aff.mat"
    Affine(np.eye(4), reference=nib.load(ref)).to_filename(
        str(itk), fmt="itk", moving=nib.load(mov)
    )

    node = AffineToFSL()
    node.inputs.in_transform = str(itk)
    node.inputs.in_fmt = "itk"
    node.inputs.source_file = mov
    node.inputs.reference_file = ref
    node.inputs.out_file = str(tmp_path / "d2r.mat")
    node.inputs.out_file_inverse = str(tmp_path / "r2d.mat")
    res = node.run()

    fwd = np.loadtxt(res.outputs.out_fsl)
    inv = np.loadtxt(res.outputs.out_fsl_inverse)
    assert fwd.shape == (4, 4)
    # the emitted inverse is the numeric inverse of the forward matrix
    assert np.allclose(fwd @ inv, np.eye(4), atol=1e-6)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/media/Dati/venv/bin/python -m pytest swane/tests/nipype_pipeline/nodes/test_affine_to_fsl.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'swane.nipype_pipeline.nodes.AffineToFSL'`.

- [ ] **Step 3: Write minimal implementation**

`swane/nipype_pipeline/nodes/AffineToFSL.py`:

```python
import os

import numpy as np
import nibabel as nib
from nipype.interfaces.base import (
    BaseInterface,
    BaseInterfaceInputSpec,
    TraitedSpec,
    File,
    traits,
)


class AffineToFSLInputSpec(BaseInterfaceInputSpec):
    in_transform = traits.Either(
        File(exists=True),
        traits.List(File(exists=True)),
        mandatory=True,
        desc="diff->ref affine to convert (ITK .mat for ANTs, LTA for FreeSurfer)",
    )
    in_fmt = traits.Enum(
        "itk", "fs", usedefault=True, desc="source transform format for nitransforms"
    )
    source_file = File(
        exists=True, mandatory=True, desc="registration moving image (b0/nodif brain)"
    )
    reference_file = File(
        exists=True, mandatory=True, desc="registration fixed image (reference brain)"
    )
    out_file = traits.Str(
        "diff2ref.mat", usedefault=True, desc="forward FSL matrix filename (diff->ref)"
    )
    out_file_inverse = traits.Str(
        "ref2diff.mat", usedefault=True, desc="inverse FSL matrix filename (ref->diff)"
    )


class AffineToFSLOutputSpec(TraitedSpec):
    out_fsl = File(exists=True, desc="diff->ref affine in FSL format")
    out_fsl_inverse = File(exists=True, desc="ref->diff affine in FSL format")


class AffineToFSL(BaseInterface):
    """Convert a linear diff<->ref transform to an FSL .mat pair via nitransforms.

    probtrackx accepts only a single FSL transform per slot; ANTs (and, in
    future, SynthMorph outside FreeSurfer) produce ITK/LTA affines. This node
    bridges them without depending on FSL or FreeSurfer command-line tools.
    """

    input_spec = AffineToFSLInputSpec
    output_spec = AffineToFSLOutputSpec

    def _run_interface(self, runtime):
        from nitransforms import linear

        transform = self.inputs.in_transform
        if isinstance(transform, (list, tuple)):
            # diff<->ref is affine-only: the ordered list holds a single affine
            transform = transform[-1]

        ref_img = nib.load(self.inputs.reference_file)
        mov_img = nib.load(self.inputs.source_file)

        xfm = linear.load(
            transform, fmt=self.inputs.in_fmt, reference=ref_img, moving=mov_img
        )
        xfm.reference = ref_img

        fwd_path = os.path.abspath(self.inputs.out_file)
        xfm.to_filename(fwd_path, fmt="fsl", moving=mov_img)

        matrix = np.loadtxt(fwd_path)
        inv_path = os.path.abspath(self.inputs.out_file_inverse)
        np.savetxt(inv_path, np.linalg.inv(matrix), fmt="%.10f")
        return runtime

    def _list_outputs(self):
        outputs = self._outputs().get()
        outputs["out_fsl"] = os.path.abspath(self.inputs.out_file)
        outputs["out_fsl_inverse"] = os.path.abspath(self.inputs.out_file_inverse)
        return outputs
```

- [ ] **Step 4: Add nitransforms to `setup.py`**

In `setup.py` `install_requires` (after the `nibabel>=5.3.0,<6` line), add:

```python
        "nitransforms>=25.1.0",
```

- [ ] **Step 5: Run test to verify it passes**

Run: `/media/Dati/venv/bin/python -m pytest swane/tests/nipype_pipeline/nodes/test_affine_to_fsl.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add swane/nipype_pipeline/nodes/AffineToFSL.py swane/tests/nipype_pipeline/nodes/test_affine_to_fsl.py setup.py
git commit -m "feat: add AffineToFSL node (nitransforms ITK/LTA -> FSL) + dependency"
```

---

## Task 2: `dti_preproc` emits FSL diff2ref/ref2diff mats

**Files:**
- Modify: `swane/nipype_pipeline/workflows/dti_preproc_workflow.py` (imports; outputnode fields ~130-140; transform emission block ~262-289)
- Test: `swane/tests/nipype_pipeline/matrix/test_dti_matrix.py` + snapshots under `swane/tests/nipype_pipeline/matrix/snapshots/dti/`

**Interfaces:**
- Consumes: `AffineToFSL` from Task 1.
- Produces: `dti_preproc` outputnode exposes FSL `diff2ref_mat` (diff→ref) and `ref2diff_mat` (ref→diff), replacing `diff2ref_transforms`, `diff2ref_which_to_invert`, `ref2diff_transforms`, `ref2diff_which_to_invert`. `nodif_brain` output is unchanged.

- [ ] **Step 1: Add the import**

At the top of `dti_preproc_workflow.py`, add to the `swane.nipype_pipeline.nodes` imports:

```python
from swane.nipype_pipeline.nodes.AffineToFSL import AffineToFSL
```

- [ ] **Step 2: Update outputnode fields**

In the outputnode `IdentityInterface(fields=[...])`, replace the four lines

```python
                "diff2ref_transforms",
                "diff2ref_which_to_invert",
                "ref2diff_transforms",
                "ref2diff_which_to_invert",
```

with:

```python
                "diff2ref_mat",
                "ref2diff_mat",
```

- [ ] **Step 3: Replace the transform-list emission block**

Replace the block that currently emits `diff2ref_transforms`/`ref2diff_transforms`/`*_which_to_invert` (the `fwd_node, fwd_field = dif2ref.fwd_transforms[0]` ... `workflow.connect(b0_deskull, "out_file", outputnode, "nodif_brain")` section) with:

```python
    # probtrackx consumes a single FSL .mat per transform slot. Emit the
    # diff<->ref affine as FSL: on FSL the FLIRT .mat and its ConvertXFM inverse
    # pass straight through; on ANTs the ITK affine is converted with
    # nitransforms (AffineToFSL), which needs no FSL/FreeSurfer CLI. dif2ref is
    # affine-only and SYNTH is downgraded to FSL above, so engine is FSL or ANTS.
    if engine == RegistrationEngine.FSL:
        fwd_node, fwd_field = dif2ref.fwd_transforms[0]
        workflow.connect(fwd_node, fwd_field, outputnode, "diff2ref_mat")
        inv_node, inv_field = dif2ref.inv_transforms[0]
        workflow.connect(inv_node, inv_field, outputnode, "ref2diff_mat")
    else:
        dif2ref_to_fsl = Node(AffineToFSL(), name="dif2ref_to_fsl")
        dif2ref_to_fsl.long_name = "DTI-to-reference affine FSL conversion"
        dif2ref_to_fsl.inputs.in_fmt = "itk"
        fwd_node, fwd_field = dif2ref.fwd_transforms[0]
        workflow.connect(fwd_node, fwd_field, dif2ref_to_fsl, "in_transform")
        workflow.connect(b0_deskull, "out_file", dif2ref_to_fsl, "source_file")
        workflow.connect(inputnode, "reference_brain", dif2ref_to_fsl, "reference_file")
        workflow.connect(dif2ref_to_fsl, "out_fsl", outputnode, "diff2ref_mat")
        workflow.connect(dif2ref_to_fsl, "out_fsl_inverse", outputnode, "ref2diff_mat")
    workflow.connect(b0_deskull, "out_file", outputnode, "nodif_brain")
```

- [ ] **Step 4: Regenerate the dti matrix snapshots and run the test**

Run: `/media/Dati/venv/bin/python -m pytest swane/tests/nipype_pipeline/matrix/test_dti_matrix.py -v`
Expected: FAIL — the workflow graph no longer matches the pinned snapshots (new `dif2ref_to_fsl` node on ANTs; renamed outputnode fields).

Regenerate snapshots with `SWANE_SNAPSHOT_UPDATE=1 /media/Dati/venv/bin/python -m pytest swane/tests/nipype_pipeline/matrix/test_dti_matrix.py` (see `swane/tests/nipype_pipeline/matrix/README.md`). Then eye-review the diff: on ANTs there must be a `dif2ref_to_fsl` node feeding `outputnode.diff2ref_mat`/`ref2diff_mat`; on FSL the FLIRT `.mat` + ConvertXFM inverse feed them directly. Update the test docstring to describe the FSL-mat emission, and regenerate reports with `/media/Dati/venv/bin/python swane/tests/nipype_pipeline/matrix/generate_report.py`.

Re-run: `/media/Dati/venv/bin/python -m pytest swane/tests/nipype_pipeline/matrix/test_dti_matrix.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add swane/nipype_pipeline/workflows/dti_preproc_workflow.py swane/tests/nipype_pipeline/matrix/test_dti_matrix.py swane/tests/nipype_pipeline/matrix/snapshots/dti
git commit -m "feat: dti_preproc emits FSL diff2ref/ref2diff mats (ANTs via nitransforms)"
```

---

## Task 3: `tractography_workflow` runs probtrackx in reference space

**Files:**
- Modify: `swane/nipype_pipeline/workflows/tractography_workflow.py`
- Test: `swane/tests/nipype_pipeline/matrix/test_tractography_matrix.py` + snapshots under `.../snapshots/tractography/`

**Interfaces:**
- Consumes: `dti_preproc` outputs `diff2ref_mat` / `ref2diff_mat` (from Task 2) via the inputnode.
- Produces: `tractography_workflow` inputnode fields `reference_brain`, `mask`, `fsamples`, `phsamples`, `thsamples`, `diff2ref_mat`, `ref2diff_mat`, `mni2ref_warp` (drops `nodif_brain`, `diff2ref_transforms`, `diff2ref_which_to_invert`, `ref2diff_transforms`, `ref2diff_which_to_invert`). Outputnode unchanged (`fdt_paths_<side>`, `waytotal_<side>`).

- [ ] **Step 1: Restore the CustomProbTrackX2 import**

Replace `from nipype.interfaces.fsl import ProbTrackX2` with:

```python
from swane.nipype_pipeline.nodes.CustomProbTrackX2 import CustomProbTrackX2
```

(Keep the other imports. `resolve_registration_engine`, `RegistrationNodeWrapper`, `apply_registration_node` are still needed for the MNI→ref applies.)

- [ ] **Step 2: Update inputnode fields**

In the inputnode `IdentityInterface(fields=[...])`, replace

```python
                "nodif_brain",
                "diff2ref_transforms",
                "diff2ref_which_to_invert",
                "ref2diff_transforms",
                "ref2diff_which_to_invert",
```

with:

```python
                "diff2ref_mat",
                "ref2diff_mat",
```

- [ ] **Step 3: Remove the diff-space plumbing**

Delete these constructs (added by `34890d2`), keeping the MNI→ref `*_2_ref` nodes:
- the `ref2diff` and `diff2ref` `RegistrationNodeWrapper` instances,
- the `apply_diff_transform(...)` helper,
- the `diff_engine` computation (keep `engine = resolve_registration_engine(synth_config, allow_ants=True)` for the `*_2_ref` applies),
- the `seed_2_diff`, `targets_2_diff`, `exclude_2_diff`, `stop_2_diff` nodes,
- the `sum_2_ref` node.

- [ ] **Step 4: Restore ref-space probtrackx wiring**

Change the tractography node back to `CustomProbTrackX2` and wire it in reference space. The main `probtrackx` block becomes:

```python
        # NODE 10: Tractography (runs in reference space; probtrackx bridges to
        # diffusion internally via the FSL xfm/inv_xfm matrices)
        probtrackx = MapNode(
            CustomProbTrackX2(),
            name="probtrackx_%s_%s" % (name, side),
            iterfield=["random_seed"],
        )
```

Keep the existing `probtrackx.inputs.*` scalar settings and `use_gpu`. Replace the connection block so that:

```python
        workflow.connect(inputnode, "fsamples", probtrackx, "fsamples")
        workflow.connect(inputnode, "mask", probtrackx, "mask")
        workflow.connect(inputnode, "reference_brain", probtrackx, "seed_ref")
        workflow.connect(inputnode, "phsamples", probtrackx, "phsamples")
        workflow.connect(inputnode, "thsamples", probtrackx, "thsamples")
        workflow.connect(inputnode, "ref2diff_mat", probtrackx, "xfm")
        workflow.connect(inputnode, "diff2ref_mat", probtrackx, "inv_xfm")
        workflow.connect(seed_2_ref, "out_file", probtrackx, "seed")
        workflow.connect(random_seed, "seeds", probtrackx, "random_seed")
```

For the targets, wire the ref-space `targets_2_ref` (single or via `merge_targets`) to `probtrackx, "waypoints"` (replace the `targets_2_diff` references with `targets_2_ref`).

For the inverted run (`probtrackx_inverted`), mirror the same: use `CustomProbTrackX2`, `seed_ref=reference_brain`, `xfm=ref2diff_mat`, `inv_xfm=diff2ref_mat`, `seed=targets_2_ref`, `waypoints=seed_2_ref`.

For exclusion and stop masks, connect `exclude_2_ref`/`stop_2_ref` (ref space) to `probtrackx, "avoid_mp"` / `probtrackx, "stop_mask"` (and the inverted node), replacing the `*_2_diff` references.

- [ ] **Step 5: Restore direct sum→outputnode wiring**

Replace the `sum_2_ref` connection with the direct connection (the sum already runs in reference space now):

```python
        workflow.connect(
            sum_multi_tracks, "out_file", outputnode, "fdt_paths_%s" % side
        )
```

Leave the `waytotal_sum` → outputnode connection unchanged.

- [ ] **Step 6: Regenerate the tractography matrix snapshots and run the test**

Run: `/media/Dati/venv/bin/python -m pytest swane/tests/nipype_pipeline/matrix/test_tractography_matrix.py -v`
Expected: FAIL — the graph changed (no `*_2_diff`/`sum_2_ref`; `CustomProbTrackX2` with `xfm`/`inv_xfm`; new inputnode fields).

Regenerate the tractography snapshots with `SWANE_SNAPSHOT_UPDATE=1 /media/Dati/venv/bin/python -m pytest swane/tests/nipype_pipeline/matrix/test_tractography_matrix.py` for both the FSL golden and the `cst_real_graph_ants_backend` ANTS golden, and update `test_tractography_ants_construction` if it asserts the removed `*_2_diff` nodes. Eye-review: seed/waypoints/avoid come from `*_2_ref`; probtrackx has `seed_ref`, `xfm`, `inv_xfm` set; no diffusion-space resample nodes remain. Regenerate reports with `/media/Dati/venv/bin/python swane/tests/nipype_pipeline/matrix/generate_report.py`.

Re-run: `/media/Dati/venv/bin/python -m pytest swane/tests/nipype_pipeline/matrix/test_tractography_matrix.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add swane/nipype_pipeline/workflows/tractography_workflow.py swane/tests/nipype_pipeline/matrix/test_tractography_matrix.py swane/tests/nipype_pipeline/matrix/snapshots/tractography
git commit -m "feat: run probtrackx in reference space via FSL xfm/inv_xfm again"
```

---

## Task 4: Rewire `MainWorkflow`

**Files:**
- Modify: `swane/nipype_pipeline/MainWorkflow.py:1069-1100` (dti_preproc→tractography connections)

**Interfaces:**
- Consumes: `dti_preproc` outputs `diff2ref_mat`/`ref2diff_mat` (Task 2); `tractography_workflow` inputnode `diff2ref_mat`/`ref2diff_mat` (Task 3).
- Produces: no new interface; connects the two workflows.

- [ ] **Step 1: Replace the transform connections**

In the tractography wiring block, remove the `outputnode.nodif_brain → inputnode.nodif_brain` connection and the four transform-list connections (`diff2ref_transforms`, `diff2ref_which_to_invert`, `ref2diff_transforms`, `ref2diff_which_to_invert`), and add:

```python
                    self.connect(
                        self.dti_preproc,
                        "outputnode.diff2ref_mat",
                        tract_workflow,
                        "inputnode.diff2ref_mat",
                    )
                    self.connect(
                        self.dti_preproc,
                        "outputnode.ref2diff_mat",
                        tract_workflow,
                        "inputnode.ref2diff_mat",
                    )
```

Keep the `reference_brain`, `mask`, `fsamples`, `phsamples`, `thsamples`, and `mni2ref_warp` connections as they are.

- [ ] **Step 2: Verify the full pipeline builds**

Run: `/media/Dati/venv/bin/python -m pytest swane/tests/nipype_pipeline/matrix/test_dti_matrix.py swane/tests/nipype_pipeline/matrix/test_tractography_matrix.py -v`
Expected: PASS (both workflows still build and snapshot-match).

If a whole-`MainWorkflow` construction test exists, run it too; expected: PASS (connections resolve, no missing inputnode fields).

- [ ] **Step 3: Commit**

```bash
git add swane/nipype_pipeline/MainWorkflow.py
git commit -m "feat: wire dti_preproc FSL mats into tractography inputnode"
```

---

## Task 5: Integration verification (prerelease re-run)

**Files:** none (verification only).

**Interfaces:** consumes the fully-wired pipeline from Tasks 1–4.

- [ ] **Step 1: Run the FSL tractography prerelease scenario**

Run the prerelease `dti_tractography` scenario (FSL engine) per `swane/tests/prerelease/README.md`, writing to a fresh output dir.

- [ ] **Step 2: Assert the tract is thin again**

With FSL loaded, compare the final `r-cst_lh.nii.gz` footprint against the fat baseline:

```bash
fslstats <new_run>/results/dti/r-cst_lh.nii.gz -V -R
```

Expected: non-zero voxel count back in the OLD thin range (~7 000–9 000, integer max value), not the ~14 000 float-valued fat output. Repeat for `dti_tractography_ants` (ANTs engine) — expected similarly thin, exercising the `AffineToFSL` path (PoC gave 8 410 vs 14 032).

- [ ] **Step 3: Record the result**

Note the before/after footprints in the PR description; no code commit.

---

## Self-review notes

- **Spec coverage:** dependency (Task 1), `AffineToFSL` (Task 1), dti_preproc per-engine FSL mats (Task 2), tractography ref-space revert (Task 3), MainWorkflow rewiring (Task 4), prerelease validation (Task 5). All spec sections covered.
- **Type consistency:** output names `out_fsl`/`out_fsl_inverse` (Task 1) are consumed in Task 2; outputnode fields `diff2ref_mat`/`ref2diff_mat` (Task 2) match tractography inputnode fields (Task 3) and MainWorkflow connections (Task 4).
- **Synth caveat:** `AffineToFSL` supports `"fs"` but dti_preproc downgrades SYNTH→FSL for diffusion, so the `"fs"` branch is future-ready, not live. Flag to the maintainer whether to also lift that downgrade (out of scope here).
- **Snapshot mechanism:** confirm the exact update flag from `swane/tests/nipype_pipeline/matrix/README.md` before regenerating (Tasks 2 and 3).
