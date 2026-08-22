# SWANe agent instructions

This file is versioned with the repository so every trusted clone uses the same project guidance.

## Required workflow

- Use `$swane-dev-assistant` for every SWANe code, configuration, workflow, GUI, worker, packaging, release, or validation task.
- Inspect the live code and the skill's architecture map before proposing or implementing changes.
- Preserve unrelated work. For versioned changes starting from `dev` or `main`, create a `codex/<descriptive-name>` branch.
- Do not commit, push, publish, merge, or open a pull request unless the user explicitly requests it.
- Treat preference keys, input identifiers, workflow and node names, Traits fields, signals, result filenames, and Slicer mappings as stable contracts.

## Safety and evidence

- Never add patient data, identifiers, private DICOM metadata, local subject paths, credentials, decrypted secrets, logs, caches, or generated clinical results.
- Use synthetic or de-identified fixtures only.
- Distinguish software regression evidence from scientific or clinical validation.
- The light suite (`swane/tests/{config,utils,workers,ui,nipype_pipeline}`, run with `-m "not heavy"`) is headless, uses disposable `tmp_path` fixtures, and needs no external tools. Heavy tests (marked `@pytest.mark.heavy`, opt-in via `--run-heavy`) are interleaved in those same directories and run against synthetic/mocked fixtures or a real toolchain (FSL/FreeSurfer/dcm2niix/Slicer), never against patient data.
- `swane/tests/prerelease/` runs the real workflows over a generated synthetic phantom under the disposable root `~/test_swane/prerelease`; before running it, verify the resolved root is exactly that and never substitute a clinical working directory.
- Prefer Windows for static and lightweight checks. Use a supported Linux/macOS environment for FSL, FreeSurfer, Slicer, and representative workflow validation.

## SWANe component map

- This repository owns the main application and Nipype workflows and uses `$swane-dev-assistant` from `.agents/skills/`.
- Related repositories are normally checked out as siblings, but agents must discover them from the workspace instead of assuming an absolute path:
  - `../swane_supplement` owns packaged icons and scientific resources and uses `$swane-supplement-maintainer`.
  - `../dicom_sequence_classifier` owns metadata-based DICOM classification and uses `$dicom-sequence-classifier-maintainer`.
  - `../swane_classifier` owns lesion-classifier research code and uses `$swane-classifier-research`.
  - `../swane.wiki` owns the public GitHub wiki and uses `$swane-wiki-maintainer`.

When a change crosses repositories, inspect and validate every producer and consumer, but keep each repository's changes isolated and reviewable.
