# Experimental Windows Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make SWANe's FSL-free pipelines run natively on Windows (experimental), validated by manually triggered GitHub Actions runs of the light, heavy and prerelease suites.

**Architecture:** CI first: a `workflow_dispatch` workflow exposes Windows (and macOS) runners; portability fixes land at the narrowest layer (a `pwd` stub before Nipype's plugin import, symlink/encoding fallbacks, argv-list subprocesses for Slicer); the prerelease sweep stops requiring FSL and FreeSurfer by gating FSL axis values and fetching the two fsaverage segmentations from the MNE mirror.

**Tech Stack:** Python 3.12, Nipype 1.12 (SWANe-pinned), PySide6, pytest + pytest-qt, GitHub Actions (`windows-latest`, `macos-latest`).

**Spec:** `docs/superpowers/specs/2026-10-04-windows-support-design.md`

## Global Constraints

- Branch: `claude/windows-support` (from `dev` at `7bb1297`). Commits are allowed per task; **pushing requires the maintainer's explicit OK in the conversation** (needed before any CI run).
- Python for every local command: `/media/Dati/Installer_completi/Programmi/conda_env/swane-env/bin/python` (abbreviated `$PY` below). Never fslpython/fspython. Always add `-p no:datalad` to pytest.
- English only in code, comments, docs, UI strings. Never "patient" (use "subject"); never imply clinical use.
- No preference key, enum member, workflow/node name, Traits field, signal, result filename or Slicer mapping may change.
- Never commit fsaverage files, phantom data, logs or results. CI artifacts carry only reports/logs.
- fsaverage mirror: URL `https://github.com/mne-tools/mne-data/releases/download/fsaverage-1.0/fsaverage-root.zip`, md5 `5133fe92b7b8f03ae19219d5f46e4177`; only `fsaverage/mri/aseg.mgz` and `fsaverage/mri/aparc+aseg.mgz` are extracted.
- Format changed Python files with `$PY -m black <files>`; do not reformat unrelated files.
- Linux behaviour must stay identical; macOS is covered by the workflow's `os=macos-latest` option.
- Subagent models: Opus for Task 2 and Task 5; Sonnet for every other task.

## Review Focus

1. **Spawned workers on Windows import Nipype plugins before the `pwd` stub** → the pool dies with `ModuleNotFoundError: pwd`. Pinned by Task 2's subprocess test that imports `swane` and `nipype.pipeline.plugins` with `pwd` unavailable, and by the real `spawn` run in `test_workflow_process.py`.
2. **Paths containing spaces** (`C:\Users\Name Surname\...`) passed through `shell=True` command lines → arguments split. Pinned by Task 4's argv-list assertions and by Task 1's `--basetemp` with a space in CI.
3. **A no-FSL host silently "covers" an FSL-only axis value** (e.g. BET threshold with no BET running) → false coverage. Pinned by Task 5's `test_fsl_free_host_reports_fsl_values_unreachable`.
4. **Corrupt or partial fsaverage download** reused as cache → wrong phantom. Pinned by Task 6's md5-mismatch test and by the `.part` + `os.replace` write.
5. **User without symlink privilege** (Windows, no Developer Mode) → template cache creation crashes. Pinned by Task 3's symlink-failure test.

---

### Task 1: Manual Windows/macOS workflow with the light suite

**Files:**
- Create: `.github/workflows/windows-tests.yml`

**Interfaces:**
- Produces: workflow `windows-tests.yml`, inputs `suite` (`light|heavy|prerelease|all`), `os` (`windows-latest|macos-latest`), `passes` (string), `rebuild_cache` (boolean). Task 7 adds the `heavy`/`prerelease-*` jobs to this same file.

- [ ] **Step 1: Write the workflow**

```yaml
name: Windows tests

# Manual only: never runs on push or pull_request.
on:
  workflow_dispatch:
    inputs:
      suite:
        description: "Suite to run"
        type: choice
        options: [light, heavy, prerelease, all]
        default: light
      os:
        description: "Runner OS for light/heavy (prerelease is Windows-only)"
        type: choice
        options: [windows-latest, macos-latest]
        default: windows-latest
      passes:
        description: "Comma-separated prerelease passes (empty = every runnable pass)"
        type: string
        default: ""
      rebuild_cache:
        description: "Rebuild phantom/weights caches"
        type: boolean
        default: false

permissions:
  contents: read

jobs:
  light:
    if: ${{ inputs.suite == 'light' || inputs.suite == 'all' }}
    runs-on: ${{ inputs.os }}
    timeout-minutes: 90
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install SWANe
        shell: bash
        run: |
          python -m pip install --upgrade pip
          python -m pip install -e . pytest pytest-qt
      - name: Environment report
        shell: bash
        run: |
          python -c "import sys; print(sys.executable); print(sys.version)"
          python -c "import dcm2niix, niimath; print('dcm2niix', dcm2niix.__file__); print('niimath', niimath.__file__)"
          python -m pip freeze > pip-freeze.txt
      - name: Light suite
        shell: bash
        # The base temp contains a space on purpose: Windows home folders often
        # do, and unquoted command lines must not split it.
        run: >
          python -m pytest swane/tests -m "not heavy"
          --basetemp "${{ runner.temp }}/swane tmp"
          --junitxml=junit-light.xml -p no:cacheprovider -rs
      - if: always()
        uses: actions/upload-artifact@v4
        with:
          name: light-${{ inputs.os }}
          path: |
            junit-light.xml
            pip-freeze.txt
```

- [ ] **Step 2: Validate the YAML parses**

Run: `$PY -c "import yaml,sys; d=yaml.safe_load(open('.github/workflows/windows-tests.yml')); print(list(d[True]['workflow_dispatch']['inputs']))"`
Expected: `['suite', 'os', 'passes', 'rebuild_cache']` (PyYAML parses the `on` key as `True`). If PyYAML is not importable in `$PY`, do not install it: report the check as not run.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/windows-tests.yml
git commit -m "ci: add manual Windows/macOS test workflow (light suite)"
```

- [ ] **Step 4: Hand off the first run**

Tell the maintainer: the branch must be pushed (ask for explicit OK), then `gh workflow run windows-tests.yml -r claude/windows-support -f suite=light -f os=windows-latest`. Expected first result on Windows: collection fails with `ModuleNotFoundError: No module named 'pwd'` (fixed by Task 2). This expected failure is the evidence that Task 2 is needed.

---

### Task 2: `pwd` stub for Nipype + real MultiProc tests on every platform (Opus)

**Files:**
- Create: `swane/patches/windows_compat.py`
- Modify: `swane/patches/__init__.py:1-6` (install the stub first)
- Modify: `swane/tests/conftest.py` (install the stub before anything imports Nipype; fix the stale docstring line "runs green on a plain Windows/CI box" only if still inaccurate)
- Modify: `swane/utils/mp_start_method.py:36-40` (docstring)
- Modify: `swane/tests/workers/test_workflow_process.py:137-188`
- Modify: `swane/tests/prerelease/test_runner.py:186`
- Modify: `swane/tests/nipype_pipeline/engine/test_monitored_multiproc_plugin.py:27-41`
- Test: `swane/tests/patches/test_windows_compat.py`

**Interfaces:**
- Produces: `swane.patches.windows_compat.install_pwd_stub() -> bool` (True when the stub was installed). Imported first by `swane/patches/__init__.py`, so `import swane` anywhere (including in `spawn` workers unpickling `swane.patches.nipype_patches.swane_run_node`) installs it before `nipype.pipeline.plugins` is imported.

Background: `swane/patches/nipype_patches.py:72` does `from nipype.pipeline.plugins.multiproc import run_node`; `nipype/pipeline/plugins/__init__.py` imports `sge.py`, which does `import pwd` at module top. On Windows, therefore, `import swane` itself fails today. `sge.py` only calls `pwd` inside SGE job submission, which SWANe never uses.

- [ ] **Step 1: Write the failing tests**

```python
"""The Windows ``pwd`` stub that lets Nipype's plugin package import."""

import os
import subprocess
import sys
import textwrap

import pytest

from swane.patches import windows_compat


def test_stub_installed_on_windows_when_pwd_is_missing(monkeypatch):
    monkeypatch.setattr(windows_compat.os, "name", "nt")
    # A None entry makes ``import pwd`` raise ImportError, like on Windows.
    monkeypatch.setitem(sys.modules, "pwd", None)

    assert windows_compat.install_pwd_stub() is True

    import pwd

    assert getattr(pwd, "__swane_stub__", False) is True
    with pytest.raises(KeyError):
        pwd.getpwuid(0)
    with pytest.raises(KeyError):
        pwd.getpwnam("anyone")
    assert pwd.getpwall() == []


def test_stub_is_a_no_op_off_windows(monkeypatch):
    monkeypatch.setattr(windows_compat.os, "name", "posix")
    monkeypatch.setitem(sys.modules, "pwd", None)
    assert windows_compat.install_pwd_stub() is False
    assert sys.modules["pwd"] is None


def test_stub_never_replaces_a_real_pwd(monkeypatch):
    if os.name == "nt":
        pytest.skip("no real pwd module on Windows")
    import pwd as real_pwd

    monkeypatch.setattr(windows_compat.os, "name", "nt")
    assert windows_compat.install_pwd_stub() is False
    assert sys.modules["pwd"] is real_pwd


def test_swane_import_makes_nipype_plugins_importable_without_pwd():
    """End to end, in a fresh interpreter: with ``pwd`` unavailable (as on
    Windows), importing swane must install the stub so MultiProcPlugin imports."""
    code = textwrap.dedent(
        """
        import os, sys
        sys.modules["pwd"] = None  # ``import pwd`` now fails, as on Windows
        real_name = os.name
        os.name = "nt"  # windows_compat reads os.name when the stub is installed
        import swane  # swane/patches/__init__.py installs the stub first
        os.name = real_name
        from nipype.pipeline.plugins.multiproc import MultiProcPlugin
        import pwd
        assert getattr(pwd, "__swane_stub__", False), pwd
        print("OK")
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=300
    )
    assert result.returncode == 0, result.stderr[-3000:]
    assert "OK" in result.stdout
```

Note for the implementer: flipping `os.name` to `"nt"` while `import swane` runs may trip other import-time `os.name` checks. If it does, keep `os.name = "nt"` only for the single call `swane.patches.windows_compat.install_pwd_stub()` executed *before* `import swane`, and assert separately (second assertion block) that `swane/patches/__init__.py` calls `install_pwd_stub()` before importing `nipype_patches` by reading its source order. Document which variant you kept and why.

- [ ] **Step 2: Run them to verify they fail**

Run: `$PY -m pytest swane/tests/patches/test_windows_compat.py -p no:datalad -v`
Expected: FAIL / ERROR with `ImportError: cannot import name 'windows_compat'`.

- [ ] **Step 3: Implement the stub**

`swane/patches/windows_compat.py`:

```python
"""Windows compatibility shims installed before Nipype is imported.

Nipype's ``nipype/pipeline/plugins/__init__.py`` imports every execution
plugin, including ``sge.py``, which does ``import pwd`` at module level. ``pwd``
exists only on Unix, so on Windows the whole plugin package -- and with it the
MultiProc plugin SWANe runs every workflow with -- fails to import. ``sge.py``
only queries ``pwd`` while submitting SGE cluster jobs, which SWANe never does,
so a stub whose lookups fail like an unknown user is enough.
"""

import os
import sys
import types


def install_pwd_stub() -> bool:
    """Register a minimal ``pwd`` module on Windows when the real one is missing.

    Returns
    -------
    bool
        True when the stub was installed, False when nothing was needed.
    """
    if os.name != "nt" or sys.modules.get("pwd") is not None:
        return False
    try:
        import pwd  # noqa: F401
    except ImportError:
        pass
    else:
        return False

    stub = types.ModuleType("pwd")

    def _unknown_user(*args, **kwargs):
        raise KeyError("the pwd database is not available on Windows")

    stub.getpwuid = _unknown_user
    stub.getpwnam = _unknown_user
    stub.getpwall = lambda: []
    stub.__swane_stub__ = True
    sys.modules["pwd"] = stub
    return True
```

`swane/patches/__init__.py`, new first statements (before the scipy patch block):

```python
# The pwd stub MUST be installed before anything imports nipype.pipeline.plugins
# (nipype_patches below does): on Windows that package fails on ``import pwd``.
from swane.patches.windows_compat import install_pwd_stub

install_pwd_stub()
```

`swane/tests/conftest.py`: as the first import after `import pytest`, add

```python
# On Windows, nipype.pipeline.plugins only imports once SWANe's pwd stub is in
# place; some test modules import nipype before swane, so install it here first.
from swane.patches.windows_compat import install_pwd_stub

install_pwd_stub()
```

Update the module docstring line about "runs green on a plain Windows/CI box" only if it is no longer accurate after this task.

- [ ] **Step 4: Run the new tests**

Run: `$PY -m pytest swane/tests/patches/test_windows_compat.py -p no:datalad -v`
Expected: 4 passed (or 3 passed + 1 skipped on Windows).

- [ ] **Step 5: Un-skip the real MultiProc tests and add `spawn`**

In `swane/tests/workers/test_workflow_process.py` remove the `@pytest.mark.skipif(os.name == "nt", ...)` line and change the parametrization so `spawn` is exercised everywhere it exists (it is the only method on Windows):

```python
@pytest.mark.parametrize(
    "start_method",
    [m for m in ("fork", "forkserver", "spawn") if m in mp.get_all_start_methods()],
)
```

Keep the final assertion as it is (`fork` → parent is this process; any other method → it is not). Update the docstring to mention `spawn` (Windows' only method).

In `swane/tests/prerelease/test_runner.py:186` remove the `skipif(os.name == "nt", ...)` line.

In `swane/tests/nipype_pipeline/engine/test_monitored_multiproc_plugin.py` replace the comment + `try/except pytest.skip(..., allow_module_level=True)` block (lines 27-41) with:

```python
# nipype's plugin package imports the Unix-only ``pwd`` module (via its sge
# plugin); swane's pwd stub (swane.patches.windows_compat, installed by
# conftest) makes it importable on Windows too, so nothing is skipped here.
from nipype.pipeline.plugins.multiproc import (  # noqa: F401
    MultiProcPlugin as _RealMultiProcPlugin,
)
```

- [ ] **Step 6: Fix the start-method docstring**

In `swane/utils/mp_start_method.py` replace "(Windows, which SWANe does not support for workflow execution)" with "(Windows, where ``spawn`` is the only start method)". `test_platform_without_fork_falls_back_to_spawn` already covers `win32`; no new test.

- [ ] **Step 7: Run the affected suites on Linux**

Run: `$PY -m pytest swane/tests/patches swane/tests/workers/test_workflow_process.py swane/tests/prerelease/test_runner.py swane/tests/nipype_pipeline/engine/test_monitored_multiproc_plugin.py swane/tests/utils/test_mp_start_method.py -p no:datalad -v`
Expected: all pass, including the new `spawn` parametrization of `test_real_worker_pool_uses_the_selected_start_method`. Read the `spawn` case output: the worker parent pid must differ from the test process pid.

- [ ] **Step 8: Black, then commit**

```bash
$PY -m black swane/patches/windows_compat.py swane/patches/__init__.py swane/tests/conftest.py swane/utils/mp_start_method.py swane/tests/patches/test_windows_compat.py swane/tests/workers/test_workflow_process.py swane/tests/prerelease/test_runner.py swane/tests/nipype_pipeline/engine/test_monitored_multiproc_plugin.py
git add swane/patches/windows_compat.py swane/patches/__init__.py swane/tests/conftest.py swane/utils/mp_start_method.py swane/tests/patches/test_windows_compat.py swane/tests/workers/test_workflow_process.py swane/tests/prerelease/test_runner.py swane/tests/nipype_pipeline/engine/test_monitored_multiproc_plugin.py
git commit -m "fix(windows): stub pwd so nipype's MultiProc plugin imports"
```

---

### Task 3: Symlink fallback and UTF-8 for SWANe-owned text files

**Files:**
- Modify: `swane/utils/templates.py:1-6` (import `shutil`), `:100-103`
- Modify: `swane/config/ConfigManager.py:78,89,128,223`
- Modify: `swane/utils/print_error.py:36`
- Test: `swane/tests/utils/test_templates.py`, `swane/tests/config/test_config_manager.py` (extend the existing file; create it only if absent)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: no new API.

- [ ] **Step 1: Write the failing symlink test** (append to `swane/tests/utils/test_templates.py`)

```python
def test_las_template_falls_back_to_copy_without_symlink_rights(tmp_path, monkeypatch):
    """Windows without Developer Mode cannot create symlinks: the already-LAS
    template must then be copied into the SWANe cache instead of crashing."""
    import os
    import numpy as np
    import nibabel as nib

    src_dir = tmp_path / "tf"
    src_dir.mkdir()
    src = src_dir / "tpl-FakeMNI_res-01_desc-brain_T1w.nii.gz"
    affine = np.diag([-1.0, 1.0, 1.0, 1.0])  # LAS
    nib.save(nib.Nifti1Image(np.zeros((2, 2, 2), np.float32), affine), str(src))

    cache = tmp_path / "cache"
    cache.mkdir()
    fake_tf = MagicMock()
    fake_tf.get.return_value = str(src)

    def no_symlink(*args, **kwargs):
        raise OSError(1314, "A required privilege is not held by the client")

    monkeypatch.setattr(os, "symlink", no_symlink)
    with patch.object(templates_module, "_SWANE_TEMPLATE_CACHE", cache), patch.dict(
        "sys.modules", {"templateflow.api": fake_tf, "templateflow": MagicMock()}
    ):
        result = get_swane_template(
            name="FakeMNI", resolution=1, desc="brain", enforce_las=True
        )

    out = Path(result)
    assert out.exists() and not out.is_symlink()
    assert out.read_bytes() == src.read_bytes()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `$PY -m pytest swane/tests/utils/test_templates.py::test_las_template_falls_back_to_copy_without_symlink_rights -p no:datalad -v`
Expected: FAIL with `OSError: [Errno 1314] A required privilege is not held by the client`.

- [ ] **Step 3: Implement the fallback** (`swane/utils/templates.py`, add `import shutil` with the other imports)

```python
        if axcodes == ("L", "A", "S"):
            # It is already LAS, just link it to avoid copying. Windows without
            # Developer Mode (or a filesystem without links) refuses symlinks:
            # copy instead, the file is small.
            try:
                os.symlink(tf_path, str(las_path))
            except (OSError, NotImplementedError):
                shutil.copy2(tf_path, str(las_path))
            return str(las_path)
```

- [ ] **Step 4: Run it to verify it passes**

Run: same command as Step 2. Expected: PASS.

- [ ] **Step 5: Write the failing UTF-8 config test** (in `swane/tests/config/test_config_manager.py`)

```python
def test_config_file_is_utf8_with_non_ascii_values(tmp_path):
    """Windows' default text encoding is cp1252: SWANe's own config must be
    written and read as UTF-8 so non-ASCII folders survive a round trip."""
    from swane.config.ConfigManager import ConfigManager
    from swane.config.config_enums import GlobalPrefCategoryList

    config = ConfigManager(global_base_folder=str(tmp_path))
    folder = str(tmp_path / "Niccolò Brontë 測試")
    config.set_main_working_directory(folder)
    config.save()

    raw = open(config.config_file, "rb").read()
    assert "Niccolò Brontë 測試".encode("utf-8") in raw

    reloaded = ConfigManager(global_base_folder=str(tmp_path))
    assert reloaded.get_main_working_directory() == folder
```

If `set_main_working_directory` validates the folder's existence, create it first with `os.makedirs(folder)`. Check `git grep -n "def set_main_working_directory" swane/config/ConfigManager.py` before writing the test.

- [ ] **Step 6: Run it**

Run: `$PY -m pytest swane/tests/config/test_config_manager.py::test_config_file_is_utf8_with_non_ascii_values -p no:datalad -v`
Expected on Linux: PASS even before the fix (UTF-8 locale). This test is the Windows regression guard: on `windows-latest` it fails without Step 7 (cp1252 cannot encode `測試`). Record this in the commit message.

- [ ] **Step 7: Pin UTF-8**

`ConfigManager.py`: `temp_config.read(self.config_file, encoding="utf-8")` (line ~78), `self.read(self.config_file, encoding="utf-8")` (lines ~89 and ~128), `with open(self.config_file, "w", encoding="utf-8") as openedFile:` (line ~223).
`print_error.py:36`: `with open(ERROR_FILE, "a+", encoding="utf-8") as f:`.
Do not touch `open()` calls that read files produced by external tools (FSL, nipype `command.txt`, MELODIC mix, waytotal) or the Linux-only `.desktop` writer.

- [ ] **Step 8: Run config + utils suites, Black, commit**

Run: `$PY -m pytest swane/tests/config swane/tests/utils -m "not heavy" -p no:datalad -q`
Expected: all pass.

```bash
$PY -m black swane/utils/templates.py swane/config/ConfigManager.py swane/utils/print_error.py swane/tests/utils/test_templates.py swane/tests/config/test_config_manager.py
git add swane/utils/templates.py swane/config/ConfigManager.py swane/utils/print_error.py swane/tests/utils/test_templates.py swane/tests/config/test_config_manager.py
git commit -m "fix(windows): copy when symlinks are refused; UTF-8 config and error log"
```

---

### Task 4: Slicer discovery on Windows and argv-list subprocesses

**Files:**
- Modify: `swane/workers/SlicerCheckWorker.py` (imports; `find_slicer_python`; `run()` version and module-install calls)
- Modify: `swane/workers/SlicerExportWorker.py:47-66`
- Modify: `swane/workers/SlicerViewerWorker.py:33-45`
- Test: `swane/tests/workers/test_slicer_check_worker.py`, `test_slicer_export_worker.py`, `test_slicer_viewer_worker.py`

**Interfaces:**
- Produces: `SlicerCheckWorker._find_slicer_python_windows(current_slicer_path: str) -> list[str]`; `find_slicer_python` returns `(paths, "../Slicer.exe")` on Windows. Linux/macOS return values unchanged.

- [ ] **Step 1: Write the failing tests**

Append to `test_slicer_check_worker.py`:

```python
def test_find_slicer_python_windows_searches_localappdata(monkeypatch, tmp_path):
    install = tmp_path / "slicer.org" / "Slicer 5.8.1"
    (install / "bin").mkdir(parents=True)
    (install / "bin" / "PythonSlicer.exe").write_bytes(b"")
    (install / "Slicer.exe").write_bytes(b"")
    monkeypatch.setattr(platform, "system", lambda: "Windows")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.delenv("ProgramFiles", raising=False)
    monkeypatch.delenv("ProgramW6432", raising=False)

    def no_find(*args, **kwargs):
        raise AssertionError("GNU find must not be used on Windows")

    monkeypatch.setattr(subprocess, "run", no_find)

    paths, rel = SlicerCheckWorker.find_slicer_python("")
    assert rel == "../Slicer.exe"
    assert paths == [str(install / "bin" / "PythonSlicer.exe")]
    slicer = os.path.abspath(os.path.join(os.path.dirname(paths[0]), rel))
    assert slicer == str(install / "Slicer.exe")


def test_find_slicer_python_windows_prefers_newest_and_user_path(monkeypatch, tmp_path):
    for version in ("Slicer 5.6.2", "Slicer 5.8.1"):
        (tmp_path / "slicer.org" / version / "bin").mkdir(parents=True)
        (tmp_path / "slicer.org" / version / "bin" / "PythonSlicer.exe").write_bytes(b"")
    monkeypatch.setattr(platform, "system", lambda: "Windows")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    paths, _ = SlicerCheckWorker.find_slicer_python("")
    assert "Slicer 5.8.1" in paths[0]

    # A user-chosen install folder (or its Slicer.exe) restricts the search.
    chosen = tmp_path / "slicer.org" / "Slicer 5.6.2"
    paths, _ = SlicerCheckWorker.find_slicer_python(str(chosen))
    assert paths == [str(chosen / "bin" / "PythonSlicer.exe")]
```

Replace the two `fake_run(cmd, shell, stdout)` helpers in the existing tests with argv-aware fakes and assert no shell. For `test_module_install_command_keeps_script_path_separate`:

```python
    def fake_run(cmd, **kwargs):
        assert isinstance(cmd, list), "Slicer must be invoked with an argv list"
        assert not kwargs.get("shell"), "no shell: paths with spaces must survive"
        commands.append(cmd)
        joined = " ".join(cmd)
        if "--version" in cmd:
            s = b"Slicer 5.0\n"
        elif "slicer_script_module_install.py" in joined:
            s = b"MODULE FOUND\n"
        else:
            s = b""
        return type("P", (), {"stdout": s})

    monkeypatch.setattr(subprocess, "run", fake_run)

    w.run()

    install_cmd = next(
        c for c in commands if any("slicer_script_module_install.py" in t for t in c)
    )
    idx = install_cmd.index("--python-script")
    assert install_cmd[idx + 1].endswith("slicer_script_module_install.py")
    assert install_cmd[idx + 2] == ",".join(DependencyManager.SLICER_MODULES)
```

Apply the same `fake_run(cmd, **kwargs)` + `" ".join(cmd)` change to the earlier `fake_run` in the "run should append a result" test (line ~124). Drop the now-unused `shlex` import if nothing else uses it.

In `test_slicer_export_worker.py`, change both `FakePopen.__init__` signatures to `def __init__(self, cmd, **kwargs):`, assert `isinstance(cmd, list)` and `not kwargs.get("shell")`, and rewrite the second test's token checks on the list directly:

```python
    cmd = captured["cmd"]
    idx = cmd.index("--python-script")
    assert cmd[idx + 1].endswith("slicer_script_result.py")
    for flag in ("--dti_threshold", "--vein_threshold_mr", "--vein_threshold_ct"):
        assert flag in cmd
```

In `test_slicer_viewer_worker.py`, change both fakes to `def __init__(self, cmd, **kwargs):` storing `(cmd, kwargs)`, and assert:

```python
    assert calls[0][0] == ["/path/to/slicer", "/path/to/scene.mrml"]
    assert not calls[0][1].get("shell")
```

(and `captured["stdout"] = kwargs["stdout"]` for the DEVNULL test).

- [ ] **Step 2: Run them to verify they fail**

Run: `$PY -m pytest swane/tests/workers/test_slicer_check_worker.py swane/tests/workers/test_slicer_export_worker.py swane/tests/workers/test_slicer_viewer_worker.py -p no:datalad -v`
Expected: the new Windows tests FAIL (GNU find invoked / wrong `rel_path`), and the rewritten fakes FAIL on `isinstance(cmd, list)`.

- [ ] **Step 3: Implement Windows discovery** (`SlicerCheckWorker.py`; add `import glob`; delete the TODO comment at the top of `find_slicer_python`)

Right after the existing `current_slicer_path` normalisation (the `if not os.path.exists(...)`/`elif os.path.isfile(...)` block) insert:

```python
        if platform.system() == "Windows":
            return (
                SlicerCheckWorker._find_slicer_python_windows(current_slicer_path),
                "../Slicer.exe",
            )
```

and add the helper:

```python
    @staticmethod
    def _find_slicer_python_windows(current_slicer_path: str) -> list[str]:
        """Locate PythonSlicer.exe without GNU find.

        Slicer's Windows installer puts each version in its own folder, by
        default ``%LOCALAPPDATA%\\slicer.org\\Slicer <version>`` (per user) or
        ``%ProgramFiles%\\Slicer <version>`` (all users). Newest version first.
        """
        if current_slicer_path:
            roots = [current_slicer_path]
        else:
            roots = [
                os.path.join(os.environ.get("LOCALAPPDATA", ""), "slicer.org"),
                os.environ.get("ProgramW6432", ""),
                os.environ.get("ProgramFiles", ""),
            ]
        for root in roots:
            if not root or not os.path.isdir(root):
                continue
            found = []
            for depth in ("", "*", os.path.join("*", "*")):
                pattern = os.path.join(root, depth, "bin", "PythonSlicer.exe")
                found.extend(glob.glob(pattern))
            if found:
                return sorted(set(found), reverse=True)
        return []
```

- [ ] **Step 4: Switch the Slicer subprocesses to argv lists**

`SlicerCheckWorker.run()`:

```python
                output2 = subprocess.run(
                    [cmd, "--version"], stdout=subprocess.PIPE
                ).stdout.decode("utf-8")
```

```python
                    cmd3 = [
                        cmd,
                        "--no-splash",
                        "--no-main-window",
                        "--python-script",
                        module_install_script,
                        ",".join(DependencyManager.SLICER_MODULES),
                    ]
                    output3 = subprocess.run(
                        cmd3, stdout=subprocess.PIPE
                    ).stdout.decode("utf-8")
```

Update the surrounding comment: the script path is a separate argv element, no shell involved. Remove `import shlex` if unused.

`SlicerExportWorker.run()`:

```python
        cmd = [
            self.slicer_path,
            "--no-splash",
            "--no-main-window",
            "--python-script",
            result_script,
            "--dti_threshold",
            str(dti_threshold),
            "--vein_threshold_mr",
            str(vein_threshold_mr),
            "--vein_threshold_ct",
            str(vein_threshold_ct),
        ]

        popen = subprocess.Popen(
            cmd,
            cwd=self.result_dir,
            stdout=subprocess.PIPE,
            universal_newlines=True,
        )
```

`SlicerViewerWorker.run()`:

```python
        subprocess.Popen(
            [self.slicer_path, self.scene_path],
            cwd=os.getcwd(),
            stdout=subprocess.DEVNULL,
            universal_newlines=True,
        )
```

Remove now-unused `shlex` imports. Before editing, run `git grep -n "slicer_path" swane | grep -v tests` and confirm `slicer_path` is always a bare executable path (no embedded arguments); if any caller embeds arguments, stop and report.

- [ ] **Step 5: Run the worker tests**

Run: `$PY -m pytest swane/tests/workers -m "not heavy" -p no:datalad -v`
Expected: all pass.

- [ ] **Step 6: Real Slicer on Linux (heavy)**

Run: `$PY -m pytest swane/tests/workers/test_slicer_check_worker.py --run-heavy -m heavy -p no:datalad -v`
Expected: `TestSlicerCheckWorkerReal` passes against `~/.local/share/Slicer-5.6.2-linux-amd64` (proves the argv change still detects version and modules). If it skips, report the skip reason verbatim.

- [ ] **Step 7: Black, commit**

```bash
$PY -m black swane/workers/SlicerCheckWorker.py swane/workers/SlicerExportWorker.py swane/workers/SlicerViewerWorker.py swane/tests/workers/test_slicer_check_worker.py swane/tests/workers/test_slicer_export_worker.py swane/tests/workers/test_slicer_viewer_worker.py
git add swane/workers/SlicerCheckWorker.py swane/workers/SlicerExportWorker.py swane/workers/SlicerViewerWorker.py swane/tests/workers/test_slicer_check_worker.py swane/tests/workers/test_slicer_export_worker.py swane/tests/workers/test_slicer_viewer_worker.py
git commit -m "fix(slicer): find Slicer on Windows and invoke it without a shell"
```

---

### Task 5: Prerelease plan without FSL (Opus)

**Files:**
- Modify: `swane/tests/prerelease/capabilities.py` (`BLOCKING`, `blocking_failures`, `_probe_xtract`, new `tractography` capability)
- Modify: `swane/tests/prerelease/plan.py` (axis gates, `_PASS_REQUIREMENTS`)
- Modify: `swane/tests/prerelease/test_plan_integrity.py`
- Modify: `swane/tests/prerelease/README.md` (blocking list, FSL-free hosts)
- Test: `swane/tests/prerelease/test_plan_integrity.py`, new `swane/tests/prerelease/test_fsl_free_plan.py`

**Interfaces:**
- Consumes: `swane.config.dependency_policy.FSL_MANDATORY` (bool).
- Produces: `capabilities.BLOCKING == ("dcm2niix", "fsaverage", "ram_budget")`; `capabilities.blocking_failures(caps)` additionally requires `"fsl"` when `FSL_MANDATORY` is True; capability `"tractography"` = `xtract or dipy`; capability `"xtract"` now also requires FSL (`dependency_manager.is_fsl()`); every FSL-only axis value is gated on `"fsl"`.

Facts from the live plan (verify before editing — `$PY -c "from swane.tests.prerelease import plan; [print(a.name, a.values, a.gates) for a in plan.AXES]"`): ungated FSL values today are `deskull_engine=BET`, `registration_engine=FSL`, `fmri_engine=FSL`, `segmentation_engine=FSL`; `tractography=true` is gated on `xtract` only although `DIPY_RECOBUNDLES` runs without FSL; `_safe_value` falls back to the first *ungated* value, so gating FSL values changes fallbacks too.

- [ ] **Step 1: Write the failing tests** (`swane/tests/prerelease/test_fsl_free_plan.py`)

```python
"""The sweep plan on a host without FSL: nothing blocks, FSL-only values are
reported unreachable (never silently covered), FSL-free passes still run."""

import pytest

from swane.config import dependency_policy
from swane.tests.prerelease import capabilities as caps_mod
from swane.tests.prerelease.capabilities import Capabilities
from swane.tests.prerelease.plan import (
    AXES,
    _PASS_REQUIREMENTS,
    build_plan,
    coverage,
    plan_holes,
)

FSL_ONLY = {"fsl", "xtract"}


@pytest.fixture
def no_fsl_host():
    caps = Capabilities(cores=4, ram_gb=14.0)
    needed = {gate for axis in AXES for gate in axis.gates.values()}
    needed.update({"dcm2niix", "fsaverage", "ram_budget", "slicer", "tractography"})
    needed.update(c for reqs in _PASS_REQUIREMENTS.values() for c in reqs)
    for name in needed - FSL_ONLY:
        caps.add(name, True, "assumed available in this test")
    for name in FSL_ONLY:
        caps.add(name, False, "no FSL on this host")
    return caps


def test_fsl_is_not_blocking_when_optional(no_fsl_host, monkeypatch):
    monkeypatch.setattr(dependency_policy, "FSL_MANDATORY", False)
    assert caps_mod.blocking_failures(no_fsl_host) == []


def test_fsl_blocks_when_mandatory(no_fsl_host, monkeypatch):
    monkeypatch.setattr(dependency_policy, "FSL_MANDATORY", True)
    names = [item.name for item in caps_mod.blocking_failures(no_fsl_host)]
    assert names == ["fsl"]


def test_fsl_free_host_reports_fsl_values_unreachable(no_fsl_host):
    resolved = build_plan(no_fsl_host)
    assert plan_holes(coverage(resolved, no_fsl_host)) == {}
    report = coverage(resolved, no_fsl_host)
    for axis_name, value in (
        ("deskull_engine", "BET"),
        ("registration_engine", "FSL"),
        ("fmri_engine", "FSL"),
        ("segmentation_engine", "FSL"),
        ("tractography_engine", "FSL_XTRACT"),
    ):
        assert value in report[axis_name].unreachable, (axis_name, value)


def test_fsl_free_host_still_runs_dipy_tractography(no_fsl_host):
    resolved = {item.name: item for item in build_plan(no_fsl_host)}
    assert not resolved["dti_tractography_dipy"].skipped, resolved[
        "dti_tractography_dipy"
    ].skip_reason
    assert resolved["structural_fsl"].skipped
    assert resolved["fmri_task_and_rest_fsl"].skipped
```

Before running, confirm the exact names and return shapes of `coverage()` / `plan_holes()` and the `unreachable` attribute in `plan.py` (lines ~1110-1160) and adapt the assertions to them without weakening them.

- [ ] **Step 2: Run to verify they fail**

Run: `$PY -m pytest swane/tests/prerelease/test_fsl_free_plan.py -p no:datalad -v`
Expected: FAIL — `fsl` still blocking; FSL values covered or missing rather than unreachable; `dti_tractography_dipy` skipped for `xtract`.

- [ ] **Step 3: Capabilities**

In `capabilities.py`:

```python
#: Capabilities without which nothing can run at all. FSL joins them only when
#: the build makes it mandatory (swane.config.dependency_policy.FSL_MANDATORY).
BLOCKING = ("dcm2niix", "fsaverage", "ram_budget")


def blocking_failures(caps: Capabilities) -> list:
    """Return the capabilities that make a run pointless, if any."""
    from swane.config import dependency_policy

    names = (("fsl",) if dependency_policy.FSL_MANDATORY else ()) + BLOCKING
    return [caps.items[name] for name in names if not caps.has(name)]
```

Update `_probe_fsl`'s missing message from "nothing can run" to "FSL engines are dropped". Change `_probe_xtract(caps)` to `_probe_xtract(dependency_manager, caps)` requiring `dependency_manager.is_fsl()` as well as the protocol folder (XTRACT runs FSL's probtrackx), and add after `_probe_dipy`:

```python
def _probe_tractography(caps: Capabilities) -> None:
    """Tractography runs with either engine: FSL XTRACT or dipy RecoBundles."""
    ok = caps.has("xtract") or caps.has("dipy")
    caps.add(
        "tractography",
        ok,
        "XTRACT or dipy available" if ok else "neither XTRACT nor dipy is usable",
    )
```

called from `probe()` after `_probe_dipy(caps)`.

- [ ] **Step 4: Gates in the plan**

In `plan.py`: add `"BET": "fsl"` to `deskull_engine.gates`, `"FSL": "fsl"` to `registration_engine`, `fmri_engine`, `segmentation_engine`; change `tractography.gates` to `{"true": "tractography"}`. Add `"structural_fsl": ("fsl",)` and `"fmri_task_and_rest_fsl": ("fsl",)` to `_PASS_REQUIREMENTS` with a comment mirroring the `structural_ants` one.

Then audit every remaining axis and pass for implicit FSL use. Criterion: **an axis value whose effect exists only when an FSL tool runs gets gate `"fsl"`; a pass that cannot run any FSL-free variant gets `("fsl",)` in `_PASS_REQUIREMENTS`.** Candidates to check with evidence (read the consuming workflow for each): `ref_bet_bias_correction`, `ref_bet_thr`, `venous_mr_bet_thr` (BET parameters), `old_eddy_correct` (FSL `eddy_correct`), the DTI preprocessing path (FSL `eddy` vs dipy), FLAT1 / ASL / PET / venous workflows, the prerelease `checks.py` MNI152 lookup from `$FSLDIR`. For each candidate write one line in the commit body: "kept/gated — why (file:line)". If gating every value of an axis, the axis becomes wholly unreachable without FSL — that is the correct report.

- [ ] **Step 5: Update the existing plan-integrity fixture and test**

In `test_plan_integrity.py`, add `"tractography"` to the `all_capable` capability set; in the test around line 124 replace the hard-coded `("fsl", "dcm2niix", "fsaverage", "ram_budget", "slicer")` loop with names derived from `capabilities.BLOCKING` plus `"fsl"`/`"slicer"` where the test needs them, keeping its intent (read it first).

- [ ] **Step 6: Run the plan tests**

Run: `$PY -m pytest swane/tests/prerelease -m "not heavy" -p no:datalad -v`
Expected: all pass, including the 4 new tests.

- [ ] **Step 7: Construction proof without FSL**

Add to `test_fsl_free_plan.py` a test that, for every non-skipped pass of `build_plan(no_fsl_host)`, builds the subject with `swane.tests.prerelease.subject.prepare_subject` against a stub `PhantomExam` whose `root` is `tmp_path` and whose `series` mirrors the phantom manifest keys used by `_wiring` (create the empty series folders; `n_vols`/`bvals` entries as `volumes()` expects), then constructs `MainWorkflow(..., test_run=True)` with `DependencyManager.check_fsl` monkeypatched to MISSING and `FSLDIR` unset (reuse the setup of `swane/tests/nipype_pipeline/test_fsl_free_main_workflow.py`), and asserts no node is an FSL command other than niimath (reuse its `_is_niimath` predicate and FSL-node filter). Mark it `@pytest.mark.heavy` only if the whole parametrized run exceeds 60 s locally. Any FSL node found is either a missed gate (fix in Step 4) or a real FSL dependency of an FSL-free default (report to the maintainer, do not paper over it).

Run: `$PY -m pytest swane/tests/prerelease/test_fsl_free_plan.py -p no:datalad -v` (add `--run-heavy` if marked heavy).
Expected: PASS for every pass.

- [ ] **Step 8: Real dry run on Linux with FSL hidden**

Run: `env -u FSLDIR -u FSLOUTPUTTYPE $PY -m swane.tests.prerelease --dry-run --cores 8 --ram 10`
Expected: no blocking failure for FSL; FSL passes listed as skipped "needs fsl"; coverage shows FSL values as unreachable and **no missing**. Then run `$PY -m swane.tests.prerelease --dry-run --cores 8 --ram 10` with FSL visible: identical plan to `dev` except the new `tractography` capability line (diff the two outputs against a `git stash`-free run on `dev` via `git worktree add $TMPDIR/dev-wt origin/dev`).

- [ ] **Step 9: README, Black, commit**

Update `swane/tests/prerelease/README.md`: blocking list (dcm2niix, fsaverage, RAM budget; FSL only when `FSL_MANDATORY`), FSL axes unreachable on FSL-free hosts.

```bash
$PY -m black swane/tests/prerelease/capabilities.py swane/tests/prerelease/plan.py swane/tests/prerelease/test_plan_integrity.py swane/tests/prerelease/test_fsl_free_plan.py
git add swane/tests/prerelease/capabilities.py swane/tests/prerelease/plan.py swane/tests/prerelease/test_plan_integrity.py swane/tests/prerelease/test_fsl_free_plan.py swane/tests/prerelease/README.md
git commit -m "test(prerelease): run the sweep without FSL; gate FSL-only values"
```

---

### Task 6: fsaverage from FreeSurfer or the MNE mirror

**Files:**
- Create: `swane/tests/helpers/phantom/fsaverage_source.py`
- Modify: `swane/tests/helpers/phantom/tissue.py:97-106` (`_fsaverage_dir`)
- Modify: `swane/tests/helpers/phantom/dataset.py:94-115,140-145` (`_cache_key`, `_resolve_freesurfer_home`, `get_phantom_subject`)
- Modify: `swane/tests/prerelease/capabilities.py:425-438` (`_probe_freesurfer_subject`)
- Modify: `swane/tests/helpers/phantom/test_deformation.py:24-28`, `test_ground_truth.py:27-31` (`_has_fsaverage`)
- Modify: `swane/tests/helpers/phantom/README.md`, `swane/tests/prerelease/README.md` (license note)
- Test: `swane/tests/helpers/phantom/test_fsaverage_source.py`

**Interfaces:**
- Produces:
  - `FSAVERAGE_FILES = ("aseg.mgz", "aparc+aseg.mgz")`
  - `MNE_FSAVERAGE_URL: str`, `MNE_FSAVERAGE_MD5: str`, `DEFAULT_CACHE_DIR: str` (`~/.cache/swane/fsaverage/mri`)
  - `freesurfer_fsaverage_mri_dir(freesurfer_home: str | None = None) -> str` ("" when absent)
  - `fsaverage_available(freesurfer_home: str | None = None, cache_dir: str | None = None) -> bool` (no network)
  - `download_fsaverage_mri(cache_dir: str | None = None, url: str = MNE_FSAVERAGE_URL, md5: str = MNE_FSAVERAGE_MD5) -> str`
  - `resolve_fsaverage_mri_dir(freesurfer_home: str | None = None, allow_download: bool = True, cache_dir: str | None = None) -> str`
  - `fsaverage_fingerprint(mri_dir: str) -> str` (md5 hex over both files, in `FSAVERAGE_FILES` order)

- [ ] **Step 1: Write the failing tests** (`test_fsaverage_source.py`)

```python
"""fsaverage resolution: FreeSurfer first, then the md5-pinned MNE mirror."""

import hashlib
import io
import zipfile

import pytest

from swane.tests.helpers.phantom import fsaverage_source as fs


def _zip_bytes(extra=True) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("fsaverage/mri/aseg.mgz", b"aseg-bytes")
        archive.writestr("fsaverage/mri/aparc+aseg.mgz", b"aparc-bytes")
        if extra:
            archive.writestr("fsaverage/mri/T1.mgz", b"not wanted")
    return buf.getvalue()


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _fake_urlopen(payload, calls):
    def urlopen(url, timeout=None, context=None):
        calls.append(url)
        return _Response(payload)

    return urlopen


def test_freesurfer_install_wins(tmp_path, monkeypatch):
    mri = tmp_path / "fs" / "subjects" / "fsaverage" / "mri"
    mri.mkdir(parents=True)
    for name in fs.FSAVERAGE_FILES:
        (mri / name).write_bytes(b"x")
    calls = []
    monkeypatch.setattr(fs.urllib.request, "urlopen", _fake_urlopen(b"", calls))
    got = fs.resolve_fsaverage_mri_dir(
        freesurfer_home=str(tmp_path / "fs"), cache_dir=str(tmp_path / "cache")
    )
    assert got == str(mri)
    assert calls == []


def test_download_extracts_only_the_two_files(tmp_path, monkeypatch):
    payload = _zip_bytes()
    calls = []
    monkeypatch.setattr(fs.urllib.request, "urlopen", _fake_urlopen(payload, calls))
    cache = tmp_path / "cache" / "mri"
    got = fs.download_fsaverage_mri(
        cache_dir=str(cache), md5=hashlib.md5(payload).hexdigest()
    )
    assert got == str(cache)
    assert sorted(p.name for p in cache.iterdir()) == sorted(fs.FSAVERAGE_FILES)
    assert (cache / "aseg.mgz").read_bytes() == b"aseg-bytes"
    assert list((cache.parent).glob("*.zip")) == []
    assert len(calls) == 1
    # Second resolution uses the cache, no network.
    assert fs.resolve_fsaverage_mri_dir(
        freesurfer_home=str(tmp_path / "nofs"), cache_dir=str(cache)
    ) == str(cache)
    assert len(calls) == 1


def test_md5_mismatch_leaves_no_cache(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        fs.urllib.request, "urlopen", _fake_urlopen(_zip_bytes(), calls)
    )
    cache = tmp_path / "cache" / "mri"
    with pytest.raises(RuntimeError, match="md5"):
        fs.download_fsaverage_mri(cache_dir=str(cache), md5="0" * 32)
    assert not fs.fsaverage_available(
        freesurfer_home=str(tmp_path / "nofs"), cache_dir=str(cache)
    )


def test_no_download_allowed_raises_clearly(tmp_path):
    with pytest.raises(RuntimeError, match="fsaverage"):
        fs.resolve_fsaverage_mri_dir(
            freesurfer_home=str(tmp_path / "nofs"),
            allow_download=False,
            cache_dir=str(tmp_path / "cache"),
        )


def test_fingerprint_depends_on_content_not_location(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    for d in (a, b):
        d.mkdir()
        (d / "aseg.mgz").write_bytes(b"1")
        (d / "aparc+aseg.mgz").write_bytes(b"2")
    assert fs.fsaverage_fingerprint(str(a)) == fs.fsaverage_fingerprint(str(b))
    (b / "aseg.mgz").write_bytes(b"3")
    assert fs.fsaverage_fingerprint(str(a)) != fs.fsaverage_fingerprint(str(b))
```

- [ ] **Step 2: Run them to verify they fail**

Run: `$PY -m pytest swane/tests/helpers/phantom/test_fsaverage_source.py -p no:datalad -v`
Expected: ERROR `ImportError: cannot import name 'fsaverage_source'`.

- [ ] **Step 3: Implement** (`fsaverage_source.py`)

```python
"""Locate the two fsaverage segmentations the phantom anatomy is built from.

The phantom reads only ``fsaverage/mri/aseg.mgz`` and ``aparc+aseg.mgz``.
They come from ``$FREESURFER_HOME/subjects/fsaverage`` when FreeSurfer is
installed; otherwise they are downloaded at runtime from the fsaverage archive
MNE-Python mirrors (``mne-tools/mne-data``, release ``fsaverage-1.0``), pinned
by md5. The mirrored files were verified byte-identical to FreeSurfer 8.2's.

License: these are FreeSurfer data, distributed under the FreeSurfer Software
License (https://github.com/freesurfer/freesurfer/blob/dev/LICENSE.txt); the
mirror repository's own license does not change that. SWANe only fetches them
to build a local phantom: they are never committed, packaged or uploaded.
"""

import hashlib
import os
import shutil
import ssl
import tempfile
import urllib.request
import zipfile

FSAVERAGE_FILES = ("aseg.mgz", "aparc+aseg.mgz")
MNE_FSAVERAGE_URL = (
    "https://github.com/mne-tools/mne-data/releases/download/"
    "fsaverage-1.0/fsaverage-root.zip"
)
MNE_FSAVERAGE_MD5 = "5133fe92b7b8f03ae19219d5f46e4177"
DEFAULT_CACHE_DIR = os.path.join(
    os.path.expanduser("~"), ".cache", "swane", "fsaverage", "mri"
)
_DOWNLOAD_TIMEOUT_S = 600


def _has_files(mri_dir: str) -> bool:
    return bool(mri_dir) and all(
        os.path.isfile(os.path.join(mri_dir, name)) for name in FSAVERAGE_FILES
    )


def freesurfer_fsaverage_mri_dir(freesurfer_home: str | None = None) -> str:
    """Return ``<FREESURFER_HOME>/subjects/fsaverage/mri`` if usable, else ""."""
    home = freesurfer_home or os.environ.get("FREESURFER_HOME") or ""
    path = os.path.join(home, "subjects", "fsaverage", "mri") if home else ""
    return path if _has_files(path) else ""


def fsaverage_available(
    freesurfer_home: str | None = None, cache_dir: str | None = None
) -> bool:
    """True when the files are on disk already (never touches the network)."""
    return bool(freesurfer_fsaverage_mri_dir(freesurfer_home)) or _has_files(
        cache_dir or DEFAULT_CACHE_DIR
    )


def _md5(path: str) -> str:
    digest = hashlib.md5()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _ssl_context():
    # python.org macOS builds ship without CA certificates (see
    # swane.utils.antspynet_weights): prefer certifi's bundle when present.
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def download_fsaverage_mri(
    cache_dir: str | None = None,
    url: str = MNE_FSAVERAGE_URL,
    md5: str = MNE_FSAVERAGE_MD5,
) -> str:
    """Download the mirror archive, verify it, keep only the two segmentations."""
    cache_dir = cache_dir or DEFAULT_CACHE_DIR
    if _has_files(cache_dir):
        return cache_dir
    os.makedirs(cache_dir, exist_ok=True)
    handle, tmp_zip = tempfile.mkstemp(suffix=".zip", dir=os.path.dirname(cache_dir))
    os.close(handle)
    try:
        with urllib.request.urlopen(
            url, timeout=_DOWNLOAD_TIMEOUT_S, context=_ssl_context()
        ) as response, open(tmp_zip, "wb") as out:
            shutil.copyfileobj(response, out)
        got = _md5(tmp_zip)
        if got != md5:
            raise RuntimeError(
                "fsaverage archive md5 mismatch: expected %s, got %s (%s)"
                % (md5, got, url)
            )
        with zipfile.ZipFile(tmp_zip) as archive:
            for name in FSAVERAGE_FILES:
                staging = os.path.join(cache_dir, name + ".part")
                with archive.open("fsaverage/mri/" + name) as src, open(
                    staging, "wb"
                ) as dst:
                    shutil.copyfileobj(src, dst)
                os.replace(staging, os.path.join(cache_dir, name))
    finally:
        if os.path.exists(tmp_zip):
            os.remove(tmp_zip)
    return cache_dir


def resolve_fsaverage_mri_dir(
    freesurfer_home: str | None = None,
    allow_download: bool = True,
    cache_dir: str | None = None,
) -> str:
    """Return a folder holding both segmentations, downloading them if needed."""
    local = freesurfer_fsaverage_mri_dir(freesurfer_home)
    if local:
        return local
    cache_dir = cache_dir or DEFAULT_CACHE_DIR
    if _has_files(cache_dir):
        return cache_dir
    if not allow_download:
        raise RuntimeError(
            "fsaverage not found: install FreeSurfer (set FREESURFER_HOME) or "
            "allow the download of the MNE fsaverage mirror into %s" % cache_dir
        )
    return download_fsaverage_mri(cache_dir)


def fsaverage_fingerprint(mri_dir: str) -> str:
    """md5 over both segmentations: identifies the anatomy, not its location."""
    digest = hashlib.md5()
    for name in FSAVERAGE_FILES:
        digest.update(_md5(os.path.join(mri_dir, name)).encode())
    return digest.hexdigest()
```

- [ ] **Step 4: Run the new tests**

Run: `$PY -m pytest swane/tests/helpers/phantom/test_fsaverage_source.py -p no:datalad -v`
Expected: 5 passed.

- [ ] **Step 5: Route the phantom through it**

`tissue.py`:

```python
def _fsaverage_dir(freesurfer_home: str | None = None) -> str:
    from swane.tests.helpers.phantom.fsaverage_source import resolve_fsaverage_mri_dir

    return resolve_fsaverage_mri_dir(freesurfer_home)
```

(Update the module docstring sentence "Only ``fsaverage`` is read (it ships with FreeSurfer)" to mention the MNE-mirror fallback.)

`dataset.py`: replace `_resolve_freesurfer_home` with a resolver of the mri folder and key the cache on content:

```python
def _cache_key(profile: PhantomProfile, fsaverage_mri: str) -> str:
    payload = json.dumps(
        {
            "version": GENERATOR_VERSION,
            "profile": asdict(profile),
            # Content, not location: FreeSurfer's fsaverage and the MNE mirror
            # are byte-identical and must give the same cached phantom.
            "fsaverage": fsaverage_fingerprint(fsaverage_mri),
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]
```

In `get_phantom_subject`: `fs_mri = resolve_fsaverage_mri_dir(freesurfer_home)`, `key = _cache_key(profile, fs_mri)`, and keep passing `freesurfer_home` (possibly None) to `build_phantom` unchanged (its `build_tissue_model(freesurfer_home)` resolves the same folder). Grep for every other caller of `_resolve_freesurfer_home` (`git grep -n _resolve_freesurfer_home`) and switch them too.

`capabilities._probe_freesurfer_subject`: `ok = fsaverage_available() or _can_download()` is NOT wanted (no network in a probe). Use:

```python
def _probe_freesurfer_subject(caps: Capabilities) -> None:
    """The phantom anatomy is derived from fsaverage (FreeSurfer or MNE mirror)."""
    from swane.tests.helpers.phantom.fsaverage_source import (
        DEFAULT_CACHE_DIR,
        freesurfer_fsaverage_mri_dir,
        fsaverage_available,
    )

    local = freesurfer_fsaverage_mri_dir()
    caps.add(
        "fsaverage",
        True,
        (
            "fsaverage from FreeSurfer (%s)" % local
            if local
            else (
                "fsaverage from the MNE mirror cache (%s)" % DEFAULT_CACHE_DIR
                if fsaverage_available()
                else "fsaverage will be downloaded from the MNE mirror"
            )
        ),
    )
```

A failed download then surfaces as a clear `RuntimeError` when the phantom is built (`load_phantom`), not as a silent capability.

`test_deformation.py` / `test_ground_truth.py` `_has_fsaverage()`:

```python
def _has_fsaverage() -> bool:
    from swane.tests.helpers.phantom.fsaverage_source import fsaverage_available

    return fsaverage_available()
```

(The heavy phantom tests thus run wherever FreeSurfer or a warmed cache exists; CI warms the cache in Task 7.)

- [ ] **Step 6: Prove identity on Linux**

Run:

```bash
$PY - <<'EOF'
import os, tempfile
from swane.tests.helpers.phantom import fsaverage_source as fs
local = fs.freesurfer_fsaverage_mri_dir()
mirror = fs.download_fsaverage_mri(cache_dir=os.path.join(tempfile.mkdtemp(dir=os.environ.get("TMPDIR")), "mri"))
print(local, mirror)
assert fs.fsaverage_fingerprint(local) == fs.fsaverage_fingerprint(mirror)
print("identical")
EOF
```

Expected: prints `identical` (network to github.com required; if blocked, record that and rely on the md5 check done during design).

- [ ] **Step 7: Phantom suites**

Run: `$PY -m pytest swane/tests/helpers/phantom swane/tests/prerelease -m "not heavy" -p no:datalad -q`, then `$PY -m pytest swane/tests/helpers/phantom --run-heavy -m heavy -p no:datalad -q`.
Expected: all pass. The local phantom cache key changes, so the heavy run rebuilds the phantom once under `~/test_swane/phantom` (expected, several minutes).

- [ ] **Step 8: Docs, Black, commit**

Add the license paragraph (same wording as the module docstring) to `swane/tests/helpers/phantom/README.md` and the prerelease README "Requirements" section.

```bash
$PY -m black swane/tests/helpers/phantom/fsaverage_source.py swane/tests/helpers/phantom/tissue.py swane/tests/helpers/phantom/dataset.py swane/tests/prerelease/capabilities.py swane/tests/helpers/phantom/test_deformation.py swane/tests/helpers/phantom/test_ground_truth.py swane/tests/helpers/phantom/test_fsaverage_source.py
git add swane/tests/helpers/phantom swane/tests/prerelease/capabilities.py swane/tests/prerelease/README.md
git commit -m "test(phantom): fall back to the md5-pinned MNE fsaverage mirror"
```

(Check `git status` first: `swane/tests/helpers/phantom` must contain no generated data.)

---

### Task 7: Heavy and prerelease CI jobs

**Files:**
- Modify: `.github/workflows/windows-tests.yml`

**Interfaces:**
- Consumes: Task 1 workflow inputs; Task 5 CLI behaviour (`--list`, `--dry-run`, `--only`, `--work-dir`, `--timeout`); Task 6 `DEFAULT_CACHE_DIR` (`~/.cache/swane/fsaverage/mri`) and phantom cache root (`~/test_swane/phantom`, overridable with `SWANE_PHANTOM_DIR`).

- [ ] **Step 1: Read the CLI contract**

Run: `$PY -m swane.tests.prerelease --help` and `$PY -m swane.tests.prerelease --list | head -40`. Note the exact `--list` output format and `--timeout` unit. If `--list` cannot be filtered to runnable passes on the host, add a `--list-json` option in `swane/tests/prerelease/__main__.py` that prints `json.dumps([p.name for p in build_plan(caps) if not p.skipped])` after probing, with a light test in `swane/tests/prerelease/test_runner.py` (monkeypatched probe), and commit it separately: `test(prerelease): --list-json for CI matrices`.

- [ ] **Step 2: Add the jobs** (append under `jobs:`)

```yaml
  heavy:
    if: ${{ inputs.suite == 'heavy' || inputs.suite == 'all' }}
    runs-on: ${{ inputs.os }}
    timeout-minutes: 240
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install SWANe
        shell: bash
        run: |
          python -m pip install --upgrade pip
          python -m pip install -e . pytest pytest-qt
      - name: Restore model/data caches
        uses: actions/cache@v4
        with:
          path: |
            ~/.keras
            ~/.antspy
            ~/.cache/templateflow
            ~/.cache/swane
            ~/.dipy
          key: heavy-${{ inputs.os }}-${{ hashFiles('setup.py') }}-${{ inputs.rebuild_cache && github.run_id || 'v1' }}
      - name: Heavy tests
        shell: bash
        run: >
          python -m pytest swane/tests --run-heavy -m heavy
          --basetemp "${{ runner.temp }}/swane tmp"
          --junitxml=junit-heavy.xml -p no:cacheprovider -rs
      - if: always()
        uses: actions/upload-artifact@v4
        with:
          name: heavy-${{ inputs.os }}
          path: junit-heavy.xml

  prerelease-plan:
    if: ${{ inputs.suite == 'prerelease' || inputs.suite == 'all' }}
    runs-on: windows-latest
    timeout-minutes: 120
    outputs:
      passes: ${{ steps.plan.outputs.passes }}
    env:
      SWANE_PHANTOM_DIR: D:\swp_phantom
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install SWANe
        shell: bash
        run: |
          python -m pip install --upgrade pip
          python -m pip install -e . pytest pytest-qt
      - name: Phantom cache
        id: phantom
        uses: actions/cache@v4
        with:
          path: |
            D:\swp_phantom
            ~/.cache/swane/fsaverage
          key: phantom-${{ hashFiles('swane/tests/helpers/phantom/**/*.py') }}-${{ inputs.rebuild_cache && github.run_id || 'v1' }}
          enableCrossOsArchive: true
      - name: Build phantom
        if: steps.phantom.outputs.cache-hit != 'true'
        shell: bash
        run: python -c "from swane.tests.prerelease.subject import load_phantom; print(load_phantom().root)"
      - name: Plan
        id: plan
        shell: bash
        run: |
          python -m swane.tests.prerelease --dry-run --cores 4 --ram 14 | tee dry-run.txt
          if [ -n "${{ inputs.passes }}" ]; then
            passes=$(python -c "import json,sys; print(json.dumps([p.strip() for p in sys.argv[1].split(',') if p.strip()]))" "${{ inputs.passes }}")
          else
            passes=$(python -m swane.tests.prerelease --list-json --cores 4 --ram 14)
          fi
          echo "passes=$passes" >> "$GITHUB_OUTPUT"
      - if: always()
        uses: actions/upload-artifact@v4
        with:
          name: prerelease-plan
          path: dry-run.txt

  prerelease-run:
    needs: prerelease-plan
    if: ${{ needs.prerelease-plan.outputs.passes != '[]' }}
    runs-on: windows-latest
    timeout-minutes: 350
    strategy:
      fail-fast: false
      max-parallel: 4
      matrix:
        pass: ${{ fromJSON(needs.prerelease-plan.outputs.passes) }}
    env:
      SWANE_PHANTOM_DIR: D:\swp_phantom
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install SWANe
        shell: bash
        run: |
          python -m pip install --upgrade pip
          python -m pip install -e . pytest pytest-qt
      - uses: actions/cache/restore@v4
        with:
          path: |
            D:\swp_phantom
            ~/.cache/swane/fsaverage
          key: phantom-${{ hashFiles('swane/tests/helpers/phantom/**/*.py') }}-${{ inputs.rebuild_cache && github.run_id || 'v1' }}
          enableCrossOsArchive: true
          fail-on-cache-miss: true
      - uses: actions/cache@v4
        with:
          path: |
            ~/.keras
            ~/.antspy
            ~/.cache/templateflow
            ~/.dipy
          key: prerelease-models-${{ hashFiles('setup.py') }}
      - name: Run pass
        shell: bash
        run: >
          python -m swane.tests.prerelease --only ${{ matrix.pass }}
          --cores 4 --ram 14 --work-dir "D:/swp" --timeout 5.5
      - if: always()
        uses: actions/upload-artifact@v4
        with:
          name: prerelease-${{ matrix.pass }}
          path: |
            D:/swp/*.html
            D:/swp/*.json
            D:/swp/**/log/*.txt
            D:/swp/**/log/pypeline.log
```

`--timeout` is in hours (float, default 3.0): 5.5 keeps each pass under the 6 h job limit. The artifact globs (reports are `prerelease_report.json`/`.html`, per-pass `pass_result.json`, state `prerelease_state.json`) must match the real report/crash file locations written by `runner.py`/`report.py` — read them (`git grep -n "prerelease_report\|crashdump_dir\|LOG_DIR_NAME" swane/tests/prerelease swane/workers`) and adjust; never include `dicom/`, phantom or result volumes.

- [ ] **Step 3: Validate YAML and job graph**

Run: `$PY -c "import yaml; d=yaml.safe_load(open('.github/workflows/windows-tests.yml')); print(sorted(d['jobs']))"`
Expected: `['heavy', 'light', 'prerelease-plan', 'prerelease-run']`.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/windows-tests.yml
git commit -m "ci: add heavy and sharded prerelease jobs to the manual workflow"
```

---

### Task 8: Experimental notice, docs and local handoff

**Files:**
- Modify: `swane/utils/platform_and_tools_utils.py` (`get_os_type`, `is_windows`)
- Modify: `swane/utils/ResourceManager.py:16-37` (add `"windows"` keys equal to `"other"`)
- Modify: `swane/resources/strings.py` (new `windows_experimental_warn`)
- Modify: `swane/ui/PreferenceWizardWindow.py:_page_welcome`
- Modify: `swane/ui/MainWindow.py:home_tab_ui`
- Modify: `README.md` (platforms)
- Create: `~/test_swane/windows/HANDOFF.md` (outside the repo, not committed)
- Create (draft, not committed here): `~/test_swane/windows/wiki-windows-note.md`
- Test: `swane/tests/utils/test_platform_and_tools_utils.py`, `swane/tests/ui/test_preference_wizard.py`, `swane/tests/ui/test_main_window.py`

**Interfaces:**
- Produces: `get_os_type()` returns `"windows"` on Windows (was `"other"`); `is_windows() -> bool`; `strings.windows_experimental_warn: str`. Every `ResourceManager.*_RAM_REQUIREMENT` dict gains a `"windows"` key with the current `"other"` value, so lookups keep working.

- [ ] **Step 1: Write the failing tests**

In `test_platform_and_tools_utils.py`, extend the existing `Windows` block:

```python
    monkeypatch.setattr(pu.platform, "system", lambda: "Windows")
    assert pu.get_os_type() == "windows"
    assert pu.is_windows() is True
    assert pu.is_linux() is False
    assert pu.is_mac() is False
```

Add to `swane/tests/utils/test_resource_manager.py` (or the existing ResourceManager test file — `git grep -ln ResourceManager swane/tests/utils`):

```python
def test_every_ram_requirement_has_a_windows_value():
    from swane.utils.ResourceManager import ResourceManager

    for name in dir(ResourceManager):
        if name.endswith("_RAM_REQUIREMENT"):
            table = getattr(ResourceManager, name)
            assert table["windows"] == table["other"], name
```

In `test_preference_wizard.py`:

```python
    def test_welcome_page_warns_on_windows_only(
        self, qtbot, global_config, dependency_manager, monkeypatch
    ):
        import swane.ui.PreferenceWizardWindow as wizard_module
        from swane.resources import strings
        from PySide6.QtWidgets import QLabel

        def texts(wizard):
            page = wizard._stack.widget(0)
            return " ".join(label.text() for label in page.findChildren(QLabel))

        monkeypatch.setattr(wizard_module, "is_windows", lambda: True)
        wizard = PreferenceWizardWindow(global_config, dependency_manager)
        qtbot.addWidget(wizard)
        assert "experimental" in texts(wizard)

        monkeypatch.setattr(wizard_module, "is_windows", lambda: False)
        wizard = PreferenceWizardWindow(global_config, dependency_manager)
        qtbot.addWidget(wizard)
        assert "experimental" not in texts(wizard)
```

Check first that `_make_title` renders text into `QLabel`s and that page 0 is the welcome page; adapt the `texts()` helper to the real widgets without weakening the assertion.

In `test_main_window.py`:

```python
def test_home_tab_shows_windows_notice(monkeypatch, request):
    import swane.ui.MainWindow as main_window_module

    monkeypatch.setattr(main_window_module, "is_windows", lambda: True)
    window = request.getfixturevalue("main_window")
    from PySide6.QtWidgets import QLabel

    texts = [w.text() for w in window.homeTab.findChildren(QLabel)]
    assert any("experimental" in t for t in texts)
```

(Check `swane/tests/ui/conftest.py`: if the `main_window` fixture builds the window before the monkeypatch can apply, build a window directly with the same arguments the fixture uses.)

- [ ] **Step 2: Run them to verify they fail**

Run: `$PY -m pytest swane/tests/utils/test_platform_and_tools_utils.py swane/tests/ui/test_preference_wizard.py swane/tests/ui/test_main_window.py -p no:datalad -v` plus the ResourceManager test file.
Expected: FAIL (`is_windows` missing, `"other" != "windows"`, no notice).

- [ ] **Step 3: Implement**

`platform_and_tools_utils.py`:

```python
    :return: 'mac' if macOS, 'linux' if Linux, 'windows' if Windows, 'other' otherwise
    ...
    elif system == "windows":
        return "windows"
```

```python
def is_windows() -> bool:
    """
    Check if the operating system is Windows.
    """
    return get_os_type() == "windows"
```

Before changing `get_os_type`, run `git grep -n "get_os_type\|\"other\"" swane | grep -v tests` and update every consumer keyed on `"other"` (today: `ResourceManager` tables) so Windows keeps the same values.

`strings.py` (next to `wizard_advanced_models_macos_warn`):

```python
windows_experimental_warn = "<b>Please note</b>: Windows support is <b>experimental</b>. FSL and FreeSurfer are not available natively on Windows; 3D Slicer integration is best-effort."
```

`PreferenceWizardWindow._page_welcome`: import `is_windows` alongside `is_mac`, then

```python
        welcome_text = strings.wizard_welcome_text
        if is_windows():
            welcome_text += "<br><br>" + strings.windows_experimental_warn
        lay.addWidget(self._make_title(strings.wizard_welcome_title, welcome_text))
```

`MainWindow.home_tab_ui`: import `is_windows`, and right after `label_welcome3` is added:

```python
        if is_windows():
            label_windows = QLabel(strings.windows_experimental_warn)
            label_windows.setWordWrap(True)
            self.home_grid_layout.addWidget(label_windows, x, 0, 1, 5)
            x += 1
```

- [ ] **Step 4: Run the tests**

Run: same as Step 2. Expected: PASS. Then `$PY -m pytest swane/tests/ui swane/tests/utils -m "not heavy" -p no:datalad -q` — all pass.

- [ ] **Step 5: README**

In the README platforms/requirements section add one line: "Windows (experimental): FSL-free pipelines only; FSL and FreeSurfer are not available natively; 3D Slicer integration is best-effort."

- [ ] **Step 6: Local handoff (not committed)**

Write `~/test_swane/windows/HANDOFF.md` containing: the branch name; install (`py -3.12 -m venv swane-env`, `swane-env\Scripts\pip install -e .[...]` exactly as the CI step); what CI covered (link the latest green run IDs once known); the manual checklist — launch via the `swane` entry point (`pythonw`, no console) and via `python -m swane`; run the wizard; create a subject under a folder containing a space and a non-ASCII character; run an FSL-free workflow end to end; delete a subject while its log is open in another program; run as a non-admin user without Developer Mode (symlinks refused); install real 3D Slicer and run the dependency check, export and viewer; check `slicer_script_result.py`'s FreeSurfer-segmentation branch on Windows; report anything with the exact traceback. Also write `~/test_swane/windows/wiki-windows-note.md` with the README line expanded for the wiki's installation page, for the maintainer to commit in `../swane.wiki`.

- [ ] **Step 7: Black, commit**

```bash
$PY -m black swane/utils/platform_and_tools_utils.py swane/utils/ResourceManager.py swane/resources/strings.py swane/ui/PreferenceWizardWindow.py swane/ui/MainWindow.py swane/tests/utils/test_platform_and_tools_utils.py swane/tests/ui/test_preference_wizard.py swane/tests/ui/test_main_window.py
git add swane/utils/platform_and_tools_utils.py swane/utils/ResourceManager.py swane/resources/strings.py swane/ui/PreferenceWizardWindow.py swane/ui/MainWindow.py README.md swane/tests/utils swane/tests/ui
git commit -m "feat(windows): flag Windows support as experimental in the UI and README"
```

---

### Task 9: CI-driven hardening loop (spec W2.5)

This task has no predetermined code: it turns real Windows failures into fixes.

- [ ] **Step 1:** With the maintainer's OK, push the branch (`git push -u origin claude/windows-support`) and ask them to run, in order: `suite=light os=windows-latest`, `suite=light os=macos-latest`, `suite=heavy os=windows-latest`, `suite=heavy os=macos-latest`, `suite=prerelease`.
- [ ] **Step 2:** For each failing test or pass, use superpowers:systematic-debugging on the downloaded artifacts/logs. Expected classes: unquoted paths with spaces in nipype `CommandLine` (fix: quote the path `argstr` in SWANe's own niimath/dcm2niix interfaces only), MAX_PATH (fix: shorter node/work dir names only if no contract changes; otherwise document `LongPathsEnabled`), open-file locks on delete/rename, `pythonw` stdout/stderr `None`.
- [ ] **Step 3:** Each fix gets its own failing test (runnable on Linux where possible, otherwise a Windows-only test with `skipif(os.name != "nt")`), its own commit, and a re-run of the failing CI job.
- [ ] **Step 4:** Done when light+heavy are green on Windows and macOS and every runnable prerelease pass is green on Windows with no coverage *missing*. Update `~/test_swane/windows/HANDOFF.md` with the green run IDs.

---

### Final verification (before declaring the branch complete)

- [ ] `$PY -m compileall -q swane`
- [ ] `$PY -m pytest swane/tests -m "not heavy" -p no:datalad -q` — all pass on Linux.
- [ ] `$PY -m pytest swane/tests/nipype_pipeline/matrix -p no:datalad -q` — no snapshot diff (this branch must not change graphs).
- [ ] Prerelease on Linux: `$PY -m swane.tests.prerelease --only structural_ants --cores 8 --ram 10` and `--only structural_fsl` — green (FSL path unchanged, ANTS path unchanged); root `~/test_swane/prerelease` verified before running.
- [ ] Windows and macOS: green CI runs from Task 9 recorded.
- [ ] `$PY -m black --check` on every changed Python file.
- [ ] Update `.claude/skills/swane-dev-assistant/references/testing.md` (prerelease blocking requirements; Windows/macOS manual workflow) — the skills folder is write-protected for agents: draft the change and hand it to the maintainer.
