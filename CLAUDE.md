# SWANe — Claude Code project instructions

This file is loaded into every conversation in this repository. Keep it short; put detailed reference material in `.claude/skills/`.

## Working agreement

- Investigate the live code before proposing or implementing a change; do not invent APIs, node names, output fields, preferences, signals, or external-tool behavior.
- Start every new change/implementation from `dev`, unless already working inside an existing sub-branch of `dev` created for the current task. When starting from `dev` or `main`, create a `claude/<descriptive-name>` branch.
- Preserve unrelated work in the working tree.
- Never commit, push, merge, or open a pull request unless the user explicitly asks for it in the current conversation.
- Treat these as stable contracts unless the task explicitly includes a compatibility plan: persisted preference keys, enum member names, workflow/node names, Traits fields, signals, result filenames, Slicer mappings.
- A change is complete only after the relevant tests have been run and reviewed for correctness (not merely added or left green by accident) and code has been proved to run both on linux and macOS systems. See the `swane-dev-assistant` skill for which suite to run and how to update tests.
- Every part of SWANe code and documentation is written in English language.

## Licensing

- SWANe orchestrates external neuroimaging tools (FSL, FreeSurfer, dcm2niix, 3D Slicer, etc.) as separate processes/dependencies. Never copy, adapt, or embed code derived from those tools into this repository — their licenses are distinct from SWANe's and must not be violated. Check `NOTICE.md` before touching anything that looks derived from Nipype or another project, and preserve existing source disclaimers.

## Safety

- Never add real patient data, identifiers, private DICOM metadata, local subject paths, credentials, decrypted secrets, execution logs, or generated clinical results to source control. Use synthetic or de-identified fixtures only.
- Do not present a passing test as clinical or scientific validation — it is software regression evidence only.
- `swane/tests/prerelease/` runs against the disposable root `~/test_swane/prerelease`; verify that exact path before running it and never point it at a clinical working directory.

## Terminology

- SWANe is a research tool, not a medical device: never describe or imply clinical/medical use in code, comments, docstrings, UI strings, documentation, or commit messages.
- Never use "patient" (or its translations) anywhere in code or docs — always use "subject".

## Related repositories

Normally checked out as siblings; discover them from the workspace rather than assuming an absolute path:
- `../swane_supplement` — packaged icons and scientific resources
- `../dicom_sequence_classifier` — metadata-based DICOM classification
- `../swane_classifier` — lesion-classifier research code
- `../swane.wiki` — public GitHub wiki

When a change crosses repositories, validate every producer and consumer, but keep each repository's changes isolated and reviewable.

## Where to look next

For architecture, Nipype workflows, configuration/preferences, UI/workers details, and validation/test commands, see the `swane-dev-assistant` skill — it is discovered automatically based on the task.

