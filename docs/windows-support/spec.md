# Experimental Windows support — design

Date: 2026-10-04
Branch: `claude/windows-support` (from `dev` at `7bb1297`)

## Goal

Let SWANe run natively on Windows as an **experimental** platform: the FSL-free
pipelines (ANTs, dipy, nilearn, niimath, dcm2niix engines — the defaults since
`FSL_MANDATORY=False`) execute end to end; 3D Slicer integration is best-effort;
FSL and FreeSurfer are reported as unavailable. Windows is validated by manually
triggered GitHub Actions runs (light, heavy, prerelease suites); a later local
Windows session continues from a handoff file.

Success criteria:

1. `windows-tests.yml` (manual `workflow_dispatch`) runs the light and heavy
   suites green on `windows-latest`, with Nipype MultiProc actually exercised
   (no `os.name == "nt"` skips left for MultiProc).
2. The FSL-free prerelease passes run green on `windows-latest`, with the FSL
   axes reported as *unreachable* (never *missing*) in the coverage report.
3. Linux and macOS behaviour is unchanged: light suite, matrix snapshots and the
   touched prerelease passes stay green on Linux; light/heavy run green on
   `macos-latest` through the same workflow.
4. Windows users see an explicit "experimental" notice.

Non-goals: installer / Start-menu shortcut, GPU on Windows (native TensorFlow is
CPU-only), WSL-based FSL/FreeSurfer, automatic CI triggers on push/PR.

## Findings that drive the design

- Every native Python dependency ships `win_amd64` cp312 wheels (antspyx,
  tensorflow, niimath, dcm2niix, dipy, PySide6); `ica_aroma_py` is pure Python.
- `nipype/pipeline/plugins/__init__.py` imports `sge.py`, which does
  `import pwd` (Unix-only): `MultiProcPlugin` cannot be imported on Windows.
  This is the only hard blocker for workflow execution.
- `WorkflowProcess` is already spawn-safe (macOS default start method);
  `worker_pool_start_method()` already falls back to `spawn`;
  `DipyMotionCorrection` already uses `spawn` on Windows; dcm2niix/niimath
  wrappers already resolve `.exe`.
- POSIX-only spots: GNU `find` for Slicer discovery
  (`SlicerCheckWorker.find_slicer_python`); `shell=True` + `shlex.quote`
  (POSIX quoting) in the Slicer workers; `os.symlink` in
  `utils/templates.py` (needs Developer Mode on Windows); ~23 text-mode
  `open()` calls without `encoding` (cp1252 default on Windows).
- The prerelease sweep blocks on `fsl` and on
  `$FREESURFER_HOME/subjects/fsaverage`. The phantom only reads
  `fsaverage/mri/aseg.mgz` and `aparc+aseg.mgz`.
- The MNE mirror `mne-tools/mne-data` release `fsaverage-1.0`,
  `fsaverage-root.zip` (md5 `5133fe92b7b8f03ae19219d5f46e4177`) contains both
  files, byte-identical (same md5) to FreeSurfer 8.2's. They remain FreeSurfer
  data under the FreeSurfer Software License (the BSD-3 license of the mirror
  repository does not change that). Downloading them at runtime to build a
  local phantom is use, not redistribution. TemplateFlow `tpl-fsaverage` has no
  volumetric segmentation and cannot replace them.
- `LICE-dev/swane` is public with default branch `dev`: GitHub-hosted runners
  are free and unmetered; limits are 6 h per job, 10 GB cache per repository.

## Approach

CI first, then fixes driven by what the CI shows. Phases:

| Phase | Content |
|---|---|
| W1 | Manual Windows/macOS workflow, light job first |
| W2 | Execution-core portability (`pwd` shim, start method, symlink, encoding, CI-driven checks) |
| W3 | Slicer best-effort on Windows |
| W4 | FSL-free prerelease + fsaverage fallback + heavy/prerelease jobs |
| W5 | Experimental notice, docs, local-session handoff |

## W1 — `.github/workflows/windows-tests.yml`

- Trigger: `workflow_dispatch` only. Inputs:
  - `suite`: `light` | `heavy` | `prerelease` | `all` (default `light`);
  - `os`: `windows-latest` | `macos-latest` (default `windows-latest`;
    prerelease is Windows-only);
  - `passes`: comma-separated prerelease pass names, empty = every pass the
    host can run;
  - `rebuild_cache`: boolean, forces phantom/weights cache regeneration.
- `permissions: contents: read`; no secrets; only official actions
  (`actions/checkout`, `actions/setup-python`, `actions/cache`,
  `actions/upload-artifact`).
- Common steps: Python 3.12, `pip install -e .` plus `pytest pytest-qt`;
  print `sys.executable`, dcm2niix/niimath versions; upload `pip freeze`.
  `PYTHONUTF8` is deliberately **not** set, so encoding bugs users would hit
  surface in CI.
- The repository is checked out under a path containing a space (or the test
  temp root is pointed at one) in at least one job, to exercise unquoted
  command lines.
- `light` job: `pytest swane/tests -m "not heavy" --junitxml=...`.
- Artifacts: junit XML, logs. Never the phantom or fsaverage files.
- The workflow file only shows a "Run workflow" button once it exists on `dev`;
  until then it is started with `gh workflow run ... -r claude/windows-support`.

## W2 — Execution-core portability

1. **`pwd` shim.** A module in `swane/patches/` that, only when `os.name == "nt"`
   and `pwd` is not importable, registers a minimal `pwd` stub in
   `sys.modules` before any `nipype.pipeline.plugins` import. It must also be
   active in spawned workers: it is imported from `swane.patches.nipype_patches`
   (which provides `swane_run_node`, imported by workers before running a task)
   and from every SWANe entry point that imports the plugins. Remove the
   `skipif(os.name == "nt", reason="Nipype MultiProc requires POSIX")` marks
   (`tests/workers/test_workflow_process.py`, `tests/prerelease/test_runner.py`)
   and the `object` fallback skip in
   `tests/nipype_pipeline/engine/test_monitored_multiproc_plugin.py`. An
   upstream nipype PR is suggested but out of scope.
2. **Start method.** Keep the existing `spawn` fallback; fix the
   `mp_start_method` docstring ("SWANe does not support Windows") and add the
   `win32` case to its tests. The fork-calibrated RAM estimators stay
   conservative under `spawn` (workers are smaller), no change.
3. **Symlink.** `utils/templates.py`: `os.symlink` with a `shutil.copy2`
   fallback on `OSError`/`NotImplementedError`, same pattern as
   `tests/prerelease/subject.py:_link`. The FreeSurfer-only `recon-all.log`
   link is untouched.
4. **Encoding.** `encoding="utf-8"` on text-mode `open()` calls that read or
   write SWANe-produced text (reports, scripts, license texts, config). Binary
   modes and files written by external tools are excluded.
5. **CI-driven checks**, fixed only if they fail: `pythonw` (`gui_scripts`)
   with `sys.stdout`/`sys.stderr` set to `None`; paths containing spaces in
   nipype `CommandLine` interfaces (fix = quote path `argstr` in the custom
   niimath/dcm2niix interfaces); MAX_PATH (260) and open-file locking
   surfacing in prerelease runs.

## W3 — Slicer best-effort

- `SlicerCheckWorker.find_slicer_python`: Windows branch using `glob` over
  `%LOCALAPPDATA%\slicer.org\Slicer *\bin\PythonSlicer.exe` and
  `%ProgramFiles%\Slicer *\bin\PythonSlicer.exe`, `rel_path` to `Slicer.exe`.
  Linux/macOS keep `find`.
- Slicer check/export/viewer workers: argument lists without `shell=True`
  instead of strings with `shlex.quote`. Same behaviour on Linux/macOS, which
  must be re-verified there.
- `slicer_script_result.py`: keep the `fslstats` fallback threshold; verify the
  `"linux" in sys.platform` segmentation branch on Windows.

## W4 — FSL-free prerelease

1. **FSL not blocking.** `capabilities.BLOCKING` becomes
   `("dcm2niix", "fsaverage", "ram_budget")` (plus `"fsl"` when
   `FSL_MANDATORY` is True). Every pass/axis that needs FSL declares
   `gate="fsl"`, so `coverage()` reports it as *unreachable*, never *missing*.
   Check each pass for implicit FSL use (e.g. MNI152 from `$FSLDIR`; the `mni`
   capability already falls back to `swane.resources`). Update
   `test_plan_integrity.py`.
2. **fsaverage fallback.** New `swane/tests/helpers/phantom/fsaverage_source.py`
   with `resolve_fsaverage_mri_dir()`:
   1. `$FREESURFER_HOME/subjects/fsaverage/mri` when present;
   2. otherwise download `fsaverage-root.zip` from the pinned mne-data URL,
      verify md5 `5133fe92b7b8f03ae19219d5f46e4177`, extract only `aseg.mgz`
      and `aparc+aseg.mgz` into `~/.cache/swane/fsaverage/mri/`, delete the zip;
   3. otherwise raise a clear error.
   `tissue._fsaverage_dir`, `dataset._resolve_freesurfer_home`,
   `capabilities._probe_freesurfer_subject` and the phantom tests'
   `_has_fsaverage()` all go through it. The phantom cache key switches from
   FreeSurfer's `build-stamp.txt` to the md5 of the two `.mgz` files
   (source-independent; existing local phantoms rebuild once). Docstring and
   prerelease README state the files are FreeSurfer data under the FreeSurfer
   Software License, fetched at runtime and never redistributed. Light tests
   with a mocked download: FreeSurfer precedence, md5 mismatch error, only the
   two files extracted.
3. **CI jobs.**
   - `heavy`: `pytest swane/tests --run-heavy -m heavy`; cache antspynet
     weights and TemplateFlow keyed on the antspynet version; real Slicer is not
     installed (its heavy test is skipped with an explicit reason).
   - `prerelease-plan`: `--dry-run`/`--list`, build or restore the phantom
     (cache key `phantom-<generator version>-<fsaverage md5>`), emit the
     runnable pass list as JSON.
   - `prerelease-run`: `strategy.matrix` over that list, `fail-fast: false`,
     `max-parallel: 4`; each job restores caches and runs
     `python -m swane.tests.prerelease --only <pass> --cores 4 --ram 14
     --work-dir D:\swp --timeout <below 6 h>`; uploads report HTML/JSON and
     crash files.
   - `prerelease-summary`: aggregates outcomes and coverage.
   The CI work dir is disposable by construction; the
   `~/test_swane/prerelease` rule of `CLAUDE.md` applies to developer machines.

## W5 — Experimental notice and handoff

- `is_windows()` in `utils/platform_and_tools_utils.py`.
- New string in `strings.py` shown by the setup wizard and the home tab on
  Windows: "Windows support is experimental: FSL and FreeSurfer are not
  available natively; 3D Slicer integration is best-effort."
- README platforms line; wiki note drafted for `../swane.wiki` (committed
  there separately by the maintainer).
- `~/test_swane/windows/HANDOFF.md` for the local Windows session: install
  steps, what CI covered, manual checklist (launch via `pythonw`/`swane`
  entry point, GUI, subject path with spaces, real Slicer, locked files, non-admin
  user without symlink rights).

## Contracts touched

No preference key, enum member, workflow/node name, Traits field, signal,
result filename or Slicer mapping changes. Touched behaviour: prerelease
blocking set and coverage gates, phantom cache key, Slicer subprocess
invocation (argument list instead of shell string).

## Validation

- Linux (local): light suite, matrix, targeted tests per phase, prerelease
  `structural_fsl` + one ANTS pass (unchanged results with FSL), `--dry-run`
  with FSL hidden (FSL axes unreachable).
- macOS: `windows-tests.yml` with `os=macos-latest` (light, heavy).
- Windows: `windows-tests.yml` light → heavy → prerelease, triggered manually.

## Execution notes

Subagents: Opus for W2.1/W2.2 and W4.1; Sonnet for W1, W2.3–W2.5, W3, W4.2,
W4.3, W5.
