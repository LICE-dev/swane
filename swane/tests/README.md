# SWANe test suite

## Layout

Tests are grouped by the package area they exercise, one folder per area:

```
swane/tests/
├── conftest.py            # shared fixtures + marker auto-skip
├── pytest.ini             # marker registration / warning filters
├── helpers/               # test-only utilities (NOT tests)
│   ├── dicom_factory.py   #   header-only phantom DICOM (unit tests, no pixel data)
│   ├── dicom_scenarios.py #   ready-made scenarios + expected metadata
│   └── phantom/           #   full synthetic exam, real pixel data (used by prerelease/)
├── config/                # swane/config  (ConfigManager, preferences, enums)
├── utils/                 # swane/utils   (Subject, DicomTree, managers, ...)
├── workers/               # swane/workers (DICOM search, Slicer, workflow, ...)
├── ui/                    # swane/ui      (head-less widget tests)
├── nipype_pipeline/       # swane/nipype_pipeline
│   ├── engine/            #   engine helpers (report, ram estimator, workflow)
│   ├── nodes/             #   node interfaces (FSL-free logic)
│   └── matrix/            #   settings matrix + golden snapshots (incl. CUDA on/off)
├── prerelease/            # real-execution sweep on the phantom (opt-in, heavy)
└── integration/           # slow end-to-end tests (real FSL/FreeSurfer/Slicer)
```

`swane/nipype_pipeline/` is covered by the light unit tests under
`nipype_pipeline/`: engine helpers and pure-Python (and pure-helper) node logic.
Workflow **construction** — assembling each builder's node graph and asserting
its structure across every relevant setting — is covered by
`nipype_pipeline/matrix/`, which records a deterministic golden *snapshot* of
each resulting graph under `matrix/snapshots/` (including **CUDA on/off**), so
both a reviewer and the regression suite can check what SWANe assembles for each
configuration. None of these run FSL/FreeSurfer/Slicer or read DICOM. Browse the
overview in [`nipype_pipeline/matrix/MATRIX.md`](nipype_pipeline/matrix/MATRIX.md);
see [`nipype_pipeline/matrix/README.md`](nipype_pipeline/matrix/README.md) for
how it works.

`prerelease/` goes the other way: it *executes* the real workflows
(dcm2niix + FSL/FreeSurfer/Slicer) over a synthetic phantom exam generated at
run time (`helpers/phantom/`), across the same setting matrix, and checks the
output is scientifically plausible — registration overlap, FA localisation,
activation, vein position. It is opt-in and heavy; see
[`prerelease/README.md`](prerelease/README.md) and
[`prerelease/TODO.md`](prerelease/TODO.md).

## Naming standard

* One file per module: `test_<module_snake_case>.py`
  (e.g. `swane/utils/Subject.py` → `utils/test_subject.py`).
* Test classes: `Test<Thing>`. Free functions `test_<behaviour>` are fine too.
* No numeric ordering prefixes — tests must be independent and order-free.
* No test imports another test module. Share data through `helpers/` and
  fixtures in `conftest.py`.

## Phantom DICOM

Never commit real DICOM files. Two generators, for two different jobs:

- **Header-only** (`helpers/dicom_factory.py` / `dicom_scenarios.py`): tiny
  files with no pixel data, for testing DICOM *parsing* logic
  (`DicomSearchWorker`, `DicomTree`). Use directly, or the session-scoped
  `phantom_dicom_tree` fixture (`dict[str, Scenario]`, path + expected result).
- **Full exam, real pixel data** (`helpers/phantom/`): a complete synthetic
  subject dcm2niix actually converts and FSL/FreeSurfer actually process, used
  by `prerelease/` to run and validate the real workflows. See
  [`helpers/phantom/README.md`](helpers/phantom/README.md).

## Markers

The "light" suite runs with no external neuroimaging tools. Tests that need
them (or that are slow) are marked and **skipped automatically** when the tool
is missing:

| marker               | skipped unless…                              |
|----------------------|----------------------------------------------|
| `requires_dcm2niix`  | `dcm2niix` on PATH                           |
| `requires_fsl`       | `bet` on PATH or `FSLDIR` set                |
| `requires_freesurfer`| `recon-all` on PATH or `FREESURFER_HOME` set |
| `requires_slicer`    | `Slicer` on PATH or `SWANE_SLICER_PATH` set  |
| `requires_display`   | a real display is available                  |
| `heavy`              | `--run-heavy` is passed                      |

## Running

```bash
# light suite (Windows/CI friendly), Qt head-less
pytest swane/tests -m "not heavy"

# everything, including full-workflow integration tests
pytest swane/tests --run-heavy
```

Install the test dependencies once with:

```bash
pip install -e . pytest pytest-qt pytest-xdist
```
