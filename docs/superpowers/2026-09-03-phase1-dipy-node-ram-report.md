# Phase 1 · dipy nodes — RAM report & regressors (for a future RAM estimator)

Date: 2026-09-03 · Branch: `claude/dipy-recobundles` · Machine: **4 cores, 11 GB RAM, no GPU** (linux).

Purpose: record the measured RAM of every new dipy node **together with the
input-size regressors that drive it**, so a future per-node RAM estimator (the way
SWANe/nipype size FNIRT, SynthSeg, etc.) can be fit instead of the current fixed
`_mem_gb` reservations. All measurements are isolated tree-peak RSS (parent + all
spawned workers) with each node run alone in its own process — the honest figure
for nipype's per-node scheduling. Throwaway harness under `~/test_swane/dipy_test/`;
nothing subject-derived is committed (these are aggregate resource + acquisition
numbers only).

> **macOS is NOT measured** (no macOS box here). Every figure below is linux, 4
> cores. The reservations and the 8 GB floor carry the same value on macOS pending
> a real measurement there.

## Oracle subjects — input-size regressors

| regressor | subj1 | subj2 |
|---|---|---|
| DWI dims | 256×256×52×16 | 144×144×60×65 |
| DWI spatial voxels | 3,407,872 | 1,244,160 |
| DWI 4D samples (vox×vol) | 54.5 M | 80.9 M |
| voxel size mm | 0.94×0.94×2.5 | 1.56×1.56×2.2 |
| directions / volumes | 15 / 16 | 64 / 65 |
| CSD `sh_order_max` (SH coeffs) | 4 (15) | 8 (45) |
| T1 reference dims | 224×256×170 | 320×320×200 |
| T1 voxels | 9,748,480 | 20,480,000 |
| tractogram streamlines (density=2) | 409,155 | 34,818 |

The two subjects deliberately straddle the regime boundary: subj1 has the larger
DWI FOV and T1 is smaller; subj2 has the larger 4D (more directions) and a much
larger T1. That opposition is what lets each node's dominant regressor show.

## Per-node RAM (isolated, 4 cores)

Tree-peak RSS in GB; wall in s; `avg_cores = CPU-seconds / wall` (getrusage
self+children). `reserv` is the committed integer `_mem_gb` (max across subjects,
rounded to the nearest GB, min 1).

| node | subj1 GB | subj1 s | subj2 GB | subj2 s | avg_cores | max GB | reserv | dominant regressor |
|---|---|---|---|---|---|---|---|---|
| DipyDenoise (nlmeans) | 1.11 | 52.7 | 1.37 | 72.8 | parallel¹ | 1.37 | 1 | DWI 4D samples |
| DipyMotionCorrection (pool) | 7.11 | 655.9 | 8.44 | 1251.3 | **3.88**² | 8.44 | **8** | 4D samples × #workers |
| DwiBiasCorrection (N4) | 0.85 | 31.9 | 0.99 | 17.8 | ~1¹ | 0.99 | 1 | DWI 4D samples |
| DipyTensorFit | 0.89 | 23.2 | 1.16 | 11.2 | ~1¹ | 1.16 | 1 | DWI 4D samples |
| DipyCsdFit (peaks_from_model) | 3.57 | 196.7 | 3.05 | 92.3 | 3.32 | 3.57 | 4 | DWI spatial voxels |
| DipyTissueClassifier (HMRF/T1) | 2.58 | 207.8 | 5.17 | 489.1 | 1.0 | 5.17 | 5 | **T1 voxels** |
| AffineToRAS | 0.11 | 1.1 | 0.11 | 1.3 | 0.55 | 0.11 | 1³ | none (trivial) |
| DipyTracking (cropped prob+CMC) | 5.09 | 783.6 | 2.04 | 182.0 | 3.48 | 5.09 | 5 | streamlines + cropped SH |
| DipyAtlasSLR | 4.75 | 58.6 | 0.98 | 20.0 | 2.15 | 4.75 | 5 | **streamline count** |

¹ subj2 denoise/motion/bias/tensorfit predate the cores instrumentation; cores
there are from the motion probe (2) or the node design (bias/tensorfit run at
`n_procs`≈1 in the workflow). ² motion pool avg_cores measured separately (see
below). ³ AffineToRAS rounds to 0; kept at a 1 GB minimum reservation.

## Provisional regressor slopes (2 points — seed for a real fit)

Two subjects give a line, not a fit; these are the *starting coefficients* for an
estimator to refine with more data. `Mvox` = million voxels, `Msamp` = million 4D
samples, `kstrl` = thousand streamlines.

| node | provisional model | note |
|---|---|---|
| DipyTissueClassifier | `GB ≈ 0.24·T1_Mvox + 0.2` | cleanest linear (0.24 GB/Mvox both subjects) |
| DipyAtlasSLR | `GB ≈ 0.0101·kstrl + 0.63` | RAM is the streamline set held for SLR |
| DipyTracking | `GB ≈ 0.0082·kstrl + 1.76` | +baseline from the cropped SH array (FOV×coeffs) |
| DipyCsdFit | `GB ≈ 0.24·DWI_spatial_Mvox + 2.75` | peaks_from_model scales with spatial voxels, not coeffs |
| DipyMotionCorrection | `GB ≈ 0.05·DWI_Msamp + 4.4` (4 workers) | intercept ≈ 4-worker registration replication |
| DipyDenoise | `GB ≈ 0.01·DWI_Msamp + 0.6` | nlmeans over the 4D block |

## Motion parallelization — the RAM ceiling explained

DipyMotionCorrection is the whole path's RAM ceiling (8.44 GB). Its two paths were
compared on subj2 (64-dir) to understand the tradeoff:

| motion path | avg_cores | peak RAM | speed |
|---|---|---|---|
| dipy serial + `OPENBLAS_NUM_THREADS=4` (intrinsic) | **1.01** | 0.91 GB | 35 s/vol (~38 min/65 vols) |
| our process pool (`parallel=True`, 4 workers) | **3.88** | 8.48 GB | ~16–21 min |

dipy's `motion_correction` is a serial `for` loop over volumes (no thread arg); its
only intrinsic parallelism is OpenBLAS inside each `affine_registration`, which
**does not engage** here (1.01 cores). The process pool is what delivers multicore
(3.88), at ~9× the RAM (one full registration replicated per worker). Decision
(user): keep the pool, reserve `motion` at 8 GB, floor the engine at 8 GB.

## All tracking/save RAM probes (subj1, `tracking_mem.jsonl`)

Every RAM figure gathered while arriving at the cropped streaming node:

| variant | density | streamlines | peak GB |
|---|---|---|---|
| pft + CMC, materialise .trx (uncropped) | 1 | 338,671 | 9.82 |
| pft + CMC, brain-bbox crop | 1 | 339,309 | 7.87 |
| prob + binary-WM, cropped | 1 | 59,772 | 0.91 |
| prob + CMC, cropped | 1 | 79,360 | 1.17 |
| prob + CMC, cropped, streaming smoke | 1 | 12,703 | 5.40 |
| prob + CMC, cropped, streaming | 2 | 623,794 | 4.80 |
| **prob + CMC, shipped node (crop+stream)** | 2 | 409,155 (subj1) | **5.09** |

The shipped node's 5.09 GB (subj1) is the cropped prob+CMC streaming path; the
uncropped full-FOV path was ~7 GB and hard-froze this box (see the crop findings).

## Reservations & floor

Committed integer `_mem_gb` (max across subjects, nearest GB): denoise 1, motion 8,
bias 1, tensorfit 1, csd 4, tissue 5, ras 1, tracking 5, slr 5. RAM floor for
`tractography_engine = DIPY_RECOBUNDLES`: **8 GB** (`ResourceManager.
dipy_tractography_ram_requirements`), set from the motion ceiling. On an 8 GB box
the subject RAM allocation must be raised to 8 GB to enable the engine; motion's
8.44 GB measured peak is 0.44 GB above that, a known tight fit recorded here.

The floor is not only advisory: nipype's MultiProc `_prerun_check` **hard-raises**
`RuntimeError("Insufficient resources available for job")` if any node's `_mem_gb`
exceeds the plugin `memory_gb` (= the subject `ram_gb`). With `motion._mem_gb = 8`,
the whole workflow refuses to start unless `ram_gb >= 8` — so the 8 GB floor is
exactly the minimum at which the graph can schedule, confirmed by a full end-to-end
run failing at `ram_gb = 7.5` and proceeding at 8.
