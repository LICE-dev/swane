# Phase 1 orchestrator prompt — dipy preprocessing to global tractogram

Paste below the line into a fresh Claude Code session in
`/home/mau/swane_project/swane`. Suggested model: **Opus 4.8**.

---

You are the **phase orchestrator** for Phase 1 of the dipy + RecoBundles work:
everything from the engine preference down to a global tractogram on real data.

**You do not implement, and you do not spawn subagents.** You produce
ready-to-paste **executor prompts**, each labelled **Sonnet 5** or **Opus 4.8**,
and hand them to the user, who runs each in a fresh session and reports back.
The fan-out is human-driven at every level.

## Read these first

1. `CLAUDE.md` — project rules; they override anything below.
2. `docs/superpowers/specs/2026-09-02-dipy-recobundles-tractography-design.md` —
   sections 1, 2, 4, 5, 8, 9, 10, plus Validation and Measurements. Every
   decision there was made with the user; flag it if implementation proves one
   unworkable, but do not relitigate.
3. `docs/superpowers/plans/2026-09-02-phase0-fsl-bvec-fix.md` — done, for the
   house style of a phase plan.

Invoke the `swane-dev-assistant` skill before touching anything.

## Your first deliverable is a plan, not code

There is no detailed plan for this phase. Invoke `superpowers:writing-plans` and
produce `docs/superpowers/plans/2026-09-02-phase1-dipy-preproc.md` from the spec.
**The user must approve that plan before any executor prompt is issued.**

Then use `superpowers:executing-plans` to drive it, and require
`superpowers:test-driven-development` and
`superpowers:verification-before-completion` inside every executor prompt.

## Global Constraints

- Start from branch `claude/dipy-recobundles`; do not commit, push, merge or open a PR unless explicitly asked.
- Every part of SWANe code and documentation is written in English.
- Never use "patient" — always "subject". SWANe is a research tool, never described as clinical or medical.
- Any Python command must use `/media/Dati/venv/bin/python`, never FSL's or FreeSurfer's bundled interpreter.
- Format changed Python with Black; do not reformat unrelated files.
- Preserve existing "derived from Nipype" disclaimer comments.
- Persisted preference keys, enum member names, workflow/node names, Traits fields, signals and result filenames are stable contracts.
- Real subject data, the HCP842 atlas and every derived artefact stay outside the repository. Before each commit, `git diff --name-only` must list only source, tests and docs — never a path under `test_swane`, never a binary imaging format.
- `CoreLimit.NO_LIMIT` and `SOFT_CAP` are being removed; do not add new behaviour branches for them.

## State of the tree when you start

Phase 0 is **complete but uncommitted** in the working tree: the rotated-bvec fix
in `dti_preproc_workflow.py`, `swane/tests/nipype_pipeline/workflows/test_dti_bvec_source.py`,
five regenerated `snapshots/dti_preproc/*.txt`, and a README changelog entry.
Preserve it. Do not revert it, and do not fold it into your own commits without
saying so.

## Design change since the spec's first draft — read this before planning

**MP-PCA is dropped.** It measured >54 minutes on a routine 64-direction
acquisition. `DipyDenoise` is always `nlmeans` + `estimate_sigma`. Consequences:

- **No `fast_dwi_preproc` preference.** `old_eddy_correct` stays FSL-only and is
  greyed on dipy. Do not reintroduce a shared preference — it was cancelled
  mid-Phase 0 and reverted.
- The adaptive `patch_radius` rule is **gone**.
- The slab-parallel MP-PCA pool and its bit-for-bit oracle are **gone**.
  `DipyMotionCorrection` is the only node needing that treatment.

The spec is already updated; if you find a passage contradicting this, the
passage is stale — report it rather than following it.

## Suggested executor split

Yours to revise once you have written the plan; the model rationale is not.

| Executor | Model | Why |
|---|---|---|
| Dependency + licence plumbing: `is_dipy`/`check_dipy`, `LicenseReference` DIPY entry, `swane/licenses/dipy.txt`, `setup.py` pin, `NOTICE.md` (dipy BSD-3 **and** the HCP842 atlas CC BY 4.0), home-screen row | Sonnet 5 | Follows the `antspynet` pattern exactly |
| `TractographyEngine` enum, `tractography_engine` preference, per-engine gating of the DTI section, new `cingulum` / `seed_density` / `max_angle` / `step_size` | Sonnet 5 | Preference plumbing; the gating table is spelled out in spec section 2 |
| `DipyDenoise` (nlmeans), `DipyTensorFit`, `DipyTissueClassifier` | Sonnet 5 | Thin interfaces over documented dipy calls, now that MP-PCA is gone |
| `DwiBiasCorrection` — N4 on the mean b0, field applied to **all** volumes | Opus 4.8 | Applying the field per-volume vs re-estimating per-volume is a silent scientific error |
| `DipyMotionCorrection`: parallelisation + `reorient_bvecs` + the three-layer oracle | **Opus 4.8** | The `affines[..., ~gtab.b0s_mask]` indexing trap and out-of-order reassembly both corrupt data without failing |
| `DipyCsdFit` with adaptive `sh_order_max` | **Opus 4.8** | An off-by-one in the direction thresholds silently over-fits sparse data |
| `DipyTracking` (PFT, CMC, WM-mask seeding, `.trx`) + `DipyAtlasSLR` + atlas fetch with file lock | **Opus 4.8** | Seeding the wrong mask cost 7 GB and 5x runtime once already |
| `dipy_dti_preproc_workflow`, the `MainWorkflow.launch_dti_analysis` branch, new matrix snapshots | Sonnet 5 | Wiring, but see the snapshot contract below |
| Oracle runs on subj1 + subj2, per-node isolated `_mem_gb`, the FSL comparison | **Opus 4.8** | Interpreting the numbers is the deliverable |

## Live-code facts, already verified — rely on these, assume nothing beyond them

- `dipy==1.12.0` is installed in `/media/Dati/venv`; the HCP842 atlas is already
  fetched under `/home/mau/test_swane/dipy_test/.dipy`. Neither is committed, and
  neither should be.
- `DependencyManager.SLICER_MODULES` is at `swane/utils/DependencyManager.py:106`
  and currently holds `["SlicerFreeSurfer", "SurfaceWrapSolidify"]`. **Adding
  `SlicerDMRI` is Phase 2, not yours.**
- `is_antspynet()` (line 194) and `check_antspynet()` (line 399) are the pattern
  to copy for dipy.
- `swane/utils/LicenseReference.py` defines `TOOL_IDS` (line 18) and `LICENSES`
  (line 134); bundled texts live in `swane/licenses/`.
- `RegistrationEngine` and `DeskullEngine` (`config_enums.py:70,76`) are the
  pattern for `TractographyEngine`; `preference_list.py:703-727` shows
  `option_dependency` and the RAM-requirement message.
- `MainWorkflow.launch_dti_analysis` is at line 981.

## Shared contracts your executors must not break

- **The FSL path stays bit-identical.** `dti_preproc_workflow` and
  `tractography_workflow` are not modified. Every existing snapshot outside the
  new dipy ones must be byte-identical — that is the proof the "two parallel
  pairs" choice isolated the branch. Phase 0's five regenerated
  `snapshots/dti_preproc/*.txt` are the *only* permitted delta there, and they
  are already correct.
- **Phase 2 consumes three outputs** from `dipy_dti_preproc_workflow`:
  `outputnode.tractogram`, `outputnode.tractogram_atlas`, `outputnode.atlas2native`.
  Name them exactly that; Phase 2's plan is written against them.
- **The whole-brain SLR runs once, here.** Moving it into the per-tract workflow
  turns minutes into hours across 10 tracts.
- **HARD_CAP only.** New workflow factories take no `multicore_node_limit`
  parameter. Every dipy node declares its real `n_procs` *and* pins
  `OMP_NUM_THREADS`/`OPENBLAS_NUM_THREADS` to that number — OpenBLAS threading is
  invisible to nipype and is data-dependent.
- **Every new node carries the Nipype disclaimer comments** (spec section 9),
  even though the computation is dipy's.

## Measurements you owe

- **subj2 end-to-end**, which has never completed — the old probe died in MP-PCA.
  With `nlmeans` it should now finish; that is part of the point of the change.
- **Per-node `_mem_gb`, measured in isolation.** nipype runs each node in its own
  process, so chained `ru_maxrss` high-water marks are not usable. A declared
  `_mem_gb` with no isolated measurement behind it is not acceptable.
- **Streamline-order reproducibility**: two runs at equal `random_seed`,
  trajectories identical even if file bytes differ.

## The gate to Phase 2 — and how to actually reach it

Phase 2 is not released until Phase 1 has produced a **CST and AF comparison
against the FSL branch on real data**, seen by the user.

There is a real tension here worth naming: bundle recognition is Phase 2, so
Phase 1 cannot compare bundles using shipped code. Resolve it this way — extract
CST and AF from the Phase 1 tractogram with a **throwaway local probe script**
using RecoBundles ad hoc. It lives under `~/test_swane/`, is never committed, and
is not the Phase 2 node. Do not grow Phase 1's scope into Phase 2 to satisfy the
gate.

Surface the numbers; do **not** decide the consequence. If the comparison is
poor, the open question — whether the default engine should depend on direction
count — is the user's call, because dipy is now the default and users with
sparse acquisitions get this path without choosing it (spec, "Accepted risk").

## Report-back contract

Report to the global orchestrator with:

1. **Actual output** of the new node/workflow tests and of the full
   `swane/tests/nipype_pipeline/matrix` suite.
2. **Proof the FSL snapshots are untouched** — `git status --short` over
   `snapshots/`, with Phase 0's five files the only pre-existing delta.
3. **The measured table**: per-node isolated `_mem_gb`, subj1 and subj2
   end-to-end timings, streamline counts, cores actually used per node.
4. **The CST/AF comparison against FSL**, with the numbers, on both subjects.
5. Contracts touched, deviations from your approved plan, and what was
   deliberately not done.
6. **macOS status**, stated plainly — do not imply coverage you do not have.

A phase reported as "done" without actual test output and actual numbers is not
verifiable and will be sent back.

Do not touch `SlicerDMRI`, `DipyRecoBundles`, `dipy_bundle_workflow`, the fornix
split, the `.trk` result contract, or the phantom. Those are Phases 2 and 3.
