# Phase 2 — E2c: `DipyTissueClassifier` RAM estimator (findings)

Date: 2026-09-06
Branch: `claude/dipy-recobundles`
Task: E2c of `docs/superpowers/plans/2026-09-04-phase2-recobundles.md`

## Outcome

`DipyTissueRamEstimator` is a **classic one-way** `RamEstimator` (like the FSL
estimators), **not** the tunable bidirectional estimator the plan sketched. The
plan's prescribed lever for this node — "thread/BLAS count down" — was measured
to move neither RAM nor wall time, so there is nothing to tune. The estimator
reserves RAM from the T1 voxel count and inherits the default `negotiate` (empty
`tuned_params`, `n_procs=None`). Decision taken jointly with the user.

## Why the thread lever is dead

`DipyTissueClassifier` runs dipy's `TissueClassifierHMRF.classify` on the T1
`reference_brain`. The node already pins `OMP_NUM_THREADS=1` inside `classify`
and exposes **no** thread/worker input trait. The HMRF classify is a serial
Python/numpy loop that OMP/BLAS threads do not parallelise.

Probe: `classify(data, 3, 0.1)` on each oracle T1 brain, thread pools
(`OMP_/OPENBLAS_/MKL_/NUMEXPR_/VECLIB`) pinned **before** the numpy/dipy import,
process peak RSS via `resource.RUSAGE_SELF`:

| subject | T1 shape | voxels | threads | peak RSS |
|---|---|---|---|---|
| subj1 | (224,256,170) | 9,748,480 | 1 | 2.569 GB |
| subj1 | (224,256,170) | 9,748,480 | 2 | 2.569 GB |
| subj1 | (224,256,170) | 9,748,480 | 4 | 2.569 GB |
| subj1 | (224,256,170) | 9,748,480 | 8 | 2.569 GB |
| subj2 | (320,320,200) | 20,480,000 | 1 | 5.160 GB |
| subj2 | (320,320,200) | 20,480,000 | 8 | 5.159 GB |

Peak RSS is byte-identical across thread counts; wall time is flat too (~63 s
subj1, ~165 s subj2, regardless of threads). This also confirms the earlier
recollection that the node stays single-core whatever `OMP_NUM_THREADS` says.

## RAM is linear in input voxels

Subsampling subj2's T1 by leading z-slices (threads=1), same peak-RSS method:

| voxels (M) | peak RSS |
|---|---|
| 2.048 | 0.857 GB |
| 5.120 | 1.588 GB |
| 10.240 | 2.842 GB |
| 15.360 | 4.096 GB |
| 20.480 | 5.312 GB |

Least-squares fit: **peak ≈ 260 B/voxel · voxels + 0.36 GB** (midpoint predicted
2.837 GB vs 2.842 measured). The real-node native peaks (subj1 2.569, subj2
5.160 — no subsample copy) sit *below* this line. The subsample points carry a
one-time `ascontiguousarray` copy the real node does not, so they slightly
over-state the node's true peak — conservative for our purpose.

## The conservative bound

`DipyTissueRamEstimator`: `280 B/voxel + 0.4 GB`, `min_gb=0.5`, `max_gb=None`.

A deliberate over-estimate of the fit, covering every measured point with margin:

| input | voxels | estimate | measured peak | margin |
|---|---|---|---|---|
| subj1 T1 | 9,748,480 | 2.94 GB | 2.569 GB | 1.14× |
| subj2 T1 | 20,480,000 | 5.74 GB | 5.160 GB | 1.11× |

`max_gb=None` (like the motion/tracking estimators): clamping the estimate down
would make the node under-reserve and let the scheduler co-admit other heavy
work — deciding a node cannot fit is the scheduler's job, not the estimator's.

`STATIC_FALLBACK_GB = 6.0` is the node's pre-negotiation `_mem_gb`, read only if
the negotiation cannot run at all (input header unreadable — a state in which the
node cannot run either). It replaces the old static `_MEM_GB["tissue"] = 5`.

## Testing

Per the joint decision, **unit tests only** — no heavy test. The prescribed
"tuned-vs-untuned identical PVE maps" heavy equivalence is degenerate for a
classic estimator (no lever ⇒ the node runs identically regardless of the
estimator), so the estimator is instead proved by
`tests/nipype_pipeline/nodes/test_dipy_ram_estimator_tissue.py`: voxel-scaling,
the multiplier formula, the min floor, no clamp-down, the conservative-bound
guard against the two measured oracle peaks, the classic no-tuning negotiation,
and plugin integration (reservation lands, inputs and `n_procs` untouched). The
bound evidence above is the record the equivalence test would otherwise carry.

## Floor

Unchanged here. The dipy engine RAM floor is the final joint step of Phase 2,
back-computed from every RAM-critical estimator's bottom rung; the current 8 GB
stands until then.
