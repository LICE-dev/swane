# License consent gate — design

- **Date:** 2026-08-23
- **Status:** Draft (approved in brainstorming, pending spec review)
- **Topic:** Explicit, blocking acceptance of the licenses of the external tools SWANe orchestrates (FSL, FreeSurfer, 3D Slicer, dcm2niix), shown at startup after the first-run wizard.

## 1. Context and problem

SWANe's own code is MIT-licensed, but at runtime SWANe cannot do useful work
without invoking external neuroimaging tools that carry their own, more
restrictive licenses. Today SWANe does not surface those licenses to the user at
all, and does not make the user acknowledge that using SWANe means complying with
them.

We want a first step toward a future "complete install" (e.g. a Docker image that
bundles FSL and FreeSurfer): make it explicit that SWANe **uses** these tools and
that the user must comply with each tool's license. For now we do **not** claim to
install or redistribute those tools — we only display their licenses and require
acceptance.

SWANe already invokes these external tools as separate processes; this design
does not change that and does not embed any tool-derived code (see `NOTICE.md`
and the project licensing rules).

## 2. Legal framing (must be reflected in the UI text and NOTICE.md)

- **FreeSurfer** is distributed under the *FreeSurfer Software License Agreement*,
  a custom license that is free but restricts commercial use and requires
  registration for a license key. **The exact current license text/name must be
  verified against the official source during implementation** — do not hardcode a
  license name from memory.
- **FSL** uses the *FMRIB Software Library License*: free for academic/non-commercial
  use; commercial use requires a separate license from Oxford University Innovation.
  It is not OSI open-source.
- **3D Slicer** (BSD-style contribution license) and **dcm2niix** (BSD 2-Clause)
  are more permissive but are still shown for consistency and completeness.
- Both FSL and FreeSurfer restrict **clinical and commercial** use. This aligns
  with SWANe's own stance ("research tool, not a medical device"). The consent
  dialog must make this consequence explicit **outside** the raw license text (see
  the fixed banner in §5.4).
- **Redistribution posture:** SWANe never ships FSL/FreeSurfer code. This design
  ships only *fallback copies of license text* (see §5.3) as a last-resort display
  source when the user's installed copy is absent and the network is unavailable.
  Displaying license text is permitted; embedding tool code is not.

## 3. Goals and non-goals

### Goals
- Show, at startup, the license of every external tool SWANe **has actually
  detected**, and require explicit acceptance before the app is usable.
- Re-prompt automatically, and only for the affected tool, when that tool's
  detected version changes or a newly detected tool appears.
- Display the license text that matches the installed tool version when possible.
- Prominently state the non-clinical / non-commercial constraint outside the
  license text.

### Non-goals (out of scope for this change)
- Installing or bundling FSL/FreeSurfer themselves (future Docker work).
- Any per-user identity, audit log, or server-side record of acceptance.
- A manual, maintainer-forced re-acceptance constant (explicitly dropped — see §4).
- Covering tools other than FSL, FreeSurfer, 3D Slicer, dcm2niix.

## 4. Consent model — per-tool, keyed by detected version

Acceptance is tracked **per tool**, keyed by the tool's **detected version string**
(as reported by `DependencyManager`). There is **no** manually maintained
`LICENSE_CONSENT_VERSION` constant — re-acceptance is entirely automatic.

Persisted state (global config, `GlobalPrefCategoryList.MAIN`): a mapping from tool
to the version whose license the user accepted, e.g. conceptually:

```
accepted_licenses = { "fsl": "6.0.6", "freesurfer": "7.3.2", "slicer": "5.6.2", "dcm2niix": "v1.0.20220720" }
```

**Storage decision:** use **discrete per-tool preference keys** in the MAIN category
(e.g. `accepted_license_version_fsl`, `..._freesurfer`, `..._slicer`, `..._dcm2niix`),
following the existing string-valued `PreferenceEntry` pattern (like `slicer_version`).
The tool set is fixed and known, so discrete keys avoid serializing a dict into the
INI config. (Alternative considered: a single JSON-encoded blob key — rejected as
heavier than the existing pattern.)

**When is a tool's license shown?** For each tool `T` that is currently **detected**:

- show `T` if there is no stored accepted version for `T`, **or**
- the stored accepted version ≠ `T`'s currently detected version.

This single rule covers every case:
- New tool detected later (e.g. Slicer configured in the wizard) → no stored value → shown.
- Tool upgraded (FSL 6.0.1 → 6.0.6) → stored ≠ detected → shown.
- Unchanged, already accepted → not shown.

**Undeterminable version (edge E1):** if a tool is detected but `DependencyManager`
cannot parse its version, use the sentinel `"unknown"` as the key. The license is
shown once and stored as accepted for `"unknown"`. If the version later becomes
known and differs, the rule re-prompts. (Confirmed decision.)

## 5. Components

### 5.1 License registry — `swane/utils/LicenseReference.py` (new module)

A single-purpose module describing each tool's license for display. For each tool
(FSL, FreeSurfer, 3D Slicer, dcm2niix):

- `display_name` (e.g. "FSL", "FreeSurfer")
- `official_license_url` — used both to fetch text online and as a shown link
- `installed_license_paths()` — resolver returning candidate on-disk paths of the
  installed license file, per tool and OS (e.g. under `$FREESURFER_HOME`, `$FSLDIR`,
  the Slicer install dir; dcm2niix commonly ships no local license file). Must not
  invent paths — confirm real locations during implementation.
- `bundled_license_path` — path to the fallback copy under `swane/licenses/<tool>.txt`.

The registry is keyed by the existing `Package` enum (`swane/utils/ToolReference.py`)
where possible to avoid a second source of truth for tool identity.

### 5.2 Detection glue — reuse `DependencyManager`

`MainWindow` already builds a `DependencyManager` and calls
`global_config.check_dependencies(...)` ([MainWindow.py:53-54](../../../swane/ui/MainWindow.py#L53-L54)).
The gate consumes it to learn **which tools are detected and their versions**. The
exact per-tool version accessor must be confirmed in code during implementation
(FSL/FreeSurfer/Slicer expose version info via `DependencyManager`; verify the
dcm2niix accessor).

### 5.3 License-text resolution chain (edge E7)

For each tool to be shown, resolve the display text in this order, recording which
source was used so the UI can warn the user:

1. **Installed copy** — read the on-disk license file from the user's installation
   (version-accurate). Source = `installed`, no warning.
2. **Online copy** — if no installed file is found, fetch the current license text
   from the official repo/site (`official_license_url`). Source = `online`, warning
   banner: "Installed license file not found; showing X's current online license,
   which may differ from your installed version."
3. **Bundled fallback** — if the fetch fails (offline / URL changed), display the
   repo copy at `swane/licenses/<tool>.txt`. Source = `bundled`, warning banner:
   same intent, noting it is a bundled copy that may be outdated.

The **online fetch must be bounded** (short timeout, run without freezing the UI)
and must degrade to the bundled copy on any failure. Network access here is a
best-effort freshness optimization, never a hard dependency.

**Release tooling:** add a maintenance script (repo tooling, not shipped runtime)
that refreshes `swane/licenses/*.txt` from the official upstream sources, to be run
before each release so the bundled fallback stays current. Details (location,
invocation) to be defined in the implementation plan.

### 5.4 Consent gate UI — sequential wizard

A modal, blocking dialog shown at startup (see §5.5 for trigger). Presentation is a
**sequential wizard**, one page per tool that needs (re)consent — not tabs:

- **Fixed header banner on every page** (outside the license text), stating the
  non-clinical / non-commercial constraint. Final English wording TBD in `strings.py`;
  intent:
  > "SWANe is a research tool — not a medical device. The underlying tools (FSL,
  > FreeSurfer, …) are licensed for non-clinical, non-commercial use only. By
  > accepting, you agree to comply with each tool's license and to use SWANe
  > accordingly."
- **Body:** the resolved license text in a scrollable view, plus the source-warning
  banner from §5.3 when the source is `online` or `bundled`.
- **Progress indicator:** e.g. "License 2 of 3".
- **`I ACCEPT` button:** disabled until the user has scrolled the current license to
  the bottom; on click it advances to the next tool's page.
- **Final page:** `I ACCEPT` confirms and closes the gate.
- **Decline / closing the dialog** at any point → **the application exits** (no
  partial state saved).
- **Atomic commit (confirmed):** the accepted-version map is persisted **only after
  the entire flow completes**. Closing midway saves nothing; the next launch
  re-prompts all pending tools.

Reuse the existing Qt patterns / wizard conventions from
[PreferenceWizardWindow](../../../swane/ui/PreferenceWizardWindow.py) for consistency.
All user-visible strings go in [strings.py](../../../swane/strings.py), in English.

### 5.5 Trigger point — after the first-run wizard

In `MainWindow.__init__`, the gate runs **after** `start_preference_wizard()`
([MainWindow.py:82-83](../../../swane/ui/MainWindow.py#L82-L83)) so that a Slicer path
configured in the wizard is detected first. Because the wizard may change detected
tools, **re-run dependency detection** (or otherwise refresh the `DependencyManager`)
before evaluating which licenses to show. Confirm during implementation whether the
wizard already refreshes detection or whether an explicit `check_dependencies` call
is needed.

Empty case (edge Q4): if **no** tool is detected, no page is shown and the gate is a
no-op; when a tool is later detected, the §4 rule shows only that tool.

### 5.6 NOTICE.md, packaging, strings

- **NOTICE.md:** add a section documenting that SWANe orchestrates FSL, FreeSurfer,
  3D Slicer and dcm2niix under their own licenses (with the FreeSurfer license
  statement from §2), and that bundled fallback license copies live in
  `swane/licenses/`. Do not claim SWANe redistributes the tools themselves.
- **Packaging:** include `swane/licenses/*.txt` via `MANIFEST.in` and `setup.py`
  (`package_data`) so the bundled fallback ships in the wheel/sdist.
- **Strings:** all new UI text in `strings.py`, English only.

## 6. Data flow (per startup)

1. `MainWindow.__init__` builds `DependencyManager`, runs the working-dir check and,
   if needed, the preference wizard.
2. Detection is refreshed post-wizard.
3. For each detected tool, apply the §4 rule to build the list of tools needing consent.
4. For each such tool, resolve license text via the §5.3 chain (installed → online →
   bundled), tagging the source.
5. If the list is non-empty, show the sequential gate (§5.4). On full completion,
   persist the accepted detected-version for each shown tool (atomic).
6. On decline/close, exit the application.

## 7. Error handling and edge cases

- **Offline + no installed file:** falls through to the bundled copy (§5.3 step 3);
  the app remains usable and the user still sees a license.
- **Version undeterminable:** sentinel `"unknown"` (§4, E1).
- **No tools detected:** gate is a no-op (§5.5).
- **User declines:** application exits; nothing persisted.
- **Partial completion:** nothing persisted (atomic commit, §5.4).
- **Online fetch slow/hanging:** bounded and non-blocking; degrades to bundled.

## 8. Testing strategy (must pass on Linux and macOS)

Follow the `swane-dev-assistant` suite conventions. Prioritize logic that can be
tested without a live GUI:

- **Consent rule (§4):** given a stored map and a set of detected tools/versions,
  the correct subset is selected for consent (new tool, upgraded tool, unchanged,
  `"unknown"` sentinel transitions).
- **Resolution chain (§5.3):** installed present → `installed`; installed absent +
  online ok → `online` + warning; both absent → `bundled` + warning. Network is
  mocked; no real HTTP in tests.
- **Storage:** per-tool keys round-trip through the config; atomic commit writes
  nothing on partial/declined flows.
- **Registry:** each tool has a bundled fallback file present and non-empty.
- GUI scroll-to-enable / sequential advance is UI behavior; cover the underlying
  state logic and, where feasible, a headless widget-level check. Manual
  verification on both OSes for the actual scroll/accept interaction.

Tests are software-regression evidence only, never clinical/scientific validation.

## 9. Future work (explicitly deferred)

- Docker "complete install" bundling FSL/FreeSurfer; at that point the bundled
  license copies become the controlled primary source.
- Optional trigger on a change in the *displayed license text itself* (hash-based),
  for the rare case where a tool's license changes without a version bump.
- Extending coverage to additional orchestrated tools if needed.

## 10. Open items to confirm during implementation

- Exact current FreeSurfer license name/text and official URL (§2).
- Real on-disk license file locations per tool and OS (§5.1).
- Per-tool version accessors on `DependencyManager`, especially dcm2niix (§5.2).
- Whether the wizard already refreshes detection or an explicit re-check is needed (§5.5).
