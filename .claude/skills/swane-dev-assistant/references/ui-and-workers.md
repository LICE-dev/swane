# SWANe UI and workers

Read this reference for application lifecycle, general Qt components, GUI state, background workers, signals, workflow process integration, cancellation, shutdown, or Slicer interactions. Read the configuration reference instead for preference-specific widgets and setup-wizard rules.

## Contents

- [UI ownership and lifecycle](#ui-ownership-and-lifecycle)
- [Background execution models](#background-execution-models)
- [Signals, state, and object lifetime](#signals-state-and-object-lifetime)
- [Workflow progress and cancellation](#workflow-progress-and-cancellation)
- [Slicer integration](#slicer-integration)
- [License consent gate](#license-consent-gate)
- [Error and shutdown behavior](#error-and-shutdown-behavior)
- [Verification](#verification)

## UI ownership and lifecycle

- Keep `swane/__main__.py` responsible for `QApplication`, the single-instance PID guard, the restart exit-code loop, and final cleanup.
- Keep `MainWindow` responsible for application-level navigation, global dependency/status views, subject-tab ownership, and global shutdown coordination.
- Keep `SubjectTab` responsible for one subject's DICOM input state, workflow generation/execution controls, progress tree, result availability, and Slicer actions.
- Keep reusable narrow widgets in their existing focused modules; avoid adding domain state to presentation-only controls.
- Treat `Subject`, `SubjectInputStateList`, `ConfigManager`, `MainWorkflow`, and `WorkflowReport` as sources of truth. Widgets reflect that state; they must not create a competing model.
- Preserve tab enablement, button state, progress text, and result visibility across reload, reset, workflow stop, and late worker completion.

## Background execution models

- Use `QRunnable` with `QThreadPool.globalInstance()` for bounded background operations such as DICOM scans, update checks, Slicer checks/exports, scene viewing, and queue monitoring.
- Use explicit signal-holder `QObject` instances for worker results and progress, following the existing worker pattern.
- Keep full Nipype execution inside `WorkflowProcess`, not a Qt thread. The multiprocessing boundary exists so the process and its descendants can be terminated safely.
- Keep the multiprocessing `Queue` -> `WorkflowMonitorWorker` -> Qt signal path for workflow reports.
- Do not perform filesystem-wide searches, external commands, DICOM parsing, workflow execution, network checks, or Slicer operations on the GUI thread.
- Pass workers the smallest immutable snapshot they need. Do not hand a mutable UI object or `ConfigManager` to a worker unless the existing contract requires it and thread safety is demonstrated.

## Signals, state, and object lifetime

- Treat every signal signature and callback payload as a contract. Search producer, connector, and all consumers before changing it.
- Update widgets and persist configuration only in GUI-side slots/callbacks, not from worker code.
- Retain worker/signal objects for as long as their operation can emit. Prevent garbage collection or callback delivery to destroyed widgets.
- Emit explicit success, failure, and terminal signals for long operations. Ensure exceptions cannot leave the UI permanently in a loading or checking state.
- When multiple requests can overlap, associate a token/generation with the request and ignore stale results that no longer match current user state.
- Disconnect or guard late callbacks when a subject tab or main window closes.
- Avoid signal loops when programmatically updating widgets; preserve the existing initialization order where change connections are attached after initial values.

## Workflow progress and cancellation

- Preserve `WorkflowSignals` semantics and the mapping from reports to the `SubjectTab` progress tree.
- Keep node/workflow identities stable because progress entries use graph names and full names.
- On user stop, signal the workflow process through its stop event; let the process own descendant termination and queue closure.
- Ensure every terminal path eventually emits `WORKFLOW_STOP` and resets UI controls, running icons, and tab close behavior.
- Preserve log and resource-handler cleanup on success, error, and cancellation.
- Do not call process-kill helpers from the main GUI process.

## Slicer integration

- `SlicerCheckWorker` discovers Slicer, checks its version/modules, maintains a marker-delimited stub (`BEGIN`/`END SWANE PATCH`) in `~/.slicerrc.py` that only bootstraps `swane/workers/slicerrc_swane.py` (the actual logic, shipped with SWANe — currently installing the MELODIC resting-state timecourse viewer), and emits `(slicer_path, slicer_version, message, DependenceStatus)`.
- Hide-zero display is handled entirely at scene-export time (`SlicerExportWorker`), not via a slicerrc patch. `SlicerCheckWorker.LEGACY_MARKERS` cleans up the old inline `HIDEZERO PATCH` block on migration — do not resurrect logic under those legacy markers; the mechanism they supported is dead.
- Keep `MainWindow.slicer_row` as the GUI-side owner of status rendering and persisted path/version/validation changes.
- Preserve status semantics: detected capabilities can clear validation; warnings remain visible and require revalidation; missing checks must not overwrite a known-good configuration without explicit intent.
- `SlicerExportWorker` generates scenes from result contracts; `SlicerViewerWorker` opens an existing scene. Keep result filenames and scene extensions aligned with scripts and preferences.
- Treat edits to `~/.slicerrc.py`, `swane/workers/slicerrc_swane.py`, and external Slicer subprocesses as user-visible side effects. Keep the stub itself tiny and stable (real behavior changes belong in `slicerrc_swane.py`, not the injected stub), make markers idempotent, preserve unrelated file content, handle paths containing spaces, and report failures.
- Handle subprocess return codes, stderr, timeouts, missing modules, unsupported versions, and closure during an active Slicer task.

## License consent gate

- `swane/__main__.py` calls `MainWindow.run_license_consent_gate()` after `MainWindow` construction (so the setup wizard has already run) and before `app.exec()`; a decline aborts startup without entering the event loop and leaves the PID cleanup intact.
- Consent is per external tool, keyed by the tool's detected version, in the global config `accepted_license_<tool>` MAIN keys. The gate prompts only tools that are detected/usable (non-MISSING) whose stored accepted version differs from the current one; persistence is atomic (written only after the whole flow is accepted).
- Resolve license text off the GUI thread: `LicenseResolveWorker` (a `QThreadPool` worker) performs the possibly-networked resolution while a modal busy indicator keeps a local `QEventLoop` running, so the main window never freezes during a download. Never fetch on the GUI thread.
- `swane/utils/license_consent.py` owns resolution (`resolve_license_text`: installed file -> online -> bundled), consent evaluation (`tools_needing_consent`, `detected_tool_versions`), and the inline label helper (`version_with_license`); `swane/utils/LicenseReference.py` is the per-tool registry (display name, official URL, installed-file candidates, bundled fallback under `swane/licenses/`). Reference only the legal license text, never a per-user key file (e.g. FreeSurfer's `_license.txt`).
- Home dependency labels embed a license link inside the version parenthesis via `version_with_license` (built in `DependencyManager`/`SlicerCheckWorker`): shown whenever a version is detected, opening the local license file when present else the official URL. This "version present" rule is intentionally more permissive than the gate's "tool usable" rule.
- `LicenseConsentWindow` is a sequential, blocking dialog (one page per tool, fixed non-clinical/non-commercial banner, scroll-to-enable "I ACCEPT", monospace themed panel). Keep it presentation-only; the caller persists consent.

## Error and shutdown behavior

- Surface actionable errors through existing status/reporting paths and always restore interactive controls.
- Preserve application restart semantics when a preference requires restart; do not confuse restart with workflow cancellation.
- Before closing the application or a subject tab, account for running workflows, background workers, filesystem watchers, progress dialogs, and pending callbacks.
- Preserve the last-PID cleanup in `__main__.py`, including exceptional exits where possible.
- Keep automatic shutdown-after-workflow guarded by the absence of running workflows and unresolved errors.

## Verification

- Use `pytest-qt` to verify signal delivery, widget state, restart/reset return codes, and GUI-thread ownership.
- Prove responsiveness with a deliberately blocked worker while a GUI timer continues to fire.
- Test success, warning, missing, exception, cancellation, and late-completion paths.
- Record `QThread.currentThread()` in worker and slot tests when thread ownership matters.
- Test overlapping requests and confirm stale results cannot overwrite newer state.
- Test window/tab closure while work is active and ensure no callback targets destroyed widgets.
- Mock external commands for focused Slicer tests; run real Slicer smoke tests separately on supported Ubuntu/macOS environments.
- For workflow UI changes, verify report-to-progress mapping and the final reset after `WORKFLOW_STOP`.
