# Phantom DICOM subject generator

Generates, at run time and from scratch, a complete synthetic DICOM exam that
covers **every** `DataInputList` input of SWANe, so workflow *execution* can be
driven end to end (dcm2niix → FSL/FreeSurfer/Slicer) without any real patient
data.

Nothing is committed to the repository: the anatomy is derived at run time from
`$FREESURFER_HOME/subjects/fsaverage` (shipped with every FreeSurfer install)
and the generated DICOM is cached on disk between runs.

## Quick start

```python
from swane.tests.helpers.phantom.dataset import get_phantom_subject

subject_dir = get_phantom_subject()      # builds once, then reuses the cache
# subject_dir/dicom/<input_name>/*.dcm    -- the layout SWANe expects
```

Convert every series to NIfTI (same dcm2niix SWANe uses) for visual inspection:

```bash
python -m swane.tests.helpers.phantom.to_nifti <subject_dir> <out_dir>
```

`$FREESURFER_HOME` must be set (the anatomy comes from `fsaverage`).

## How it is built

| module            | stage                                                        |
|-------------------|--------------------------------------------------------------|
| `tissue.py`       | `fsaverage` segmentations → a tissue **class map** (real anatomical scale, cropped to the head) |
| `sequences.py`    | class map → per-modality intensity volumes (T1/FLAIR/T2/CT/PET/ASL/PC-MRA/DWI/BOLD) |
| `dicom_writer.py` | intensity volumes → DICOM series dcm2niix converts correctly  |
| `catalog.py`      | one entry per input: LUTs, geometry, timing, misalignment    |
| `dataset.py`      | orchestration, `PhantomProfile`, on-disk cache               |
| `to_nifti.py`     | dcm2niix conversion of a whole subject (dev aid / smoke check)|

Only the tissue **class codes** ever reach the sequence layer — `fsaverage`
intensities are never copied — so the phantom is fully under our control and
carries no external, licence-restricted content.

## What is deliberately baked in

- **Real contrast per modality** (WM/GM/CSF ordering, HU for CT, GM≈4×WM for
  ASL/PET, bright vessels for venous, etc.).
- **Bias field** on 3D T1w and 3D FLAIR, to exercise bias-field correction.
- **Inter-series misalignment**: every series except the `t13d` reference has
  its anatomy displaced by a few mm / degrees on an otherwise clean scanner
  grid — the "subject moved between series" case, so a registration that
  silently fails leaves a visible offset.
- **Anatomical CST**: a wide-but-centred cortico-spinal corridor following the
  true descending course (M1 → corona radiata → internal capsule → cerebral
  peduncle → pons → medulla); anisotropic in DWI (high FA there, low elsewhere).
- **Partial-coverage coronal T2** over the temporal lobes only.
- **fMRI**: two motor task runs (`rArA` and `rArBrArB`, contralateral
  activation, task/rest of different fixed lengths, dummy volumes at both ends)
  plus a resting-state run (two anatomical networks + one nuisance component).
- **Venous MR, both input shapes**: `venous_mr` is a single 2-volume series
  (anatomic + angiographic) for the one-series path; `venous_mr_split_anat` and
  `venous_mr_split_angio` carry the same two phases as separate single-volume
  series for the two-series path.  `venous_mr2` has no folder by default.
- **Venous CT**: a non-contrast `venous_ct` baseline plus `venous_ct2` /
  `venous_ct3` opacifying the sinuses on one side each, so the workflow's
  subtract-then-sum reconstruction can be checked (a dropped addend shows).

## Caching

Results live under `~/test_swane/phantom/phantom_<key>/` (override with
`$SWANE_PHANTOM_DIR`). The `<key>` hashes the generator version, the
`PhantomProfile`, and the `fsaverage` build, so retuning any parameter
transparently invalidates the cache. Pass `force=True` to rebuild.
