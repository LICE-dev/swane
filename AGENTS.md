# SWANe agent instructions

This file is versioned with the repository so every trusted clone uses the same project guidance. It is the single source of instructions for every coding agent: Claude Code reads it through `CLAUDE.md`, which only imports it. Keep it short; put detailed reference material in `.agents/skills/` (`.claude/skills/<name>` is a symlink to it, because Claude Code only discovers `.claude/skills/`).

## Required workflow

- Use `$swane-dev-assistant` for every SWANe code, configuration, workflow, GUI, worker, packaging, release, or validation task.
- Investigate the live code and the skill's architecture map before proposing or implementing changes; do not invent APIs, node names, output fields, preferences, signals, or external-tool behavior.
- Start every new change/implementation from `dev`, unless already working inside an existing sub-branch of `dev` created for the current task. When starting from `dev` or `main`, create a `<agent>/<descriptive-name>` branch, where `<agent>` is the name of the coding agent doing the work (e.g. `claude/`, `codex/`).
- Preserve unrelated work in the working tree.
- Never commit, push, publish, merge, or open a pull request unless the user explicitly asks for it in the current conversation.
- Treat these as stable contracts unless the task explicitly includes a compatibility plan: persisted preference keys, input identifiers, enum member names, workflow/node names, Traits fields, signals, result filenames, Slicer mappings.
- A change is complete only after the relevant tests have been run and reviewed for correctness (not merely added or left green by accident) and code has been proved to run both on linux and macOS systems. See the `swane-dev-assistant` skill for which suite to run and how to update tests.
- Any Python command you run in this repo (executing code or tests, exploring, checking files, launching the app) must use the system Python or a dedicated environment that has SWANe's dependencies — never a neuroimaging tool's bundled interpreter, e.g. FSL's (`$FSLDIR/bin/python`, fslpython) or FreeSurfer's (`$FREESURFER_HOME/bin/fspython` and its bundled `python`). Most developers have these tools installed and, when they are sourced, `python`/`python3` on `PATH` may resolve to them; these interpreters lack SWANe's dependencies and pip-installing into them pollutes the tool install. Verify with `python -c "import sys; print(sys.executable)"` when unsure.
- Every part of SWANe code and documentation is written in English language.

## Licensing

- SWANe orchestrates external neuroimaging tools (FSL, FreeSurfer, dcm2niix, 3D Slicer, etc.) as separate processes/dependencies. Never copy, adapt, or embed code derived from those tools into this repository — their licenses are distinct from SWANe's and must not be violated. Check `NOTICE.md` before touching anything that looks derived from Nipype or another project, and preserve existing source disclaimers.

## Safety and evidence

- Never add real patient data, identifiers, private DICOM metadata, local subject paths, credentials, decrypted secrets, execution logs, caches, or generated clinical results to source control. Use synthetic or de-identified fixtures only.
- Distinguish software regression evidence from scientific or clinical validation: a passing test is never clinical or scientific validation.
- The light suite (`swane/tests/{config,utils,workers,ui,nipype_pipeline}`, run with `-m "not heavy"`) is headless, uses disposable `tmp_path` fixtures, and needs no external tools. Heavy tests (marked `@pytest.mark.heavy`, opt-in via `--run-heavy`) are interleaved in those same directories and run against synthetic/mocked fixtures or a real toolchain (FSL/FreeSurfer/dcm2niix/Slicer), never against patient data.
- `swane/tests/prerelease/` runs the real workflows over a generated synthetic phantom under the disposable root `~/test_swane/prerelease`; before running it, verify the resolved root is exactly that and never substitute a clinical working directory.
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
