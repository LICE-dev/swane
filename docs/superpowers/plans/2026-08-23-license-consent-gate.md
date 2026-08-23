# License Consent Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** At startup (after the first-run wizard), require the user to explicitly accept the licenses of every external tool SWANe has detected (FSL, FreeSurfer, 3D Slicer, dcm2niix), re-prompting automatically and per-tool whenever a tool's detected version changes or a new tool appears.

**Architecture:** A small pure-logic core (a license registry, a text-resolution chain, and a consent-evaluation function) drives a sequential Qt consent dialog. Consent is persisted per tool keyed by the detected tool version in the global config; the dialog only collects acceptance and the caller persists it atomically after the whole flow completes. The gate is invoked from `__main__` right after `MainWindow` construction (so the wizard has already run); declining aborts startup before the event loop starts.

**Tech Stack:** Python 3.10+, PySide6 (Qt), nipype `Info` classes for tool versions, `urllib` for the online license fetch, pytest + pytest-qt for tests.

**Spec:** `docs/superpowers/specs/2026-08-23-license-consent-gate-design.md`

## Global Constraints

- All code, comments, docstrings and UI strings in **English**.
- Terminology: SWANe is a **research tool, not a medical device**; never "patient" (use "subject"). No clinical/medical use implied anywhere.
- Never embed external-tool *code*; this feature only *displays* license text. Bundled license text is display data, not tool code.
- Never display the user's FreeSurfer registration key file (`FS_LICENSE`, `~/license.txt`, `$FREESURFER_HOME/.license`) — that is a personal key, not the legal license. The legal license lives elsewhere (see Task 2).
- Preserve existing stable contracts: persisted preference keys, enum member names, workflow/node names, signals, result filenames.
- Start work on branch `claude/license-consent-gate` (already created). Do **not** commit/push/merge/PR unless the user explicitly asks — the plan's `git commit` steps are to be run only with that standing permission; otherwise stage the change and report.
- A change is complete only after the relevant tests are run and reviewed, and the code is shown to work on both Linux and macOS. GUI tests gate on `QT_AVAILABLE`.
- Canonical tool ids used as consent keys and registry keys: `"fsl"`, `"freesurfer"`, `"slicer"`, `"dcm2niix"`.
- Official license sources (verified 2026-08-23):
  - FSL: `https://fsl.fmrib.ox.ac.uk/fsl/docs/license.html` (HTML)
  - FreeSurfer: `https://raw.githubusercontent.com/freesurfer/freesurfer/dev/LICENSE.txt` (plain text; the *legal* agreement, not the user key)
  - 3D Slicer: `https://raw.githubusercontent.com/Slicer/Slicer/main/License.txt` (plain text)
  - dcm2niix: `https://raw.githubusercontent.com/rordenlab/dcm2niix/master/license.txt` (plain text)

---

## File Structure

- `swane/config/preference_list.py` (modify) — 4 hidden MAIN prefs storing the accepted version per tool.
- `swane/config/ConfigManager.py` (modify) — `get_accepted_license_version` / `set_accepted_license_version`.
- `swane/utils/LicenseReference.py` (create) — tool-id constants + `LicenseInfo` registry + bundled-path helper.
- `swane/licenses/*.txt` (create) — bundled fallback license copies.
- `tools/refresh_bundled_licenses.py` (create) — release-time refresh of the bundled copies from upstream.
- `swane/utils/license_consent.py` (create) — text resolution chain + detected-version extraction + `tools_needing_consent`.
- `swane/ui/LicenseConsentWindow.py` (create) — sequential consent dialog.
- `swane/strings.py` (modify) — English UI strings for the gate.
- `swane/ui/MainWindow.py` (modify) — `run_license_consent_gate()` method.
- `swane/__main__.py` (modify) — invoke the gate; abort startup on decline.
- `NOTICE.md` (modify) — document orchestrated tools + bundled fallbacks.
- `setup.py` / `MANIFEST.in` (modify) — ship `swane/licenses/*.txt`.
- Tests: `swane/tests/utils/test_license_reference.py`, `swane/tests/utils/test_license_consent.py`, `swane/tests/ui/test_license_consent_window.py`, and additions to a config test module.

---

### Task 1: Per-tool consent storage

**Files:**
- Modify: `swane/config/preference_list.py` (MAIN category block, near `last_swane_version` at ~L517)
- Modify: `swane/config/ConfigManager.py` (near `get_slicer_version`/`set_slicer_version`, ~L318-338)
- Test: `swane/tests/utils/test_license_consent_storage.py`

**Interfaces:**
- Consumes: `GlobalPrefCategoryList.MAIN`, `PreferenceEntry`, `config[...]` item access, `config.save()`.
- Produces:
  - Pref keys `accepted_license_fsl`, `accepted_license_freesurfer`, `accepted_license_slicer`, `accepted_license_dcm2niix` (string, default `""`, `hidden=True`).
  - `ConfigManager.get_accepted_license_version(tool_id: str) -> str` (returns `""` if unset/unknown tool).
  - `ConfigManager.set_accepted_license_version(tool_id: str, tool_version: str) -> None`.

- [ ] **Step 1: Write the failing test**

```python
# swane/tests/utils/test_license_consent_storage.py
def test_accepted_license_version_roundtrip(global_config):
    assert global_config.get_accepted_license_version("fsl") == ""
    global_config.set_accepted_license_version("fsl", "6.0.6")
    assert global_config.get_accepted_license_version("fsl") == "6.0.6"


def test_accepted_license_version_unknown_tool_is_empty(global_config):
    assert global_config.get_accepted_license_version("not_a_tool") == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest swane/tests/utils/test_license_consent_storage.py -v`
Expected: FAIL (`AttributeError: 'ConfigManager' object has no attribute 'get_accepted_license_version'`).

- [ ] **Step 3: Add the preference entries**

In `swane/config/preference_list.py`, inside the `GlobalPrefCategoryList.MAIN` block (right after the `last_swane_version` entry), add:

```python
for _license_tool in ("fsl", "freesurfer", "slicer", "dcm2niix"):
    GLOBAL_PREFERENCES[category]["accepted_license_" + _license_tool] = PreferenceEntry(
        input_type=InputTypes.TEXT,
        label="Accepted license version for " + _license_tool,
        default="",
        hidden=True,
    )
```

(Confirm `category` still refers to `GlobalPrefCategoryList.MAIN` at that point in the file; the MAIN block is the first one.)

- [ ] **Step 4: Add the ConfigManager helpers**

In `swane/config/ConfigManager.py`, after `set_slicer_version`:

```python
def get_accepted_license_version(self, tool_id: str) -> str:
    """
    Return the tool version whose license the user last accepted, or "".

    Parameters
    ----------
    tool_id: str
        Canonical tool id ("fsl", "freesurfer", "slicer", "dcm2niix").
    """
    if not self.global_config:
        return ""
    key = "accepted_license_" + tool_id
    if key not in self[GlobalPrefCategoryList.MAIN]:
        return ""
    return self[GlobalPrefCategoryList.MAIN][key]

def set_accepted_license_version(self, tool_id: str, tool_version: str):
    """
    Store the tool version whose license the user accepted.

    Parameters
    ----------
    tool_id: str
        Canonical tool id ("fsl", "freesurfer", "slicer", "dcm2niix").
    tool_version: str
        The detected tool version accepted by the user.
    """
    if self.global_config:
        self[GlobalPrefCategoryList.MAIN]["accepted_license_" + tool_id] = str(
            tool_version
        )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest swane/tests/utils/test_license_consent_storage.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add swane/config/preference_list.py swane/config/ConfigManager.py swane/tests/utils/test_license_consent_storage.py
git commit -m "feat: add per-tool license consent storage"
```

---

### Task 2: License registry + bundled fallback copies + refresh tool

**Files:**
- Create: `swane/utils/LicenseReference.py`
- Create: `swane/licenses/fsl.txt`, `swane/licenses/freesurfer.txt`, `swane/licenses/slicer.txt`, `swane/licenses/dcm2niix.txt`
- Create: `tools/refresh_bundled_licenses.py`
- Test: `swane/tests/utils/test_license_reference.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - Constants `FSL, FREESURFER, SLICER, DCM2NIIX` (str) and `TOOL_IDS` (tuple).
  - `LicenseInfo` dataclass with: `tool_id: str`, `display_name: str`, `official_url: str`, `is_html_online: bool`, `installed_path_candidates(context: dict) -> list[str]`, `bundled_filename: str`.
  - `LICENSES: dict[str, LicenseInfo]` keyed by tool id.
  - `bundled_license_path(info: LicenseInfo) -> str` (absolute path under `swane/licenses/`).

- [ ] **Step 1: Write the failing test**

```python
# swane/tests/utils/test_license_reference.py
import os
from swane.utils import LicenseReference as LR


def test_registry_has_all_tools():
    assert set(LR.LICENSES) == set(LR.TOOL_IDS)
    assert set(LR.TOOL_IDS) == {"fsl", "freesurfer", "slicer", "dcm2niix"}


def test_each_tool_has_url_and_bundled_file():
    for tool_id, info in LR.LICENSES.items():
        assert info.official_url.startswith("http")
        path = LR.bundled_license_path(info)
        assert os.path.isfile(path), f"missing bundled license for {tool_id}: {path}"
        with open(path, encoding="utf-8", errors="replace") as fh:
            assert fh.read().strip(), f"empty bundled license for {tool_id}"


def test_freesurfer_candidates_exclude_user_key_file(monkeypatch):
    monkeypatch.setenv("FREESURFER_HOME", "/opt/freesurfer")
    candidates = LR.LICENSES["freesurfer"].installed_path_candidates({})
    # The legal license, never the per-user registration key files
    assert any(c.endswith("LICENSE.txt") for c in candidates)
    assert all(not c.endswith(".license") for c in candidates)
    assert all(os.path.basename(c) != "license.txt" for c in candidates)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest swane/tests/utils/test_license_reference.py -v`
Expected: FAIL (`ModuleNotFoundError: swane.utils.LicenseReference`).

- [ ] **Step 3: Create the registry module**

```python
# swane/utils/LicenseReference.py
"""Static registry describing how to locate/display each external tool's license.

This module only points at license *text* for display. It never references any
external tool's source code, and never points FreeSurfer at the per-user
registration key file (that is a personal secret, not the legal license).
"""

import os
from dataclasses import dataclass
from typing import Callable

FSL = "fsl"
FREESURFER = "freesurfer"
SLICER = "slicer"
DCM2NIIX = "dcm2niix"
TOOL_IDS = (FSL, FREESURFER, SLICER, DCM2NIIX)

_BUNDLED_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "licenses")


@dataclass(frozen=True)
class LicenseInfo:
    tool_id: str
    display_name: str
    official_url: str
    is_html_online: bool
    installed_path_candidates: Callable[[dict], list]
    bundled_filename: str


def bundled_license_path(info: "LicenseInfo") -> str:
    return os.path.normpath(os.path.join(_BUNDLED_DIR, info.bundled_filename))


def _fsl_candidates(context: dict) -> list:
    fsldir = os.environ.get("FSLDIR", "")
    if not fsldir:
        return []
    return [
        os.path.join(fsldir, "LICENSE"),
        os.path.join(fsldir, "LICENCE"),
        os.path.join(fsldir, "LICENSE.txt"),
    ]


def _freesurfer_candidates(context: dict) -> list:
    # The LEGAL license text shipped with FreeSurfer, never the user key file.
    fs_home = os.environ.get("FREESURFER_HOME", "")
    if not fs_home:
        return []
    return [
        os.path.join(fs_home, "LICENSE.txt"),
        os.path.join(fs_home, "LICENSE"),
        os.path.join(fs_home, "docs", "LICENSE.txt"),
    ]


def _slicer_candidates(context: dict) -> list:
    slicer_path = context.get("slicer_path", "")
    if not slicer_path:
        return []
    base = os.path.dirname(os.path.abspath(slicer_path))
    return [
        os.path.join(base, "License.txt"),
        os.path.join(base, "LICENSE.txt"),
        os.path.join(base, "share", "License.txt"),
    ]


def _dcm2niix_candidates(context: dict) -> list:
    # dcm2niix is typically a single binary with no local license file.
    return []


LICENSES = {
    FSL: LicenseInfo(
        tool_id=FSL,
        display_name="FSL (FMRIB Software Library)",
        official_url="https://fsl.fmrib.ox.ac.uk/fsl/docs/license.html",
        is_html_online=True,
        installed_path_candidates=_fsl_candidates,
        bundled_filename="fsl.txt",
    ),
    FREESURFER: LicenseInfo(
        tool_id=FREESURFER,
        display_name="FreeSurfer",
        official_url="https://raw.githubusercontent.com/freesurfer/freesurfer/dev/LICENSE.txt",
        is_html_online=False,
        installed_path_candidates=_freesurfer_candidates,
        bundled_filename="freesurfer.txt",
    ),
    SLICER: LicenseInfo(
        tool_id=SLICER,
        display_name="3D Slicer",
        official_url="https://raw.githubusercontent.com/Slicer/Slicer/main/License.txt",
        is_html_online=False,
        installed_path_candidates=_slicer_candidates,
        bundled_filename="slicer.txt",
    ),
    DCM2NIIX: LicenseInfo(
        tool_id=DCM2NIIX,
        display_name="dcm2niix",
        official_url="https://raw.githubusercontent.com/rordenlab/dcm2niix/master/license.txt",
        is_html_online=False,
        installed_path_candidates=_dcm2niix_candidates,
        bundled_filename="dcm2niix.txt",
    ),
}
```

- [ ] **Step 4: Create the refresh tool and fetch the real bundled copies**

Create `tools/refresh_bundled_licenses.py`:

```python
#!/usr/bin/env python3
"""Refresh the bundled fallback license copies from upstream.

Run before a release so swane/licenses/*.txt stays current. This only fetches
license *text* for display; it does not fetch or vendor any tool source code.
"""

import os
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from swane.utils.LicenseReference import LICENSES, bundled_license_path  # noqa: E402


def main() -> int:
    for tool_id, info in LICENSES.items():
        dest = bundled_license_path(info)
        print(f"Fetching {tool_id} license from {info.official_url}")
        with urllib.request.urlopen(info.official_url, timeout=30) as resp:
            data = resp.read()
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as fh:
            fh.write(data)
        print(f"  wrote {dest} ({len(data)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Then create the `swane/licenses/` directory and populate the real copies:

```bash
mkdir -p swane/licenses
python tools/refresh_bundled_licenses.py
```

Verify each file is non-empty and looks like a license (spot-check `swane/licenses/freesurfer.txt` contains "FreeSurfer Software License"). If a URL is unreachable in the build environment, download it manually into the same path; the file must exist and be non-empty.

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest swane/tests/utils/test_license_reference.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add swane/utils/LicenseReference.py swane/licenses tools/refresh_bundled_licenses.py swane/tests/utils/test_license_reference.py
git commit -m "feat: add license registry, bundled fallbacks and refresh tool"
```

---

### Task 3: License text resolution chain

**Files:**
- Create: `swane/utils/license_consent.py` (resolution part)
- Test: `swane/tests/utils/test_license_consent.py` (resolution cases)

**Interfaces:**
- Consumes: `LicenseReference.LICENSES`, `LicenseInfo`, `bundled_license_path` (Task 2).
- Produces:
  - `class LicenseSource(Enum): INSTALLED; ONLINE; BUNDLED`
  - `@dataclass ResolvedLicense: tool_id: str; display_name: str; text: str; is_html: bool; source: LicenseSource`
  - `fetch_online_license(url: str, is_html_online: bool, timeout: float = 8.0) -> tuple | None` returning `(text, is_html)` or `None` on any failure.
  - `resolve_license_text(info: LicenseInfo, context: dict, timeout: float = 8.0) -> ResolvedLicense`

- [ ] **Step 1: Write the failing test**

```python
# swane/tests/utils/test_license_consent.py
import os
from swane.utils import license_consent as lc
from swane.utils import LicenseReference as LR


def _fake_info(tmp_path, installed=None):
    return LR.LicenseInfo(
        tool_id="fsl",
        display_name="FSL",
        official_url="https://example.invalid/license",
        is_html_online=False,
        installed_path_candidates=lambda ctx: [installed] if installed else [],
        bundled_filename="fsl.txt",
    )


def test_resolve_prefers_installed(tmp_path, monkeypatch):
    installed = tmp_path / "LICENSE"
    installed.write_text("INSTALLED TEXT", encoding="utf-8")
    info = _fake_info(tmp_path, installed=str(installed))
    result = lc.resolve_license_text(info, {})
    assert result.source is lc.LicenseSource.INSTALLED
    assert "INSTALLED TEXT" in result.text


def test_resolve_falls_back_to_online(tmp_path, monkeypatch):
    info = _fake_info(tmp_path, installed=None)
    monkeypatch.setattr(lc, "fetch_online_license", lambda *a, **k: ("ONLINE TEXT", False))
    result = lc.resolve_license_text(info, {})
    assert result.source is lc.LicenseSource.ONLINE
    assert "ONLINE TEXT" in result.text


def test_resolve_falls_back_to_bundled_when_offline(tmp_path, monkeypatch):
    info = _fake_info(tmp_path, installed=None)
    monkeypatch.setattr(lc, "fetch_online_license", lambda *a, **k: None)
    monkeypatch.setattr(LR, "bundled_license_path", lambda i: str(tmp_path / "bundled.txt"))
    (tmp_path / "bundled.txt").write_text("BUNDLED TEXT", encoding="utf-8")
    monkeypatch.setattr(lc, "bundled_license_path", LR.bundled_license_path)
    result = lc.resolve_license_text(info, {})
    assert result.source is lc.LicenseSource.BUNDLED
    assert "BUNDLED TEXT" in result.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest swane/tests/utils/test_license_consent.py -v`
Expected: FAIL (`ModuleNotFoundError: swane.utils.license_consent`).

- [ ] **Step 3: Implement the resolution chain**

```python
# swane/utils/license_consent.py
"""License text resolution and consent evaluation for external tools."""

import os
import urllib.request
from dataclasses import dataclass
from enum import Enum, auto

from swane.utils.LicenseReference import (
    LICENSES,
    LicenseInfo,
    bundled_license_path,
    FSL,
    FREESURFER,
    SLICER,
    DCM2NIIX,
)

UNKNOWN_VERSION = "unknown"


class LicenseSource(Enum):
    INSTALLED = auto()
    ONLINE = auto()
    BUNDLED = auto()


@dataclass
class ResolvedLicense:
    tool_id: str
    display_name: str
    text: str
    is_html: bool
    source: LicenseSource


def _read_first_existing(candidates: list):
    for path in candidates:
        try:
            if path and os.path.isfile(path):
                with open(path, encoding="utf-8", errors="replace") as fh:
                    return fh.read(), path
        except OSError:
            continue
    return None


def fetch_online_license(url: str, is_html_online: bool, timeout: float = 8.0):
    """Fetch license text online. Return (text, is_html) or None on any failure."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            raw = resp.read()
    except Exception:
        return None
    try:
        text = raw.decode("utf-8", errors="replace")
    except Exception:
        return None
    if not text.strip():
        return None
    return text, is_html_online


def resolve_license_text(info: LicenseInfo, context: dict, timeout: float = 8.0) -> ResolvedLicense:
    installed = _read_first_existing(info.installed_path_candidates(context))
    if installed is not None:
        return ResolvedLicense(info.tool_id, info.display_name, installed[0], False, LicenseSource.INSTALLED)

    online = fetch_online_license(info.official_url, info.is_html_online, timeout)
    if online is not None:
        return ResolvedLicense(info.tool_id, info.display_name, online[0], online[1], LicenseSource.ONLINE)

    with open(bundled_license_path(info), encoding="utf-8", errors="replace") as fh:
        bundled_text = fh.read()
    return ResolvedLicense(info.tool_id, info.display_name, bundled_text, False, LicenseSource.BUNDLED)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest swane/tests/utils/test_license_consent.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add swane/utils/license_consent.py swane/tests/utils/test_license_consent.py
git commit -m "feat: add license text resolution chain (installed/online/bundled)"
```

---

### Task 4: Consent evaluation (detected tools + version key)

**Files:**
- Modify: `swane/utils/license_consent.py` (append evaluation functions)
- Test: `swane/tests/utils/test_license_consent.py` (append evaluation cases)

**Interfaces:**
- Consumes: `ConfigManager.get_accepted_license_version` (Task 1); `DependencyManager` detection methods; nipype `Info` version accessors; `LICENSES` (Task 2).
- Produces:
  - `detected_tool_versions(dependency_manager, config) -> dict[str, str]` — for each *detected* tool, `{tool_id: version_or_UNKNOWN_VERSION}`.
  - `tools_needing_consent(dependency_manager, config) -> list[str]` — detected tools whose stored accepted version differs from the current detected version, in `TOOL_IDS` order.
  - Per-tool version helpers `_fsl_version()`, `_freesurfer_version()`, `_dcm2niix_version()` (module-level, monkeypatchable), each returning `str` or `None`.

- [ ] **Step 1: Write the failing test**

```python
# append to swane/tests/utils/test_license_consent.py
import types
from swane.utils import license_consent as lc


class _FakeDM:
    def __init__(self, fsl=True, fs=True, dcm=True):
        self._fsl, self._fs, self._dcm = fsl, fs, dcm
    def is_fsl(self): return self._fsl
    def is_freesurfer(self): return self._fs
    def is_dcm2niix(self): return self._dcm


class _FakeConfig:
    def __init__(self, accepted=None, slicer_path="", slicer_version=""):
        self._accepted = accepted or {}
        self._slicer_path, self._slicer_version = slicer_path, slicer_version
    def get_accepted_license_version(self, tool_id): return self._accepted.get(tool_id, "")
    def get_slicer_path(self): return self._slicer_path
    def get_slicer_version(self): return self._slicer_version


def _patch_versions(monkeypatch, fsl="6.0.6", fs="7.3.2", dcm="v1.0.20241211"):
    monkeypatch.setattr(lc, "_fsl_version", lambda: fsl)
    monkeypatch.setattr(lc, "_freesurfer_version", lambda: fs)
    monkeypatch.setattr(lc, "_dcm2niix_version", lambda: dcm)
    monkeypatch.setattr(lc, "_is_slicer_detected", lambda config: False)


def test_first_run_all_detected_need_consent(monkeypatch):
    _patch_versions(monkeypatch)
    dm, cfg = _FakeDM(), _FakeConfig()
    assert lc.tools_needing_consent(dm, cfg) == ["fsl", "freesurfer", "dcm2niix"]


def test_unchanged_versions_need_no_consent(monkeypatch):
    _patch_versions(monkeypatch)
    dm = _FakeDM()
    cfg = _FakeConfig(accepted={"fsl": "6.0.6", "freesurfer": "7.3.2", "dcm2niix": "v1.0.20241211"})
    assert lc.tools_needing_consent(dm, cfg) == []


def test_upgraded_tool_reprompts_only_that_tool(monkeypatch):
    _patch_versions(monkeypatch, fsl="6.0.7")
    dm = _FakeDM()
    cfg = _FakeConfig(accepted={"fsl": "6.0.6", "freesurfer": "7.3.2", "dcm2niix": "v1.0.20241211"})
    assert lc.tools_needing_consent(dm, cfg) == ["fsl"]


def test_undeterminable_version_uses_sentinel(monkeypatch):
    _patch_versions(monkeypatch, fsl=None)
    dm = _FakeDM(fs=False, dcm=False)
    cfg = _FakeConfig()
    assert lc.detected_tool_versions(dm, cfg) == {"fsl": lc.UNKNOWN_VERSION}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest swane/tests/utils/test_license_consent.py -v`
Expected: FAIL (`AttributeError: module ... has no attribute 'tools_needing_consent'`).

- [ ] **Step 3: Implement evaluation**

Append to `swane/utils/license_consent.py`:

```python
def _fsl_version():
    from nipype.interfaces import fsl
    return fsl.base.Info.version()


def _freesurfer_version():
    from nipype.interfaces import freesurfer
    if freesurfer.base.Info.version() is None:
        return None
    return str(freesurfer.base.Info.looseversion())


def _dcm2niix_version():
    from nipype.interfaces import dcm2nii
    value = dcm2nii.Info.version()
    return None if value is None else str(value)


def _is_slicer_detected(config) -> bool:
    from swane.utils.DependencyManager import DependencyManager
    return DependencyManager.is_slicer(config)


def _norm(value) -> str:
    value = "" if value is None else str(value).strip()
    return value if value else UNKNOWN_VERSION


def detected_tool_versions(dependency_manager, config) -> dict:
    """Return {tool_id: detected_version_or_UNKNOWN} for each detected tool."""
    versions = {}
    if dependency_manager.is_fsl():
        versions[FSL] = _norm(_fsl_version())
    if dependency_manager.is_freesurfer():
        versions[FREESURFER] = _norm(_freesurfer_version())
    if _is_slicer_detected(config):
        versions[SLICER] = _norm(config.get_slicer_version())
    if dependency_manager.is_dcm2niix():
        versions[DCM2NIIX] = _norm(_dcm2niix_version())
    return versions


def tools_needing_consent(dependency_manager, config) -> list:
    """Detected tools whose accepted version differs from the detected version."""
    detected = detected_tool_versions(dependency_manager, config)
    ordered = [FSL, FREESURFER, SLICER, DCM2NIIX]
    needing = []
    for tool_id in ordered:
        if tool_id not in detected:
            continue
        if config.get_accepted_license_version(tool_id) != detected[tool_id]:
            needing.append(tool_id)
    return needing
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest swane/tests/utils/test_license_consent.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add swane/utils/license_consent.py swane/tests/utils/test_license_consent.py
git commit -m "feat: add per-tool license consent evaluation"
```

---

### Task 5: UI strings for the consent gate

**Files:**
- Modify: `swane/strings.py`
- Test: `swane/tests/utils/test_license_strings.py`

**Interfaces:**
- Produces (module-level strings in `swane.strings`), used by Task 6:
  - `license_consent_title`
  - `license_consent_banner` (the fixed non-clinical/non-commercial banner)
  - `license_consent_progress` (format with `{current}` and `{total}`)
  - `license_consent_accept_button`
  - `license_consent_scroll_hint`
  - `license_consent_source_online` (format with `{tool}`)
  - `license_consent_source_bundled` (format with `{tool}`)

- [ ] **Step 1: Write the failing test**

```python
# swane/tests/utils/test_license_strings.py
from swane import strings


def test_license_strings_present_and_english():
    assert "research tool" in strings.license_consent_banner.lower()
    assert "not a medical device" in strings.license_consent_banner.lower()
    assert "{current}" in strings.license_consent_progress
    assert "{total}" in strings.license_consent_progress
    assert "{tool}" in strings.license_consent_source_online
    assert "{tool}" in strings.license_consent_source_bundled
    assert strings.license_consent_accept_button
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest swane/tests/utils/test_license_strings.py -v`
Expected: FAIL (`AttributeError: module 'swane.strings' has no attribute 'license_consent_banner'`).

- [ ] **Step 3: Add the strings**

Append to `swane/strings.py`:

```python
license_consent_title = "Third-party tool licenses"
license_consent_banner = (
    "SWANe is a research tool, not a medical device. The external tools it uses "
    "(FSL, FreeSurfer, 3D Slicer, dcm2niix) are licensed for non-clinical, "
    "non-commercial use only. By accepting, you agree to comply with each tool's "
    "license and to use SWANe accordingly."
)
license_consent_progress = "License {current} of {total}"
license_consent_accept_button = "I ACCEPT"
license_consent_scroll_hint = "Please scroll to the end of the license to continue."
license_consent_source_online = (
    "Installed license file not found for {tool}; showing the current online "
    "license, which may differ from your installed version."
)
license_consent_source_bundled = (
    "Could not load the online license for {tool}; showing a bundled copy that "
    "may differ from your installed version."
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest swane/tests/utils/test_license_strings.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add swane/strings.py swane/tests/utils/test_license_strings.py
git commit -m "feat: add license consent UI strings"
```

---

### Task 6: Sequential consent dialog

**Files:**
- Create: `swane/ui/LicenseConsentWindow.py`
- Test: `swane/tests/ui/test_license_consent_window.py`

**Interfaces:**
- Consumes: `ResolvedLicense`, `LicenseSource` (Task 3); strings (Task 5).
- Produces:
  - `class LicenseConsentWindow(QDialog)`:
    - `__init__(self, resolved_licenses: list[ResolvedLicense], parent=None)`
    - After `exec()` returns `QDialog.Accepted`, `self.accepted_tool_ids` is the list of tool ids shown (all of them, since acceptance is atomic).
    - Reject/close leaves `self.accepted_tool_ids == []`.

- [ ] **Step 1: Write the failing test**

```python
# swane/tests/ui/test_license_consent_window.py
import pytest
from swane.utils.qt_compat import QT_AVAILABLE

pytestmark = pytest.mark.skipif(not QT_AVAILABLE, reason="requires a working Qt binding")

if QT_AVAILABLE:
    from PySide6.QtWidgets import QDialog
    from swane.ui.LicenseConsentWindow import LicenseConsentWindow
    from swane.utils.license_consent import ResolvedLicense, LicenseSource


def _mk(text="line\n" * 500):
    return [
        ResolvedLicense("fsl", "FSL", text, False, LicenseSource.INSTALLED),
        ResolvedLicense("freesurfer", "FreeSurfer", text, False, LicenseSource.ONLINE),
    ]


def test_accept_disabled_until_scrolled(qtbot):
    win = LicenseConsentWindow(_mk())
    qtbot.addWidget(win)
    win.show()
    qtbot.waitExposed(win)
    assert not win._accept_btn.isEnabled()
    browser = win._current_browser()
    browser.verticalScrollBar().setValue(browser.verticalScrollBar().maximum())
    assert win._accept_btn.isEnabled()


def test_sequence_and_atomic_accept(qtbot):
    win = LicenseConsentWindow(_mk())
    qtbot.addWidget(win)
    win.show()
    qtbot.waitExposed(win)
    # Page 1
    b = win._current_browser()
    b.verticalScrollBar().setValue(b.verticalScrollBar().maximum())
    win._accept_btn.click()
    # Page 2
    b = win._current_browser()
    b.verticalScrollBar().setValue(b.verticalScrollBar().maximum())
    win._accept_btn.click()
    assert win.result() == QDialog.Accepted
    assert win.accepted_tool_ids == ["fsl", "freesurfer"]


def test_short_license_enables_immediately(qtbot):
    win = LicenseConsentWindow([
        ResolvedLicense("fsl", "FSL", "short", False, LicenseSource.INSTALLED),
    ])
    qtbot.addWidget(win)
    win.show()
    qtbot.waitExposed(win)
    assert win._accept_btn.isEnabled()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest swane/tests/ui/test_license_consent_window.py -v`
Expected: FAIL (`ModuleNotFoundError: swane.ui.LicenseConsentWindow`).

- [ ] **Step 3: Implement the dialog**

```python
# swane/ui/LicenseConsentWindow.py
"""Blocking, sequential dialog to accept external tool licenses at startup."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QStackedWidget,
    QWidget,
    QLabel,
    QPushButton,
    QTextBrowser,
    QFrame,
)

from swane import strings
from swane.utils.license_consent import LicenseSource


class LicenseConsentWindow(QDialog):
    def __init__(self, resolved_licenses, parent=None):
        super().__init__(parent)
        self._licenses = list(resolved_licenses)
        self.accepted_tool_ids = []

        self.setWindowTitle(strings.license_consent_title)
        self.setModal(True)
        self.resize(720, 640)

        root = QVBoxLayout()

        banner = QLabel(strings.license_consent_banner)
        banner.setWordWrap(True)
        banner.setStyleSheet("font-weight: 600;")
        root.addWidget(banner)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        root.addWidget(line)

        self._progress = QLabel("")
        root.addWidget(self._progress)

        self._stack = QStackedWidget()
        self._browsers = []
        for res in self._licenses:
            page = QWidget()
            lay = QVBoxLayout()

            if res.source is LicenseSource.ONLINE:
                warn = QLabel(strings.license_consent_source_online.format(tool=res.display_name))
                warn.setWordWrap(True)
                warn.setStyleSheet("color: #b06000;")
                lay.addWidget(warn)
            elif res.source is LicenseSource.BUNDLED:
                warn = QLabel(strings.license_consent_source_bundled.format(tool=res.display_name))
                warn.setWordWrap(True)
                warn.setStyleSheet("color: #b06000;")
                lay.addWidget(warn)

            browser = QTextBrowser()
            browser.setOpenExternalLinks(True)
            if res.is_html:
                browser.setHtml(res.text)
            else:
                browser.setPlainText(res.text)
            browser.verticalScrollBar().valueChanged.connect(self._maybe_enable_accept)
            lay.addWidget(browser)
            self._browsers.append(browser)

            page.setLayout(lay)
            self._stack.addWidget(page)

        root.addWidget(self._stack)

        hint = QLabel(strings.license_consent_scroll_hint)
        hint.setStyleSheet("color: #666;")
        root.addWidget(hint)

        nav = QHBoxLayout()
        nav.addStretch(1)
        self._accept_btn = QPushButton(strings.license_consent_accept_button)
        self._accept_btn.clicked.connect(self._accept_current)
        nav.addWidget(self._accept_btn)
        root.addLayout(nav)

        self.setLayout(root)
        self._sync_page()

    def _current_browser(self):
        return self._browsers[self._stack.currentIndex()]

    def _sync_page(self):
        idx = self._stack.currentIndex()
        self._progress.setText(
            strings.license_consent_progress.format(current=idx + 1, total=len(self._licenses))
        )
        self._maybe_enable_accept()

    def _maybe_enable_accept(self, *args):
        bar = self._current_browser().verticalScrollBar()
        at_bottom = bar.maximum() == 0 or bar.value() >= bar.maximum()
        self._accept_btn.setEnabled(at_bottom)

    def _accept_current(self):
        idx = self._stack.currentIndex()
        if idx < len(self._licenses) - 1:
            self._stack.setCurrentIndex(idx + 1)
            self._sync_page()
            return
        # Last page: atomic accept
        self.accepted_tool_ids = [res.tool_id for res in self._licenses]
        self.accept()

    def showEvent(self, event):
        super().showEvent(event)
        # Enable immediately when the current license fits without scrolling.
        self._maybe_enable_accept()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest swane/tests/ui/test_license_consent_window.py -v`
Expected: PASS (or SKIP where Qt is unavailable — that is acceptable on headless CI, but it MUST pass on a real Qt environment on both Linux and macOS).

- [ ] **Step 5: Commit**

```bash
git add swane/ui/LicenseConsentWindow.py swane/tests/ui/test_license_consent_window.py
git commit -m "feat: add sequential license consent dialog"
```

---

### Task 7: Startup wiring + abort on decline

**Files:**
- Modify: `swane/ui/MainWindow.py` (add `run_license_consent_gate`)
- Modify: `swane/__main__.py` (invoke gate; skip `app.exec()` on decline)
- Test: `swane/tests/ui/test_license_consent_window.py` (append integration cases) or `swane/tests/ui/test_main_window.py`

**Interfaces:**
- Consumes: `tools_needing_consent`, `detected_tool_versions`, `resolve_license_text` (Tasks 3-4); `LICENSES` (Task 2); `LicenseConsentWindow` (Task 6); `ConfigManager.set_accepted_license_version` (Task 1).
- Produces: `MainWindow.run_license_consent_gate(self) -> bool` — `True` to proceed, `False` to abort.

- [ ] **Step 1: Write the failing test**

```python
# append to swane/tests/ui/test_license_consent_window.py
def test_gate_returns_true_when_nothing_to_consent(qtbot, monkeypatch, global_config, offline_update):
    import swane.ui.MainWindow as mw
    from swane.ui.MainWindow import MainWindow
    monkeypatch.setattr(mw, "tools_needing_consent", lambda dm, cfg: [])
    window = MainWindow(global_config)
    qtbot.addWidget(window)
    assert window.run_license_consent_gate() is True
```

(Reuses the `global_config` and `offline_update` fixtures already defined in the test tree.)

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest swane/tests/ui/test_license_consent_window.py -v`
Expected: FAIL (`AttributeError: 'MainWindow' object has no attribute 'run_license_consent_gate'`).

- [ ] **Step 3: Add the gate method to MainWindow**

Add imports near the other `swane.utils` / `swane.ui` imports in `swane/ui/MainWindow.py`:

```python
from swane.utils.license_consent import (
    tools_needing_consent,
    detected_tool_versions,
    resolve_license_text,
)
from swane.utils.LicenseReference import LICENSES
from swane.ui.LicenseConsentWindow import LicenseConsentWindow
```

Add the method to `MainWindow`:

```python
def run_license_consent_gate(self) -> bool:
    """
    Show the external-tool license consent gate if needed.

    Returns
    -------
    bool
        True to proceed with startup, False if the user declined and the
        application must abort.
    """
    # Refresh detection so tools configured during the wizard are considered.
    self.dependency_manager = DependencyManager()

    needing = tools_needing_consent(self.dependency_manager, self.global_config)
    if not needing:
        return True

    context = {"slicer_path": self.global_config.get_slicer_path()}
    resolved = [
        resolve_license_text(LICENSES[tool_id], context) for tool_id in needing
    ]

    dialog = LicenseConsentWindow(resolved, parent=self)
    if dialog.exec() != QDialog.Accepted:
        return False

    detected = detected_tool_versions(self.dependency_manager, self.global_config)
    for tool_id in dialog.accepted_tool_ids:
        self.global_config.set_accepted_license_version(
            tool_id, detected.get(tool_id, "")
        )
    self.global_config.save()
    return True
```

Ensure `QDialog` is imported in `MainWindow.py` (add `QDialog` to the existing `PySide6.QtWidgets` import if absent). Note: Slicer's detection may complete asynchronously after the wizard; when it is not yet detected here it is simply consented on a later startup — the per-tool model handles that. Document this with a short comment.

- [ ] **Step 4: Wire the gate into `__main__.py`**

In `swane/__main__.py`, replace the construction/exec block:

```python
        try:
            widget = MainWindow(global_config)
            widget.setWindowIcon(QIcon(QPixmap(swane_supplement.appIcon_file)))
            if widget.run_license_consent_gate():
                current_exit_code = app.exec()
            else:
                current_exit_code = 0
        finally:
```

(Keep the existing `finally` block unchanged.)

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest swane/tests/ui/test_license_consent_window.py -v`
Expected: PASS (or SKIP without Qt).

- [ ] **Step 6: Commit**

```bash
git add swane/ui/MainWindow.py swane/__main__.py swane/tests/ui/test_license_consent_window.py
git commit -m "feat: wire license consent gate into startup with abort-on-decline"
```

---

### Task 8: NOTICE.md, packaging, and docs

**Files:**
- Modify: `NOTICE.md`
- Modify: `setup.py`
- Modify: `MANIFEST.in`
- Test: `swane/tests/utils/test_license_packaging.py`

**Interfaces:**
- Consumes: `swane/licenses/*.txt` (Task 2).
- Produces: shipped license data + documentation.

- [ ] **Step 1: Write the failing test**

```python
# swane/tests/utils/test_license_packaging.py
import os
from swane.utils import LicenseReference as LR


def test_all_bundled_licenses_declared_and_present():
    licenses_dir = os.path.normpath(
        os.path.join(os.path.dirname(LR.__file__), "..", "licenses")
    )
    for info in LR.LICENSES.values():
        assert os.path.isfile(os.path.join(licenses_dir, info.bundled_filename))
```

- [ ] **Step 2: Run test to verify it fails/passes**

Run: `python -m pytest swane/tests/utils/test_license_packaging.py -v`
Expected: PASS if Task 2 populated the files (this test guards regressions in packaging layout). If it fails, the bundled files are missing — fix Task 2 first.

- [ ] **Step 3: Add packaging declarations**

In `setup.py`, inside `setup(...)`, add:

```python
    include_package_data=True,
    package_data={"swane": ["licenses/*.txt"]},
```

In `MANIFEST.in`, add:

```
recursive-include swane/licenses *.txt
```

- [ ] **Step 4: Update NOTICE.md**

Append a section to `NOTICE.md`:

```markdown
---
## External neuroimaging tools orchestrated by SWANe

SWANe orchestrates the following external tools as separate processes. SWANe
does not include or redistribute these tools' code; users install them
separately and must comply with each tool's own license:

- **FSL (FMRIB Software Library)** — free for non-commercial use; commercial use
  requires a license from Oxford University Innovation.
  https://fsl.fmrib.ox.ac.uk/fsl/docs/license.html
- **FreeSurfer** — distributed under the FreeSurfer Software License Agreement;
  free, restricts commercial use, requires registration for a license key.
  https://github.com/freesurfer/freesurfer/blob/dev/LICENSE.txt
- **3D Slicer** — Slicer License (BSD-style).
  https://github.com/Slicer/Slicer/blob/main/License.txt
- **dcm2niix** — BSD 2-Clause License.
  https://github.com/rordenlab/dcm2niix/blob/master/license.txt

At first launch (and whenever a tool's detected version changes), SWANe shows the
license of each detected tool and requires explicit acceptance. For display,
SWANe reads the license installed on the user's system when available, otherwise
fetches the current license online, otherwise falls back to a bundled copy under
`swane/licenses/`. These bundled copies are license text only (no tool code) and
are refreshed from upstream before releases via `tools/refresh_bundled_licenses.py`.
```

Also remove the now-addressed `# TODO: maybe we should cite all sublicenses` comment in `setup.py` if desired (optional), since this section documents the sublicenses.

- [ ] **Step 5: Run test + build sanity**

Run: `python -m pytest swane/tests/utils/test_license_packaging.py -v`
Expected: PASS.

Optionally verify sdist includes the files:
Run: `python -m build --sdist 2>/dev/null && tar tzf dist/swane-*.tar.gz | grep licenses/`
Expected: the `swane/licenses/*.txt` files are listed.

- [ ] **Step 6: Commit**

```bash
git add NOTICE.md setup.py MANIFEST.in swane/tests/utils/test_license_packaging.py
git commit -m "docs: document orchestrated tool licenses and ship bundled fallbacks"
```

---

## Final validation (run after all tasks)

- [ ] Run the full relevant suite: `python -m pytest swane/tests/utils swane/tests/ui swane/tests/config -v` (adjust to the suites named in the `swane-dev-assistant` skill).
- [ ] Confirm the GUI tests actually run (not merely skip) on at least one real-Qt environment, on both Linux and macOS.
- [ ] Manual smoke test on Linux and macOS: fresh config → wizard → consent gate shows one page per detected tool; `I ACCEPT` unlocks only after scrolling; declining exits SWANe; re-launch shows nothing; simulate a version change (edit the stored `accepted_license_*` value) and confirm only that tool re-prompts.

## Self-Review notes (addressed)

- **Spec coverage:** consent model (Task 1+4), registry & bundled fallbacks & refresh script (Task 2), resolution chain (Task 3), sequential scroll-to-accept dialog with fixed banner and atomic commit (Task 5+6), trigger-after-wizard + abort-on-decline (Task 7), NOTICE/packaging (Task 8). Legal framing carried into strings (Task 5) and NOTICE (Task 8).
- **FreeSurfer key-vs-license hazard:** explicitly excluded from installed candidates and asserted in Task 2's test.
- **Type consistency:** `ResolvedLicense`, `LicenseSource`, `tools_needing_consent`, `detected_tool_versions`, `get/set_accepted_license_version`, `run_license_consent_gate`, `accepted_tool_ids` used consistently across tasks.
- **Open items to verify during implementation** (from spec §10): the exact installed license paths per tool/OS are best-effort candidate lists that degrade gracefully to online/bundled — confirm real paths on Linux/macOS installs; confirm dcm2niix has no local license file; confirm the wizard does not need an explicit Slicer re-check beyond rebuilding `DependencyManager`.
```
