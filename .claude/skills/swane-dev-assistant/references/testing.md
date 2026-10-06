# SWANe testing

Read this reference to decide which suite to run and how to add or update tests for a change.

## Suites

- **Light suite**: `swane/tests/{config,utils,workers,ui,nipype_pipeline}` (includes `nipype_pipeline/matrix/`), run with `-m "not heavy"`. Headless (Qt forced offscreen by `swane/tests/conftest.py`). Needs no external tool for the vast majority of tests: `swane/tests/conftest.py` marks tests `requires_dcm2niix` / `requires_fsl` / `requires_freesurfer` / `requires_slicer` / `requires_display`, and auto-skips each one whose tool/display isn't detected — this is separate from, and in addition to, the `-m "not heavy"` marker filter.
- **Heavy tests**: marked `@pytest.mark.heavy`, opt-in via `--run-heavy` (skipped by default even without `-m`), interleaved in the same directories, run against a real toolchain where nothing can be mocked (e.g. `workers/test_slicer_check_worker.py::TestSlicerCheckWorkerReal` against a real installed Slicer).
- **Matrix (construction-only golden snapshots)**: `swane/tests/nipype_pipeline/matrix/` — see dedicated section below.
- **Prerelease (real execution sweep)**: `swane/tests/prerelease/` — see dedicated section below.

## Commands

```bash
python3 -m compileall swane
python3 -m pytest <targeted-test-file-or-node>
python3 -m black --check <changed-python-files>
python3 -m pytest swane/tests -m "not heavy" --color=yes --verbose
```

**Pytest configuration.** `pytest.ini` and a root `conftest.py` live at the repository root (not in `swane/tests/`). The root conftest runs before pytest imports the `swane` package: it installs the Windows `pwd` stub and nipype's FSL-version fallback, which must exist before `swane` (and therefore `nipype.interfaces.fsl`) is imported. `swane/tests/conftest.py` keeps the fixtures, markers handling and `--run-heavy`.

**Interpreter / environment.** Use an interpreter that has SWANe's runtime dependencies (nipype, PySide6, etc.) — a dedicated virtualenv/conda env — and never a neuroimaging tool's bundled Python (FSL's fslpython / FreeSurfer's fspython); see the interpreter rule in `CLAUDE.md` and verify with `python -c "import sys; print(sys.executable)"` before a general test run. If the environment carries a broken `datalad` pytest plugin (`ModuleNotFoundError: fasteners` at collection), add `-p no:datalad` to the pytest commands.

## Matrix — construction-only golden snapshots (delicate)

`swane/tests/nipype_pipeline/matrix/` builds every workflow factory across a settings matrix (66 scenarios / 14 workflow families) and records each resulting graph as a deterministic, human-reviewed text snapshot in `snapshots/<workflow>/<scenario>.txt`. It never executes FSL/FreeSurfer/Slicer/dcm2niix and reads no real DICOM — it only asserts what graph SWANe *assembles* for a given preference combination. A handful of scenarios do read real FSL data files (MNI templates, XTRACT protocols) at construction time and **skip** (not fail) when that data is absent, via `conftest.require_fsl_data`.

- **Regression check** (run this for any change that could alter graph shape — node names, connections, boundary fields, conditional wiring):
  ```bash
  pytest swane/tests/nipype_pipeline/matrix
  ```
- **After an intentional graph change**, regenerate the golden files, then **read them by hand** — this manual review is not optional, the snapshot is only as trustworthy as its first review:
  ```bash
  SWANE_SNAPSHOT_UPDATE=1 pytest swane/tests/nipype_pipeline/matrix
  ```
  Confirm the diff in `snapshots/<workflow>/<scenario>.txt` shows only nodes, commands, flags, and wiring you actually intended to change.
- **Refresh the generated reports** and commit test + snapshot + report together:
  ```bash
  python3 swane/tests/nipype_pipeline/matrix/generate_report.py
  ```
  This rewrites `MATRIX.md` (committed, GitHub-rendered) and `matrix_report.html` (git-ignored, local). Never hand-edit either.
- Snapshots are OS-agnostic by construction: the renderer sorts nodes/traits/connections and rewrites volatile absolute paths (`tmp_path`, home, `swane.resources`, `$FSLDIR`, `site-packages`, cwd) to stable tokens. A snapshot diff that only changes a path or an OS-specific separator signals a renderer regression, not a real graph change — investigate before regenerating.
- Adding a workflow/scenario: add it to the module's `SCENARIOS` dict (or a new `test_<workflow>_matrix.py`), generate its golden file, read it by hand, regenerate the reports, commit all three together.

## Prerelease — real execution sweep (delicate)

`swane/tests/prerelease/` (`python3 -m swane.tests.prerelease`) runs the **real** workflows (dcm2niix, FSL, FreeSurfer, Slicer) over a synthetic phantom exam generated on the machine that runs it — no DICOM is committed or required. It is the only suite that proves scientific/numeric correctness rather than just graph construction, via layered checks: execution (no failed node/crash), integrity (finite, non-constant, on the reference grid), and plausibility (registration overlap, FA/tractography localization, vein localization — quantitative, graded against the phantom's known ground truth, not eyeballed).

- Always resolve and verify the working root before running: default `~/test_swane/prerelease`, disposable — **never point it at a clinical working directory.**
- Blocking requirements (nothing runs without them): dcm2niix, the fsaverage segmentations used to build the phantom, and the RAM budget. FSL is blocking only when `swane.config.dependency_policy.FSL_MANDATORY` is True; otherwise a host without FSL reports every FSL-only axis value as **unreachable** and runs the FSL-free passes, including the stand-in twins declared with `PassSpec.stands_in_for` (they run only where their FSL original is skipped, so FSL hosts run the same passes as before). Everything else (CUDA, Synth tools, Slicer, XTRACT data) degrades gracefully — a missing capability drops only the axes that need it, with the reason recorded in the report.
- fsaverage comes from `$FREESURFER_HOME/subjects/fsaverage` when FreeSurfer is installed; otherwise `swane/tests/helpers/phantom/fsaverage_source.py` downloads the md5-pinned MNE mirror (`mne-tools/mne-data`, release `fsaverage-1.0`) and keeps only `aseg.mgz` and `aparc+aseg.mgz` in `~/.cache/swane/fsaverage/mri`. They are FreeSurfer data under the FreeSurfer Software License: fetched at runtime, never committed, packaged or uploaded. The phantom cache key depends on their content, not on where they came from.
- Commands:
  ```bash
  python3 -m swane.tests.prerelease --dry-run                 # what would run / what this host cannot do
  python3 -m swane.tests.prerelease --cores 8 --ram 10         # the default sweep
  python3 -m swane.tests.prerelease --cores 8 --ram 10 --with-reconall   # + slow FreeSurfer passes (hours each)
  python3 -m swane.tests.prerelease --only <pass_name> --cores 8 --ram 10  # a single pass, see --list
  python3 -m swane.tests.prerelease --list-json --cores 8 --ram 10   # runnable passes as JSON (CI matrices); fails if a blocking capability is missing
  python3 -m swane.tests.prerelease --checks-only              # re-check results already on disk
  python3 -m swane.tests.prerelease --view <pass_name>         # open finished pass in Slicer
  ```
  Pick `--ram` to what the machine actually has — Synth tools have hard floors (SynthStrip 5 GB, SynthMorph/SynthSeg 14 GB, Synth recon-all 20 GB on Linux); passes needing more are skipped, not OOM-killed.
- A full sweep takes hours; progress is saved after every pass, so re-running the same command resumes. `--retry-failed` re-runs failed passes; `--no-resume` starts over.
- Coverage is enforced, not just attempted: `plan.py`'s `coverage()` walks every settings axis and reports **unreachable** (host cannot run it — expected), **deferred** (a pass covers it but was skipped this run — expected for opt-in passes), or **missing** (no pass anywhere covers it — this is a plan bug and fails the sweep). Never treat a coverage hole as acceptable without checking which of the three it is.
- Exit status is 0 only when every pass ran, every error-level check passed, and there are no coverage holes. Inspect `~/test_swane/prerelease/prerelease_report.html` for anything suspicious before treating a green sweep as sufficient scientific evidence.

## How to update tests for a change

- Start from the closest existing test file for the module you changed; extend it rather than creating a parallel one.
- When a contract changes (preference key, enum name, workflow/node name, output filename, signal payload), grep for every producer and consumer, including tests, before editing — a test that still passes after a silent rename is a false negative, not a green light.
- Prefer disposable `tmp_path` / isolated `global_base_folder` fixtures over touching `~/.SWANe` or a real subject folder.
- Add the smallest test that would have failed before your fix/feature; do not add unrelated coverage in the same change.
- For workflow/graph changes, regenerate and hand-review the matrix snapshot (see above) — do not accept a snapshot diff you have not read.
- For scientific/numeric changes, prefer a `prerelease/` pass when the change is execution-level; for smaller synthetic-fixture comparisons, state explicitly what remains scientifically unvalidated.
- Never report a test as "passed" if its prerequisite tool/display was absent and it was skipped — report the skip and the missing prerequisite instead.

## Before calling a change complete

1. Run the targeted test(s) for the changed module.
2. Run the light suite when the change could affect other modules through a shared contract.
3. For graph-shape changes, run the matrix suite and hand-review any regenerated snapshot.
4. For execution/scientific changes, run the relevant `prerelease/` pass(es) when the required tools are available.
5. Review the test diff/output yourself — "no errors" is not sufficient without checking the test actually exercises the changed behavior.
6. Note any check that could not run and why (missing tool, no display, no dataset).
7. Confirm the change has been exercised on both Linux and macOS where the change can plausibly behave differently (subprocess paths, filesystem case-sensitivity, Qt/Slicer integration); state explicitly if only one platform was available. Windows support is experimental: when a change can behave differently there (paths, quoting, subprocesses, multiprocessing), run the manual workflow below on Windows too.

## Windows and macOS CI (manual workflow)

`.github/workflows/windows-tests.yml` runs only on demand (`workflow_dispatch`, from the Actions page or `gh workflow run windows-tests.yml -r <branch> -f suite=<suite> -f os=<os>`); runs use the workflow and code of the selected branch.

- `suite`: `light`, `heavy`, `prerelease` or `all`; `os`: `windows-latest` or `macos-latest` for light/heavy (prerelease always runs on Windows, so do not combine `all` with macOS).
- Prerelease runs one matrix job per runnable pass (from `--list-json`), `--timeout 5` hours each under the 6 h job limit, and a `prerelease-summary` job that merges the per-pass reports (`swane/tests/prerelease/ci_summary.py`). Phantom, fsaverage, model weights and the HCP842 atlas live only in the repository's Actions cache; artifacts carry reports and logs only.
- Leave `rebuild_cache` off unless a cache is corrupt: it creates a new cache entry per run.
- Windows-only behaviour lives behind `swane.patches.windows_compat` / `swane.utils.platform_and_tools_utils.is_windows()` and must leave Linux/macOS command lines and snapshots byte-identical. In Linux tests simulate Windows by patching those helpers; never reassign `os.name` globally.
