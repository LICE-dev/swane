# Phase 1bis — corrections to the dipy path before Phase 2

Date: 2026-09-04 · Branch: `claude/dipy-recobundles` · Status: design, pending plan

## Goal

Five corrections to the Phase 1 dipy tractography path, required before Phase 2
can be built on it. Phase 1 is functionally complete but three of its choices are
now known to be wrong or unmeasured, and two more are optimisations the user has
decided to take now rather than carry into Phase 2.

Phase 2 is **blocked on this phase**, not merely sequenced after it: the tracking
changes (C3) alter what the tractogram contains, and Phase 2's whole job is
recognising bundles inside that tractogram.

## Blocking external input

The seed/stop probe (`docs/superpowers/plans/2026-09-04-seed-stop-af-probe-prompt.md`)
is running. It supplies two values this phase cannot invent:

1. **The FA stopping threshold** (C3). Literature range ~0.10-0.25; the probe
   sweeps it and reports what it chose and why.
2. **Whether seeding moves from the WM PVE mask to FA** (C3), and at what value.

Do not guess either. If the probe has not reported, implement everything else and
leave these two parameterised.

## C1 — crop the 4D DWI upfront, with `median_otsu`

Today the pipeline carries the full FOV through denoising, motion correction,
bias correction, tensor and CSD fitting, and crops only at tracking. subj1 is
256x256x52; the brain occupies roughly 161x192x52. Every upstream node pays for
the empty margin, in both time and RAM.

Following dipy's `reconst_dti` example, crop the 4D series immediately after
conversion/orientation using `dipy.segment.mask.median_otsu`, whose signature is:

```
median_otsu(input_volume, *, vol_idx=None, median_radius=4, numpass=4,
            autocrop=False, dilate=None, finalize_mask=False)
```

`autocrop=True` returns the cropped volume and its mask in one call.

**Crop generously.** The crop must be lossless with respect to the brain: use
`dilate` and an explicit voxel pad, and treat a too-large crop as correct and a
too-small crop as a defect. A crop is not a mask — nothing downstream depends on
the boundary being tight, and cutting brain is unrecoverable.

The crop's affine shift must follow the existing `shift_affine_for_crop`
convention so that world coordinates are preserved end to end. Streamlines,
registration matrices and the reference-space transform must be unaffected: the
regression test is that a full-FOV run and a cropped run produce the same
streamlines in world coordinates, within tracking's own reproducibility.

## C2 — `DipyMotionCorrection`: process context, IPC, dtype, mask

Four changes to the hand-written pool. The **serial-vs-parallel equivalence
oracle is the contract**; it must still pass, and any change that alters output
must be reported as a number rather than assumed benign.

### C2.1 Explicit `mp_context`

`DipyMotionCorrection.py:108` builds a `ProcessPoolExecutor` with no `mp_context`,
inheriting the platform default.

**Decided by the user, 2026-09-04: use `spawn` on every operating system.** Not
`forkserver`, not the platform default — one context everywhere, so that Linux and
macOS run the same code path and a measurement taken on one is evidence about the
other. This is the direct answer to the trap below, which exists precisely because
the two platforms currently differ.

**The trap that makes this urgent**: with `fork`, workers inherit the parent's
already-applied BLAS thread pinning; with `spawn` they do not — they re-import
the module and start from library defaults. So a pool that is pinned to one BLAS
thread per worker on Linux may be unpinned on macOS, where `spawn` has been the
default since Python 3.8. That is both a resource-accounting break under HARD_CAP
and a possible equivalence break, and it would appear only on the platform this
project has never validated.

Under `spawn` the worker **must pin its own BLAS threads in a pool
`initializer`**; inheritance is no longer available anywhere, so this is not
optional and not platform-conditional.

Three further consequences of `spawn` that the implementation must handle:

- **Worker startup is expensive.** Each worker re-imports the module, and
  importing dipy costs seconds. Create the pool **once and reuse it** for all
  volumes; never build a pool per job. On Linux this is a change from the current
  `fork` default and will show up in the wall clock — measure it, and report the
  before/after honestly even if `spawn` costs time. Correctness and cross-platform
  uniformity were the reason for the choice, not speed.
- **Everything crossing the boundary must be picklable**, and the module must be
  import-safe: no side effects at import, no reliance on parent state. Verify the
  BLAS pinning is applied in the initializer and not at module import, or it will
  silently do nothing.
- **It raises the value of C2.2.** With `fork`, large arrays were cheap to inherit;
  under `spawn` every payload is pickled and shipped. Hoisting the static
  reference into the initializer stops being an optimisation and becomes the
  difference between shipping it once per worker and once per volume.

### C2.2 IPC

Each job currently ships a 3D moving volume **and the static reference** to the
worker and ships a 3D volume back. The static is identical for every job, so
passing it per job is pure waste: hoist it into a pool `initializer`/`initargs`,
or into shared memory.

For the moving volumes and the output, evaluate `multiprocessing.shared_memory`
or a memmapped 4D array against the current copy. Measure before and after;
adopt only if it wins. On a 4-core box the pool already reaches 3.88 cores, so
the realistic gain is wall clock and peak RSS, not parallel efficiency.

### C2.3 dtype

`np.zeros(...)` at lines 105, 106, 176 and 180 defaults to float64. Evaluate
float32 for the volume buffers.

**This is the change most likely to break the oracle silently.** Requirements:
report the max absolute and relative difference between float64 and float32
output on a real subject; re-run the serial-vs-parallel oracle and confirm it
still passes; and state explicitly whether results changed versus Phase 1. Keep
the affine arrays float64 — a 4x4 transform costs nothing and precision there
propagates to every voxel.

### C2.4 b0 brain mask

`affine_registration` accepts static/moving masks. Passing the b0 brain mask
should speed registration and improve robustness by excluding background from the
metric. Verify the parameter exists in dipy 1.12 before designing around it, and
measure the speedup; this is a proposal to test, not a settled fact.

## C3 — tracking: FA stopping, fixed density and seed buffer

- **Drop `CmcStoppingCriterion`**, replace with an FA threshold criterion. The
  value comes from the probe.
- **`seed_density = 2` always**, but mapped to dipy `(N, 1, 1)`, **not cubic
  `(N,N,N)`** (REVISED 2026-09-05 after implementation). Cubic `(2,2,2)` = 8
  seeds/voxel segfaulted / swap-thrashed subj1 on the 8 GB box — a real RAM risk,
  not a fluke. `generate_wm_seeds` maps the preference value N → dipy density
  `(N,1,1)` for every N in `[1,10]`; `(2,1,1)` ≈ 1.5 seeds/voxel is the probe's
  operating point (~11 min, ~5.4 GB track). This changes the *meaning* of the
  `seed_density` preference (anisotropic, one-axis seeding); key/default/range are
  unchanged and only the "8 seeds per voxel" tooltip wording is corrected.
- **`seed_buffer_fraction = 0.7`**, fixed (REVISED 2026-09-05 from the earlier 0.1;
  probe-backed "buffer 0.7 safe"). Present in dipy 1.12's `probabilistic_tracking`
  (default `1.0`). It streams seeds in chunks and mitigates the memory spike that
  density 2 otherwise causes.
- **Possibly seed from FA rather than the WM PVE mask** — the probe decides.

### The consequence that must be decided, not discovered

`pve_wm`, `pve_gm` and `pve_csf` are consumed **only** by the tracking node
(`dipy_dti_preproc_workflow.py:357-359`). If CMC goes and seeding also moves off
the WM PVE mask, then `DipyTissueClassifier` and the three PVE registration-apply
nodes become dead: a 207.8 s / 5 GB node and its warps, removed from every run.

That is a large win and a workflow-contract change. It must be an explicit
decision with the user, taken once the probe fixes the seeding criterion — not an
incidental side effect of deleting CMC. If seeding stays PVE-based, the tissue
classifier stays and only the stopping criterion changes.

**Two open questions for the user**, to be raised rather than assumed:

- `seed_density` is an existing preference from Phase 1's gating work. Fixing it
  at 2 means either removing the preference (a persisted-key change) or forcing
  its value and leaving a dead control in the UI. Persisted preference keys are
  stable contracts; pick deliberately.
- The same applies to any preference that only made sense under CMC.

## C4 — the crop bug: use the brain-mask bbox, not the foreground bbox

`DipyTracking.py:268` computes the crop from the CSD signal:

```python
sh_signal = np.any(sh_data != 0, axis=-1)
```

The CSD shm is stored as int16 with NaN scaling, so it reads non-zero across the
**whole FOV**. The foreground bbox therefore degenerates to the full volume and
the crop becomes a no-op — which is how a 4.15 GB allocation survived a node whose
docstring says it crops.

**Fix**: derive the crop from the brain-mask bbox. This is scientifically
identical — outside the brain there are no seeds, no tissue for the stopping
criterion, and only spurious shm — and on subj1 it actually shrinks the volume to
161x192x52.

**Regression test, mandatory**: an shm array that is non-zero everywhere, plus a
brain mask covering part of the volume, must produce a crop that follows the
mask. A test that only feeds a well-behaved shm would have passed against the bug.

C1 makes this less load-bearing, since the data arrives cropped. Fix it anyway:
two independent defences against the failure that hard-rebooted the machine.

## C5 — deskull by `median_otsu`, only if an oracle says so

Proposal: replace the deskull engine on the dipy DWI path with dipy's
`median_otsu`, making the path independent of antspynet, FSL and FreeSurfer for
brain extraction.

**Gold standard: SynthStrip.** The oracle compares, on the b0/nodif of both
oracle subjects:

| Arm | What it is |
|---|---|
| SynthStrip | gold standard |
| current deskull engine | the incumbent |
| `median_otsu` | the candidate |

Report Dice, Jaccard, 95% Hausdorff distance, and false-positive / false-negative
volume against SynthStrip for both candidates — plus the practical readout, which
is whether the resulting mask changes the tractogram.

**Decision rule, to be confirmed by the user before the oracle runs**: adopt
`median_otsu` only if it is close to SynthStrip in absolute terms *and* not
materially worse than the incumbent. A proposed bar is Dice >= 0.95 against
SynthStrip and within 0.01 Dice of the current engine, but the user sets it — a
brain extraction that is 3% worse is not a fair trade for a dependency, and only
the user can price that.

`median_otsu` is a threshold-and-morphology method competing against two learned
models. It may well lose. The oracle exists because that is a real possibility,
not a formality: if it loses, the incumbent stays and C5 is closed as measured
and rejected.

SynthStrip is used **only as the oracle's gold standard**, never in the pipeline;
this does not add a FreeSurfer dependency to the dipy path.

## Note on C1 and C5

Both are `median_otsu`. They are nevertheless separate decisions: C1 uses it for
a **generous crop bounding box**, where being loose is harmless, and ships
regardless. C5 uses it as a **brain mask**, where being loose is a defect, and
ships only if the oracle approves. Do not let C5's rejection remove C1, and do not
let C1's acceptance imply C5.

## Out of scope

RecoBundles, `dipy_bundle_workflow`, the fornix split, SlicerDMRI, the `.trk`
result contract and the phantom — all Phase 2 and 3. The FSL/XTRACT path is not
touched.
