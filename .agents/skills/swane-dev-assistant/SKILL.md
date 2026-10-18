---
name: swane-dev-assistant
description: Use when creating, changing, refactoring, debugging, reviewing, documenting, or validating SWANe code — Nipype nodes/workflows, DICOM inputs, configuration/preferences, resource scheduling, external neuroimaging tool integration (FSL, FreeSurfer, dcm2niix, 3D Slicer), GUI components, background workers, tests, pip dependency upgrades, or packaging/releases.
---

# SWANe Dev Assistant

## Overview

Develop SWANe while preserving its workflow contracts, scientific behavior, persisted preferences, resource limits, GUI responsiveness, and repository conventions. Treat the current checkout as source of truth — inspect real code before proposing or implementing a change; do not invent APIs, node names, output fields, preferences, signals, or external-tool behavior.

## Choose a reference

Always read [references/architecture-and-change-map.md](references/architecture-and-change-map.md) first — it routes to the others based on what is changing.

| Change area | Reference |
|---|---|
| Workflow graphs, custom Nipype interfaces, execution/resources/reporting, scientific processing | [references/workflows-and-nipype.md](references/workflows-and-nipype.md) |
| Global/subject preferences, `PreferenceEntry`, presets, dependency gates, setup wizard, secrets | [references/configuration-and-preferences.md](references/configuration-and-preferences.md) |
| Application lifecycle, `MainWindow`/`SubjectTab`, workers, signals, Slicer integration | [references/ui-and-workers.md](references/ui-and-workers.md) |
| Which suite to run, how to add/update tests for a given change | [references/testing.md](references/testing.md) |
| Bumping a pinned `setup.py` dependency (e.g. Nipype), checking monkeypatches and deprecated APIs, transitive dependency changes | [references/dependency-updates.md](references/dependency-updates.md) |

## Repository workflow

1. Check the active branch and working tree (`git branch --show-current`, `git status --short --branch`).
2. Trace the requested behavior end to end: configuration/input → subject state → `MainWorkflow` → subworkflow → Nipype interface/external tool → result/report → GUI or Slicer consumer.
3. Identify the stable contracts touched by the change (see `CLAUDE.md`).
4. Implement the smallest coherent change using existing abstractions and patterns.
5. Add or update focused regression coverage — see [references/testing.md](references/testing.md).
6. Run the narrowest useful checks first, then broaden validation in proportion to risk. Report every check that could not run and why.
7. If the change makes a reference file inaccurate (a renamed class/method, a moved file, a changed mechanism, a dead cross-reference), update that reference in the same change — do not leave it to drift. A reference describing code that no longer exists is worse than no reference.

## Style

- Format changed Python with Black; do not reformat unrelated files.
- Match the surrounding NumPy-style docstring convention for public classes, workflow factories, and non-obvious methods.
- Avoid opportunistic refactors; do not rewrite existing wildcard-import areas solely for style.
- Preserve established public names and mixed legacy filename conventions unless the rename is the task itself.

## Reporting the result

- Lead with the implemented or diagnosed outcome.
- Name affected persisted, workflow, scientific, signal, and result contracts.
- Report tests run, tests skipped, and missing prerequisites precisely.
- If the requested approach conflicts with the live architecture or a stable contract, explain the conflict and propose the smallest aligned alternative.
