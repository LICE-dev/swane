# SWANe architecture and change map

Use this reference for every SWANe task. Re-check the live files because this map describes responsibilities and change routing, not frozen implementation details.

## Runtime flow

`DICOM folders -> DicomSearchWorker/DicomTree -> Subject and SubjectInputStateList -> configuration gates -> MainWorkflow -> reusable subworkflows -> Nipype interfaces and external tools -> DataSink results and WorkflowReport -> SubjectTab/MainWindow and Slicer`

Names and identities cross several layers. Treat input identities, preference keys, workflow/node names, Traits fields, output filenames, reports, and Slicer mappings as contracts rather than cosmetic labels.

## Repository map

| Area | Responsibility | Important contracts |
|---|---|---|
| `swane/__main__.py` | Startup, Qt lifecycle, single-instance guard, restart loop | Exit code, PID cleanup, `QApplication` lifetime |
| `swane/strings.py` | User-facing labels and messages | Keys referenced by UI, reports, and dependency errors |
| `swane/config/` | Preference metadata, enums, defaults, presets, persistence, validation | Sections, keys, enum names, defaults, requirements |
| `swane/utils/DataInputList.py` | Supported imaging inputs and modality metadata | Enum members, serialized names, parents, volumes, workflow names |
| `swane/utils/Subject.py`, `SubjectInputStateList.py`, `DicomTree.py` | Subject folders, input state, DICOM organization | Folder layout, loaded state, return values, input identities |
| `swane/utils/DependencyManager.py`, `ResourceManager.py` | External tools and host/resource capabilities | Versions, status, environment, RAM/CPU/GPU limits |
| `swane/nipype_pipeline/nodes/` | Custom Nipype interfaces and wrappers | Traits, commands, outputs, paths, disclaimers |
| `swane/nipype_pipeline/workflows/` | Reusable analysis graphs | Factory signatures, boundary nodes, connections, filenames |
| `swane/nipype_pipeline/MainWorkflow.py` | Subject-level orchestration | Feature gates, cross-workflow connections, result sinks, resources |
| `swane/nipype_pipeline/engine/` | Graph inspection, monitored execution, scheduling, reporting | Node metadata, memory estimates, process/GPU slots, signals |
| `swane/workers/` | Background operations and process boundaries | Qt signals, queues, callbacks, subprocess and cleanup semantics |
| `swane/ui/` | Main window, subject tabs, preferences, progress, tool views | Widget state, signal connections, non-blocking behavior |
| `swane/tests/` | Integration-oriented regression suite and fixtures | External prerequisites, temporary paths, graph/name expectations |
| `setup.py`, `MANIFEST.in`, `swane/__init__.py` | Packaging and version | Python floor, dependencies, entry point, included files |
| `README.md`, `NOTICE.md`, `.github/` | User docs, attribution, automation | Platforms/tools, changelog, licensing, Black workflow |

## Change routing

| Requested change | Inspect first | Then read |
|---|---|---|
| New imaging input or analysis | `DataInputList`, subject/input state, preference catalog, `MainWorkflow`, result consumers | All three thematic references |
| Workflow factory, node, output, registration, segmentation | Parent/child graph connections and current tests | [workflows-and-nipype.md](workflows-and-nipype.md) |
| CPU, RAM, GPU, process, cache, or execution report | `MainWorkflow`, engine, `WorkflowProcess`, monitoring | [workflows-and-nipype.md](workflows-and-nipype.md) and, for GUI delivery, [ui-and-workers.md](ui-and-workers.md) |
| Global or subject preference, preset, dependency, validation | Catalog, `ConfigManager`, runtime consumers | [configuration-and-preferences.md](configuration-and-preferences.md) |
| Preferences window or setup wizard | Preference schema plus UI generator | [configuration-and-preferences.md](configuration-and-preferences.md) |
| General GUI state, worker, callback, Slicer action | State owner, signal producer/consumer, shutdown path | [ui-and-workers.md](ui-and-workers.md) |
| External dependency | `setup.py` versus `DependencyManager`, configuration gates, user guidance | Relevant workflow/configuration/UI references |
| Packaging or release | Version, dependencies, manifest, docs, notices | Live packaging files and release history |

## Cross-cutting completion checks

- Trace each changed identifier to every producer and consumer.
- Preserve ownership: schema in config, domain state in models/utilities, analysis in Nipype, presentation in UI.
- Update README/wiki when supported platforms, tools, installation, user workflow, or visible analyses change.
- Update `NOTICE.md` and source disclaimers when derived code or bundled third-party material changes.
- Verify that optional capabilities fail closed or remain disabled when tools, inputs, resources, or requirements are missing.
- Avoid adding package data, test artifacts, logs, caches, local configuration, or clinical data to distributions.

## Validation routing

| Change | Minimum focused evidence | Broader evidence when available |
|---|---|---|
| Utility/config logic | Import/compile plus targeted pytest | Config, subject, or DICOM test module |
| Preference/input identity | Persistence/default test plus graph construction | Preference UI and workflow enablement tests |
| Nipype interface | Trait/output test and mocked failure edges | Real external-tool smoke test |
| Workflow connections/names | Construct graph and assert nodes/connections/outputs | `integration/test_workflow.py` with required tools |
| GUI/worker | Signal/state test with `pytest-qt` | Complete GUI workflow with a display |
| Scientific algorithm/flags | Synthetic fixture comparison | Representative workflow comparison and domain review |
| Packaging/release | Version/import/build-content check | Clean-environment installation smoke test |

The light suite (`config/`, `utils/`, `workers/`, `ui/`) uses disposable `tmp_path` fixtures and needs no external tools. The `integration/` fixtures use `TEST_DIR = ~/test_swane` (defined in `swane/tests/__init__.py`) and delete/recreate task-specific subdirectories. Resolve that path before execution. `integration/test_complete_workflow.py` also reads the configured working directory to find `subj_test`; never substitute real clinical data for this fixture.
