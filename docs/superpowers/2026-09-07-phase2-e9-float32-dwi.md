# Phase 2 — E9: float32 DWI-chain output + RAM re-evaluation

Date: 2026-09-07
Branch: `claude/dipy-recobundles`
Task: E9 of `docs/superpowers/plans/2026-09-04-phase2-recobundles.md`

## What changed

The dipy DWI-domain nodes computed **float** results and wrote them back
through the raw dcm2niix DWI's **int16** header (no scaling slope set, so floats
were rounded to the nearest integer), quantizing every correction. Fixed by
writing **float32** on disk (affine/orientation/zooms preserved, only the data
dtype changes):

- `DipyDenoise` (nlmeans output) — `nodes/DipyDenoise.py`
- `DipyMotionCorrection` (registered volumes) — `nodes/DipyMotionCorrection.py`
- `DwiBiasCorrection` (bias-divided volumes) — `nodes/DwiBiasCorrection.py`

`DwiCrop` is deliberately **left int16**: it is a lossless spatial subset of the
raw data (no float computation), so casting it would only inflate RAM for no
precision gain. Confirmed in code (`nodes/DwiCrop.py` casts back to
`in_nii.get_data_dtype()`) and guarded by a test.

## CHANGELOG note (scientific)

**Re-running a subject processed before 2026-09-07 will NOT reproduce the old
FA / CSD / tractography numbers.** The int16 output was lossy; float32 is
faithful. The shift is the correction that was previously being discarded, not a
regression. Golden per-node dtype assertions and any downstream numeric baseline
for the dipy engine must be regenerated from a float32 run.

## Precision loss measured (Step 1) — the effect the review had not quantified

Real bias-corrected DWI (mean-b0 N4 field divided out), saved int16 (old) vs
float32 (new), reloaded, compared to the in-memory float32 the node computed.
Cropped-brain statistics, both oracle subjects:

| metric (bias output) | subj1 (15-dir) | subj2 (64-dir) |
|---|---|---|
| int16 max abs err | 0.0917 | 0.4561 |
| int16 mean abs err | 0.0456 | 0.2280 |
| voxels altered by int16 | 99.85% | 99.98% |
| float32 round-trip err (control) | 0 | 0 |
| on-disk size int16 → float32 (bias output, .nii.gz) | 33.1 → 75.6 MB (2.29×) | 44.0 → 97.6 MB (2.22×) |

Propagated to the reconstruction (int16-DWI vs float32-DWI into tensor + CSD):

| metric | subj1 | subj2 |
|---|---|---|
| FA mean abs delta (brain) | 1.04e-4 | 5.43e-5 |
| FA mean abs delta (WM, FA>0.2) | 1.41e-4 | 7.36e-5 |
| FA max abs delta (WM) | ~1* | 0.0995 |
| **shm_coeff rel-L2 (brain)** | **1.08%** | **2.87%** |
| shm_coeff max abs / mean abs | 0.130 / 2.1e-4 | 0.239 / 3.8e-4 |
| sh_order / n_coeff | 4 / 15 | 8 / 45 |

\* subj1 FA max of ~1 is a handful of degenerate near-zero-signal edge voxels
where FA is ill-defined; the mean (1e-4) is the meaningful figure. The headline
is **shm_coeff**: the SH coefficients that drive RecoBundles tractography shift
by ~1–3% in relative L2 across the brain — a real, previously-unmeasured effect.

## RAM + wall-time impact (Step 3) — isolated tree-peak, one node per process

int16 vs float32 DWI, `num_threads=4`, cropped brain, both subjects:

| node | subj1 int16 | subj1 f32 | subj2 int16 | subj2 f32 |
|---|---|---|---|---|
| denoise | 0.522 GB / 25.0 s | 0.522 / 25.7 | 0.661 / 34.6 | 0.660 / 34.3 |
| bias | 0.497 / 18.0 | 0.497 / 18.0 | 0.503 / 12.3 | 0.504 / 12.7 |
| tensorfit | 0.506 / 26.7 | 0.503 / 26.9 | 0.648 / 12.0 | 0.639 / 12.5 |
| csd | 1.550 / 233 | 1.535 / 225 | 1.561 / 100 | 1.629 / 101 |

**RAM delta int16 → float32 ≈ 0.** Every node loads the DWI via `get_fdata()` →
float64 in memory *regardless* of the on-disk dtype, so the reservation-relevant
working set is dtype-independent. The only measurable delta is CSD subj2
+0.068 GB (+4%), which is exactly the +2 B/(voxel × volume) float32 load
transient (4 B float32 raw vs 2 B int16, alongside the float64 copy): 30 M
voxel·vol × 2 B = 0.06 GB, matching the measurement. Wall-time delta is noise.

## Follow-on (user decision, 2026-09-07): load all volume nodes as float32

Rationale (user): if the output is float32, computing/saving in float64 wastes
RAM and time only to approximate at save. Applied to the volume nodes still on
`get_fdata()`'s float64 default — **DipyDenoise, DipyTensorFit, DipyCsdFit** now
`get_fdata(dtype=np.float32)`. (DwiCrop, DwiBiasCorrection and DipyTracking
already loaded float32.)

Scientific effect: **tensor and CSD upcast to float64 internally**, so float32
input is lossless (FA delta ~7e-7, shm_coeff rel-L2 ~1.6e-8) — far below the
int16 loss this task removes. **nlmeans (denoise) computes in the input dtype**,
so float32 there is a genuine but small change (denoised-DWI mean abs 0.0125 vs
the float64 path), still an order of magnitude under the int16 quantization.

RAM/time saving (isolated tree-peak, subj2 65-vol crop, float64-load vs
float32-load):

| node | float64 load | float32 load | RAM saved | wall |
|---|---|---|---|---|
| denoise | 0.621 GB | 0.395 GB | −36% | 55→46 s (−16%) |
| tensorfit | 0.638 GB | 0.454 GB | −29% | flat |
| csd | 0.556 GB | 0.446 GB | −20% | flat |

**Excluded (hard constraints, not omissions):**
- `DipyTissueClassifier` — dipy's HMRF is a typed-`double` Cython kernel
  (`segment/mrf.pyx`); float32 raises `Buffer dtype mismatch, expected 'double'`.
  Stays float64.
- `DipyMotionCorrection` — dipy's `motion_correction` controls the internal load
  dtype; forcing float32 on only the parallel path would break the
  serial-vs-parallel bit-for-bit oracle. Stays float64.
- Streamline nodes (`DipyAtlasSLR`, RecoBundles build/recognize, chunker, union,
  to-ref, fornix) — no `get_fdata` volume loads; streamlines are float32 in
  `.trx` already; dipy's registration/clustering upcast internally as needed.

## Estimator recalibration

- `DipyCsdRamEstimator.DATA_BYTES_PER_VOXEL_VOLUME`: **10 → 8** — with the
  float32 load the input buffer is 4 B resident (was float64 8 B) plus a
  same-size raw copy during the load; 8 bounds both. (This supersedes the interim
  int16→float32 value of 12, which had assumed a float64 load.) Confirmed: the
  float32 load dropped CSD's serial peak by exactly the 4 B/(voxel×volume) this
  reflects (subj2: 0.556 → 0.446 GB). The dominant term — the per-voxel output
  copies (float64 SH, unchanged) — keeps the estimate conservative at the serial
  and 4-worker rungs.
- `DipyMotionRamEstimator` (32 B/voxel·vol): **unchanged, stays conservative.**
  The float32 save buffer replaces the old int16 one (was float32→int16 dual
  buffer at save; now float32 only), adding no peak. Motion still loads float64
  (dipy-controlled). Fit was 26–28 B; 32 keeps margin.
- Static `_MEM_GB["denoise"|"bias"|"tensorfit"]` (all 1 GB): **unchanged and
  still conservative.** Float32 load lowers them (0.40–0.45 GB), well under 1 GB.
- `DipyTrackingRamEstimator`: **unaffected.** `DipyTracking` consumes `shm_coeff`
  (SH, already float32 since Phase-1bis), `pve_wm`, `nodif_brain` — never the DWI.
- `DipyTissueRamEstimator`: unaffected (T1 input, float64 by dipy constraint).

## Floor input

**Does not rise; it falls slightly.** The write change is memory-neutral and the
float32 load lowers every reconstruction node's peak (−20 to −36%). The 8 GB
floor stands until the final joint re-derivation, which now has more headroom.

## Snapshots / tests

- Dipy matrix snapshot **unchanged** (graph and static `_mem_gb` untouched; the
  snapshot carries no dtype assertion) — `test_dipy_dti_matrix.py` passes as is.
- Motion serial-vs-parallel oracle stays **bit-for-bit** (both paths save the
  same float32 buffer; the comparison reads `get_fdata()`, dtype-agnostic).

## Downstream headers — resolved transitively (verified 2026-09-07)

`DipyCsdFit`, `DipyTensorFit` and `DipyTissueClassifier` save their outputs
(`shm_coeff`, FA, PVE) by reusing **their input image's header** (`in_nii.header`).
That was the concern (int16 inheritance), but it is resolved by fixing the
source rather than each consumer:

- `DipyCsdFit` and `DipyTensorFit` take the **bias output** as `in_file`
  (`dipy_dti_preproc_workflow.py:430`), which E9 made float32 — so their reused
  header is float32 and `shm_coeff`/FA are written **float32**. Verified: with a
  float32 input the node emits float32 shm (`out_csd_f32_shm.nii.gz`), with an
  int16 input it emits int16 — and production feeds it the float32 bias output.
- `DipyTissueClassifier` takes the T1 `reference_brain`, which comes from deskull
  as **float32** already; existing PVE maps are float32 and graded (400k+ unique
  values in [0,1]), not quantized.

So no separate fix is needed: making the DWI chain float32 propagates to every
downstream node that inherits its input's header. The 1–3% shm_coeff delta above
is the genuine reconstruction improvement, and it now reaches disk in float32.
