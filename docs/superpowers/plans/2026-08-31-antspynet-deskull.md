# antspynet Default Deskull Engine — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add antspynet (ANTsPyNet `brain_extraction`) as a third brain-extraction engine and make it the default, mirroring the existing `RegistrationEngine` pattern (enum preference, dependency gate, license consent, home row), with a per-input modality assignment.

**Architecture:** A new lazy-import Nipype node `AntsPyNetBrainExtraction` produces a brain image + mask from an antspynet probability map. `get_deskull_node()` gains a `DeskullEngine` selector (ANTSPYNET default / SYNTHSTRIP / BET) plus a `DeskullModality`; a `resolve_deskull_engine()` helper mirrors `resolve_registration_engine()`. Each MR deskull call site passes its modality; `fMRI_preproc_workflow` is routed through the wrapper with SynthStrip excluded. A single boolean preference `strip` is replaced by a `deskull_engine` enum, with a new antspynet dependency gate, license entry, and home row.

**Tech Stack:** Python, Nipype, antspyx, **antspynet + tensorflow (new deps)**, PySide6, pytest.

**Spec:** [docs/superpowers/specs/2026-08-31-antspynet-deskull-design.md](../specs/2026-08-31-antspynet-deskull-design.md)

## Orchestration model

Tasks are executed by the user in **independent sessions**; this plan's author acts as **orchestrator** and integrates reported results. Each task names a **recommended model**:

- **sonnet5** — mechanical/pattern-following changes.
- **opus4.8** — cross-cutting logic, shared functions, workflow wiring.
- **opus5** — critical/scientific or final-validation steps only.

**Dependency order (what blocks what):**

```
Task 1 (enums) ──┬─> Task 5 (get_deskull_node) ──┬─> Task 10 (wire workflows) ─> Task 11 (fMRI)
                 │                                │
Task 3 (node) ───┘                                └─> Task 13 (matrices+validation)
Task 2 (ORACLE, parallel, local) ─> Task 9 (setup.py pins), Task 12 (constants), refines Task 3 API
Task 4 (DependencyManager) ─> Task 6 (preferences)
Task 1 ─> Task 6 (preferences), Task 7 (license), Task 8 (home)
```

Recommended sequencing across sessions: **1 and 2 first** (2 is long-running/local and unblocks 9/12); then 3, 4; then 5, 6, 7, 8, 9; then 10, 11; then 12; then 13. Tasks 2, 4, 7, 8 can run in parallel with others.

## Global Constraints

- **Branch:** `claude/antspynet-deskull` (off `dev`). Commit per task; **never push**.
- **Language:** all code, comments, docstrings, UI strings in **English**.
- **Terminology:** never "patient" — use "subject"; never imply clinical/medical use (research tool only).
- **Interpreter:** run Python/tests with system Python or a dedicated SWANe env (has antspyx 0.6.3). **Never** FSL's or FreeSurfer's bundled interpreter. Verify with `python -c "import sys; print(sys.executable)"`.
- **Licensing:** never copy external-tool source into the repo. The bundled antspynet license is the license *text* only. Preserve existing "derived from Nipype" disclaimers.
- **antspyx nodes are lazy-import:** `import ants` / `import antspynet` only inside `_run_interface`, so importing the module never loads tensorflow.
- **Oracle isolation:** nothing about the local oracle (scripts, downloaded weights, `/home/mau/test_swane/ant_deskull/` data, outputs) is committed or referenced from tracked code.
- **Stable contracts changing intentionally here:** the `strip` preference key is removed; `deskull_engine` and `accepted_license_antspynet` are added; deskull node names gain an `_antspynet` variant (matrix snapshots regenerate).
- **New node RAM:** fixed `mem_gb=5` for now.
- **Testing:** light suite runs with no external tools; `--run-heavy` and `prerelease` need a real toolchain. Format changed Python with Black; don't reformat unrelated files.

---

### Task 1: `DeskullEngine` and `DeskullModality` enums

**Model:** sonnet5
**Depends on:** none

**Files:**
- Modify: `swane/config/config_enums.py` (add two enums near `RegistrationEngine`, ~line 70-74)
- Test: `swane/tests/config/test_deskull_enums.py` (create)

**Interfaces:**
- Produces:
  - `class DeskullEngine(Enum)` with members `ANTSPYNET = "ANTs (antspynet)"`, `SYNTHSTRIP = "FreeSurfer SynthStrip"`, `BET = "FSL BET"`.
  - `class DeskullModality(Enum)` with members `T1 = "t1"`, `FLAIR = "flair"`, `T2 = "t2"`, `BOLD = "bold"`, `NODIF = "__oracle_nodif__"`, `VENOUS = "__oracle_venous__"`. The `.value` of `T1/FLAIR/T2/BOLD` is the literal antspynet modality key. `NODIF`/`VENOUS` hold sentinel placeholders that **Task 12** replaces with the oracle-chosen antspynet keys.

- [ ] **Step 1: Write the failing test**

```python
# swane/tests/config/test_deskull_enums.py
from swane.config.config_enums import DeskullEngine, DeskullModality


def test_deskull_engine_members_and_labels():
    assert {e.name for e in DeskullEngine} == {"ANTSPYNET", "SYNTHSTRIP", "BET"}
    assert DeskullEngine.ANTSPYNET.value == "ANTs (antspynet)"
    assert DeskullEngine.SYNTHSTRIP.value == "FreeSurfer SynthStrip"
    assert DeskullEngine.BET.value == "FSL BET"


def test_deskull_modality_fixed_keys_are_antspynet_literals():
    assert DeskullModality.T1.value == "t1"
    assert DeskullModality.FLAIR.value == "flair"
    assert DeskullModality.T2.value == "t2"
    assert DeskullModality.BOLD.value == "bold"


def test_oracle_decided_modalities_exist():
    # Placeholder values filled by the oracle (Task 12); the members must exist now.
    assert DeskullModality.NODIF in DeskullModality
    assert DeskullModality.VENOUS in DeskullModality
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest swane/tests/config/test_deskull_enums.py -v`
Expected: FAIL with `ImportError: cannot import name 'DeskullEngine'`.

- [ ] **Step 3: Add the enums**

In `swane/config/config_enums.py`, after the `RegistrationEngine` class:

```python
class DeskullEngine(Enum):
    ANTSPYNET = "ANTs (antspynet)"
    SYNTHSTRIP = "FreeSurfer SynthStrip"
    BET = "FSL BET"


class DeskullModality(Enum):
    T1 = "t1"
    FLAIR = "flair"
    T2 = "t2"
    BOLD = "bold"
    # Oracle-decided antspynet keys; placeholders replaced in Task 12.
    NODIF = "__oracle_nodif__"
    VENOUS = "__oracle_venous__"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest swane/tests/config/test_deskull_enums.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add swane/config/config_enums.py swane/tests/config/test_deskull_enums.py
git commit -m "feat: add DeskullEngine and DeskullModality enums"
```

---

### Task 2: Local oracle — choose nodif/venous modalities and dependency pins (LOCAL, UNCOMMITTED)

**Model:** opus5
**Depends on:** none (runs in parallel). **Unblocks:** Task 9 (pins), Task 12 (constants), and confirms the real antspynet API used by Task 3.

This task produces **reported findings only** — no committed files. Work in a scratch directory outside the repo (e.g. `/home/mau/test_swane/ant_deskull/oracle_run/`).

**Inputs:** `/home/mau/test_swane/ant_deskull/nodif.nii.gz`, `nodif2.nii.gz`, `anatomicavenosa.nii.gz`.

- [ ] **Step 1: Find a working dependency triple**

In a throwaway virtualenv (NOT the SWANe env), install `antspyx==0.6.3` plus candidate `antspynet` and `tensorflow` versions until `import antspynet` and a `brain_extraction` call both succeed on CPU. Record the exact working `antspynet==X` and `tensorflow==Y` versions. **Report these pins** (they feed Task 9).

- [ ] **Step 2: Confirm the real `brain_extraction` API shape**

For a known modality (e.g. `"t1"`), call `antspynet.brain_extraction(ants.image_read(path), modality="t1")` and record: the return type, whether it is a probability image in the input grid, and how to binarize it. **Report** whether `prob.numpy()` + `prob.new_image_like(...)` and `img * mask` behave as Task 3 assumes; note any deviation.

- [ ] **Step 3: nodif modality bake-off**

Run `brain_extraction` on `nodif.nii.gz` and `nodif2.nii.gz` with `modality` in `{"t2", "bold", "fa"}`. Threshold at 0.5, overlay on the b0. Judge which mask best captures the brain without clipping/leaking. **Report the winning key** → becomes `DeskullModality.NODIF`.

- [ ] **Step 4: venous intracranial bake-off**

Run `brain_extraction` on `anatomicavenosa.nii.gz` across the plausible modalities (include `t1`, and any whose mask reaches the inner skull table). The goal is the **whole intracranial (inskull) space**, matching the old SynthStrip (CSF-inclusive) / BET-surfaces behaviour, not just parenchyma. If no modality alone covers it, test a morphological post-step (binary fill-holes + closing / convex hull toward skull) on the best brain mask. **Report:** the winning modality key (→ `DeskullModality.VENOUS`) **and** whether an `intracranial` post-step is required, including the concrete operation that worked (for Task 12).

- [ ] **Step 5: Record pretrained-weight names**

Note which pretrained weights each chosen modality downloads (filenames under antspynet's cache) so Task 13's pre-cache helper can force them. **Report** the modality→download list.

**Deliverable to orchestrator:** a short written report with (a) antspynet+tensorflow pins, (b) API confirmation, (c) NODIF key, (d) VENOUS key + intracranial decision/operation, (e) weight names. Commit nothing.

---

### Task 3: `AntsPyNetBrainExtraction` Nipype node

**Model:** opus4.8
**Depends on:** Task 1 (uses no enum directly, but conceptually paired). Real API is confirmed by Task 2; if Task 2 reports a deviation, adjust Steps 3/6 accordingly before implementing.

**Files:**
- Create: `swane/nipype_pipeline/nodes/AntsPyNetBrainExtraction.py`
- Test: `swane/tests/nipype_pipeline/nodes/test_antspynet_brain_extraction.py` (create)

Model this on [`swane/nipype_pipeline/nodes/AntsN4BiasFieldCorrection.py`](../../../swane/nipype_pipeline/nodes/AntsN4BiasFieldCorrection.py) (lazy import, ITK threads env var, `_gen_outfilename`, disclaimers). The test fakes `antspynet` via `sys.modules` and keeps **real antspyx** for image I/O (antspyx 0.6.3 is installed in the test env).

**Interfaces:**
- Produces node `AntsPyNetBrainExtraction` with inputs `in_file` (File, mandatory), `modality` (Str, mandatory), `out_file` (File), `mask_file` (File), `num_threads` (Int, nohash); outputs `out_file`, `mask_file`.

- [ ] **Step 1: Write the failing test**

```python
# swane/tests/nipype_pipeline/nodes/test_antspynet_brain_extraction.py
import os
import sys
import types

import numpy as np
import pytest

import ants  # real antspyx (installed)
from swane.nipype_pipeline.nodes.AntsPyNetBrainExtraction import AntsPyNetBrainExtraction


@pytest.fixture
def fake_antspynet(monkeypatch):
    """Inject a fake `antspynet` whose brain_extraction returns a real ants
    probability image derived from the input, recording the modality it saw."""
    calls = {}

    def brain_extraction(image, modality=None, **kwargs):
        calls["modality"] = modality
        arr = image.numpy()
        prob = np.zeros_like(arr, dtype="float32")
        prob[arr > arr.mean()] = 0.9  # bright voxels -> "brain"
        return image.new_image_like(prob)

    module = types.ModuleType("antspynet")
    module.brain_extraction = brain_extraction
    monkeypatch.setitem(sys.modules, "antspynet", module)
    return calls


def _write_image(path):
    arr = np.zeros((6, 6, 6), dtype="float32")
    arr[2:4, 2:4, 2:4] = 100.0
    img = ants.from_numpy(arr)
    ants.image_write(img, path)
    return path


def test_produces_brain_and_binary_mask(tmp_path, fake_antspynet):
    in_file = _write_image(str(tmp_path / "in.nii.gz"))
    node = AntsPyNetBrainExtraction()
    node.inputs.in_file = in_file
    node.inputs.modality = "t1"
    node.inputs.out_file = str(tmp_path / "brain.nii.gz")
    node.inputs.mask_file = str(tmp_path / "mask.nii.gz")
    node.run()

    assert fake_antspynet["modality"] == "t1"
    mask = ants.image_read(str(tmp_path / "mask.nii.gz")).numpy()
    assert set(np.unique(mask)).issubset({0.0, 1.0})
    assert mask.sum() > 0
    brain = ants.image_read(str(tmp_path / "brain.nii.gz")).numpy()
    # Brain image is input masked: zero wherever mask is zero.
    assert np.all(brain[mask == 0] == 0)


def test_num_threads_sets_itk_env(tmp_path, fake_antspynet):
    seen = {}

    real_be = sys.modules["antspynet"].brain_extraction

    def spy(image, modality=None, **kwargs):
        seen["itk"] = os.environ.get("ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS")
        return real_be(image, modality=modality, **kwargs)

    sys.modules["antspynet"].brain_extraction = spy
    in_file = _write_image(str(tmp_path / "in.nii.gz"))
    node = AntsPyNetBrainExtraction()
    node.inputs.in_file = in_file
    node.inputs.modality = "t2"
    node.inputs.num_threads = 3
    node.inputs.out_file = str(tmp_path / "brain.nii.gz")
    node.run()
    assert seen["itk"] == "3"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest swane/tests/nipype_pipeline/nodes/test_antspynet_brain_extraction.py -v`
Expected: FAIL with `ModuleNotFoundError`/`ImportError` for `AntsPyNetBrainExtraction`.

- [ ] **Step 3: Implement the node**

```python
# swane/nipype_pipeline/nodes/AntsPyNetBrainExtraction.py
# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-
import os
from os.path import abspath

from nipype.interfaces.base import (
    traits,
    BaseInterface,
    BaseInterfaceInputSpec,
    TraitedSpec,
    File,
    isdefined,
)

# antspyx and antspynet are imported lazily inside _run_interface, as in
# AntsN4BiasFieldCorrection, so importing this module never loads tensorflow.

ITK_THREADS_VAR = "ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS"


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
class AntsPyNetBrainExtractionInputSpec(BaseInterfaceInputSpec):
    in_file = File(exists=True, mandatory=True, desc="the input image")
    modality = traits.Str(
        mandatory=True,
        desc="antspynet brain_extraction modality key (e.g. t1, flair, t2, bold)",
    )
    out_file = File(desc="the skull-stripped brain image")
    mask_file = File(desc="the binary brain mask")
    num_threads = traits.Int(nohash=True, desc="number of ITK threads")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class AntsPyNetBrainExtractionOutputSpec(TraitedSpec):
    out_file = File(desc="the skull-stripped brain image")
    mask_file = File(desc="the binary brain mask")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class AntsPyNetBrainExtraction(BaseInterface):
    """
    Skull-strip an image with antspynet deep-learning brain extraction.

    antspynet.brain_extraction returns a probability image in the input grid;
    this node binarizes it at 0.5, writes the mask, and writes the input masked
    by it as the brain image.
    """

    input_spec = AntsPyNetBrainExtractionInputSpec
    output_spec = AntsPyNetBrainExtractionOutputSpec

    def _run_interface(self, runtime):
        import ants
        import antspynet

        out_file = self._gen_outfilename()
        img = ants.image_read(self.inputs.in_file, pixeltype="float")

        previous_threads = os.environ.get(ITK_THREADS_VAR)
        if isdefined(self.inputs.num_threads):
            os.environ[ITK_THREADS_VAR] = str(self.inputs.num_threads)
        try:
            prob = antspynet.brain_extraction(img, modality=self.inputs.modality)
        finally:
            if previous_threads is None:
                os.environ.pop(ITK_THREADS_VAR, None)
            else:
                os.environ[ITK_THREADS_VAR] = previous_threads

        mask = prob.new_image_like((prob.numpy() >= 0.5).astype("float32"))

        if isdefined(self.inputs.mask_file):
            ants.image_write(mask, abspath(self.inputs.mask_file))

        ants.image_write(img * mask, out_file)
        return runtime

    def _gen_outfilename(self):
        out_file = self.inputs.out_file
        if not isdefined(out_file) and isdefined(self.inputs.in_file):
            out_file = "brain_" + os.path.basename(self.inputs.in_file)
        return abspath(out_file)

    def _list_outputs(self):
        outputs = self.output_spec().get()
        outputs["out_file"] = self._gen_outfilename()
        if isdefined(self.inputs.mask_file):
            outputs["mask_file"] = abspath(self.inputs.mask_file)
        return outputs
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest swane/tests/nipype_pipeline/nodes/test_antspynet_brain_extraction.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git add swane/nipype_pipeline/nodes/AntsPyNetBrainExtraction.py \
        swane/tests/nipype_pipeline/nodes/test_antspynet_brain_extraction.py
git commit -m "feat: add AntsPyNetBrainExtraction node"
```

---

### Task 4: `DependencyManager.is_antspynet` / `check_antspynet` + strings

**Model:** sonnet5
**Depends on:** none. **Unblocks:** Task 6 (preference `option_dependency` references `is_antspynet`).

**Files:**
- Modify: `swane/utils/DependencyManager.py` (constant near line 84-88; `__init__` near 95-100; new methods near the antspyx ones ~166-361)
- Modify: `swane/strings.py` (add `check_dep_antspynet_*` mirroring `check_dep_antspyx_*`)
- Test: `swane/tests/utils/test_dependency_manager.py` (add cases; see existing antspyx cases)

**Interfaces:**
- Consumes: `LicenseReference.ANTSPYNET` is **not** required here (version string is used directly). `version_with_license(ANTSPYX, ...)` pattern is mirrored but Task 7 adds `ANTSPYNET`; to avoid a cross-task dependency, `check_antspynet` formats its label with a plain version string and does **not** call `version_with_license` (the consent flow's label uses `detected_tool_versions`).
- Produces: `DependencyManager.is_antspynet() -> bool`, `DependencyManager.check_antspynet() -> Dependence`, `self.antspynet` set in `__init__`, `MIN_ANTSPYNET_VERSION` constant.

- [ ] **Step 1: Write the failing test**

```python
# add to swane/tests/utils/test_dependency_manager.py
import importlib

from swane.utils.DependencyManager import DependencyManager, DependenceStatus


def test_is_antspynet_true_when_present(monkeypatch):
    monkeypatch.setattr(
        "swane.utils.DependencyManager.importlib.util.find_spec",
        lambda name: object() if name == "antspynet" else None,
    )
    monkeypatch.setattr(
        "swane.utils.DependencyManager.importlib.metadata.version",
        lambda name: DependencyManager.MIN_ANTSPYNET_VERSION,
    )
    assert DependencyManager.is_antspynet() is True
    assert DependencyManager.check_antspynet().state == DependenceStatus.DETECTED


def test_is_antspynet_false_when_absent(monkeypatch):
    monkeypatch.setattr(
        "swane.utils.DependencyManager.importlib.util.find_spec",
        lambda name: None,
    )
    assert DependencyManager.is_antspynet() is False
    assert DependencyManager.check_antspynet().state == DependenceStatus.MISSING
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest swane/tests/utils/test_dependency_manager.py -k antspynet -v`
Expected: FAIL (`AttributeError`/`ImportError` — `importlib` not imported or method missing).

- [ ] **Step 3: Implement**

In `swane/utils/DependencyManager.py`, ensure `import importlib.util` and `import importlib.metadata` at the top. Add the constant beside `MIN_ANTSPYX_VERSION`:

```python
    # Kept in sync with the antspynet pin in setup.py.
    MIN_ANTSPYNET_VERSION = "<pin from Task 9>"
```

(Use the Task 2 / Task 9 pin; until then a conservative floor is acceptable and updated in Task 9.)

In `__init__`, after `self.antspyx = ...`:

```python
        self.antspynet = DependencyManager.check_antspynet()
```

Add the methods next to the antspyx ones:

```python
    @staticmethod
    def is_antspynet() -> bool:
        """
        Returns
        -------
        True if the antspynet package is importable (even if outdated).
        """
        return DependencyManager.check_antspynet().state != DependenceStatus.MISSING

    @staticmethod
    def check_antspynet() -> Dependence:
        """
        Returns
        -------
        A Dependence object with antspynet information. Presence is detected
        without importing antspynet (which would load tensorflow) via
        importlib.util.find_spec; the version is read from package metadata.
        """
        if importlib.util.find_spec("antspynet") is None:
            return Dependence(
                DependenceStatus.MISSING, strings.check_dep_antspynet_error
            )
        try:
            antspynet_version = importlib.metadata.version("antspynet")
        except Exception:
            return Dependence(
                DependenceStatus.WARNING, strings.check_dep_antspynet_no_version
            )
        found_version = version.parse(antspynet_version)
        if found_version < version.parse(DependencyManager.MIN_ANTSPYNET_VERSION):
            return Dependence(
                DependenceStatus.WARNING,
                strings.check_dep_antspynet_wrong_version
                % (antspynet_version, DependencyManager.MIN_ANTSPYNET_VERSION),
            )
        return Dependence(
            DependenceStatus.DETECTED,
            strings.check_dep_antspynet_found % antspynet_version,
        )
```

In `swane/strings.py`, add (mirroring the antspyx strings, matching their exact `%` arity):

```python
check_dep_antspynet_error = "antspynet not found: brain extraction with antspynet is disabled"
check_dep_antspynet_no_version = "antspynet found but its version could not be determined"
check_dep_antspynet_wrong_version = "antspynet %s found but %s or newer is recommended"
check_dep_antspynet_found = "antspynet %s found"
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest swane/tests/utils/test_dependency_manager.py -k antspynet -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add swane/utils/DependencyManager.py swane/strings.py swane/tests/utils/test_dependency_manager.py
git commit -m "feat: add antspynet dependency detection"
```

---

### Task 5: `resolve_deskull_engine` + `get_deskull_node` refactor

**Model:** opus4.8
**Depends on:** Task 1 (enums), Task 3 (node).

**Files:**
- Modify: `swane/nipype_pipeline/nodes/utils.py` (imports ~15-21; `get_deskull_node` 138-188; add `resolve_deskull_engine` near `resolve_registration_engine` ~41-57)
- Modify callers (signature only in this task, real modality wiring in Task 10/11): `ref_workflow.py`, `linear_reg_workflow.py`, `dti_preproc_workflow.py`, `venous_mr_workflow.py`
- Test: `swane/tests/nipype_pipeline/nodes/test_deskull_abstraction.py` (create; model on `test_registration_abstraction.py`)

**Interfaces:**
- Consumes: `DeskullEngine`, `DeskullModality` (Task 1); `AntsPyNetBrainExtraction` (Task 3).
- Produces:
  - `resolve_deskull_engine(synth_config, allow_synthstrip=True) -> DeskullEngine` — reads `synth_config.getenum_safe("deskull_engine")`; if `allow_synthstrip=False` and result is `SYNTHSTRIP`, returns `ANTSPYNET`.
  - `get_deskull_node(name, deskull_engine, mask=False, bet_thr=None, bet_bias_correction=False, bet_robust=False, bet_threshold=False, bet_surfaces=False, synth_exclude_csf=False, deskull_modality=None, out_file=None, name_prefix="", max_cpu=0, multicore_node_limit=CoreLimit.SOFT_CAP, limit_synth_cores=False) -> Node` — the `use_synth: bool` parameter is **removed** and replaced by `deskull_engine: DeskullEngine`; `deskull_modality: DeskullModality = None` is added. ANTSPYNET branch node name is `name + "_antspynet"`.

- [ ] **Step 1: Write the failing test**

```python
# swane/tests/nipype_pipeline/nodes/test_deskull_abstraction.py
import pytest

from swane.config.config_enums import DeskullEngine, DeskullModality
from swane.nipype_pipeline.nodes.utils import (
    get_deskull_node,
    resolve_deskull_engine,
)
from swane.nipype_pipeline.nodes.AntsPyNetBrainExtraction import AntsPyNetBrainExtraction
from swane.nipype_pipeline.nodes.SynthStrip import SynthStrip
from nipype.interfaces.fsl import BET


class _Cfg(dict):
    def getenum_safe(self, key):
        return self[key]


def test_resolve_prefers_configured_engine():
    cfg = _Cfg(deskull_engine=DeskullEngine.BET)
    assert resolve_deskull_engine(cfg) == DeskullEngine.BET


def test_resolve_folds_synthstrip_when_excluded():
    cfg = _Cfg(deskull_engine=DeskullEngine.SYNTHSTRIP)
    assert resolve_deskull_engine(cfg, allow_synthstrip=False) == DeskullEngine.ANTSPYNET
    # honoured when allowed
    assert resolve_deskull_engine(cfg, allow_synthstrip=True) == DeskullEngine.SYNTHSTRIP


def test_resolve_leaves_antspynet_and_bet_under_exclusion():
    for eng in (DeskullEngine.ANTSPYNET, DeskullEngine.BET):
        cfg = _Cfg(deskull_engine=eng)
        assert resolve_deskull_engine(cfg, allow_synthstrip=False) == eng


def test_get_deskull_node_dispatches_by_engine():
    a = get_deskull_node(name="x", deskull_engine=DeskullEngine.ANTSPYNET,
                         deskull_modality=DeskullModality.T1, mask=True)
    assert isinstance(a.interface, AntsPyNetBrainExtraction)
    assert a.name == "x_antspynet"
    assert a.inputs.modality == "t1"

    s = get_deskull_node(name="x", deskull_engine=DeskullEngine.SYNTHSTRIP, mask=True)
    assert isinstance(s.interface, SynthStrip)
    assert s.name == "x_synthstrip"

    b = get_deskull_node(name="x", deskull_engine=DeskullEngine.BET,
                        bet_thr=0.3, mask=True)
    assert isinstance(b.interface, BET)
    assert b.name == "x_bet"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest swane/tests/nipype_pipeline/nodes/test_deskull_abstraction.py -v`
Expected: FAIL (`ImportError: resolve_deskull_engine`).

- [ ] **Step 3: Implement `resolve_deskull_engine` and refactor `get_deskull_node`**

In `utils.py` add to the imports: `from swane.config.config_enums import CoreLimit, RegistrationEngine, DeskullEngine, DeskullModality` and `from swane.nipype_pipeline.nodes.AntsPyNetBrainExtraction import AntsPyNetBrainExtraction`.

Add near `resolve_registration_engine`:

```python
def resolve_deskull_engine(
    synth_config, allow_synthstrip: bool = True
) -> DeskullEngine:
    """
    Resolve the configured brain-extraction engine.

    ``allow_synthstrip=False`` keeps a workflow that must avoid FreeSurfer Synth
    tools (fMRI_preproc, mirroring its SynthMorph exclusion) off SYNTHSTRIP: when
    the configured engine is SYNTHSTRIP it falls back to the default ANTSPYNET.
    ANTSPYNET and BET are honoured either way.
    """
    engine = synth_config.getenum_safe("deskull_engine")
    if not allow_synthstrip and engine == DeskullEngine.SYNTHSTRIP:
        return DeskullEngine.ANTSPYNET
    return engine
```

Replace the `get_deskull_node` signature `use_synth: bool` with `deskull_engine: DeskullEngine` and add `deskull_modality: DeskullModality = None`. Replace the `if use_synth: ... else: <BET>` body with a three-way dispatch:

```python
    if deskull_engine == DeskullEngine.ANTSPYNET:
        deskull_node = Node(
            AntsPyNetBrainExtraction(), name=name + "_antspynet", mem_gb=5
        )
        if deskull_modality is not None:
            deskull_node.inputs.modality = deskull_modality.value
        if mask:
            mask_name = "brain_mask.nii.gz"
            if out_file:
                mask_name = fname_presuffix(out_file, suffix="_brain", use_ext=True)
            deskull_node.inputs.mask_file = mask_name
        threads, hard = get_tool_cpu_config(
            max_cpu, multicore_node_limit, limit_synth_cores
        )
        # antspynet/ITK take threads only through num_threads (a real, nipype-aware
        # reservation), like the ANTs registration node -- no soft env-var path.
        apply_tool_num_threads(deskull_node, threads, hard)
        if bet_surfaces:
            deskull_node.inskull_out_name = "mask_file"
    elif deskull_engine == DeskullEngine.SYNTHSTRIP:
        deskull_node = Node(SynthStrip(), name=name + "_synthstrip", mem_gb=5)
        if mask:
            mask_name = "brain_mask.nii.gz"
            if out_file:
                mask_name = fname_presuffix(out_file, suffix="_brain", use_ext=True)
            deskull_node.inputs.mask_file = mask_name
        deskull_node.inputs.exclude_csf = synth_exclude_csf
        threads, hard = get_tool_cpu_config(
            max_cpu, multicore_node_limit, limit_synth_cores
        )
        apply_tool_num_threads(
            deskull_node, threads, hard, soft_env_vars=("OMP_NUM_THREADS",)
        )
        if bet_surfaces:
            deskull_node.inskull_out_name = "mask_file"
    else:  # DeskullEngine.BET
        deskull_node = Node(BET(), name=name + "_bet")
        deskull_node.inputs.mask = mask
        deskull_node.inputs.threshold = bet_threshold
        if bet_thr is not None:
            deskull_node.inputs.frac = bet_thr
        if bet_bias_correction:
            deskull_node.inputs.reduce_bias = True
        elif bet_surfaces:
            deskull_node.inputs.surfaces = True
            deskull_node.inskull_out_name = "inskull_mask_file"
        elif bet_robust:
            deskull_node.inputs.robust = True

    deskull_node.long_name = name_prefix + " %s"
    if out_file:
        deskull_node.inputs.out_file = out_file

    return deskull_node
```

Then update the four current callers to pass `deskull_engine=resolve_deskull_engine(synth_config)` instead of `use_synth=synth_config.getboolean_safe("strip")` (modality wiring lands in Task 10; for now pass `deskull_modality=DeskullModality.T1` at each so graphs still build — Task 10 corrects per-site values). Add the needed imports (`resolve_deskull_engine`, `DeskullModality`) to each caller.

- [ ] **Step 4: Run tests**

Run: `python -m pytest swane/tests/nipype_pipeline/nodes/test_deskull_abstraction.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add swane/nipype_pipeline/nodes/utils.py \
        swane/nipype_pipeline/workflows/ref_workflow.py \
        swane/nipype_pipeline/workflows/linear_reg_workflow.py \
        swane/nipype_pipeline/workflows/dti_preproc_workflow.py \
        swane/nipype_pipeline/workflows/venous_mr_workflow.py \
        swane/tests/nipype_pipeline/nodes/test_deskull_abstraction.py
git commit -m "feat: add resolve_deskull_engine and DeskullEngine dispatch in get_deskull_node"
```

---

### Task 6: Preferences — drop `strip`, add `deskull_engine` + `accepted_license_antspynet`

**Model:** opus4.8
**Depends on:** Task 1 (enums), Task 4 (`is_antspynet`).

**Files:**
- Modify: `swane/config/preference_list.py` (SYNTH category ~626-704; license loop ~522-528)
- Test: `swane/tests/config/test_deskull_engine_pref.py` (create; model on `test_registration_engine_pref.py`)

**Interfaces:**
- Consumes: `DeskullEngine` (Task 1), `is_antspynet` name (Task 4), `ResourceManager.synth_strip_ram_requirements()`.
- Produces: preference key `deskull_engine` (SYNTH category, default `DeskullEngine.ANTSPYNET`); hidden `accepted_license_antspynet`; the `strip` key no longer exists.

- [ ] **Step 1: Write the failing test**

```python
# swane/tests/config/test_deskull_engine_pref.py
from swane.config.config_enums import DeskullEngine, GlobalPrefCategoryList
from swane.config.preference_list import GLOBAL_PREFERENCES


def test_deskull_engine_default_is_antspynet():
    entry = GLOBAL_PREFERENCES[GlobalPrefCategoryList.SYNTH]["deskull_engine"]
    assert entry.default == DeskullEngine.ANTSPYNET
    assert entry.value_enum is DeskullEngine


def test_strip_pref_removed():
    assert "strip" not in GLOBAL_PREFERENCES[GlobalPrefCategoryList.SYNTH]


def test_antspynet_license_key_exists():
    cat = GLOBAL_PREFERENCES[GlobalPrefCategoryList.MAIN]  # same category as other accepted_license_*
    assert "accepted_license_antspynet" in cat
```

(If `test_antspynet_license_key_exists` names the wrong category, fix it to the category holding `accepted_license_antspyx` — read line ~522 of `preference_list.py` for the active `category` variable.)

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest swane/tests/config/test_deskull_engine_pref.py -v`
Expected: FAIL (`KeyError: 'deskull_engine'`).

- [ ] **Step 3: Implement**

Add `"antspynet"` to the license loop tuple:

```python
for _license_tool in ("fsl", "freesurfer", "slicer", "dcm2niix", "antspyx", "antspynet"):
```

In the SYNTH category, **delete** the `GLOBAL_PREFERENCES[category]["strip"] = PreferenceEntry(...)` block and add:

```python
GLOBAL_PREFERENCES[category]["deskull_engine"] = PreferenceEntry(
    input_type=InputTypes.ENUM,
    label="Brain extraction engine",
    value_enum=DeskullEngine,
    default=DeskullEngine.ANTSPYNET,
    option_dependency={
        DeskullEngine.ANTSPYNET: [
            "is_antspynet",
            "antspynet brain extraction requires the antspynet package",
        ],
        DeskullEngine.SYNTHSTRIP: [
            "is_freesurfer_synth",
            "SynthStrip requires FreeSurfer 8.1.0",
        ],
    },
    option_pref_requirement={
        DeskullEngine.ANTSPYNET: {
            GlobalPrefCategoryList.PERFORMANCE: [("ram_gb", 5.0)]
        },
        DeskullEngine.SYNTHSTRIP: {
            GlobalPrefCategoryList.PERFORMANCE: [
                ("ram_gb", ResourceManager.synth_strip_ram_requirements())
            ]
        },
    },
    option_pref_requirement_fail_tooltip={
        DeskullEngine.ANTSPYNET: "antspynet brain extraction requires at least 5.0 GB RAM",
        DeskullEngine.SYNTHSTRIP: "SynthStrip requires at least %.1f GB RAM"
        % ResourceManager.synth_strip_ram_requirements(),
    },
    section=True,
)
```

Import `DeskullEngine` at the top of `preference_list.py` alongside `RegistrationEngine`. Verify no other module reads the `strip` key (grep `getboolean_safe("strip")` — Task 5 already removed the workflow callers; the light suite will catch stragglers).

- [ ] **Step 4: Run tests**

Run: `python -m pytest swane/tests/config/test_deskull_engine_pref.py swane/tests/config/test_preferences.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add swane/config/preference_list.py swane/tests/config/test_deskull_engine_pref.py
git commit -m "feat: replace strip boolean with deskull_engine preference"
```

---

### Task 7: LicenseReference `ANTSPYNET` + bundled license + consent wiring

**Model:** sonnet5
**Depends on:** Task 1 not required. Independent; pairs with Task 4/6.

**Files:**
- Modify: `swane/utils/LicenseReference.py` (ids ~11-17; `_LICENSES` dict near the ANTSPYX entry ~169)
- Create: `swane/licenses/antspynet_license.txt`
- Test: `swane/tests/utils/test_license_reference.py` (add a case; see the antspyx case)

**Interfaces:**
- Produces: `LicenseReference.ANTSPYNET = "antspynet"` in `TOOL_IDS`, a `LicenseInfo` entry keyed by it, and a bundled Apache-2.0 license file.

- [ ] **Step 1: Write the failing test**

```python
# add to swane/tests/utils/test_license_reference.py
from swane.utils import LicenseReference
from swane.utils.LicenseReference import ANTSPYNET, TOOL_IDS, bundled_license_path
import os


def test_antspynet_in_tool_ids_and_has_bundled_license():
    assert ANTSPYNET == "antspynet"
    assert ANTSPYNET in TOOL_IDS
    info = LicenseReference._LICENSES[ANTSPYNET]
    assert os.path.exists(bundled_license_path(info))
```

(If the licenses registry is exposed under a different name than `_LICENSES`, read `LicenseReference.py` and adjust the accessor.)

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest swane/tests/utils/test_license_reference.py -k antspynet -v`
Expected: FAIL (`ImportError: ANTSPYNET`).

- [ ] **Step 3: Implement**

Obtain the exact antspynet LICENSE text (Apache-2.0). Prefer the file shipped with the installed distribution (`importlib.metadata.files("antspynet")` → the `LICENSE`), else fetch it from the ANTsX/ANTsPyNet repository `LICENSE`. Save it verbatim to `swane/licenses/antspynet_license.txt`. Do not paraphrase.

In `LicenseReference.py`:

```python
ANTSPYNET = "antspynet"
TOOL_IDS = (FSL, FREESURFER, SLICER, DCM2NIIX, ANTSPYX, ANTSPYNET)
```

Add to the licenses registry, mirroring the ANTSPYX entry, an `ANTSPYNET: LicenseInfo(...)` with `display_name="ANTsPyNet"`, the official ANTsX/ANTsPyNet repo URL, `online_is_official=True`, `bundled_filename="antspynet_license.txt"`, an empty installed-path candidates lambda (`lambda context: []`), and a comment noting the downloaded pretrained model weights carry their own upstream terms.

- [ ] **Step 4: Run tests**

Run: `python -m pytest swane/tests/utils/test_license_reference.py swane/tests/utils/test_license_packaging.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add swane/utils/LicenseReference.py swane/licenses/antspynet_license.txt \
        swane/tests/utils/test_license_reference.py
git commit -m "feat: add antspynet license reference and bundled license"
```

---

### Task 8: Home-window antspynet row

**Model:** sonnet5
**Depends on:** Task 4 (`self.dependency_manager.antspynet`).

**Files:**
- Modify: `swane/ui/MainWindow.py` (~line 929, after the antspyx `add_home_entry`)
- Test: covered by the existing UI smoke tests; add a targeted assertion only if a home-tab test exists (`swane/tests/ui/`), otherwise verify manually.

- [ ] **Step 1: Implement the row**

After `x = self.add_home_entry(self.dependency_manager.antspyx, x)`:

```python
        x = self.add_home_entry(self.dependency_manager.antspynet, x)
```

- [ ] **Step 2: Verify import + construction**

Run: `python -c "import swane.ui.MainWindow"` (compile check) and, if a home-tab pytest-qt test exists, `python -m pytest swane/tests/ui/ -k home -v`.
Expected: no import error; test passes if present.

- [ ] **Step 3: Commit**

```bash
git add swane/ui/MainWindow.py
git commit -m "feat: show antspynet dependency row in home window"
```

---

### Task 9: `setup.py` — add antspynet + tensorflow pins

**Model:** opus4.8
**Depends on:** Task 2 (working pins). **Blocks:** real end-to-end runs, Task 13.

**Files:**
- Modify: `setup.py` (`install_requires` ~32-53)
- Modify: `swane/utils/DependencyManager.py` (`MIN_ANTSPYNET_VERSION` to match the pin)

- [ ] **Step 1: Add the pins reported by Task 2**

In `install_requires`, after `"antspyx==0.6.3",`:

```python
        "antspynet==<X>",
        "tensorflow==<Y>",
```

Set `MIN_ANTSPYNET_VERSION = "<X>"` in `DependencyManager.py`.

- [ ] **Step 2: Verify the environment resolves and imports**

In the SWANe env (or a clean env), `pip install -e .` and run `python -c "import antspynet, tensorflow; print('ok')"`.
Expected: import succeeds on both linux and macOS (confirm cross-platform per the working agreement; report if a platform needs a different tensorflow distribution, e.g. `tensorflow-macos`).

- [ ] **Step 3: Commit**

```bash
git add setup.py swane/utils/DependencyManager.py
git commit -m "build: add antspynet and tensorflow dependencies"
```

---

### Task 10: Wire per-site modality into the four deskull workflows + MainWorkflow

**Model:** opus4.8
**Depends on:** Task 5 (get_deskull_node signature), Task 1 (DeskullModality).

**Files:**
- Modify: `swane/nipype_pipeline/workflows/ref_workflow.py`, `linear_reg_workflow.py`, `dti_preproc_workflow.py`, `venous_mr_workflow.py` (add `deskull_modality` factory param; pass to `get_deskull_node`)
- Modify: `swane/nipype_pipeline/MainWorkflow.py` (pass modality at each call: FLAIR calls → `FLAIR`, `t2_cor` → `T2`, `mdc` → `T1`, `venous_mr` → `VENOUS`, `dti_preproc` → `NODIF`; `t1` ref → `T1`)
- Test: `swane/tests/nipype_pipeline/` graph-construction test asserting the antspynet deskull node gets the right modality per workflow (model on existing workflow construction tests; use `DeskullEngine.ANTSPYNET` config).

**Interfaces:**
- Consumes: `get_deskull_node(..., deskull_engine=, deskull_modality=)`.
- Produces: each of the four factory functions gains `deskull_modality: DeskullModality = DeskullModality.T1` and forwards it; MainWorkflow sets the correct value per site (see the table in the spec §4).

- [ ] **Step 1: Write the failing test**

```python
# swane/tests/nipype_pipeline/test_deskull_modality_wiring.py
from swane.config.config_enums import DeskullModality
from swane.nipype_pipeline.workflows.linear_reg_workflow import linear_reg_workflow
# ... build a linear_reg_workflow with a synth_config selecting ANTSPYNET and
# assert the "<name>_antspynet" node's inputs.modality == "flair" when
# deskull_modality=DeskullModality.FLAIR is passed. Mirror an existing workflow
# construction test's fixtures for config/synth_config.
```

(Fill the fixtures from an existing workflow-construction test in `swane/tests/nipype_pipeline/`; assert `wf.get_node("<name>_antspynet").inputs.modality` equals the expected key for at least `linear_reg_workflow` FLAIR and `dti_preproc_workflow` NODIF.)

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest swane/tests/nipype_pipeline/test_deskull_modality_wiring.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

Add `deskull_modality: DeskullModality = DeskullModality.T1` to each factory signature; in each `get_deskull_node(...)` call pass `deskull_modality=deskull_modality` (ref/dti/venous) and, in `linear_reg_workflow`, `deskull_modality=deskull_modality`. Replace the temporary `DeskullModality.T1` from Task 5 with the parameter. In `MainWorkflow.py`, at each call site pass the modality from the spec table (e.g. `deskull_modality=DeskullModality.FLAIR` for `flair`/`flair2d`, `DeskullModality.T2` for `t2_cor`, `DeskullModality.T1` for `mdc`, `DeskullModality.VENOUS` for `venous_mr`, `DeskullModality.NODIF` for `dti_preproc`). Import `DeskullModality` where needed.

- [ ] **Step 4: Run tests**

Run: `python -m pytest swane/tests/nipype_pipeline/test_deskull_modality_wiring.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add swane/nipype_pipeline/workflows/ref_workflow.py \
        swane/nipype_pipeline/workflows/linear_reg_workflow.py \
        swane/nipype_pipeline/workflows/dti_preproc_workflow.py \
        swane/nipype_pipeline/workflows/venous_mr_workflow.py \
        swane/nipype_pipeline/MainWorkflow.py \
        swane/tests/nipype_pipeline/test_deskull_modality_wiring.py
git commit -m "feat: assign antspynet deskull modality per workflow"
```

---

### Task 11: Route `fMRI_preproc_workflow` through the deskull wrapper (exclude SynthStrip)

**Model:** opus4.8
**Depends on:** Task 5, Task 1.

**Files:**
- Modify: `swane/nipype_pipeline/workflows/fMRI_preproc_workflow.py` (imports; `meanfuncmask` node ~217-221)
- Test: `swane/tests/nipype_pipeline/` — assert that with `deskull_engine=SYNTHSTRIP` configured, the fMRI mean-func deskull node is **not** a SynthStrip (folds to antspynet), and with default it is `_antspynet` with modality `bold`.

**Interfaces:**
- Consumes: `get_deskull_node`, `resolve_deskull_engine(..., allow_synthstrip=False)`, `DeskullModality.BOLD`.

- [ ] **Step 1: Write the failing test**

```python
# swane/tests/nipype_pipeline/test_fmri_preproc_deskull.py
# Build fMRI_preproc_workflow with a synth_config selecting SYNTHSTRIP and assert
# the mean-func mask node is the antspynet node (name endswith "_antspynet",
# modality == "bold"), proving SynthStrip is excluded. Reuse an existing
# fMRI_preproc construction test's fixtures.
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest swane/tests/nipype_pipeline/test_fmri_preproc_deskull.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

Replace the direct BET node:

```python
    # NODE 10: Strip the skull from the mean functional to generate a mask
    meanfuncmask = get_deskull_node(
        name="%s_meanfuncmask" % name,
        deskull_engine=resolve_deskull_engine(synth_config, allow_synthstrip=False),
        deskull_modality=DeskullModality.BOLD,
        mask=True,
        bet_thr=0.3,
        max_cpu=max_cpu,
        multicore_node_limit=multicore_node_limit,
        limit_synth_cores=synth_config.getboolean_safe("limit_cores"),
    )
    workflow.connect(meanfunc, "out_file", meanfuncmask, "in_file")
```

Add imports: `from swane.nipype_pipeline.nodes.utils import get_deskull_node, resolve_deskull_engine` and `DeskullModality`. Keep the downstream `workflow.connect(meanfuncmask, "mask_file", maskfunc, "in_file2")` unchanged (all three engines expose `mask_file`). Remove the now-unused `BET` import if nothing else uses it in the file.

- [ ] **Step 4: Run tests**

Run: `python -m pytest swane/tests/nipype_pipeline/test_fmri_preproc_deskull.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add swane/nipype_pipeline/workflows/fMRI_preproc_workflow.py \
        swane/tests/nipype_pipeline/test_fmri_preproc_deskull.py
git commit -m "refactor: route fMRI_preproc brain extraction through deskull wrapper"
```

---

### Task 12: Finalize oracle-derived constants (NODIF/VENOUS + optional intracranial)

**Model:** sonnet5
**Depends on:** Task 2 (reported results), Task 1, Task 3, Task 10.

**Files:**
- Modify: `swane/config/config_enums.py` (`DeskullModality.NODIF`, `.VENOUS` values)
- Modify (only if oracle requires it): `swane/nipype_pipeline/nodes/AntsPyNetBrainExtraction.py` (add `intracranial` trait + fill), `swane/nipype_pipeline/nodes/utils.py` (pass `intracranial=True` for `bet_surfaces` antspynet branch), `venous_mr_workflow.py` (no change if handled in utils)
- Test: update `test_deskull_enums.py` to assert the real keys; add a node test for the intracranial fill if that path is added.

> **Orchestrator note:** the exact `NODIF`/`VENOUS` keys and the intracranial operation are supplied by the orchestrator from Task 2's report before this task runs; they are not placeholders at execution time.

- [ ] **Step 1: Set the resolved modality keys**

Replace the sentinel values with the oracle-chosen antspynet keys, e.g.:

```python
    NODIF = "<oracle key, e.g. bold>"
    VENOUS = "<oracle key, e.g. t1>"
```

Update `test_deskull_enums.py::test_oracle_decided_modalities_exist` to assert the concrete values.

- [ ] **Step 2 (conditional): add the intracranial post-step**

Only if Task 2 reports that no single modality covers the intracranial space: add an `intracranial = traits.Bool(False, usedefault=True)` input to `AntsPyNetBrainExtraction`, apply the exact morphological operation Task 2 validated after binarization, and in `get_deskull_node`'s ANTSPYNET branch set `deskull_node.inputs.intracranial = True` when `bet_surfaces` is True. Add a node test with a fake probability image asserting the filled mask is a superset of the plain mask.

- [ ] **Step 3: Run tests**

Run: `python -m pytest swane/tests/config/test_deskull_enums.py swane/tests/nipype_pipeline/nodes/test_antspynet_brain_extraction.py -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "feat: set oracle-decided nodif/venous deskull modalities"
```

---

### Task 13: Pre-cache helper, regenerate matrices, full validation

**Model:** opus5
**Depends on:** all prior tasks; needs antspynet + tensorflow installed (Task 9) and weights available.

**Files:**
- Create: `swane/tests/prerelease/` hook or a small utility for `preload_antspynet_models(modalities)`
- Modify: `swane/tests/nipype_pipeline/matrix/snapshots/*` (regenerate)

- [ ] **Step 1: Pre-cache helper**

Add `preload_antspynet_models(modalities)` that, for each modality, runs `antspynet.brain_extraction` once on a tiny synthetic image (forcing the weight download), so the prerelease sweep never downloads mid-workflow. Call it from the prerelease setup before running workflows. Verify it is a no-op when weights already exist.

- [ ] **Step 2: Regenerate matrix snapshots**

The default deskull node names changed to `_antspynet`. Regenerate the golden snapshots per `swane/tests/nipype_pipeline/matrix/README.md`, then **review the diff** to confirm only the deskull node identity/inputs changed as intended (no unintended graph changes).

Run: `python -m pytest swane/tests/nipype_pipeline/matrix/ -v` (after regeneration)
Expected: PASS.

- [ ] **Step 3: Light suite + targeted deskull suite**

Run:
```bash
python -m pytest swane/tests/config swane/tests/utils swane/tests/nipype_pipeline/nodes -v
```
Expected: PASS. Report any environment-specific skips.

- [ ] **Step 4: Prerelease sweep (real toolchain)**

Confirm the disposable root `~/test_swane/prerelease`, then run `python -m swane.tests.prerelease` with `deskull_engine=ANTSPYNET`. Verify the antspynet deskull runs, RAM gating holds, and the pipeline completes. Report results (this is regression evidence only, not clinical validation).

- [ ] **Step 5: Commit**

```bash
git add swane/tests/nipype_pipeline/matrix/snapshots swane/tests/prerelease
git commit -m "test: pre-cache antspynet models and regenerate deskull matrices"
```

---

## Self-review

**Spec coverage:** §1 node → Task 3; §2 enums → Task 1; §3 get_deskull_node/resolve → Task 5; §4 modality wiring → Task 10; §5 fMRI → Task 11; §6 preferences → Task 6; §7 dependency/license/home/setup → Tasks 4, 7, 8, 9; §8 pre-cache → Task 13; §9 oracle → Task 2 (+constants Task 12); §10 tests/matrices/prerelease → across tasks + Task 13. All covered.

**Placeholder scan:** the only deferred values are the oracle-decided `NODIF`/`VENOUS` keys, the antspynet/tensorflow pins, and the conditional intracranial operation — each is explicitly produced by Task 2 and consumed by a named later task (9/12), not left vague. `MIN_ANTSPYNET_VERSION` is set in Task 4 and finalized in Task 9.

**Type consistency:** `DeskullEngine`/`DeskullModality` names and `.value` semantics are consistent across Tasks 1, 5, 6, 10, 11, 12; `resolve_deskull_engine(synth_config, allow_synthstrip=)` and `get_deskull_node(..., deskull_engine=, deskull_modality=)` signatures match between definition (Task 5) and callers (Tasks 10, 11); `is_antspynet`/`check_antspynet`/`self.antspynet` consistent between Tasks 4, 6, 8; `LicenseReference.ANTSPYNET`/`TOOL_IDS` consistent in Task 7.
