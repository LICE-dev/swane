# Phase 1bis report to the global orchestrator — dipy path corrections

Date: 2026-09-05 · Branch: `claude/dipy-recobundles` · Phase orchestrator: Opus 4.8

Phase 1bis delivered five corrections (C1–C5) to the Phase 1 dipy tractography
path, required before Phase 2 is built on it. Four landed (C1, C2, C3, C4); one
(C5) was measured and rejected. The FSL/XTRACT path is untouched and bit-identical.
Nothing is committed by the executors; commits are done once, here, at phase end.

Plan: `docs/superpowers/plans/2026-09-04-phase1bis-corrections.md`.
Spec: `docs/superpowers/specs/2026-09-04-phase1bis-design.md` (updated in-phase for
the C3 revisions). Baselines: `docs/superpowers/2026-09-04-phase1-report.md`.

## 1. Test output (orchestrator-run, combined working tree)

- Full `swane/tests/nipype_pipeline -m "not heavy"`: **503 passed, 11 deselected**.
- Heavy serial-vs-parallel motion oracle (`test_dipy_motion.py --run-heavy`):
  **13 passed**, bit-for-bit under `fork`.
- Matrix golden graph: dipy snapshot regenerated (20→19 nodes, 42→37 edges);
  FSL `snapshots/dti_preproc/` **intact** — the two-parallel-pairs isolation holds.

## 2. Per-correction results

| Corr. | Outcome | Numbers |
|---|---|---|
| **C4** — crop from brain-mask, not shm foreground | ✅ | Crop derives from `nodif_brain` (skull-stripped b0); regression test proves the old shm∪PVE union degenerated to a no-op. New mandatory `DipyTracking.nodif_brain` input. |
| **C1** — upfront 4D `median_otsu` crop | ✅ | New node `DwiCrop` (mask from the **mean of all volumes** = motion envelope, since the crop precedes motion correction). Shape subj1 −50.6% (256²×52→167×194×52), subj2 −46.9%. World-coord equivalence (full-FOV vs cropped, same seed): 0.00 mm subj1 / 7.6e-6 mm subj2. `autocrop` not used (deprecated in dipy 1.11, gone 1.13) — bbox via `foreground_bbox_slices` + `shift_affine_for_crop`. |
| **C2.1** — process context | ✅ (revised) | **fork on Linux, spawn on Windows/macOS** (revised 2026-09-05 from "spawn everywhere"): fork avoids the per-worker dipy re-import; spawn where fork is unavailable/unsafe. Safe because BLAS is pinned in the pool **initializer** (+ `threadpool_limits(1)`), not by env inheritance, so every start method leaves workers pinned. Pool built once and reused; static reference hoisted via `initargs`. |
| **C2.2** — IPC | ✅ | Static hoisted (once/worker vs once/volume). `shared_memory` for the moving volumes **measured and rejected** (4.6 s slower; total IPC ~1.4% of a 460 s run) — per-job copy kept. |
| **C2.3** — dtype | ✅ | Volume buffers float32 (`xformed`, `data_array`); affine buffers stay float64. Measured peak dropped to ~3.7 GB (from 7.11/8.44 float64). float64-vs-float32: max_abs 6.1e-5, max_rel 5.96e-8 (= float32 eps); saved int16 differs by ±1 in 0.033 % of voxels — scientifically identical. Oracle bit-for-bit preserved via a single output cast. |
| **C2.4** — b0 registration mask | ❌ rejected | On production-consistent **cropped** data the b0 mask is 0.93× (7 % slower) and shifts the transform 0.45; the earlier "1.26× faster" was a full-FOV artifact (78 % background), which the C1 crop already removes. No node change. |
| **C3** — FA stopping, density, seed buffer | ✅ (subj1) | `CmcStoppingCriterion` → `ThresholdStoppingCriterion(FA, 0.20)` (source: seed/stop probe 2026-09-04); FA is the diffusion-space `DipyTensorFit` output, not the ref-registered copy. seeding stays WM-PVE ≥ 0.5. **Dead nodes removed**: `pve_gm_2_diff`/`pve_csf_2_diff` apply nodes and the `pve_gm`/`pve_csf` tracking inputs (`DipyTissueClassifier` stays — it makes `pve_wm`). subj1 real run: 297,813 streamlines — an **exact match** to the probe's validated `Bp_fa020_d15` arm (AF_L 2→361 @ reduction 15; CMC baseline AF_L=2), peak 5.37 GB, ~17 min. |
| **C5** — deskull by `median_otsu` | ❌ rejected | User ran the oracle: ANTs/antspynet remains superior to dipy `median_otsu`. Incumbent stays; the dipy path gains no `median_otsu` deskull option. |

## 3. Deviations from the written plan (all ratified with the user)

- **C2.1**: "spawn everywhere" → **fork Linux / spawn Windows+macOS** (2026-09-05).
  The pinning-in-initializer design makes every start method correct, removing the
  fork-inherits/spawn-doesn't trap that motivated spawn-everywhere.
- **C3 seeding**: `seed_density` maps preference N → dipy **`(N, 1, 1)`, not cubic
  `(N,N,N)`** (probe-backed; cubic `(2,2,2)`=8 seeds/voxel segfaulted/swap-thrashed
  subj1). `seed_buffer_fraction` **0.1 → 0.7** (probe: "buffer 0.7 safe"). Preference
  key/default/range unchanged; only the "8 seeds per voxel" tooltip corrected. Spec
  and plan updated in-phase.
- **C4**: crop from a new `nodif_brain` input (the canonical skull-stripped b0),
  cleaner than the planned PVE union; its snapshot was regenerated in-task.
- **C1**: `autocrop` not used (deprecated); mean-of-volumes mask; `dilate=2`, `pad=8`
  (measured: `pad=4` clips subj1's brain).

## 4. Accepted risks / owed before Phase 2 release

- **subj2 validation deferred by explicit user decision** ("for C3 and Task 4 use
  only subj1"). The CST-regression control for CMC→FA and the C2 changes was **not
  run on the 64-dir subject**; both are global defaults. Scientific risk is low
  (FA-stop 0.20 is a conservative threshold, no flooding on the harder subj1) but
  **unmeasured on the well-resolved regime**. Not signed as a passed gate — carried
  as an accepted-risk item to close before Phase 2 release.
- **`(N,1,1)` seed density is validated only at N=2.** It scales ~linearly, so high
  `seed_density` (up to the preference max 10) can still exceed 8 GB. Only 2 is
  proven safe on the 8 GB floor.
- **RAM floor is now conservative.** float32 (C2.3) cut motion's measured peak to
  ~3.7 GB, so the path ceiling is tissue/tracking (~5 GB), not motion's 8 GB
  reservation. Re-deriving the 8 GB `option_pref_requirement` floor is a deliberate
  resource-contract change left as a follow-up; the reservation was kept unchanged.
- **`_mem_gb["DwiCrop"]` is provisional** (=1, aligned with denoise); isolated
  per-node RSS measurement still owed.
- **macOS never validated** (no box). Under the C2.1 revision macOS uses spawn (like
  Windows); the spawn code path is covered by the initializer tests and earlier spawn
  oracle runs, and start method is the only difference — but no macOS run exists.
- **subj1 arcuate recovery is corroborated, not re-proven**: the streamline-count
  identity to the probe's validated arm stands in for a re-run RecoBundles extraction
  (which peaks 8.06 GB and was not repeated on the 8 GB box).

## 5. Contracts

- **Phase-2 outputs unchanged**: `outputnode.tractogram`, `outputnode.tractogram_atlas`,
  `outputnode.atlas2native`.
- **FSL/XTRACT path bit-identical**: `dti_preproc_workflow`, `tractography_workflow`,
  `snapshots/dti_preproc/` untouched.
- **Interface breaks (intentional, dipy path only)**: `DipyTracking` gains mandatory
  `nodif_brain` and `fa` inputs and loses `pve_gm`/`pve_csf`; two PVE apply nodes
  removed from `dipy_dti_preproc_workflow`.
- HARD_CAP only; BLAS pinned to declared threads, including in pool workers. Every
  node keeps its Nipype disclaimers.

## 6. Bottom line

The dipy tractography path is corrected and RAM-safer: cropped upfront, a hardened
and cross-platform-uniform motion pool, an FA stopping criterion that recovers the
arcuate on the low-direction subject, a real crop-bug fix, and a dead-node removal.
C5 is closed as measured-and-rejected. What is owed before Phase 2 release is the
**subj2 regression** (deferred by user decision) and the **RAM-floor retune**; both
are recorded, neither blocks Phase 2 planning.
