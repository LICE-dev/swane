# Phase 1 report to the global orchestrator — dipy preprocessing to global tractogram

Date: 2026-09-04 · Branch: `claude/dipy-recobundles` · Phase orchestrator: Opus 4.8

Phase 1 delivered the dipy tractography engine's preprocessing-through-tracking
half: engine preference + gating, dependency/licence plumbing, nine new dipy
Nipype nodes (plus one enabling node), `dipy_dti_preproc_workflow`, the
`MainWorkflow` branch, matrix snapshots, and a real-data measurement/validation
pass on two subjects. The FSL/XTRACT path is untouched and bit-identical.

## 1. Test output (run at report time, HEAD `1b67061`)

- **dipy nodes + workflow wiring + AffineToRAS + AffineToFSL + engine gating + dependency:** `104 passed, 2 skipped` (the 2 skipped are the `@pytest.mark.heavy` motion serial-vs-parallel oracle; it passes under `--run-heavy`, run by the T5/T11 sessions).
- **Full matrix suite** (`swane/tests/nipype_pipeline/matrix`): `117 passed`.
- Across the phase the executors also reported the full `swane/tests/nipype_pipeline -m "not heavy"` green (last: 479 passed) plus the heavy motion oracle.

## 2. FSL snapshots untouched (the "two parallel pairs" isolation proof)

`git status --short` over `snapshots/` is clean; the only Phase-1 snapshot artefact
is the **new** `snapshots/dipy_dti_preproc/` subdir. The last commit touching any
FSL snapshot (`snapshots/dti_preproc/`) is `ab0828b` — the Phase-0 rotated-bvec
fix, the single permitted pre-existing delta. No Phase-1 commit modified an FSL
snapshot. `dti_preproc_workflow` and `tractography_workflow` are unmodified.

## 3. Measured table (real subjects; box: 4 cores / 11 GB / no GPU)

subj1 = 15 dir, 256×256×52×16. subj2 = 64 dir, 144×144×60. Per-node **isolated**
tree-peak RSS (parent + workers), since nipype runs each node in its own process.

| node | _mem_gb (reserved) | subj1 GB | subj2 GB | subj1 time | cores |
|---|---|---|---|---|---|
| DipyDenoise (nlmeans) | 1 | 1.11 | 1.37 | 52.7 s | num_threads |
| DipyMotionCorrection (rigid-only, pool) | **8** | 7.11 | **8.44** | ~460 s* | 3.88 (pool) |
| DwiBiasCorrection (single N4) | 1 | 0.85 | 0.99 | 31.9 s | 1 |
| DipyTensorFit → FA | 1 | 0.89 | 1.16 | 23.2 s | 1 |
| DipyCsdFit (adaptive lmax) | 4 | 3.57 | 3.05 | 196.7 s | num_processes |
| DipyTissueClassifier (HMRF/T1) | 5 | 2.58 | 5.17 | 207.8 s | 1 |
| AffineToRAS | 1 | 0.11 | 0.11 | 1.1 s | 1 |
| DipyTracking (probabilistic+CMC, cropped) | 5 | 5.09 | 2.04 | ~90–140 s | num_threads |
| DipyAtlasSLR (whole-brain, once) | 5 | 4.75 | 0.98 | — | 1 |

`_mem_gb` = max(subj1, subj2), rounded to int. *motion rigid-only is ~30% faster
than the full 4-stage pipeline (655.9 s full → ~460 s).

- **Motion is the RAM ceiling of the path** and the one node that genuinely needs
  the hand-written pool: dipy's intrinsic parallelism is **1.01 cores** (BLAS does
  not engage), our pool reaches **3.88 cores @ 8.44 GB** on subj2.
- **Reproducibility:** the node-level test asserts identical streamline
  trajectories across two runs at equal `random_seed` (bytes may differ).
- **subj2 completed end-to-end** — it never had before (the old probe died in
  MP-PCA); with `nlmeans` + probabilistic tracking it runs to a global tractogram.
- Connected (nipype-scheduled) end-to-end wall-clock was **not** captured; per-node
  isolated timings above stand in.

## 4. CST / AF quality — and the FSL comparison

Extraction used a throwaway RecoBundles probe on the **realistic** tractograms
(antspynet-T1 PVE + ANTs diff→T1 + whole-brain SLR to HCP842); it is **not** the
Phase-2 node.

- **CST: clean on subj2 (64 dir)** at the correct config (dipy-default 10/5,
  `model_clust_thr` ≈ 2.5); recovered shape matches the atlas model. **The user
  visually validated the CST `.vtp` in Slicer — "perfect."**
- **Arcuate (AF): under-reconstructed** (≈18 streamlines at reduction 15, 0 at the
  default 10; not a `max_angle` issue). **subj1 recovers 0** at the correct config.
- **The FSL-branch quantitative comparison is DEFERRED (no GPU on this box)** — a
  CPU-only bedpostx/probtrackx run is many hours per subject. This is the formal
  Phase-2 gate item still owed, on a GPU machine.

**User decision on the quality result (records the reframe):** the AF failure is
**not** an accepted low-direction limit but a **Phase-2 fix objective**, because
FSL/XTRACT reconstructs subj1's arcuate cleanly at the *same* 15 directions — so
the data support the bundle and the current dipy pipeline does not yet recover it
(candidate causes: CST-dominated SLR skew ~1.29×, temporal-stem sparsity, single
global threshold). Spec §"RecoBundles on the realistic tractogram" and
§"Accepted risk" were reframed accordingly (`1b67061`). The engine default stays
`DIPY_RECOBUNDLES`.

## 5. Contracts touched, deviations, and what was deliberately not done

**Phase-2 contracts honoured:** `dipy_dti_preproc_workflow` emits
`outputnode.tractogram`, `outputnode.tractogram_atlas`, `outputnode.atlas2native`
(+ `FA`) — exact names. Whole-brain SLR runs once, here. HARD_CAP only (no
`multicore_node_limit`). Every dipy node carries the Nipype disclaimers.

**Deviations from the original plan (all ratified with the user):**
- **New node `AffineToRAS`** — the plan's 8 dipy nodes created the consumer
  (`DipyTracking.affine_diff2ref`, a 4×4 RAS text affine) but no producer; a
  dedicated node (nitransforms, ITK/LPS→RAS, inverse of the pull matrix) was added.
- **Registration honours the user's global engine (FSL included)** — an early T8
  version wrongly hardcoded ANTs (a spec §1 violation), corrected so
  brain-extraction and registration follow the global choice; the FA/PVE apply
  nodes were given the dual-engine warp view. FSL-registration path confirmed
  end-to-end with a real FLIRT (34.9 min, near-identity affine, tractogram 98.8%
  in-brain).
- **Tracker changed PFT → `probabilistic_tracking`** (keeps `CmcStoppingCriterion`):
  `pft_tracking(sh=)` is single-core and precomputes a 9.19 GB full-FOV PMF,
  unworkable on 8 GB / 4 cores. Still probabilistic; only PFT's particle-filtering
  reinit is lost. **A brain-bbox crop was required** (an early "no crop" call was
  wrong — the real density-2 run swap-froze the box; the crop is streamline-
  invariant).
- **Motion is rigid-only** — the affine stage was dropped (subj2 corr 0.9997, −30%
  time). Trade-off recorded: dipy motion no longer corrects eddy-current geometric
  distortion (declared asymmetry vs FSL `eddy`).
- Plumbing: `license_consent.py` includes dipy in the consent tool-set;
  `threadpoolctl` and `filelock` are explicit `setup.py` pins; RecoBundles cited as
  **Garyfallidis 2018** (Crossref) rather than the spec's earlier "2017".
- **8 GB is a soft target, by user decision** — motion peaks 8.44 GB with the
  4-worker pool; reducible by lowering pool threads; the floor stays 8 GB with the
  worker-cap optimisation deferred.

**Deliberately not done (Phase 2/3, or off-box):**
- The quantitative CST/AF-vs-FSL comparison (GPU box).
- **macOS validation — not run anywhere; all evidence is Linux.** Stated plainly.
- Arcuate recovery, per-bundle RecoBundles thresholds, the bundle node, the fornix
  split, SlicerDMRI, the `.trk` result contract, phantom v9 — all Phase 2/3.

## 6. Bottom line

Phase 1 is functionally complete: a correct global tractogram on both oracle
subjects, a clean and user-validated CST, the three Phase-2 outputs wired, and the
FSL path proven bit-identical. Two items are owed before Phase 2 release and both
are off this box: the **GPU FSL comparison** (formal gate) and **macOS**. The
**arcuate under-reconstruction is handed to Phase 2 as a fix objective**, not an
accepted limit.
