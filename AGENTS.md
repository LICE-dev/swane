# SWANe agent instructions

This file is versioned with the repository so every trusted clone uses the same project guidance. It is the single source of instructions for every coding agent: Claude Code reads it through `CLAUDE.md`, which only imports it (`@AGENTS.md`) so it also loads where native `AGENTS.md` loading is off. Keep it short; put detailed reference material in the skills. Skill files live once, in `.claude/skills/<name>/` (a path Claude Code protects from unprompted writes); `.agents/skills/<name>` is a symlink to it for Codex. Clone with symlinks enabled (`git clone -c core.symlinks=true`; on Windows this needs Developer Mode): with Git for Windows' default `core.symlinks=false` the link is checked out as a plain text file and Codex finds no skill.

## Required workflow

- Use `$swane-dev-assistant` for every SWANe code, configuration, workflow, GUI, worker, packaging, release, or validation task.
- Investigate the live code and the skill's architecture map before proposing or implementing changes; do not invent APIs, node names, output fields, preferences, signals, or external-tool behavior.
- Start every new change/implementation from `dev`, unless already working inside an existing sub-branch of `dev` created for the current task. When starting from `dev` or `main`, create a `<agent>/<descriptive-name>` branch, where `<agent>` is the name of the coding agent doing the work (e.g. `claude/`, `codex/`).
- Preserve unrelated work in the working tree: never discard, overwrite, reformat, stage, or include unrelated changes in the task. If existing changes make branch creation or safe isolation ambiguous, stop and ask for direction.
- Before handing off, review the final diff for generated files, subject data, logs, caches, broad formatting, and unrelated changes.
- Never commit, push, publish, merge, or open a pull request unless the user explicitly asks for it in the current conversation.
- Treat these as stable contracts unless the task explicitly includes a compatibility plan: persisted preference keys, input identifiers, enum member names, workflow/node names, Traits fields, signals, callback payloads, result filenames, cached work directories, Slicer mappings, package metadata.
- A change is complete only after the relevant tests have been run and reviewed for correctness (not merely added or left green by accident) and the code has been proved to run on both Linux and macOS wherever it can plausibly behave differently. When the local host cannot cover a platform, the proof is the manual GitHub workflow (`windows-tests.yml`) on a pushed branch: ask the user before pushing and again before launching any GitHub CI run; if they decline, report which platform remains unverified. See the `swane-dev-assistant` skill for which suite to run and how to update tests.
- Any Python command you run in this repo (executing code or tests, exploring, checking files, launching the app) must use the system Python or a dedicated environment that has SWANe's dependencies — never a neuroimaging tool's bundled interpreter, e.g. FSL's (`$FSLDIR/bin/python`, fslpython) or FreeSurfer's (`$FREESURFER_HOME/bin/fspython` and its bundled `python`). Most developers have these tools installed and, when they are sourced, `python`/`python3` on `PATH` may resolve to them; these interpreters lack SWANe's dependencies and pip-installing into them pollutes the tool install. Verify with `python -c "import sys; print(sys.executable)"` when unsure.
- Every part of SWANe code and documentation is written in English language.

## Licensing

- SWANe orchestrates external neuroimaging tools (FSL, FreeSurfer, dcm2niix, 3D Slicer, etc.) as separate processes/dependencies. Never copy, adapt, or embed code derived from those tools into this repository — their licenses are distinct from SWANe's and must not be violated. The only exception is a small piece of code from a permissively licensed Python library (BSD, MIT or Apache-2.0) that SWANe already depends on, adapted only when no public API gives the required behavior: it needs the user's explicit approval for that specific piece, a file-level source disclaimer, and the upstream copyright notice and licence conditions in `NOTICE.md`. Code of FSL, FreeSurfer and any other non-permissively licensed tool is never covered by this exception. Check `NOTICE.md` before touching anything that looks derived from Nipype or another project, and preserve existing source disclaimers.

## Safety and evidence

- Never add real subject data, identifiers, private DICOM metadata, local subject paths, credentials, decrypted secrets, logs, caches, or generated clinical results to source control, and never paste them into pull requests, issues, or other external services. Use synthetic or de-identified fixtures only.
- Treat changes to preprocessing, segmentation, registration, tractography, statistics, visualization, and resource scheduling (thread counts included: multi-threaded ANTs is not bit-reproducible) as scientifically sensitive. State the intended numerical or geometric effect and add comparison coverage where feasible.
- Distinguish software regression evidence from scientific or clinical validation: a passing test is never clinical or scientific validation.
- The light suite (`pytest swane/tests -m "not heavy"`, the whole test tree, as CI runs it) is headless, uses disposable `tmp_path` fixtures, and needs no external tools. Heavy tests (marked `@pytest.mark.heavy`, opt-in via `--run-heavy`) are interleaved in those same directories and run against synthetic/mocked fixtures or a real toolchain (FSL/FreeSurfer/dcm2niix/Slicer), never against real subject data.
- `swane/tests/prerelease/` runs the real workflows over a generated synthetic phantom under the disposable root `~/test_swane/prerelease` (CI passes a runner-temporary `--work-dir`); before running it, verify the resolved root is a disposable test root and never substitute a clinical working directory.
- Prefer Windows for static and lightweight checks. Use a supported Linux/macOS environment for FSL, FreeSurfer, Slicer, and representative workflow validation.

## Terminology

- SWANe is a research tool, not a medical device: never describe or imply clinical/medical use in code, comments, docstrings, UI strings, documentation, or commit messages.
- Never use "patient" (or its translations) anywhere in code or docs — always use "subject".

## SWANe component map

- This repository owns the main application and Nipype workflows and uses `$swane-dev-assistant` from `.agents/skills/`. For architecture, Nipype workflows, configuration/preferences, UI/workers details, and validation/test commands, see that skill — it is discovered automatically based on the task.
- Related repositories are normally checked out as siblings, but agents must discover them from the workspace instead of assuming an absolute path:
  - `../dicom_sequence_classifier` owns metadata-based DICOM classification and uses `$dicom-sequence-classifier-maintainer`.
  - `../swane_classifier` owns lesion-classifier research code and uses `$swane-classifier-research`.
  - `../swane.wiki` owns the public GitHub wiki and uses `$swane-wiki-maintainer`.

When a change crosses repositories, inspect and validate every producer and consumer, but keep each repository's changes isolated and reviewable.
