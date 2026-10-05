# Experimental Windows support — handoff for a new session

> Temporary working document. Delete `docs/windows-support/` before merging
> `claude/windows-support` into `dev`.

## 1. Your mission

Make the manual GitHub Actions workflow `.github/workflows/windows-tests.yml`
green, then report **once**, when everything below holds:

- `suite=light` green on **windows-latest** and **macos-latest**;
- `suite=heavy` green on **windows-latest** and **macos-latest**;
- `suite=prerelease` green on Windows: every pass runnable without FSL passes,
  no coverage hole reported as *missing*, `prerelease-summary` green;
- skips allowed only with a legitimate reason (tool not available on that OS:
  FSL, FreeSurfer, Slicer, GPU) — list them in the final report;
- the Linux light suite stays green (today: only the 2 known failures below).

Iterate on your own: trigger runs, read logs, fix, commit, push, re-run. Do not
report intermediate progress. **Stop and ask the maintainer only for**:
changes to stable contracts (preference keys, enum members, workflow/node
names, Traits fields, signals, result filenames, Slicer mappings); any change
to what a prerelease pass *executes* on an FSL host (it is the project's
scientific regression evidence); merges into `dev`, pull requests, force
pushes or other destructive/outward actions; missing permissions.

Final report: links of the green runs; list of fixes; every decision you took
on your own with what it costs if wrong; skipped tests and why; what still
needs a real Windows machine (section 8).

Keep a running log in `docs/windows-support/PROGRESS.md` on the branch (one
line per CI run and per fix, plus every decision as `Ruling: <what> — <why> —
<cost if wrong>`), so a later session can resume from it.

## 2. First steps

1. Read `CLAUDE.md` (project rules: English only, never "patient", research
   tool not medical device, no real data, licensing) and
   `.claude/skills/swane-dev-assistant/` (architecture, testing).
2. Read this file, then `spec.md` and `plan.md` in this folder (the original
   design and plan; their absolute paths and `$PY` refer to the maintainer's
   machine — use your own environment).
3. Check you can drive CI:
   `gh workflow run windows-tests.yml -r claude/windows-support -f suite=light -f os=windows-latest`,
   then `gh run list --workflow windows-tests.yml`, `gh run view <id> --log-failed`.
   Reading job logs needs repository admin rights. If you cannot trigger runs
   or read logs, stop and tell the maintainer.

## 3. Branch and CI facts

- Branch `claude/windows-support`, based on `dev` at `7bb1297`.
- The workflow file is also on `dev` (only to show the "Run workflow" button);
  runs dispatched on this branch use this branch's workflow and code.
- Inputs: `suite` (light|heavy|prerelease|all), `os` (windows-latest|macos-latest;
  prerelease always runs on Windows), `passes` (comma list), `rebuild_cache`
  (leave false; it creates a new cache per run).
- Do not use `suite=all` with macOS (prerelease would run twice on Windows).
- Limits: 6 h per job; prerelease passes run with `--timeout 5` (hours), one
  matrix job per pass, `max-parallel: 4`; 10 GB cache per repository.
- pytest prints FAILED/ERROR/SKIPPED in the short summary (`-rfEs`).
- Actions `checkout@v4`, `setup-python@v5`, `upload-artifact@v4`, `cache@v4`
  run with a Node 20 deprecation warning; newer majors exist (checkout v7,
  cache v6, download-artifact v8…) but were not adopted to avoid untested
  breaking changes. Optional cleanup once green.
- pytest config moved to the repo root (`pytest.ini`, `conftest.py`): the root
  conftest installs the `pwd` stub and the nipype FSL-version fallback before
  `swane` is imported.

## 4. CI history so far (light suite, windows-latest)

| Run | Code | Result | Causes found → fixed in |
|---|---|---|---|
| 1 | 9f7bf2f | 119 failed, 12 errors (summary hidden by `-rs`) | `-rfEs` (d2377c3) |
| 2 | d2377c3 | 119 failed, 12 errors | nipype RAM probe unsupported on Windows; `select()` on pipes; `/tmp` in tests; `fork` test; snapshot quotes → wave D |
| 3 | c9052c0 | 21 failed, 12 errors | conftest import order (FILMGLS spec); eddy snapshot depends on GPU/`eddy_cuda`; quoting tests not platform-aware; space in CI basetemp vs SWANe's no-space rule; filelock file; SimpleITK missing → wave E |
| — | HEAD | not yet run | also adds the Windows dcm2niix stdout parser (d503734) |

macOS, heavy and prerelease have **never run yet**.

## 5. What the branch does (by area)

- **Process model**: `swane/patches/windows_compat.py` installs a `pwd` stub
  (nipype's plugin package imports `pwd` via `sge.py`); `nipype_patches.py`
  replaces nipype's MultiProc `process_initializer` with a SWANe-owned one so
  `spawn` workers import SWANe (and the stub) first; Windows uses `spawn`.
- **Command lines on Windows** (`nipype_patches.py`, Windows-only): nipype's
  `shlex` in `interfaces.base.core` is rebound to an MSVCRT-compatible
  quote/split proxy (cmd.exe ignores single quotes); niimath/dcm2niix/Slicer
  executables quoted; `run_command` "stream" output avoids `select()` on pipes;
  total RAM via `psutil` (nipype's probe supports only linux/darwin).
  `CustomDcm2niix._parse_stdout` accepts `.\name` on Windows.
  Linux/macOS command lines are byte-identical (matrix snapshots unchanged).
- **Filesystem**: template cache copies when symlinks are refused; UTF-8 for
  SWANe's config and error log.
- **Slicer**: discovery on Windows via `%LOCALAPPDATA%\slicer.org\…` /
  Program Files; Slicer invoked with argv lists (no shell); workers never hang
  on a bad Slicer path.
- **Prerelease** (`swane/tests/prerelease/`): FSL is no longer blocking
  (blocking again if `FSL_MANDATORY`); FSL-only axis values gated on `fsl` and
  reported *unreachable* without FSL; FSL-free stand-in passes
  (`structural_alt_settings_fsl_free`, `dti_classic_fsl_free`, via
  `PassSpec.stands_in_for`); `dti_classic` and `dti_synthmorph` pin
  `FSL_XTRACT`; duplicate-pass and unread-value tests; `--list-json` for CI;
  `ci_summary.py` merges per-pass reports.
- **fsaverage**: `swane/tests/helpers/phantom/fsaverage_source.py` uses
  `$FREESURFER_HOME/subjects/fsaverage` or downloads the MNE mirror
  (`mne-tools/mne-data` release `fsaverage-1.0`, md5
  `5133fe92b7b8f03ae19219d5f46e4177`, verified byte-identical to FreeSurfer
  8.2) extracting only `aseg.mgz` and `aparc+aseg.mgz`. FreeSurfer data under
  the FreeSurfer Software License: fetched at runtime, never committed,
  packaged or uploaded as an artifact.
- **UI**: `is_windows()`; experimental notice on the wizard welcome page and
  home tab; README line.

## 6. Decisions already taken (do not reopen without the maintainer)

- Windows support is **experimental**: FSL-free pipelines; FSL/FreeSurfer not
  available natively; Slicer best-effort; no installer, no GPU on Windows.
- **Blank spaces in subject paths/names/working directory stay forbidden on
  every platform** (a Windows-only exception was implemented and then reverted
  on purpose, commit 59e4d91).
- CI is **manual only** (`workflow_dispatch`); no push/PR triggers.
- Twin FSL-free prerelease passes run only where their FSL original is skipped;
  no `cuda` twin (the `cuda` preference is read only by the FSL diffusion
  chain; without FSL `cuda` is *unreachable*).
- `dti_classic` and `dti_synthmorph` now run the FSL diffusion chain on FSL
  hosts (real `eddy_correct` / SynthMorph-bridge coverage) — maintainer-approved
  change of the prerelease evidence.
- Pre-existing failures on `dev`, also failing on the maintainer's Linux box:
  `test_child_bootstrap_does_not_shadow_the_stdlib`,
  `test_check_dipy_detects_installed_package` (may be local-environment only —
  check on CI before touching them).

## 7. Known open items (fix only if CI shows them or they block the goal)

- Prerelease on Windows never ran: phantom build (fsaverage download needs
  `github.com` + `release-assets.githubusercontent.com`), antspynet weights,
  TensorFlow CPU on Windows, MAX_PATH (260) in deep nipype dirs, file locks on
  delete/rename, `DipyMotionCorrection`'s own spawn pool.
- `ci_summary.py`: a completed pass with no report entry is shown "ok"
  (fail-open); an unreadable report is skipped silently.
- `cmd.exe` expands `%VAR%` even inside quotes (unavoidable; paths with `%`).
- Windows Slicer folders sorted as strings (5.10 < 5.8); `Slicer.exe --version`
  stdout on Windows unverified.
- nipype crash-report fallback calls `os.getuid` if `getpass.getuser()` fails
  (only with a stripped environment).
- On Windows, "stream" command output appears when the command ends, not live.
- `.claude/skills/swane-dev-assistant/references/testing.md` still lists FSL as
  a blocking prerelease requirement and does not mention the root
  `pytest.ini`/`conftest.py` or the Windows/macOS workflow — update it.

## 8. Needs a real Windows machine (not CI)

Launch via the `swane` entry point (`pythonw`, no console) and `python -m swane`;
wizard and home-tab notice; full FSL-free workflow on a subject; delete a
subject while its log is open; non-admin user without Developer Mode (symlinks
refused); real 3D Slicer (dependency check, export, viewer,
`slicer_script_result.py` segmentation branch); report exact tracebacks.

## 9. Conventions for your commits

- Small focused commits, conventional messages, ending with the attribution
  line your environment requires.
- Black only on files you change; some files use CRLF line endings — keep them.
- Every Windows-only behaviour must be gated so Linux/macOS stay byte-identical;
  run `pytest swane/tests/nipype_pipeline/matrix` (no snapshot change allowed
  unless intended and hand-reviewed).
- Simulate Windows in Linux tests via `swane.patches.windows_compat.is_windows`
  / `swane.utils.platform_and_tools_utils.is_windows`; never reassign `os.name`
  globally (it breaks the stdlib).
