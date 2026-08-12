# SWANe test suite

## Layout

Tests are grouped by the package area they exercise, one folder per area:

```
swane/tests/
├── conftest.py            # shared fixtures + marker auto-skip
├── pytest.ini             # marker registration / warning filters
├── helpers/               # test-only utilities (NOT tests)
│   ├── dicom_factory.py   #   synthesise phantom DICOM files
│   └── dicom_scenarios.py #   ready-made scenarios + expected metadata
├── config/                # swane/config  (ConfigManager, preferences, enums)
├── utils/                 # swane/utils   (Subject, DicomTree, managers, ...)
├── workers/               # swane/workers (DICOM search, Slicer, workflow, ...)
├── ui/                    # swane/ui      (head-less widget tests)
└── integration/           # slow end-to-end tests (real FSL/FreeSurfer/Slicer)
```

`swane/nipype_pipeline/` is intentionally **not** covered here yet.

## Naming standard

* One file per module: `test_<module_snake_case>.py`
  (e.g. `swane/utils/Subject.py` → `utils/test_subject.py`).
* Test classes: `Test<Thing>`. Free functions `test_<behaviour>` are fine too.
* No numeric ordering prefixes — tests must be independent and order-free.
* No test imports another test module. Share data through `helpers/` and
  fixtures in `conftest.py`.

## Phantom DICOM

Never commit real DICOM files. Generate them at runtime:

```python
from swane.tests.helpers.dicom_factory import write_series
from swane.tests.helpers.dicom_scenarios import build_dicom_tree
```

or, more conveniently, use the session-scoped `phantom_dicom_tree` fixture,
which returns a `dict[str, Scenario]` (path + expected scan result).

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
