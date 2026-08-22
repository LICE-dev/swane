# SWANe configuration and preferences

Read this reference for global or subject settings, preference metadata, presets, validation, dependency gates, preference-specific UI, setup wizard behavior, persisted compatibility, or secrets.

## Contents

- [Configuration scopes](#configuration-scopes)
- [Schema and catalogs](#schema-and-catalogs)
- [Load, validation, reset, and persistence](#load-validation-reset-and-persistence)
- [Preference requirements and runtime enforcement](#preference-requirements-and-runtime-enforcement)
- [Preference UI and wizard ownership](#preference-ui-and-wizard-ownership)
- [Secrets](#secrets)
- [Adding or changing a preference](#adding-or-changing-a-preference)
- [Verification](#verification)

## Configuration scopes

- `ConfigManager()` creates the global configuration. By default it persists to `~/.SWANe`; tests may supply `global_base_folder` to isolate it.
- `ConfigManager(subject_folder=...)` creates subject configuration at `<subject_folder>/.config`.
- Global configuration owns `GLOBAL_PREFERENCES` and the global copies of workflow defaults. Subject configuration owns per-subject `WF_PREFERENCES`, applies the selected `DEFAULT_WF` preset, and retains version/reset compatibility fields under the main category.
- Treat global and subject configuration as different scopes. Never write a subject-specific analysis choice into the global catalog or a machine-wide capability into a subject file without an explicit design change.
- Be aware that current subject-default initialization creates a global `ConfigManager` to copy workflow defaults. Avoid introducing recursive construction or unexpected writes around this lifecycle.

## Schema and catalogs

- Treat `PreferenceEntry` as the declarative schema for loading, validation, UI generation, and behavior.
- Define machine/application-wide entries in `GLOBAL_PREFERENCES`, analysis-specific entries in `WF_PREFERENCES`, and workflow-type presets in `DEFAULT_WF`.
- Use `GlobalPrefCategoryList`, `DataInputList`, and the enums in `config_enums.py` as typed identifiers. Persist enum member names, not display labels.
- Preserve category names, preference keys, and enum member names once released. They are serialized contracts; rename only with a migration or explicit compatibility fallback.
- Keep the default in the correct type expected by `PreferenceEntry` and `ConfigManager`; enums are serialized through `.name`, while other values are stored as strings.

Use `PreferenceEntry` metadata rather than ad hoc UI/runtime checks:

- `input_type`, `value_enum`, `default`, `range`, `decimals`, `special_value_text`, and `suffix` define value semantics.
- `label`, `tooltip`, `informative_text`, `box_text`, `hidden`, and `section` define presentation metadata.
- `dependency` and `resource` bind availability to `DependencyManager` or `ResourceManager` callables.
- `pref_requirement` and `input_requirement` define cross-preference and input prerequisites.
- `option_dependency`, `option_pref_requirement`, and their tooltips gate individual enum options.
- `restart`, `validate_on_change`, and `default_at_startup` define lifecycle behavior.

## Load, validation, reset, and persistence

`ConfigManager` follows this lifecycle:

1. Resolve global (`~/.SWANe` or test override) versus subject (`.config`) scope.
2. Load schema defaults into `_section_defaults` and the in-memory `ConfigParser`.
3. Evaluate `force_pref_reset` and `last_swane_version` compatibility.
4. Read an existing file when it remains compatible.
5. Reassign known values through `set` so `validate_type` normalizes them; restore `default_at_startup` values instead of the persisted value.
6. Update version metadata and save.

- Use `getboolean_safe`, `getint_safe`, `getfloat_safe`, and `getenum_safe` for typed reads. Keep invalid-value fallback behavior covered by tests.
- Use `ConfigManager.set` or section assignment compatible with the existing schema. Do not bypass normalization for user-editable values.
- Preserve unknown-version/reset behavior deliberately. A change to `force_pref_reset` can discard user choices across every category.
- Use `reset_to_defaults` only for the intended scope and preserve the confirmation flow in `PreferencesWindow`/`SubjectTab`.
- Treat `set_workflow_option` as a subject-only preset application. Keep `DEFAULT_WF` complete and coherent for every supported `WorkflowTypes` member.
- Save only after a coherent set of changes; avoid exposing partially updated dependent values to runtime consumers.

## Preference requirements and runtime enforcement

- Treat UI disablement as guidance, not the sole enforcement layer.
- `PreferencesWindow` evaluates external dependencies, resources, cross-preference requirements, input requirements, and option-level requirements for presentation.
- `ConfigManager.check_dependencies` sanitizes subject workflow choices when dependencies or resources are unavailable. Keep this runtime enforcement aligned with the catalog metadata.
- Ensure requirement callables exist on the declared owner and return the expected boolean contract.
- When one preference changes another preference's availability, connect the UI update and verify the persisted result remains valid after reload.
- For `validate_on_change`, preserve the `<key>_validation` companion flag and mark it when the user changes the field. Trace the worker or dependency check that consumes it.
- Optional-series preferences are derived from optional `DataInputList` entries. Adding an optional input can create a new global toggle automatically; verify its default and downstream behavior.

## Preference UI and wizard ownership

- Keep preference-specific widgets and interactions under this reference, even though their files live in `swane/ui/`.
- `PreferencesWindow` selects global or subject catalogs, builds rows, evaluates requirements, saves only changed entries, and returns a restart/reset result to its caller.
- `PreferenceUIEntry` maps `InputTypes` to Qt widgets, loads typed values, applies ranges and enum data, tracks changes, encrypts password fields, and marks restart-required edits.
- `PreferenceWizardWindow` owns first-run choices and applies performance profiles, CUDA/Synth settings, working folders, and workflow defaults through `ConfigManager`.
- Avoid duplicating preference validation in ad hoc dialogs. Extend `PreferenceEntry` metadata and the shared generators when a new input type or requirement is broadly useful.
- Keep display labels separate from persisted values. Enum UI labels come from `.value`, while storage and comparisons use `.name`.
- Update user-facing text through `strings.py` and preserve restart behavior for settings that cannot be applied safely at runtime.

## Secrets

- Treat stored mail passwords as secrets even though they live in the configuration file rather than source control.
- `PreferenceUIEntry` encrypts password text when editing finishes; `ConfigManager.get_mail_manager` and the mail-test flow decrypt only at the point of use.
- Never log, display, commit, include in fixtures, or return decrypted values in diagnostics.
- The current encryption key is derived from machine identity. Do not assume an encrypted configuration is portable to another machine; handle decryption/migration failures explicitly when changing this behavior.
- Do not replace this mechanism or change ciphertext format as a side effect of unrelated preference work.

## Adding or changing a preference

1. Choose global versus subject/workflow scope and the stable category/key.
2. Add or reuse the required enum/category identifier.
3. Define `PreferenceEntry` metadata and a type-correct default in the proper catalog.
4. Update `DEFAULT_WF` if the preference participates in workflow presets.
5. Trace load, normalization, version/reset, and persisted compatibility.
6. Trace preference UI rendering, requirements, validation flags, restart behavior, and wizard defaults.
7. Trace every runtime consumer in `MainWorkflow`, workflow factories, `Subject`, `SubjectTab`, workers, and utilities.
8. Add focused tests for defaults, persistence, invalid values, reset/upgrade, dependencies, and runtime consumption.
9. Update README/wiki when the option is user-visible or changes resource/tool requirements.

## Verification

- Isolate global configuration with `global_base_folder`; never run preference tests against the user's real `~/.SWANe`.
- Use a disposable subject folder for `.config` tests and verify its resolved path before cleanup.
- Cover global default, persistence, invalid-value, reset, and version behavior in `swane/tests/config/` (e.g. `test_config_manager.py`, `test_preferences.py`).
- Add subject-level tests for workflow defaults, preset application, dependency sanitation, and optional-series behavior.
- Use `pytest-qt` for widget type, enum label/name mapping, range, enable/disable, validation-flag, restart, save, reset, and secret-display behavior.
- Verify at least one real runtime consumer so a catalog-only change cannot pass while the analysis ignores the preference.
- Inspect generated configuration without exposing secrets and confirm unrelated persisted values survive reload or upgrade.
