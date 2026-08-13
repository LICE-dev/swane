---
name: swane-dev-assistant
description: "Develop and govern SWANe, the Python/PySide6 and Nipype application for standardized neuroimaging workflows. Use when Codex must create, change, refactor, debug, review, document, or validate SWANe code involving Nipype nodes and workflows, workflow orchestration, DICOM inputs, configuration and preferences, resource scheduling, external neuroimaging tools, GUI components, background workers, tests, packaging, releases, or repository conventions."
---

# SWANe Dev Assistant

Develop SWANe while preserving its workflow contracts, scientific behavior, persisted preferences, resource limits, GUI responsiveness, and repository conventions.

## Establish context and select references

- Treat the current repository checkout as the source of truth. Inspect real code before proposing or implementing a change; do not invent APIs, node names, output fields, preferences, signals, or external-tool behavior.
- Always read [references/architecture-and-change-map.md](references/architecture-and-change-map.md) before changing code. Use it to trace the end-to-end impact and select additional references.
- Read [references/workflows-and-nipype.md](references/workflows-and-nipype.md) for changes to `MainWorkflow`, workflow factories, custom Nipype interfaces, execution/reporting, result sinks, CPU/RAM/GPU behavior, or scientific image processing.
- Read [references/configuration-and-preferences.md](references/configuration-and-preferences.md) for changes to global or subject configuration, `PreferenceEntry`, preference catalogs, defaults, presets, dependency/resource requirements, preference UI, the setup wizard, persisted keys, or secrets.
- Read [references/ui-and-workers.md](references/ui-and-workers.md) for changes to application lifecycle, `MainWindow`, `SubjectTab`, generic Qt components, workers, signals, multiprocessing, cancellation, shutdown, or Slicer integration. Preference-specific widgets remain owned by the configuration reference.
- Read `README.md` for supported platforms, dependencies, installation, and release history. For user-facing installation or usage documentation, also consult the linked SWANe wiki when access is available.
- Inspect `NOTICE.md` before copying or substantially modifying code derived from Nipype or another project. Preserve existing source disclaimers and license notices.

## Follow the repository workflow

1. Inspect the active branch and working tree with `git branch --show-current` and `git status --short --branch`.
2. Preserve all unrelated user changes. Never discard, overwrite, reformat, stage, or include them in the task.
3. Trace the requested behavior end to end: configuration/input -> subject state -> `MainWorkflow` -> subworkflow -> Nipype interface/external tool -> result/report -> GUI or Slicer consumer.
4. Identify stable contracts affected by the change: persisted keys, enum members, workflow/node names, traits, result filenames, signals, callback payloads, cached work directories, and package metadata.
5. Implement the smallest coherent change using existing abstractions and patterns.
6. Add or update focused regression coverage and documentation when behavior, dependencies, installation, configuration, or release-visible output changes.
7. Run the narrowest useful checks first, then broaden validation in proportion to risk. Report every check that could not run and its missing prerequisite.

## Use a dedicated Git branch

- Never modify files on `dev` or `main` unless the user explicitly asks in the current conversation to work directly on that branch.
- When implementation starts from `dev`, `main`, or an unrelated branch, create a fresh task branch. Use `codex/<descriptive-kebab-name>` by default unless the user or repository workflow specifies another prefix.
- Preserve a dirty worktree. If existing changes make branch creation or safe isolation ambiguous, stop and ask for direction.
- Target `dev` for normal integration. Do not merge into or push directly to `dev`/`main` unless the user explicitly requests that exception.
- Do not commit, push, or open a pull request unless the user requests publication or the active workflow explicitly includes it.

## Preserve boundaries and stable contracts

- Keep custom interfaces in `swane/nipype_pipeline/nodes/`, reusable graphs in `workflows/`, subject orchestration in `MainWorkflow.py`, and execution/reporting infrastructure in `engine/`.
- Keep preference schema, defaults, typed identifiers, validation, and persistence in `swane/config/`. Keep subject, DICOM, dependency, resource, and reusable domain behavior in `swane/utils/`.
- Keep UI composition in `swane/ui/` and long-running GUI work in `swane/workers/` using the existing Qt signal, `QThreadPool`, and multiprocessing patterns.
- Keep user-facing text in `swane/strings.py`. Reuse `swane_supplement` and `ResourceManager` for packaged resources and resource discovery.
- Preserve persisted preference keys, enum-member names, workflow and node names, Traits fields, output filenames, report signals, and Slicer/result mappings unless the task explicitly includes a compatibility plan.
- Distinguish Python packages in `setup.py` from system tools detected by `DependencyManager` such as dcm2niix, FSL, FreeSurfer, Graphviz, and 3D Slicer.

## Apply scientific, privacy, and compatibility safeguards

- Treat changes to preprocessing, segmentation, registration, tractography, statistics, visualization, and resource scheduling as scientifically sensitive. State the intended numerical or geometric effect and add comparison coverage where feasible.
- Never add real patient data, identifiers, private DICOM metadata, local subject paths, credentials, decrypted secrets, or execution logs to source control. Use synthetic or de-identified fixtures only.
- Do not present a code change as clinically validated merely because tests pass; distinguish software regression evidence from scientific or clinical validation.
- Preserve Python 3.10 compatibility, supported Ubuntu/macOS behavior, and existing public behavior unless the user explicitly requests a breaking change.
- Avoid hard-coded developer paths, unbounded parallelism, blocking work on the Qt GUI thread, and direct external command execution from UI code.

## Match project style without expanding scope

- Preserve established public names and mixed legacy filename conventions unless a rename is part of the task.
- Format changed Python code with Black. Avoid formatting the entire repository when only a small surface changed.
- Use the surrounding NumPy-style docstring pattern for public classes, workflow factories, and non-obvious methods. Keep comments focused on rationale and scientific or lifecycle constraints.
- Avoid opportunistic refactors. Tighten legacy broad exception handling only when the relevant behavior is understood and covered.
- Prefer explicit imports over introducing new wildcard imports; do not rewrite existing wildcard-import areas solely for style.

## Validate in risk order

Use the configured project interpreter (`python3`, `python`, or an explicit environment path). The light suite (`swane/tests/{config,utils,workers,ui}`, run with `-m "not heavy"`) is headless — Qt is forced offscreen by `swane/tests/conftest.py` — uses disposable `tmp_path` fixtures, and auto-skips any test whose external tool (FSL, FreeSurfer, dcm2niix, Slicer) is absent. The heavy tests live in `swane/tests/integration/`: inspect `swane/tests/__init__.py`, which sets `TEST_DIR = ~/test_swane` and whose fixtures delete and recreate subdirectories below it, and `integration/test_complete_workflow.py`, which reads a configured `subj_test`. Verify those exact paths and never point test configuration at a clinical or user working directory.

```bash
python3 -m compileall swane
python3 -m pytest <targeted-test-file-or-node>
python3 -m black --check <changed-python-files>
python3 -m pytest swane/tests -m "not heavy" --color=yes --verbose
```

- Start with syntax/import checks and the closest targeted test.
- Run graph-construction or interface tests when changing nodes, connections, names, outputs, or preferences.
- Treat tests requiring neuroimaging tools, a Qt display, or a configured dataset as environment-dependent. Do not claim they passed when prerequisites are absent.
- For scientific output changes, add a representative workflow comparison when the required tools and de-identified data are available.
- Review the final diff for generated files, subject data, logs, caches, broad formatting, and unrelated changes.

## Communicate the result

- Answer in Italian unless the user asks otherwise.
- Lead with the implemented or diagnosed outcome.
- Name affected persisted, workflow, scientific, signal, and result contracts.
- Report tests run, tests skipped, and missing prerequisites precisely.
- If the requested approach conflicts with the live architecture or a stable contract, explain the conflict and propose the smallest aligned alternative.
