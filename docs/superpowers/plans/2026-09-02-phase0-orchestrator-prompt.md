# Phase 0 orchestrator prompt — FSL rotated-bvec fix

Paste everything below the line into a fresh Claude Code session in
`/home/mau/swane_project/swane`. Suggested model: **Opus 4.8** — one task in this
phase is a scientific correction to a validated pipeline.

Report the result back to the global orchestrator session when done.

---

You are the **phase orchestrator** for Phase 0 of the dipy + RecoBundles work:
the FSL rotated-bvec fix and the `old_eddy_correct` → `fast_dwi_preproc`
replacement. You do not implement — you dispatch executors and verify their work.

## Read these first, in this order

1. `CLAUDE.md` — project rules. They override anything below.
2. `docs/superpowers/plans/2026-09-02-phase0-fsl-bvec-fix.md` — your plan. It is
   already detailed and approved; do **not** invoke `superpowers:writing-plans`
   to rewrite it. Amend it only as described under "Required plan amendment".
3. `docs/superpowers/specs/2026-09-02-dipy-recobundles-tractography-design.md`,
   sections 2 and 12 — the reasoning behind this phase. Read for context; do not
   relitigate settled decisions.

Invoke the `swane-dev-assistant` skill before touching anything. Use
`superpowers:subagent-driven-development` to run the plan task-by-task,
`superpowers:test-driven-development` inside every executor (test first, watch it
fail, then implement), and `superpowers:verification-before-completion` before
you report anything as done.

## Global Constraints

*(carried verbatim from the plan)*

- Start from branch `claude/dipy-recobundles`; do not commit, push, merge or open a PR unless explicitly asked.
- Every part of SWANe code and documentation is written in English.
- Never use "patient" — always "subject". SWANe is a research tool, never described as clinical or medical.
- Any Python command must use `/media/Dati/venv/bin/python`, never FSL's or FreeSurfer's bundled interpreter.
- Format changed Python with Black; do not reformat unrelated files.
- Preserve existing "derived from Nipype" disclaimer comments.
- Persisted preference keys, enum member names, workflow/node names, Traits fields, signals and result filenames are stable contracts.
- Real subject data, the HCP842 atlas and every derived artefact stay outside the repository. Before each commit, `git diff --name-only` must list only source, tests and docs — never a path under `test_swane`, never a binary imaging format.
- `CoreLimit.NO_LIMIT` and `SOFT_CAP` are being removed; do not add new behaviour branches for them.

Note on the last constraint: `test_dti_matrix.py`'s scenario tuples and
`dti_preproc_workflow`'s existing `bedpostx` branch still *reference* `SOFT_CAP`.
Leave them alone. "Do not add new branches" is not "remove the existing ones" —
that removal is its own future work and is out of scope here.

## Required plan amendment — do this before dispatching Task 1

The plan's File Structure table is **incomplete**. It lists four consumers of
`old_eddy_correct`; the live tree has six. Verified by the global orchestrator:

```
swane/config/preference_list.py:383                     # the definition
swane/nipype_pipeline/workflows/dti_preproc_workflow.py:175
swane/tests/nipype_pipeline/matrix/test_dti_matrix.py   # 38, 54, 75, 100, 121, 180, 286
swane/tests/nipype_pipeline/test_deskull_modality_wiring.py:106   # NOT in the plan
swane/tests/prerelease/plan.py                          # 286, 289, 642, 667, 688, 712, 734 — NOT in the plan
```

Why this matters, and why it is not cosmetic: `ConfigManager.getboolean_safe`
(`swane/config/ConfigManager.py:575-588`) swallows a missing key and returns the
catalogue default instead of raising. So if `swane/tests/prerelease/plan.py` is
left writing `old_eddy_correct`, the prerelease sweep's diffusion axis
**silently collapses** — both `("false", "true")` arms would resolve to
`fast_dwi_preproc`'s default `"false"`, the sweep would still pass, and the
fast-preprocessing arm would stop being tested with no error anywhere.

Extend the plan's Task 1 to cover both files, then verify with:

```bash
grep -rn "old_eddy_correct" --include=*.py .
```

The only surviving hits may be deliberate ones — the local variable in
`dti_preproc_workflow.py`, if you choose to keep that name (the plan permits
either). Every preference *key* string must be gone.

One judgement call is yours, not an executor's: `swane/tests/prerelease/plan.py`
defines that axis as `Axis(name="old_eddy_correct", option="old_eddy_correct", ...)`.
The `option` must become `fast_dwi_preproc`. Before renaming `name`, check
whether `Axis.name` feeds prerelease scenario identity, directory names or
stored artefacts under `~/test_swane/prerelease`. If it does, decide and record
whether renaming it invalidates existing prerelease state, and say so in your
report.

## Executors and models

Run them **in order** — each depends on the previous one's contract. Do not
parallelise; Task 2 needs Task 1's preference key and Task 3 needs both.

| # | Task | Model | Why |
|---|---|---|---|
| 1 | Plan Task 1 — replace `old_eddy_correct` with `fast_dwi_preproc`, **including the two extra consumers above** | **Sonnet 5** | Mechanical rename across a known, enumerated file set. The plan gives the exact `PreferenceEntry` body. |
| 2 | Plan Task 2 — feed `out_rotated_bvecs` to `dtifit` and `bedpostx` on the full-eddy branch only | **Opus 4.8** | Scientific correction to a validated pipeline. A wrong-but-plausible wiring (touching the `eddy_correct` branch, or moving `bvals`) would pass a careless test and silently bias FA, MD and tractography. |
| 3 | Plan Task 3 — rename the matrix scenario, regenerate and **review** the golden snapshots | **Sonnet 5** | Mechanical, but the review step is not: see the gate below. |
| 4 | Plan Task 4 — README changelog entry | **Sonnet 5** | Prose in an existing style. The changelog section is at `README.md:128`. |

Facts already verified against the live tree — your executors may rely on these
without re-deriving them, but must not assume anything *beyond* them:

- nipype's `Eddy.output_spec` really does expose both `out_corrected` and
  `out_rotated_bvecs`; `CustomEddy` subclasses `Eddy` and does not override the
  output spec, so the field is available on the `dti_eddy` node.
- `dti_preproc_workflow`'s signature accepts `synth_config`, `deskull_modality`,
  `max_cpu` and `multicore_node_limit`, so the plan's test helper `_build` is
  callable as written.
- `swane/tests/nipype_pipeline/conftest.py` provides `subject_config`,
  `global_config` and `make_input_dir`; `swane/tests/nipype_pipeline/workflows/`
  already exists. No new fixtures are needed.
- `swane/tests/config/test_preferences.py` exists and is appendable.

## The snapshot-review gate

Task 3 regenerates golden snapshots. Regeneration always "passes" — that is what
makes it dangerous. Do not accept the executor's word that the diff is clean.
Read the diff yourself and confirm, specifically, that:

- the bvec edge moved from `dti_conv` to `dti_eddy` **only** in the full-eddy
  scenarios;
- the `fast_preproc` scenario's snapshot still shows `dti_conv -> bvecs`;
- `bvals` edges are untouched everywhere — b-values are rotation-invariant;
- no snapshot outside `snapshots/dti_preproc/` changed (`git status --short`).

If anything else moved, an earlier task overreached. Investigate rather than
accepting the regeneration.

## Shared contracts your executors must not break

Phase 0 ships ahead of all the dipy work, so these must survive intact for the
later phases to build on:

- **`fast_dwi_preproc` is engine-independent.** It is defined here but read by
  the dipy denoise node in Phase 1. Key name, boolean type, default `"false"`
  and polarity (`true` = faster and cheaper) are fixed. Do not rename it, do not
  invert it, do not turn it into an enum — a third `NONE` level was considered
  and deliberately dropped during design.
- **`dti_preproc_workflow` and `tractography_workflow` stay structurally
  intact.** Phase 1 adds *parallel* dipy workflows rather than modifying these;
  the duplication is deliberate, so the validated FSL path needs no
  re-validation. The only permitted changes here are the bvec edges and the
  preference read.
- **Node names are contracts.** `dti_conv`, `dti_eddy`, `dti_dtifit`,
  `dti_bedpostx` must keep their names — the matrix snapshots and the Phase 1
  comparison both address nodes by name.
- **Golden snapshots for every non-DTI workflow must be byte-identical.** Any
  churn outside `snapshots/dti_preproc/` means the change leaked.

## Report-back contract

Report to the global orchestrator with all of the following. A phase reported as
"done" without actual test output is not verifiable and will be sent back.

1. **Actual output** (not a summary) of:
   - `/media/Dati/venv/bin/python -m pytest swane/tests/nipype_pipeline/workflows/test_dti_bvec_source.py -v`
   - `/media/Dati/venv/bin/python -m pytest swane/tests/config/ -v`
   - `/media/Dati/venv/bin/python -m pytest swane/tests/nipype_pipeline/matrix -v`
2. **The reviewed snapshot diff.** State explicitly either "the only semantic
   change is the bvec edge" or describe exactly what else moved and why.
3. **The `grep -rn "old_eddy_correct" --include=*.py .` output** after the
   rename, with any surviving hit justified.
4. **Your decision on the prerelease `Axis.name`**, with the evidence behind it.
5. **`git diff --name-only`** against the phase's starting commit — confirming no
   path under `test_swane` and no binary imaging format.
6. Whether the `old_eddy_correct` **local variable** in `dti_preproc_workflow`
   was renamed or deliberately left, and why.
7. **macOS status.** `CLAUDE.md` requires changes to be proved on Linux and
   macOS. This phase is pure graph wiring and preference plumbing with no
   platform-specific code, but say plainly whether macOS was exercised or not —
   do not imply coverage you do not have.
8. Anything deliberately not done, and why.

Do not start Phase 1. Do not touch any `Dipy*` node, the tractography engine
enum, or `setup.py` — those belong to later phases and mixing them in would
destroy this phase's reviewability.
