# SWANe workflows and Nipype

Read this reference for changes to workflow graphs, custom interfaces, analysis outputs, monitored execution, resources, or scientific processing.

## Contents

- [Layer responsibilities](#layer-responsibilities)
- [Workflow factory contracts](#workflow-factory-contracts)
- [Custom interface contracts](#custom-interface-contracts)
- [MainWorkflow orchestration and results](#mainworkflow-orchestration-and-results)
- [Execution, reporting, and resources](#execution-reporting-and-resources)
- [Scientific compatibility](#scientific-compatibility)
- [External tool changes](#external-tool-changes)
- [Verification](#verification)

## Layer responsibilities

- Put reusable Nipype interface implementations and focused wrappers in `swane/nipype_pipeline/nodes/`.
- Put reusable graph factories in `swane/nipype_pipeline/workflows/`.
- Keep `MainWorkflow` responsible for subject-level feature gates, input paths, global/subject configuration propagation, cross-workflow connections, resources, and result sinking.
- Keep graph introspection, progress metadata, scheduling, memory estimation, and workflow signals in `swane/nipype_pipeline/engine/`.
- Keep external command construction inside Nipype interfaces. Do not duplicate analysis commands in `MainWorkflow`, workers, or UI components.

## Workflow factory contracts

- Return a `CustomWorkflow` from reusable workflow factory functions and follow neighboring signatures and docstrings.
- Use `IdentityInterface` input/output nodes for values crossing graph boundaries when the surrounding workflows use that pattern.
- Document every boundary field in the factory docstring and connect every advertised output.
- Treat workflow names, operational node names, boundary-node names, input/output field names, and deterministic filenames as stable contracts. They feed parent connections, tests, progress trees, cached work directories, DataSink, and Slicer.
- Give nodes stable operational names. Add `long_name` when progress reporting needs a clearer user label; `CustomWorkflow.format_node_name` consumes it.
- Reuse an existing workflow family before creating a one-off graph. For example, prefer extending the established linear/nonlinear registration or functional-map patterns when their scientific contract fits.
- Avoid changing a node identity solely for readability; a rename can invalidate cached work and graph assertions.

When adding an analysis, trace this complete chain:

1. Input identity and eligibility in `DataInputList` and subject input state.
2. Configuration and dependency/resource gates.
3. Workflow factory inputs, outputs, nodes, and filenames.
4. `MainWorkflow` launch method, connections, and resource arguments.
5. `sink_result` mappings and result folder contract.
6. Workflow reports, UI progress, export, visualization, and Slicer consumers.
7. Graph and representative scientific tests.

## Custom interface contracts

- Choose the correct base: `BaseInterface` for Python work, `CommandLine` or a tool-specific command base for executables, or a focused subclass of an existing Nipype interface.
- Define explicit input and output specs. Use Traits types and metadata deliberately: `mandatory`, `exists`, `usedefault`, `argstr`, enums, ranges, generated filenames, and file multiplicity.
- Return the runtime from `_run_interface` and surface failures with Nipype-compatible errors and actionable context.
- Derive outputs through the declared output spec. Ensure `_list_outputs`, `_gen_filename`, or `aggregate_outputs` matches the actual command/Python behavior.
- Return absolute output paths when the neighboring custom interfaces do so; never advertise an output that execution does not create.
- Preserve input image headers, affines, orientation, and data types unless the interface explicitly transforms them.
- Preserve source disclaimers on files derived from Nipype or other software and update `NOTICE.md` when attribution changes.

## MainWorkflow orchestration and results

- Gate optional analyses before constructing or connecting them. Check both input availability and requested configuration.
- Pass the relevant global or subject configuration section into workflow factories instead of re-reading configuration inside nodes.
- Keep cross-workflow connections explicit. Verify source/destination direction, especially for reference/moving images and transforms.
- Propagate resource choices from `MainWorkflow` rather than querying host capacity independently inside each workflow.
- Use `CustomWorkflow.sink_result` for persisted outputs and preserve its result names, subfolders, and regular-expression substitutions.
- Treat result filenames as downstream contracts. Search `Subject`, result-tree code, Slicer scripts, tests, and documentation before changing them.
- Ensure new outputs appear in the UI/export path only when the file contract actually exists.

## Execution, reporting, and resources

- Use node `mem_gb`, `n_procs`, GPU flags, and `RamEstimator` consistently with `MonitoredMultiProcPlugin`.
- Avoid unbounded concurrency. Respect global CPU/RAM/GPU preferences and `CoreLimit` behavior.
- Account for both static memory declarations and input-dependent RAM estimators for image-size-sensitive nodes.
- Preserve `WorkflowSignals`, `WorkflowReport` payloads, node status callbacks, and progress-tree identities when modifying monitored execution.
- Keep the killable workflow boundary in `WorkflowProcess`: a multiprocessing `Process` owns an internal execution thread, subprocess cleanup, log handlers, and the queue used by `WorkflowMonitorWorker`.
- Never call `WorkflowProcess.kill_with_subprocess` outside the workflow process; its contract intentionally kills the current process and descendants.
- Close queues, detach log/resource handlers, and emit `WORKFLOW_STOP` on every terminal path.
- Keep resource-monitor logging and crash directories inside the subject workflow area; never commit generated logs.

## Scientific compatibility

For every scientific change, review explicitly:

- reference and moving-image direction in registrations;
- image orientation, affine and header preservation;
- interpolation for scalar images, masks, labels, transforms, and statistical maps;
- voxel size, field of view, cropping, skull stripping, and bias correction;
- thresholds, units, timing values, volume counts, seeds, and accepted ranges;
- number and order of transform applications, especially for small structures and vascular/susceptibility images;
- CPU/GPU paths and whether their contract-level outputs are equivalent;
- downstream assumptions in FSL, FreeSurfer, Slicer, DataSink, and visualization.

Do not equate successful graph construction with scientific correctness. Require representative de-identified comparison data when geometry or numerical output changes.

## External tool changes

- Put importable Python dependencies in `setup.py`; keep system executables under `DependencyManager` detection and minimum-version checks.
- Update dependency status, configuration gates, tool-reference guidance, README/wiki installation, and tests together.
- Preserve supported Ubuntu and macOS behavior. Make platform-specific paths and commands explicit and avoid developer-local paths.
- Handle missing executables, unsupported versions, non-zero return codes, stderr, timeouts, and filenames containing spaces.
- Do not silently fall back to a scientifically different algorithm without an explicit user-visible contract.

## Verification

- Compile/import changed modules before graph tests.
- Test Traits defaults, validation, generated commands, declared outputs, and failure paths for custom interfaces.
- Construct affected graphs and assert boundary fields, node identities, connections, resource metadata, and deterministic output names.
- Update the affected `swane/tests/nipype_pipeline/matrix/` golden snapshots for graph-level changes (`SWANE_SNAPSHOT_UPDATE=1 pytest swane/tests/nipype_pipeline/matrix`), and re-run `swane/tests/prerelease/` for execution-level changes; the latter needs `--run-heavy`-equivalent real tools (FSL/dcm2niix/FreeSurfer) and is opt-in (`python -m swane.tests.prerelease`).
- Use mocked or synthetic inputs for focused tests. Run real-tool smoke tests only in a suitable neuroimaging environment.
- Compare representative de-identified outputs for scientific changes, including geometry and downstream visualization, and state what was not clinically validated.
