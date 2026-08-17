# Pre-release execution sweep

Runs the **real** SWANe workflows — dcm2niix, FSL, FreeSurfer, Slicer — over a
synthetic phantom exam, across the same configuration matrix that
`../nipype_pipeline/matrix/` only covers at *construction* time, and then checks
the results automatically.

It answers the question the snapshot matrix cannot: *does SWANe still produce
correct output for every supported combination of settings?*

```bash
python -m swane.tests.prerelease --cores 8 --ram 10
```

No DICOM is committed and none is needed: the phantom exam is generated on the
machine that runs the sweep, and cached between runs.

## How it is organised

| module | role |
|---|---|
| `capabilities.py` | probes the host: FSL, FreeSurfer (+Matlab, +Synth), Slicer, dcm2niix, CUDA, XTRACT protocols, MNI templates, and the RAM each Synth tool needs |
| `plan.py` | the configuration axes, and the passes that cover them |
| `subject.py` | builds one SWANe subject per pass from the cached phantom |
| `runner.py` | executes the passes sequentially, resumably |
| `checks.py` | decides whether a pass actually succeeded |
| `report.py` | writes the JSON and HTML reports |

## Why passes, and why so few

One **pass** is one complete `MainWorkflow` execution. A pass cannot cover two
values of the same axis — a run has a single `freesurfer_step`, a single Synth
backend — so several runs are unavoidable. But a pass *does* exercise every
input it loads at once, and axes on different inputs are independent, so the
~50 construction scenarios collapse to **16 executions**, not 50:

* **axes on different inputs are swept in parallel** inside a pass (the
  resting-state MELODIC dimensionality is unrelated to the vein detection
  mode, so they differ in the same run);
* **each pass declares which inputs it loads**, so the diffusion passes do not
  re-run the slow, already-covered fMRI chain.

The passes are written out explicitly in `plan.py` so they can be read and
reviewed. Completeness is not left to that reading: `coverage()` walks every
axis value and reports anything no pass exercises. It separates three cases
that must never look alike:

* **unreachable** — the host cannot run it (missing GPU, not enough RAM for
  SynthMorph, no Slicer), reported with the reason;
* **deferred** — a pass covers it but was skipped this run (the opt-in
  recon-all passes);
* **missing** — no pass covers it anywhere. This is a bug in the plan, and the
  only case that fails the sweep.

## What the checks verify

"The workflow finished" is a weak claim: a registration can silently leave a
series where it started, a skull strip can return the whole head, a tensor fit
can produce a field of NaN — and all of those still write a file and exit zero.
So the checks are layered:

1. **execution** — no node failed, no crash file, every loaded input produced
   at least one result;
2. **integrity** — each result loads, is finite, is not a constant image, and
   the registered results sit on the reference grid;
3. **plausibility** — the result matches the anatomy the phantom actually
   contains: the reference brain is where the phantom's brain is, registration
   removed the known few-millimetre inter-series offset, FA is in range and its
   anisotropy concentrates in the phantom's corticospinal corridor, detected
   veins land on the phantom's sinuses.

Layer 3 is possible because we generate the data: the ground truth comes from
the *same* `build_tissue_model()` call that drew the phantom, so the reference
cannot drift from what was rendered. Comparisons are done as centres of mass in
RAS millimetres, so nothing has to be resampled to be judged.

### What the phantom makes checkable — and what is still missing

SWANe performs two different registrations, and the phantom lets us grade the
quality of **both** quantitatively — not by eye.

**Linear, series → reference (T13D).** The phantom displaces every series except
the reference by a small **rigid** pose (rotations ~0.5–1.3°, translations
~0.7–1.7 mm), fixed per series, applied to the *content* on an otherwise clean
scanner grid; the header does not move with it, so header-based alignment cannot
fake the result. The target here is the subject's *own* T13D in subject space —
no atlas is involved — and because the deformation below is identical across
series, series and reference differ only by that known pose. Two checks:

* `registration.<input>` — the series' centre of mass moves closer to the
  reference after registration than before (modality bias cancels in the
  before/after difference);
* `registration.overlap.<input>` — the registered brain mask actually coincides
  with the reference brain mask (Dice ~0.97 measured; gate 0.90). This is the
  goodness measure: a gross misregistration drops a brain-sized Dice well below
  the gate.

**Non-linear, subject → atlas.** A *fixed*, smooth, low-frequency deformation is
applied to the anatomy **before** the per-series rigid pose (see
`helpers/phantom/deformation.py`, generator version 5):

* applied before the pose and identical across series, it leaves the
  inter-series relationship rigid — a real scanner (the reference brain centre
  barely moves, ~0.2 mm, while local features move a few mm: precentral ~3.5 mm,
  venous sinus ~2.7 mm);
* it makes the subject differ non-linearly **from the atlas**, giving real work
  to the subject→MNI / →symmetric paths (`nonlinear_reg`, FLAT1, the asymmetry
  index). DTI tractography no longer computes its own MNI→ref warp — it reuses
  the FLAT1/`mni1` one (built whenever FLAT1 or tractography is requested), so
  it rides on the same check rather than adding a separate path;
* it is a closed-form sum of sinusoids we generate ourselves, known exactly
  (`deformation.displacement`) and diffeomorphic. It derives nothing from FSL,
  its atlases, or XTRACT, and `build_tissue_model` applies it by default so the
  generator and the ground-truth checks build the *same* deformed subject.

Its quality is graded by:

* `nonlinear.warp_present` / `nonlinear.warp_nontrivial` — FNIRT wrote a forward
  transform and invwarp a real inverse field, whose displacement is finite and
  of sane magnitude (a degenerate FNIRT gives ~0, a diverged one tens of mm);
* `nonlinear.target_alignment.<space>` — the warped subject that SWANe writes
  into the target space is compared against the **real target**, read at run
  time from `$FSLDIR` (MNI152) or `swane_supplement` (the symmetric template).
  Measured against the real MNI152 1 mm brain: Dice 0.94, intensity NCC 0.78
  (gates 0.85 / 0.5). Reading the target to score the result is licence-clean —
  the tools are run and their output inspected; no atlas image or code is copied
  into the repo.

The one thing left to the human is *absolute* anatomical correctness of the
atlas registration beyond overlap and intensity agreement; everything the
automated checks cover is graded from measured margins, not eyeballed.

## Running it

### Requirements

The blocking ones — without these nothing runs — are FSL, dcm2niix, and
`$FREESURFER_HOME/subjects/fsaverage` (the phantom anatomy). Everything else
degrades gracefully: a missing capability drops the axes that need it, with the
reason recorded in the report.

`$FREESURFER_HOME` must be set even when FreeSurfer passes are not requested,
because the phantom is built from `fsaverage`.

### Commands

```bash
# what would run here, and what this host cannot do (runs nothing)
python -m swane.tests.prerelease --dry-run
```

```bash
# the default sweep
python -m swane.tests.prerelease --cores 8 --ram 10
```

```bash
# include the slow FreeSurfer passes (hours each)
python -m swane.tests.prerelease --cores 8 --ram 10 --with-reconall
```

```bash
# a single pass (see --list for the names)
python -m swane.tests.prerelease --only dti_tractography --cores 8 --ram 10
```

```bash
# re-run the checks over results already on disk, without re-running anything
python -m swane.tests.prerelease --checks-only
```

`--cores` and `--ram` are handed to the `MonitoredMultiProcPlugin` exactly as
the application does it, through the global preferences. Pick a RAM budget the
machine actually has: the Synth tools have hard floors (SynthStrip 5 GB,
SynthMorph/SynthSeg 14 GB, Synth recon-all 20 GB on Linux) and passes needing
more than the budget are skipped rather than left to be OOM-killed.

### Resuming

A full sweep takes hours. Progress is saved after every pass, so re-running the
same command continues where it stopped. `--retry-failed` re-runs the passes
that failed; `--no-resume` starts over.

## Inspecting the outcome

Everything lands in the work directory (default `~/test_swane/prerelease`):

```
prerelease/
├── prerelease_report.html    # read this
├── prerelease_report.json    # diff this between releases
├── prerelease_state.json     # resume state
└── <pass_name>/              # one SWANe subject per pass
    ├── dicom/                # symlinks into the cached phantom
    ├── results/              # what the workflows produced
    ├── log/                  # pypeline.log, crash files, resource monitor
    └── pass_result.json
```

The HTML report lists every pass with its settings, its checks and the path to
its results, so anything suspicious can be opened directly in a viewer. The
exit status is 0 only when every pass ran, every error-level check passed, and
the plan had no coverage holes.
