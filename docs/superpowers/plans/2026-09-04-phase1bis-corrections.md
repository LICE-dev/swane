# Phase 1bis — dipy path corrections Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: this plan is executed by the phase
> orchestrator as **per-task executor prompts**, one fresh session each, per the
> Phase 1bis orchestrator prompt. Each executor prompt REQUIRES
> `superpowers:test-driven-development` and `superpowers:verification-before-completion`,
> and must invoke `swane-dev-assistant` before touching code. The orchestrator does
> **not** spawn subagents and does **not** implement. Steps use checkbox (`- [ ]`)
> syntax for tracking.

**Goal:** Land five measured corrections (C1–C5) to the Phase 1 dipy tractography
path — an upfront brain crop, a hardened motion pool, an FA stopping criterion, a
real crop-bug fix, and an oracle-gated deskull swap — so Phase 2 can be built on a
correct, RAM-safe, cross-platform-uniform engine.

**Architecture:** Surgical changes to existing dipy nodes and
`dipy_dti_preproc_workflow`, each defended by a test that fails against the current
code. The serial-vs-parallel motion oracle and a new full-FOV-vs-cropped
world-coordinate oracle are the two hard contracts. Every scientific change (FA
stop, float32, crop, deskull) reports a measured number, never an assumed-benign
one. The FSL/XTRACT path is untouched and stays bit-identical.

**Tech Stack:** Python, dipy 1.12.0, Nipype custom interfaces, NumPy/nibabel,
`multiprocessing`/`concurrent.futures`, `threadpoolctl`, pytest.

**Spec:** `docs/superpowers/specs/2026-09-04-phase1bis-design.md`
(baselines: `docs/superpowers/2026-09-04-phase1-report.md`; overall design:
`docs/superpowers/specs/2026-09-02-dipy-recobundles-tractography-design.md`)

## Global Constraints

Copied verbatim from the spec and the orchestrator prompt; every task implicitly includes these.

- Start from branch `claude/dipy-recobundles`. Never commit, push, merge or open a PR unless the user explicitly asks in the current conversation.
- Every part of SWANe code and documentation is written in **English**.
- Never use "patient" — always **"subject"**. SWANe is a **research tool**, never described as clinical or medical.
- Any Python command must use `/media/Dati/venv/bin/python`, never FSL's or FreeSurfer's bundled interpreter. Verify with `python -c "import sys; print(sys.executable)"` when unsure.
- Format changed Python with **Black**; do not reformat unrelated files. Preserve unrelated work in the working tree.
- Preserve every existing **"derived from Nipype" disclaimer** comment, even when a node body is rewritten.
- Stable contracts (do not break without an explicit compatibility plan): persisted preference keys, enum member names, workflow/node names, Traits fields, signals, result filenames, Slicer mappings.
- **HARD_CAP only.** `CoreLimit.NO_LIMIT`/`SOFT_CAP` are being removed; add no new behaviour branches for them. Every node declares real `n_procs` and pins `OMP_NUM_THREADS`/`OPENBLAS_NUM_THREADS` to the count it declares — **including inside pool workers** (that is what C2.1 is about).
- **8 GB soft RAM budget**, 4 cores, no GPU. A full-FOV run swap-froze this box once; C1 and C4 exist to prevent a repeat. Use `/home/mau/test_swane/dipy_test/harness/safe_run.py` for any real-data run.
- Real subject data, the HCP842 atlas and every derived artefact stay **outside the repository**. Before each commit, `git diff --name-only` must list only source, tests and docs — never a path under `test_swane`, never a binary imaging format.
- **Contracts that must not move:** the FSL/XTRACT path stays bit-identical (`dti_preproc_workflow`, `tractography_workflow`, `snapshots/dti_preproc/`); Phase 2's three outputs keep their names (`outputnode.tractogram`, `outputnode.tractogram_atlas`, `outputnode.atlas2native`); the serial-vs-parallel motion oracle still passes; world coordinates survive every crop.
- **Out of scope:** RecoBundles, `dipy_bundle_workflow`, the fornix split, SlicerDMRI, the `.trk` result contract, the phantom. Those are Phase 2/3.

## User decisions embedded in this plan (raise; do not settle)

These are the user's, not the orchestrator's or an executor's. They are flagged
at the task that consumes them and must be answered **before that task's executor
starts**:

- **D-PROBE — RESOLVED (probe complete, 2026-09-04):** root cause is the **CMC
  stopping criterion** (only the FA-stopping arm recovers the arcuate; seeding
  exonerated — AF corridor 36.8% seeded at WM-PVE 0.5). Production change:
  **`CmcStoppingCriterion` → `ThresholdStoppingCriterion(FA, 0.20)`**, **seeding
  stays WM-PVE ≥ 0.5** (at equal count PVE beats FA for the arcuate: AF_L 361 vs
  274 — FA's earlier "win" was a streamline-count artifact), **step 0.2, angle 20**
  unchanged. Sweep: CMC→AF_L=2; every FA threshold→AF_L 112–361; FA **0.20** best
  CST_L and residual (higher FA loses the sparse right arcuate). **OUTSTANDING
  validation, folded into Task 5:** subj2 CST regression was not run (step/density
  experiments were substituted) — CMC→FA is a global default, so confirm it does
  not degrade subj2's clean CST before committing.
- **D-TISSUE — RESOLVED (user, 2026-09-04): remove the dead nodes.**
  `DipyTissueClassifier` (`dipy_tissue`) **stays** (produces `pve_wm`, consumed by
  seeding). The `pve_gm_2_diff` and `pve_csf_2_diff` apply-registration nodes are
  **removed** (their only consumer was CMC). In `DipyTracking`, the `pve_gm`/`pve_csf`
  inputs and the `CmcStoppingCriterion.from_pve` construction are removed; `pve_wm`
  stays for seeding. Task 5 owns this.
- **D-SEEDDENSITY — RESOLVED (user, 2026-09-04):** **keep** the persisted
  `seed_density` preference key; its default stays **2** (already the case at
  `preference_list.py:442`). No key removal. Task 5 does not touch the preference.
- **D-C5BAR — RESOLVED (user, 2026-09-04):** accept the proposed bar — adopt
  `median_otsu` only if **Dice ≥ 0.95 vs SynthStrip AND within 0.01 Dice of the
  current engine**. Task 6 measures against this bar.

---

## Task 1 — C4: crop from the brain-mask bbox, not the shm foreground (Sonnet 5)

**Why first:** smallest, fully specified in the spec, and a second independent
defence against the full-FOV allocation that hard-rebooted the box.

**Files:**
- Modify: `swane/nipype_pipeline/nodes/DipyTracking.py:259-276` (crop derivation)
- Test: `swane/tests/nipype_pipeline/nodes/test_dipy_tracking.py`

**The bug** ([DipyTracking.py:268-270](../../swane/nipype_pipeline/nodes/DipyTracking.py#L268-L270)):
```python
sh_signal = np.any(sh_data != 0, axis=-1)
crop = foreground_bbox_slices((sh_signal, pve_wm, pve_gm, pve_csf), sh_data.shape[:3], ...)
```
`DipyCsdFit` saves the shm with the int16/NaN-scaled DWI header, so `sh_data` reads
non-zero across the **whole FOV**. `sh_signal` therefore covers the full volume and
the union bbox degenerates to a no-op crop — which is how a 4.15 GB allocation
survived a node whose docstring claims it crops.

**Fix:** derive the crop from the **brain mask** only — the union of the PVE maps
(WM∪GM∪CSF = brain), i.e. drop `sh_signal` from the tuple. This is scientifically
identical: outside the brain there are no seeds, no tissue for the stopping
criterion, and only spurious shm. On subj1 it shrinks the volume to 161×192×52.
Confirm against live code whether a dedicated brain-mask input is cleaner than the
PVE union; if you add a Traits input, that is a new contract — note it in the report.

**Interfaces:**
- Consumes: `foreground_bbox_slices(masks, shape, pad)`, `shift_affine_for_crop` (unchanged).
- Produces: same crop tuple contract; no signature change if you use the PVE union.

- [ ] **Step 1: Write the failing regression test.** A shm array non-zero
  *everywhere*, plus a brain mask (PVE) covering only part of the volume, must
  produce a crop that follows the mask, not the shm.

```python
def test_crop_follows_brain_mask_not_full_fov_shm():
    # shm-like foreground is non-zero everywhere (the int16/NaN-scaled bug);
    # the brain occupies only a sub-box. The crop must follow the brain.
    shape = (20, 20, 10)
    pve_wm = np.zeros(shape, dtype=np.float32)
    pve_wm[5:12, 6:14, 2:8] = 1.0           # brain-dominant sub-box
    pve_gm = np.zeros(shape, dtype=np.float32)
    pve_csf = np.zeros(shape, dtype=np.float32)

    crop = brain_bbox_slices((pve_wm, pve_gm, pve_csf), shape)  # NOT the shm
    # pad = BBOX_PAD_VOXELS (2), clipped to bounds
    assert crop[0] == slice(3, 14)
    assert crop[1] == slice(4, 16)
    assert crop[2] == slice(0, 10)
    # and the crop is strictly smaller than the full FOV on at least one axis
    assert any(sl.stop - sl.start < shape[a] for a, sl in enumerate(crop))
```

- [ ] **Step 2: Run it, verify it fails.** `pytest swane/tests/nipype_pipeline/nodes/test_dipy_tracking.py -k crop_follows_brain -v` → FAIL. **Also prove the bug**: add a sibling assertion feeding a full-FOV `sh_signal` into the *old* union call and show it returns the full FOV (documents the defect the fix removes).
- [ ] **Step 3: Implement.** Drop `sh_signal` from the crop derivation in `_run_interface`; crop from the brain (PVE union / brain mask). Update the surrounding comment to state the shm is deliberately excluded because its header makes it full-FOV.
- [ ] **Step 4: Run tests.** The new test passes; `pytest swane/tests/nipype_pipeline/nodes/test_dipy_tracking.py -v` stays green.
- [ ] **Step 5: Black-format the two files. Do not commit** (commit only if the user asks).

**Report:** the test output showing it fails against the old code and passes
against the fix; the measured shape reduction on subj1 (expect 256×256×52 →
161×192×52); `git diff --name-only` (source + test only).

---

## Task 2 — C1: upfront 4D `median_otsu` crop with affine shift (Opus 4.8)

**Why Opus:** a crop that silently cuts brain, or shifts world coordinates,
corrupts everything downstream while every existing test still passes.

**Files:**
- Create: `swane/nipype_pipeline/nodes/DwiCrop.py` (a new dipy node — name TBD by executor, but stable once chosen; carry the Nipype disclaimers)
- Modify: `swane/nipype_pipeline/workflows/dipy_dti_preproc_workflow.py:185-234` (insert after `dipy_reOrient`, before `dipy_nodif` and `dipy_denoise`)
- Test: `swane/tests/nipype_pipeline/nodes/test_dwi_crop.py` (new)

**Approach:** immediately after `ForceOrient`, crop the 4D series with
`dipy.segment.mask.median_otsu(input_volume, vol_idx=<b0 indices>, median_radius=4,
numpass=4, autocrop=True, dilate=<n>)`. Feed the cropped 4D to both `dipy_nodif`
and `dipy_denoise` in place of `reorient, "out_file"`. **Crop generously** — use
`dilate` and an explicit voxel pad; a too-large crop is correct, a too-small crop
is a defect (cutting brain is unrecoverable). A crop is not a mask; nothing
downstream depends on a tight boundary.

The crop's affine shift MUST follow the existing `shift_affine_for_crop`
convention (see [DipyTracking.py:139-150](../../swane/nipype_pipeline/nodes/DipyTracking.py#L139-L150))
so world coordinates are preserved end to end. `median_otsu(autocrop=True)` returns
its own cropped affine — verify it matches the `shift_affine_for_crop` result on a
known crop, and use the project convention as the source of truth.

**Interfaces:**
- Produces (workflow rewiring for Task 8): the new node emits `out_file` (cropped 4D) consumed by `dipy_nodif.in_file` and `dipy_denoise.in_file`. bvals/bvecs are unchanged by a crop and keep flowing from `conversion`.

- [ ] **Step 1: Write the failing unit test — the crop never loses brain and shifts the affine correctly.**

```python
def test_crop_preserves_brain_and_world_coordinates():
    # synthetic 4D with a brain blob padded by wide empty margins
    data = np.zeros((40, 40, 20, 6), dtype=np.float32)
    data[12:28, 14:30, 4:16, :] = 100.0     # the "brain"
    affine = np.diag([2.0, 2.0, 2.5, 1.0]); affine[:3, 3] = [-40, -40, -25]
    cropped, cropped_affine = crop_4d_median_otsu(data, affine, b0_idx=[0], pad=4)
    # every brain voxel survives the crop
    assert cropped[..., 0].sum() >= data[..., 0].sum() - 1e-3
    # world coordinate of the original brain corner is unchanged after the crop
    orig_corner_world = affine @ np.array([12, 14, 4, 1.0])
    # ... find that voxel in cropped space and assert same world point
    assert np.allclose(voxel_to_world(cropped_affine, brain_corner_in_crop), orig_corner_world, atol=1e-6)
```

- [ ] **Step 2: Run it, verify it fails** (node/function not defined).
- [ ] **Step 3: Implement `DwiCrop`** as a Nipype custom interface (disclaimers, BLAS pinning to `n_procs`, `_mem_gb` measured in isolation later). Use `median_otsu(autocrop=True, dilate=...)` with an explicit pad; shift the affine via the project convention.
- [ ] **Step 4: Run the unit test → PASS.**
- [ ] **Step 5: Wire it into the workflow** between `dipy_reOrient` and `dipy_nodif`/`dipy_denoise`. Do **not** regenerate the golden matrix snapshot here — that is Task 8, which owns all graph-shape fallout.
- [ ] **Step 6: Acceptance oracle (real data, `safe_run.py`).** A full-FOV run and a cropped run must produce the **same streamlines in world coordinates**, within tracking's own reproducibility (fixed `random_seed`). Report the per-subject shape reduction and the world-coordinate equivalence result. This is C1's contract.
- [ ] **Step 7: Black-format. Do not commit.**

**Report:** the unit-test output; the measured shape reduction per subject (subj1
and subj2); the full-FOV-vs-cropped world-coordinate equivalence result with
numbers; confirmation the affine follows `shift_affine_for_crop`.

---

## Task 3 — C2.1 + C2.2: spawn everywhere, BLAS pinning in a worker initializer, pool reused, static hoisted (Opus 4.8)

**Why Opus:** under `spawn` nothing is inherited — pinning applied at import
silently does nothing, and every payload is pickled. Both failures are invisible
until measured.

**Files:**
- Modify: `swane/nipype_pipeline/nodes/DipyMotionCorrection.py:108-128` (pool construction, IPC), `:70-85` (`_register_one_volume`)
- Test: `swane/tests/nipype_pipeline/nodes/test_dipy_motion.py` (unit + the `@pytest.mark.heavy` serial-vs-parallel oracle)

**Changes:**
1. **`mp_context="spawn"` on every OS** (user decision, 2026-09-04) — one context
   everywhere so Linux and macOS run the same path. Build the pool with
   `ProcessPoolExecutor(max_workers=..., mp_context=multiprocessing.get_context("spawn"), initializer=..., initargs=...)`.
2. **BLAS pinning in the pool `initializer`**, not at module import: under spawn
   workers re-import the module and start from library defaults, so the pin must run
   in each worker. Set `OMP_NUM_THREADS`/`OPENBLAS_NUM_THREADS=1` in the initializer
   (and keep `threadpool_limits(1)` around the registration call). Verify the module
   is import-safe: no side effects at import, no reliance on parent state.
3. **Create the pool once and reuse it** for all volumes; never build a pool per
   job. Worker startup re-imports dipy (seconds) under spawn — measure the wall-clock
   change on Linux honestly even if spawn costs time (correctness and cross-platform
   uniformity were the reason, not speed).
4. **Hoist the static reference into `initializer`/`initargs`** (or shared memory):
   the static is identical for every job, so passing it per job is pure waste, and
   under spawn every payload is pickled and shipped. This stops shipping the static
   once per volume and ships it once per worker.

- [ ] **Step 1: Reassembly-by-index unit test still holds under the new pool.** Keep the existing mocked-registration test that asserts volume *i* lands at position *i* regardless of completion order; it must pass with the injected pool. Verify the `register_fn`/`use_processes` injection points survive.
- [ ] **Step 2: Add a test that the initializer pins BLAS in the worker, not at import.** Assert `os.environ["OPENBLAS_NUM_THREADS"] == "1"` is set by the worker initializer (e.g. a worker task that returns its env), and that importing the module does **not** set it in the parent.
- [ ] **Step 3: Run both, verify the new one fails** against the current per-job / import-time code.
- [ ] **Step 4: Implement** spawn context, initializer pinning, pool reuse, static hoist. Keep the serial path (`parallel=False`) reachable and unchanged as the reference.
- [ ] **Step 5: Run the heavy serial-vs-parallel oracle** (`--run-heavy`), BLAS pinned to 1 on both sides: it must still pass **bit-for-bit**. This is the C2 contract.
- [ ] **Step 6: Measure** before/after wall clock and peak RSS on a real subject via `safe_run.py`.
- [ ] **Step 7: Black-format. Do not commit.**

**Report:** confirmation `spawn` is used on every OS and BLAS pinning happens in the
pool initializer (not at import); before/after wall clock and peak RSS; whether the
equivalence oracle still passes; the static-hoist IPC change measured. **macOS
status stated plainly** — C2.1 is a macOS-specific correctness issue and macOS has
never been validated; say whether it was exercised.

---

## Task 4 — C2.3 + C2.4: float32 buffers and the b0 mask, each measured (Opus 4.8)

**Why Opus:** dtype is the change most likely to break the equivalence oracle
silently.

**Files:**
- Modify: `swane/nipype_pipeline/nodes/DipyMotionCorrection.py:105-106,176,180` (`np.zeros` buffers), `:70-85` (`affine_registration` call — add masks)
- Test: `swane/tests/nipype_pipeline/nodes/test_dipy_motion.py`

**Changes:**
- **C2.3 float32 buffers.** `np.zeros(...)` at lines 105, 106, 176, 180 defaults to
  float64. Evaluate float32 for the volume buffers (`xformed`, `data_array`). **Keep
  the affine arrays float64** — a 4×4 transform costs nothing and precision there
  propagates to every voxel. `affines`/`affine_array` stay float64.
- **C2.4 b0 brain mask.** `affine_registration` accepts static/moving masks. Verify
  the parameter exists in dipy 1.12 **before designing around it**; passing the b0
  brain mask should exclude background from the metric, speeding and stabilising
  registration. This is a proposal to test, not a settled fact — measure the speedup;
  adopt only if it helps.

- [ ] **Step 1: Write the dtype-difference test.** On a real subject (or a realistic synthetic), compute the max absolute and relative difference between float64 and float32 motion output; assert it is below a stated, justified tolerance and record the number.
- [ ] **Step 2: Verify the b0-mask parameter exists in dipy 1.12** (inspect `affine_registration` signature) before writing any mask-passing code.
- [ ] **Step 3: Implement float32 buffers** (volume buffers only; affines stay float64).
- [ ] **Step 4: Re-run the heavy serial-vs-parallel oracle** — confirm it still passes, and state explicitly whether results changed versus Phase 1 (this is the change most likely to break it silently).
- [ ] **Step 5: Implement + measure the b0 mask** via `safe_run.py`; adopt only if it wins.
- [ ] **Step 6: Black-format. Do not commit.**

**Report:** the float64-vs-float32 max absolute and relative difference on a real
subject; whether the equivalence oracle still passes; whether results changed vs
Phase 1; whether the b0 mask helped, with numbers.

---

## Task 5 — C3: FA stopping, `seed_density=2`, `seed_buffer_fraction=0.1`, seeding per the probe (Opus 4.8)

**BLOCKED ON D-PROBE, D-TISSUE, D-SEEDDENSITY.** Do not start this executor until
the user confirms the probe's final FA threshold, whether seeding moves off WM-PVE,
the tissue-classifier fate, and the `seed_density` preference decision.

**Why Opus:** changes what the tractogram contains — the thing Phase 2 recognises.

**Files:**
- Modify: `swane/nipype_pipeline/nodes/DipyTracking.py` (stopping criterion, `seed_buffer_fraction`, `seed_density` default), `swane/nipype_pipeline/workflows/dipy_dti_preproc_workflow.py:349-359` (drop CMC wiring; per D-TISSUE possibly drop `pve_gm`/`pve_csf` connections and nodes), `swane/config/preference_list.py:438-480` (per D-SEEDDENSITY)
- Test: `swane/tests/nipype_pipeline/nodes/test_dipy_tracking.py`, `swane/tests/nipype_pipeline/matrix/test_dipy_dti_matrix.py` (Task 8 owns the snapshot regen)

**Changes (parameterised on the probe):**
- **Drop `CmcStoppingCriterion`, replace with `ThresholdStoppingCriterion(FA, 0.20)`**
  (D-PROBE resolved: FA **0.20**). The FA map already exists (`DipyTensorFit → FA`);
  wire it into tracking as the stopping input.
- **`seed_density` default 2, mapped to dipy `(N, 1, 1)` — NOT cubic `(N,N,N)`**
  (REVISED from the spec, user decision 2026-09-05). Cubic `(2,2,2)`=8 seeds/voxel
  segfaulted / swap-thrashed subj1 (real RAM risk); `(2,1,1)`≈1.5 seeds/voxel is the
  probe's operating point (~11 min, 5.4 GB). `generate_wm_seeds` maps preference N →
  `(N,1,1)` for every N in [1,10]. Preference key/default/range unchanged; only the
  "8 seeds per voxel" tooltip wording is corrected. **Semantic change to a persisted
  preference's meaning — recorded in the spec.**
- **`seed_buffer_fraction = 0.7`**, fixed (REVISED from the spec's 0.1, probe-backed:
  "buffer 0.7 safe"). Streams seeds in chunks to bound the density-2 memory spike.
- **Seeding** stays WM-PVE ≥ 0.5 **unless D-PROBE says otherwise**. If it moves to
  FA, parameterise the value from the probe.

- [ ] **Step 1: Write a node test asserting the FA stopping criterion is used** with the confirmed threshold, and that streamlines terminate on FA rather than CMC (mock/inspect the criterion object). Assert `seed_buffer_fraction=0.1` and `seed_density=2` reach the tracker.
- [ ] **Step 2: Run it, verify it fails** against the current CMC code.
- [ ] **Step 3: Implement** the FA criterion, `seed_buffer_fraction`, fixed density. Remove CMC construction and, per D-TISSUE, the now-unused `pve_gm`/`pve_csf` inputs and wiring.
- [ ] **Step 4: Run node tests → green.**
- [ ] **Step 5: Real-data confirmation** via `safe_run.py`: streamline counts on both subjects, and confirm the arcuate recovers on subj1 while subj2's CST does not degrade (the probe's regression control).
- [ ] **Step 6: Per D-SEEDDENSITY**, remove the `seed_density` key or freeze its value; per D-TISSUE, remove the dead PVE apply nodes (leave the graph-snapshot regen to Task 8).
- [ ] **Step 7: Black-format. Do not commit.**

**Report:** the FA threshold used and its source; resulting streamline counts on
both subjects; the arcuate-recovery / subj2-CST-regression result; and the
tissue-classifier and preference decisions **as the user made them**.

---

## Task 6 — C5 oracle: `median_otsu` vs the incumbent vs SynthStrip (Opus 4.8)

**STATUS — CLOSED, REJECTED (user ran the oracle, 2026-09-05).** ANTs/antspynet
remains superior to dipy `median_otsu`. C5 is measured-and-rejected; the incumbent
deskull engine stays. Task 7 does not run.


**BLOCKED ON D-C5BAR** (acceptance bar set before the oracle runs). **This is a
measurement whose conclusion may be "reject"; it must be able to reach that.**

**Files:** none committed — this is measurement under
`/home/mau/test_swane/dipy_test/`. Reuse the harness; nothing enters git.

**Method:** on the b0/nodif of both oracle subjects, compare three masks —
**SynthStrip (gold standard)**, the **current deskull engine** (incumbent), and
**`median_otsu`** (candidate). SynthStrip is the oracle's gold standard only, never
in the pipeline (no FreeSurfer dependency added to the dipy path).

- [ ] **Step 1: Confirm D-C5BAR** with the user (proposed: Dice ≥ 0.95 vs SynthStrip **and** within 0.01 Dice of the incumbent).
- [ ] **Step 2: Produce all three masks** on both subjects via `safe_run.py`.
- [ ] **Step 3: Compute** Dice, Jaccard, 95% Hausdorff, and FP/FN volume vs SynthStrip for both candidates.
- [ ] **Step 4: Practical readout** — does the `median_otsu` mask change the tractogram versus the incumbent?
- [ ] **Step 5: Decide** against D-C5BAR. Record the decision **including if it is "rejected"** — if `median_otsu` loses, the incumbent stays and C5 closes as measured-and-rejected. Do not round a loss into acceptance.

**Report:** the full oracle table (Dice, Jaccard, 95% Hausdorff, FP/FN volume vs
SynthStrip for both candidates), the practical readout, and the decision.

---

## Task 7 — C5 implementation, only if the oracle approves (Sonnet 5)

**STATUS — NOT RUN.** Task 6 rejected `median_otsu` (2026-09-05); C5 is closed and
the incumbent deskull engine stays. This task is cancelled.

**BLOCKED ON Task 6 approving.** If the oracle rejects, this task does not run and
C5 is closed.

**Files:**
- Modify: the deskull node/helper used by the dipy DWI path (`get_deskull_node` / `resolve_deskull_engine` and the underlying node) to offer `median_otsu` as the dipy-path brain-extraction engine, independent of antspynet/FSL/FreeSurfer.
- Test: the corresponding node test + a preference/gating test.

**Approach:** mechanical once the decision is made — follow the existing deskull
engine pattern. Preserve the Nipype disclaimers and the engine-selection contract.

- [ ] **Step 1: Write the node/gating test** for the new `median_otsu` deskull path.
- [ ] **Step 2: Run it, verify it fails.**
- [ ] **Step 3: Implement** following the incumbent engine pattern.
- [ ] **Step 4: Run node + preference tests → green.**
- [ ] **Step 5: Black-format. Do not commit.**

**Report:** tests run and their output; contracts touched (new engine enum/option,
if any); confirmation the FSL/FreeSurfer/antspynet paths are unchanged.

---

## Task 8 — Matrix snapshots, `strings.py` / `ToolReference`, workflow-rewiring fallout (Sonnet 5)

**Runs last**, after the graph-changing tasks (C1 Task 2 ✅ landed, C3 Task 5) have
landed. C5/Task 7 was rejected and does not contribute. Follows the earlier phases'
patterns.

**Files:**
- Modify: `swane/tests/nipype_pipeline/matrix/test_dipy_dti_matrix.py` (regenerate the golden snapshot for the new graph), `swane/config/strings.py` (`node_names` label for any new node, e.g. `DwiCrop`), `ToolReference` (citation for any new node), `swane/nipype_pipeline/workflows/dipy_dti_preproc_workflow.py` (any residual rewiring).
- Test: the matrix suite.

- [ ] **Step 1: Regenerate ONLY `snapshots/dipy_dti_preproc/`.** Confirm `snapshots/dti_preproc/` (the FSL path) is untouched — that isolation is the "two parallel pairs" proof.
- [ ] **Step 2: Add `strings.py` `node_names` labels** for every new node and any `ToolReference` citation the new nodes need.
- [ ] **Step 3: Run the full matrix suite** (`swane/tests/nipype_pipeline/matrix`) → green.
- [ ] **Step 4: Run the full `swane/tests/nipype_pipeline` suite** `-m "not heavy"` plus the heavy motion oracle.
- [ ] **Step 5: `git status --short` over `snapshots/`** — only the dipy subdir changed. Black-format. Do not commit.

**Report:** the matrix + full-suite output; proof the FSL snapshots are unchanged;
`git diff --name-only` (source, tests, docs only — no `test_swane`, no binary
imaging format).

---

## Phase report-back contract (orchestrator → global orchestrator)

A phase reported "done" without actual test output and actual numbers is not
verifiable and will be sent back. The phase report must contain:

1. **Actual output** of the new/changed tests and the full `swane/tests/nipype_pipeline` suite (`-m "not heavy"`, plus the heavy motion oracle, which must be run for C2).
2. **C1:** measured shape reduction per subject; the world-coordinate equivalence result.
3. **C2:** `spawn` on every OS + BLAS pinning in the pool initializer confirmed; before/after wall clock and peak RSS; float64-vs-float32 max absolute and relative difference; whether the equivalence oracle still passes; whether the b0 mask helped, with numbers.
4. **C3:** the FA threshold used and its source; streamline counts on both subjects; the tissue-classifier decision as the user made it.
5. **C4:** proof the regression test fails against the old code.
6. **C5:** the full oracle table (Dice, Jaccard, 95% Hausdorff, FP/FN volume vs SynthStrip for both candidates) and the decision, **including if "rejected"**.
7. Contracts touched, deviations, what was deliberately not done.
8. **macOS status** — stated plainly (C2.1 is a macOS-specific correctness issue; macOS has never been validated).
9. `git diff --name-only` confirming no `test_swane` path and no binary imaging format.

## Self-review (run against the spec)

- **Spec coverage:** C1→Task 2; C2.1/C2.2→Task 3; C2.3/C2.4→Task 4; C3→Task 5;
  C4→Task 1; C5 oracle→Task 6; C5 impl→Task 7; snapshots/strings/rewiring→Task 8.
  Every spec correction maps to a task. The "Note on C1 and C5" (both use
  `median_otsu` but are independent decisions) is honoured: Task 2 ships regardless;
  Task 7 ships only if Task 6 approves; neither implies the other.
- **User decisions:** D-PROBE, D-TISSUE, D-SEEDDENSITY, D-C5BAR each flagged at the
  gating task and in the header — raised, not settled.
- **Contracts:** FSL path/snapshots (Task 8 verifies), Phase-2 output names,
  motion oracle (Tasks 3/4), world coordinates (Tasks 1/2), HARD_CAP + BLAS pinning
  in workers (Task 3), 8 GB budget (Tasks 1/4), Nipype disclaimers (all tasks).
