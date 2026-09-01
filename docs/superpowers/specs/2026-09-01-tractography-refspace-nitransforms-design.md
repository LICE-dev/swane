# Tractography in reference space with nitransforms affine conversion

- **Date:** 2026-09-01
- **Branch:** `enh-tractography-refspace-nitransforms` (from `dev`)
- **Status:** Design approved; PoC validated. Ready for implementation planning.

## Problem

Commit `34890d2` ("externalize probtrackx transforms; tractography runs in
diffusion space, results warped back to ref") changed how probtrackx handles
the diffusion↔reference coordinate mapping, to support the ANTs registration
engine. As a side effect it degraded spatial fidelity of the extracted tracts
for **every** engine, including FSL.

### Root cause (confirmed by evidence)

Before the change, probtrackx tracked and accumulated the streamline density
directly in high-resolution **reference** space:

- `--seed`/`--waypoints`/`--avoid` in reference space (T1, 1.5 mm),
  `--seedref=ref_brain`, and the diffusion↔reference affine handed to
  probtrackx as FSL `.mat` via `--xfm` (ref→diff) / `--invxfm` (diff→ref).
- probtrackx converted coordinates continuously (sub-voxel) between spaces;
  `fdt_paths` was accumulated on the 1.5 mm grid.

After the change, probtrackx runs natively in **diffusion** space (3 mm):

- ROIs pre-resampled MNI→ref→diff in two nearest-neighbour steps,
  `--seedref=nodif_brain` (3 mm), identity transform, and the resulting
  density (3 mm) is warped back diff→ref with `flirt -applyxfm` at the
  default **trilinear** interpolation.

Consequences producing "fatter" tracts (measured on the prerelease dataset,
`r-cst_lh`, both in 1.5 mm reference space):

| run | non-zero voxels | values |
|-----|-----------------|--------|
| OLD (ref-space tracking) | 7 274 | integer counts (max 40) |
| NEW FSL (diff-space + trilinear upsample) | 13 993 | interpolated floats (max 14.0) |
| NEW ANTs (same) | 14 032 | interpolated floats |

The footprint roughly doubled and integer streamline counts became
interpolated floats. Drivers: (a) tracking/accumulation on the coarse 3 mm
grid, and (b) trilinear upsampling of the density 3 mm→1.5 mm. The waytotal
also changed materially (e.g. lh 261→35) because ROIs are quantized onto the
3 mm grid, but that is a separate effect, not the visual fattening.

The reason the transform was externalized: probtrackx `--xfm`/`--invxfm`
accept only a single **FSL** transform (a FLIRT `.mat` or a FNIRT warp).
ANTs produces an ordered transform **list** with per-transform invert flags
(ITK convention), which has no representation that fits probtrackx's single
FSL slot. So the fix must give probtrackx an FSL `.mat` for the diff↔ref
affine on every engine.

## Goal

Restore reference-space tracking (OLD fidelity) for **all** engines, by
handing probtrackx the diff↔ref affine as an FSL `.mat` again. The
non-linear MNI→ref step stays externalized onto the ROIs (it already is, in
the NEW code, and is engine-aware). Only the linear diff↔ref step is reverted
to run inside probtrackx.

Enabling fact: `dif2ref` is `non_linear=False` on every engine
(`dti_preproc_workflow.py`), so diff↔ref is always a **single affine** —
convertible to FSL. This is not true only for FSL/Synth; it holds for ANTs
too (a single `0GenericAffine.mat`).

## Non-goals

- No change to the MNI→ref non-linear warp handling (kept externalized,
  engine-aware, applied to the ROIs — nodes `seed_2_ref`, `targets_2_ref`,
  `exclude_2_ref`, `stop_2_ref`).
- No new registration algorithm; we only convert the existing affine.
- No attempt to keep an optional diffusion-space tracking mode (YAGNI).

## Design

### Dependency: `nitransforms`

Add `nitransforms` (>= 25.1.0) as a runtime dependency. It reads/writes
AFNI, FSL, FreeSurfer (LTA), ITK/ANTs and SPM affine formats in pure Python.
Its core deps (numpy ≥2.0, scipy ≥1.10, nibabel ≥5.1.1, h5py ≥3.11) are all
already satisfied in the SWANe environment, so it adds no new transitive
weight. It replaces the FreeSurfer `lta_convert` bridge used by the OLD synth
path, which matters because FSL and FreeSurfer must both become **optional**
dependencies long-term.

### New node: `AffineToFSL`

`swane/nipype_pipeline/nodes/AffineToFSL.py` — a nipype interface wrapping
nitransforms.

- **Inputs:**
  - `in_transform` (File): the diff→ref affine (ITK `.mat` for ANTs, LTA for
    synth). FSL engine does not use this node.
  - `in_fmt` (Str): source format for nitransforms (`"itk"` or `"fs"`/`"lta"`).
  - `source_file` (File): moving image of the registration (b0 / `nodif_brain`).
  - `reference_file` (File): fixed image of the registration (`ref_brain`).
  - `out_file` (Str): forward FSL matrix filename (diff→ref).
  - `out_file_inverse` (Str): inverse FSL matrix filename (ref→diff).
- **Behaviour:** `nitransforms.linear.load(in_transform, fmt=in_fmt,
  reference=reference_file, moving=source_file)`, then
  `.to_filename(out_file, fmt="fsl", moving=source_file)` for diff→ref, and
  the numpy inverse of the resulting 4×4 for ref→diff (FSL matrices invert as
  plain 4×4). Emitting both from one node keeps the two directions consistent
  and avoids a second tool.
- **Outputs:** `out_fsl` (diff→ref), `out_fsl_inverse` (ref→diff).

Validated in the PoC: the converted ref→diff matrix reproduces ANTs' own
resampling of the seed (Dice = 1.0000 against the ANTs-applied
`seed_2_diff`), and probtrackx run in reference space with these matrices
produced a thin tract (8 410 non-zero voxels vs 14 032 for the fat ANTs
baseline, integer counts, native 1.5 mm).

### `dti_preproc_workflow.py`

`dif2ref` stays `non_linear=False`. Produce FSL `diff2ref_mat` / `ref2diff_mat`
on the outputnode, per engine:

- **FSL** → passthrough of the FLIRT `.mat` and its inverse (as the OLD
  `else` branch: `dif2ref.warp` / `dif2ref.inv_warp`).
- **Synth** → `AffineToFSL` with `in_fmt="fs"` on the synth LTA transform
  (replaces the two OLD `LTAConvert` nodes).
- **ANTs** → `AffineToFSL` with `in_fmt="itk"` on `0GenericAffine.mat`.

Outputnode change: replace the tractography-facing fields
`diff2ref_transforms`, `diff2ref_which_to_invert`, `ref2diff_transforms`,
`ref2diff_which_to_invert` with `diff2ref_mat` and `ref2diff_mat` (FSL).
Verified that these four transform-list fields are consumed **only** by
tractography (via MainWorkflow); `fa_2_ref` uses `dif2ref.warp` internally,
and the other workflows (fMRI, venous, nonlinear_reg) carry their own
transform-list plumbing, unaffected. `nodif_brain` output stays (still sunk /
used elsewhere) but is no longer needed as a tractography input.

### `tractography_workflow.py`

Revert the diff-space externalization added in `34890d2`:

- **Remove** `seed_2_diff`, `targets_2_diff`, `exclude_2_diff`, `stop_2_diff`,
  `sum_2_ref`, and the `apply_diff_transform` helper / `ref2diff` /
  `diff2ref` wrappers.
- **Keep** `seed_2_ref`, `targets_2_ref`, `exclude_2_ref`, `stop_2_ref`
  (MNI→ref non-linear, engine-aware — unchanged from NEW).
- probtrackx: restore `CustomProbTrackX2` (adds `use_gpu`, `--rseed` int,
  `--sampvox` float). Wire `seed_ref=reference_brain`, `seed=seed_2_ref`,
  `waypoints/avoid/stop=*_2_ref`, `xfm=ref2diff_mat`, `inv_xfm=diff2ref_mat`.
  `fdt_paths` is produced in reference space; `sumTrack_*` connects directly
  to `outputnode.fdt_paths_*` (no final diff→ref warp).
- inputnode: drop `nodif_brain`, `diff2ref_transforms`,
  `diff2ref_which_to_invert`, `ref2diff_transforms`,
  `ref2diff_which_to_invert`; add `diff2ref_mat`, `ref2diff_mat`. Keep
  `reference_brain`, `mask`, `fsamples`, `phsamples`, `thsamples`,
  `mni2ref_warp`.

### `MainWorkflow.py`

Rewire the dti_preproc → tractography connections: keep `reference_brain`,
`mask`, `fsamples`, `phsamples`, `thsamples`, `mni2ref_warp`; remove the
`nodif_brain` and four transform-list connections; add `diff2ref_mat` /
`ref2diff_mat`.

## Data flow (per side, after change)

```
MNI seed/target/exclude ROI
  → *_2_ref (engine-aware non-linear warp, ref space)      [kept]
  → CustomProbTrackX2  (seed_ref = ref_brain,
                        xfm = ref2diff_mat, inv_xfm = diff2ref_mat,
                        samples in diffusion space)
  → fdt_paths in reference space (1.5 mm, integer counts)
  → SumMultiTracks → outputnode.fdt_paths_<side>

dif2ref (affine, engine-specific)
  → FSL:   FLIRT .mat + inverse            → diff2ref_mat / ref2diff_mat
  → Synth: AffineToFSL(fs)                 → diff2ref_mat / ref2diff_mat
  → ANTs:  AffineToFSL(itk)                → diff2ref_mat / ref2diff_mat
```

## Testing

1. **AffineToFSL unit test** — convert a known ITK affine + geometry, assert
   the FSL matrix matches an independently computed reference (and that the
   inverse round-trips). Reuse the PoC's Dice-against-ANTs check as an
   integration-style assertion where feasible.
2. **Matrix tests** — update `test_dti_matrix` and `test_tractography_matrix`
   for the new node graph (removed `*_2_diff` / `sum_2_ref`, restored
   `CustomProbTrackX2`, new `AffineToFSL`, new outputnode fields).
3. **Prerelease re-run** — re-run `dti_tractography` (FSL) and
   `dti_tractography_ants` and confirm tract footprints return to the OLD
   thin range (integer counts, native reference resolution), not the fat
   diff-space output.

## Trade-offs

- Reintroduces a small per-engine branch in `dti_preproc` (FSL passthrough vs
  `AffineToFSL`) that the externalization had unified. Localized to the
  `AffineToFSL` node and justified by the fidelity recovery.
- Adds a direct dependency on `nitransforms`, a small but reputably
  maintained nipy/NiPreps project. Accepted: it removes the FreeSurfer
  `lta_convert` dependency and provides correctness-tested conversions across
  formats, aligning with making FSL/FreeSurfer optional long-term.

## Risks / open items

- Confirm nitransforms LTA (synth) conversion is as exact as the ITK path
  (PoC validated ITK; validate LTA during implementation).
- Confirm no other consumer relies on the removed dti_preproc outputnode
  transform-list fields (grep verified: only tractography).
- `CustomProbTrackX2.use_gpu` path unchanged; CUDA remains unusable on the
  current dev machine (driver), so GPU is not exercised here.
