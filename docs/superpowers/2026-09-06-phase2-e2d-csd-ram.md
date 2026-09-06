# Phase 2 / E2d — `DipyCsdFit` RAM: `npeaks` pinning and the two-branch estimator

Date: 2026-09-06. Branch `claude/dipy-recobundles`. Plan:
`docs/superpowers/plans/2026-09-04-phase2-recobundles.md` (task E2d). Spec:
`docs/superpowers/specs/2026-09-05-ram-estimator-bidirectional-design.md`
("Estimation philosophy").

## What shipped

1. `DipyCsdFit` pins `peaks_from_model(npeaks=1)`.
2. `DipyCsdRamEstimator` — a tunable estimator that models dipy's two branches
   separately and scans the worker count down to the serial rung.
3. The `"csd"` key is removed from the workflow's static `_MEM_GB` table; the
   node now carries `ram_estimator` plus a `STATIC_FALLBACK_GB` fail-safe.

## Reading dipy 1.12.0 before modelling it

`dipy/direction/peaks.py` has two branches with different memory profiles:

* **Serial** (`num_processes == 1`) allocates one full-volume set of output
  arrays: `gfa`, `qa`, `peak_dirs`, `peak_values`, `peak_indices`, `shm_coeff`.
* **Parallel** (`num_processes > 1`) sets `nbr_chunks = P**2`, and every chunk
  result returned by `pool.map` lives in the parent at once (one full-volume
  equivalent), is copied into `np.memmap` buffers (a second), and read back with
  `np.array` (a third).
* Each of the `P` concurrent workers memory-maps its slice of the saved data and
  allocates its own chunk arrays (`voxels / P**2` each), so the aggregate worker
  term is `voxels / P` — it *shrinks* as `P` grows — plus one `spawn`
  interpreter per worker (dipy calls `mp.set_start_method("spawn", force=True)`).

Two consequences shaped the design:

* The lever named in the plan ("`num_processes` down") is **not a monotone
  ladder**. The parent term is constant in `P`; only the worker and spawn terms
  move, and in opposite directions. The estimator therefore evaluates every rung
  from the declared count down to 1 and returns the largest that fits, instead
  of halving. The real cliff is `P == 1`, which switches to the serial branch.
* dipy's `qa` array is **not** rung-invariant — each chunk normalises by its own
  `global_max`. `shm_coeff`, the node's only output, is independent of that.

## `npeaks`: a free 1.1 GB

The node saves only `shm_coeff`, which is `np.dot(odf, invB)`. `npeaks` never
enters that computation: `peak_directions` is called without it, and it only
sizes and fills the peak arrays afterwards. dipy's default `npeaks=5` therefore
allocated, per voxel of the volume, `peak_dirs (5,3) f64` + `peak_values (5) f64`
+ `peak_indices (5) i32` + `qa (5) f64` = 228 B, against 52 B at `npeaks=1` —
and the parallel branch holds three full-volume copies of those.

It buys no speed either (a larger `npeaks` means slightly more zeroing and
assignment, never less work), so it is pinned to 1 rather than exposed as a
tuned lever.

Measured effect, same input and worker count, `npeaks` the only change:

| Subject | npeaks=5 | npeaks=1 | Saved |
|---|---|---|---|
| subj1 (256×256×52×16, lmax 4) | 3.551 GB | 2.440 GB | **1.111 GB** |
| subj2 (144×144×60×65, lmax 8) | 2.939 GB | 2.739 GB | **0.200 GB** |

The `npeaks=5` figures reproduce the Phase-1 measurements (3.57 / 3.05 GB),
which is what makes the rest of the campaign comparable to the earlier table.

## float32: evaluated and rejected

Casting the 4D series to float32 was evaluated first, on the real subj2 input.
It is **not** equivalent and was not adopted.

* The bias-corrected DWI is stored as int16 **with scaling**, so `get_fdata()`
  yields non-integer float64: 30.2 M of 80.9 M elements (37 %) are not exactly
  representable in float32. The cast is lossy, not a widening round-trip.
* Holding the response fixed and casting only the data, `shm_coeff` diverges by
  up to `2.1e-2` absolute — 3.0 % of the largest coefficient — and **573 642 of
  2 799 360** saved float32 elements differ (20.5 %). Casting the response too
  (the realistic node change) raises that to 649 229 (23 %).
* CSD is ill-conditioned and probabilistic tracking downstream is chaotic with
  respect to the fODF field, so this is not quality-neutral in the sense E2a–E2d
  require (bit-for-bit equivalence).
* The prize was small anyway: the 4D buffer is 0.41 GB (subj1) / 0.60 GB (subj2)
  at float64, against the ~2 GB dominated by the per-voxel arrays.

**Collateral finding, not acted on:** `DwiBiasCorrection` writes the corrected
DWI as int16-with-scaling rather than float32. That is a real precision loss
already in production and upstream of CSD. Out of E2d's scope.

## Calibration campaign

Six isolated runs of the real node (tree-peak RSS: parent + all descendants,
sampled at 0.15 s), one node per process, under the throwaway
`~/test_swane/dipy_test/harness` launcher. Real oracle inputs; nothing committed.

| Run | Subject | Workers | npeaks | Peak RSS | Wall |
|---|---|---|---|---|---|
| A | subj1 | 4 | 5 | 3.551 GB | 210 s |
| C | subj1 | 4 | 1 | 2.440 GB | 258 s |
| B | subj2 | 4 | 5 | 2.939 GB | 129 s |
| D | subj2 | 4 | 1 | 2.739 GB | 120 s |
| E | subj2 | 2 | 1 | 2.436 GB | 98 s |
| F | subj2 | 1 | 1 | 1.316 GB | 172 s |

Solving the model on subj2's three worker counts gives `OVERHEAD ≈ 0.24 GB`,
`SPAWN ≈ 0.21 GB/worker` and an **effective** `PARALLEL_COPIES ≈ 1.96`: dipy
allocates three full-volume copies, but the memmap-backed one is only partly
resident at the peak instant. Applying those to subj1 predicts 2.69 GB against
2.44 measured — the fit generalises across a 2.7× voxel ratio and a different
SH order, and errs high.

The measured curve is monotone increasing in `P` at these sizes (1.32 / 2.44 /
2.74 GB), because the spawn term still dominates the `1/P` worker term. The
model's non-monotone region starts above ~5.2 Mvoxel at lmax 8, which neither
oracle reaches. The scanning ladder is correct either way; the non-monotonicity
is a model property, not an observed one, and the estimator's docstring says so.

## The conservative bound

Per the spec's estimation philosophy the shipped constants are a defensible
**over-estimate**, not the fit above. Per-voxel array sizes are read off the
dipy allocations exactly; the copy multiplicity keeps the source-counted 3
rather than the effective 1.96; the rest is rounded up.

```
per_voxel = 52 + 8 * n_coeff                      # bytes
data_gb   = 10 * voxels * volumes / 2**30         # float64 is 8; 10 covers the mask
serial    = 0.4 + data_gb + 1 * per_voxel * voxels / 2**30
parallel  = 0.4 + data_gb + 3 * per_voxel * voxels / 2**30
                + per_voxel * voxels / (P * 2**30) + P * 0.25
```

Coverage of every measured point:

| Configuration | Measured | Estimate | Margin |
|---|---|---|---|
| subj1, 4 workers | 2.440 GB | 3.68 GB | 1.51× |
| subj2, 4 workers | 2.739 GB | 3.71 GB | 1.35× |
| subj2, 2 workers | 2.436 GB | 3.32 GB | 1.36× |
| subj2, serial | 1.316 GB | 1.63 GB | 1.24× |

Same family of margin as the motion (1.21–1.86×) and tissue (1.11–1.14×)
estimators. `STATIC_FALLBACK_GB = 4.0` — the estimate at the declared rung for a
representative DWI, rounded up. It is read only when the negotiation cannot run
at all (unreadable header or bval), a state in which the node cannot run either.

The regressors are the input sequence's **spatial voxel count** (which sizes both
the 4D buffer and every per-voxel output array), its **volume count**, and the
**SH coefficient count**, itself derived from the acquisition's non-b0 direction
count through the node's own `sh_order_for_directions`, so estimator and node
cannot disagree on the adaptive `sh_order_max`.

## Still open

The dipy engine's RAM floor (`ResourceManager.DIPY_TRACTOGRAPHY_RAM_REQUIREMENT`,
currently 8 GB) is **not** settled by this task. It is the joint step at the end
of Phase 2, back-computed from each estimator's bottom rung for a representative
average sequence. CSD's contribution to that decision is its serial rung: 1.63 GB
estimated, 1.32 GB measured on subj2.
