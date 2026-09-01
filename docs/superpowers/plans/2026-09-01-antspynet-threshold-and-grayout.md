# antspynet Brain-Extraction Threshold + Engine-Aware Grey-Out — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax. This is a small bounded feature intended for a SINGLE session; do Task A → B → C in order.

**Goal:** Let the user set a probability threshold for antspynet brain extraction (mirroring the existing BET `bet_thr` frac preference), and grey out the BET options when the antspynet engine is selected — and the antspynet option when BET/SynthStrip is selected.

**Architecture:** Add a `threshold` input to the `AntsPyNetBrainExtraction` node (default 0.5, replacing the hardcoded binarization threshold); add a per-workflow `antspynet_thr` preference next to each existing `bet_thr`; wire it through `get_deskull_node` and the three workflows that read `bet_thr` from config. The grey-out reuses the existing `pref_requirement` cross-preference mechanism: BET options require `deskull_engine == BET`, the antspynet threshold requires `deskull_engine == ANTSPYNET`, evaluated against the global config when the workflow-preferences window opens.

**Tech Stack:** Python, Nipype, antspyx/antspynet, PySide6, pytest.

**Branch:** `claude/antspynet-deskull` (the antspynet deskull feature branch — this extends it; do NOT branch off dev).

**Base feature:** built on the committed antspynet deskull work (`DeskullEngine`, `AntsPyNetBrainExtraction`, `get_deskull_node` dispatch, `deskull_engine` preference in `GlobalPrefCategoryList.SYNTH`).

## Global Constraints

- Commit per task; **never push**.
- English only; "subject" not "patient"; no clinical/medical framing.
- Interpreter: `/media/Dati/venv/bin/python` (SWANe venv, has antspyx 0.6.3; the shell's default `python` is FSL's — avoid it). Verify with `python -c "import sys; print(sys.executable)"`.
- antspynet node stays lazy-import (no `import antspynet`/tensorflow at module import).
- Format changed Python with Black (`/media/Dati/venv/bin/python -m black`); do not reformat unrelated files.
- Do NOT change `deskull_engine`, the enum members, or existing result/graph contracts.

## Facts from the live code (do not re-derive incorrectly)

- `bet_thr` PreferenceEntry: `input_type=InputTypes.FLOAT`, `default=0.3`, `range=[0, 1]`, defined in `WF_PREFERENCES` for `DataInputList.T13D` (~line 89), `FLAIR3D` (~167), `MDC` (~180), `VENOUS_MR` (~190). Each is a **separate** object.
- `bet_bias_correction` (BOOLEAN) is defined once for `T13D` (~line 83); `FLAIR3D` and `MDC` **reuse the same object** (`WF_PREFERENCES[cat]["bet_bias_correction"] = WF_PREFERENCES[DataInputList.T13D]["bet_bias_correction"]`). `VENOUS_MR` has no `bet_bias_correction`.
- Workflows reading `bet_thr` from config: `ref_workflow` (`config.getfloat_safe("bet_thr")`), `linear_reg_workflow` (`None if not config else config.getfloat_safe("bet_thr")` — `config` is `None` for the flair2d/t2_cor calls), `venous_mr_workflow` (`config.getfloat_safe("bet_thr")`). `dti_preproc_workflow` and `fMRI_preproc_workflow` pass a hardcoded `bet_thr=0.3` and expose no `bet_thr` preference — so they are **out of scope**; their antspynet threshold stays at the node default 0.5.
- `get_deskull_node(...)` signature (in `swane/nipype_pipeline/nodes/utils.py`) currently: `name, deskull_engine, mask=False, bet_thr=None, bet_bias_correction=False, bet_robust=False, bet_threshold=False, bet_surfaces=False, synth_exclude_csf=False, deskull_modality=None, out_file=None, name_prefix="", max_cpu=0, multicore_node_limit=CoreLimit.SOFT_CAP, limit_synth_cores=False`.
- The node currently binarizes with a hardcoded `prob.numpy() >= 0.5` inside `_run_interface`.
- `requirement_changed` in `PreferencesWindow.py` resolves a cross-window ENUM requirement by `self.global_config.getenum_safe(req_cat, req_key[0])` and comparing `selected_enum.name` against the required enum(s). `GlobalPrefCategoryList.SYNTH` + `deskull_engine` are valid there.

---

### Task A: node `threshold` input + `get_deskull_node` `antspynet_thr`

**Model:** opus4.8

**Files:**
- Modify: `swane/nipype_pipeline/nodes/AntsPyNetBrainExtraction.py`
- Modify: `swane/nipype_pipeline/nodes/utils.py` (`get_deskull_node`)
- Test: `swane/tests/nipype_pipeline/nodes/test_antspynet_brain_extraction.py`, `swane/tests/nipype_pipeline/nodes/test_deskull_abstraction.py`

- [ ] **Step 1: Failing tests**

Add to `test_antspynet_brain_extraction.py`:

```python
def test_threshold_default_is_half(tmp_path, fake_antspynet):
    # fake returns prob 0.6 in a block; default 0.5 keeps it as brain
    in_file = _write_image(str(tmp_path / "in.nii.gz"))
    node = AntsPyNetBrainExtraction()
    node.inputs.in_file = in_file
    node.inputs.modality = "t1"
    node.inputs.mask_file = str(tmp_path / "mask.nii.gz")
    node.inputs.out_file = str(tmp_path / "brain.nii.gz")
    node.run()
    assert ants.image_read(str(tmp_path / "mask.nii.gz")).numpy().sum() > 0


def test_threshold_is_applied(tmp_path):
    def be(image, modality=None, **k):
        arr = np.full(image.shape, 0.6, dtype="float32")
        return image.new_image_like(arr)

    module = types.ModuleType("antspynet")
    module.brain_extraction = be
    sys.modules["antspynet"] = module
    in_file = _write_image(str(tmp_path / "in.nii.gz"))
    node = AntsPyNetBrainExtraction()
    node.inputs.in_file = in_file
    node.inputs.modality = "t1"
    node.inputs.threshold = 0.7        # 0.6 < 0.7 -> nothing is brain
    node.inputs.mask_file = str(tmp_path / "mask.nii.gz")
    node.inputs.out_file = str(tmp_path / "brain.nii.gz")
    node.run()
    assert ants.image_read(str(tmp_path / "mask.nii.gz")).numpy().sum() == 0
```

Add to `test_deskull_abstraction.py`:

```python
def test_get_deskull_node_forwards_antspynet_threshold():
    n = get_deskull_node(name="x", deskull_engine=DeskullEngine.ANTSPYNET,
                         deskull_modality=DeskullModality.T1, mask=True,
                         antspynet_thr=0.6)
    assert n.inputs.threshold == 0.6


def test_get_deskull_node_antspynet_threshold_defaults_unset():
    n = get_deskull_node(name="x", deskull_engine=DeskullEngine.ANTSPYNET,
                         deskull_modality=DeskullModality.T1, mask=True)
    # left unset -> node uses its own 0.5 default
    from nipype.interfaces.base import isdefined
    assert not isdefined(n.inputs.threshold) or n.inputs.threshold == 0.5
```

- [ ] **Step 2: Run to verify failure**

Run: `/media/Dati/venv/bin/python -m pytest swane/tests/nipype_pipeline/nodes/test_antspynet_brain_extraction.py swane/tests/nipype_pipeline/nodes/test_deskull_abstraction.py -v`
Expected: the new tests FAIL (`threshold` trait / kwarg missing).

- [ ] **Step 3: Implement**

In `AntsPyNetBrainExtraction.py`, add to the input spec (after `modality`):

```python
    threshold = traits.Float(
        0.5,
        usedefault=True,
        desc="probability threshold for binarizing the brain mask (0-1)",
    )
```

In `_run_interface`, replace `prob.numpy() >= 0.5` with `prob.numpy() >= self.inputs.threshold`.

In `utils.py`, add `antspynet_thr: float = None` to the `get_deskull_node` signature (next to `bet_thr`), and in the `DeskullEngine.ANTSPYNET` branch, after setting `modality`:

```python
        if antspynet_thr is not None:
            deskull_node.inputs.threshold = antspynet_thr
```

- [ ] **Step 4: Run tests**

Run: `/media/Dati/venv/bin/python -m pytest swane/tests/nipype_pipeline/nodes/test_antspynet_brain_extraction.py swane/tests/nipype_pipeline/nodes/test_deskull_abstraction.py -v`
Expected: PASS.

- [ ] **Step 5: Black + commit**

```bash
/media/Dati/venv/bin/python -m black swane/nipype_pipeline/nodes/AntsPyNetBrainExtraction.py swane/nipype_pipeline/nodes/utils.py
git add swane/nipype_pipeline/nodes/AntsPyNetBrainExtraction.py swane/nipype_pipeline/nodes/utils.py \
        swane/tests/nipype_pipeline/nodes/test_antspynet_brain_extraction.py \
        swane/tests/nipype_pipeline/nodes/test_deskull_abstraction.py
git commit -m "feat: antspynet brain-extraction threshold input"
```

---

### Task B: `antspynet_thr` preference + engine-aware grey-out

**Model:** opus4.8

**Files:**
- Modify: `swane/config/preference_list.py`
- Test: `swane/tests/config/` (new `test_deskull_threshold_pref.py`)

**Design:** add a per-workflow `antspynet_thr` FLOAT preference (default 0.5, range [0,1]) in each category that has `bet_thr` (T13D, FLAIR3D, MDC, VENOUS_MR). Add cross-preference `pref_requirement` so the workflow-preferences window greys options by the global engine:
- `bet_thr` and `bet_bias_correction` require `deskull_engine == DeskullEngine.BET`.
- `antspynet_thr` requires `deskull_engine == DeskullEngine.ANTSPYNET`.

When the engine is SYNTHSTRIP, all three are greyed (neither requirement matches) — intended.

- [ ] **Step 1: Failing test**

```python
# swane/tests/config/test_deskull_threshold_pref.py
from swane.config.config_enums import DeskullEngine, GlobalPrefCategoryList
from swane.config.preference_list import WF_PREFERENCES
from swane.utils.DataInputList import DataInputList

BET_THR_CATS = [
    DataInputList.T13D, DataInputList.FLAIR3D,
    DataInputList.MDC, DataInputList.VENOUS_MR,
]


def test_antspynet_thr_added_to_each_bet_thr_category():
    for cat in BET_THR_CATS:
        entry = WF_PREFERENCES[cat]["antspynet_thr"]
        assert entry.default == 0.5
        assert entry.range == [0, 1]
        req = entry.pref_requirement[GlobalPrefCategoryList.SYNTH]
        assert ("deskull_engine", DeskullEngine.ANTSPYNET) in req


def test_bet_thr_gated_by_bet_engine():
    for cat in BET_THR_CATS:
        req = WF_PREFERENCES[cat]["bet_thr"].pref_requirement[
            GlobalPrefCategoryList.SYNTH
        ]
        assert ("deskull_engine", DeskullEngine.BET) in req


def test_bet_bias_correction_gated_by_bet_engine():
    for cat in (DataInputList.T13D, DataInputList.FLAIR3D, DataInputList.MDC):
        req = WF_PREFERENCES[cat]["bet_bias_correction"].pref_requirement[
            GlobalPrefCategoryList.SYNTH
        ]
        assert ("deskull_engine", DeskullEngine.BET) in req
```

- [ ] **Step 2: Run to verify failure**

Run: `/media/Dati/venv/bin/python -m pytest swane/tests/config/test_deskull_threshold_pref.py -v`
Expected: FAIL (`KeyError: 'antspynet_thr'`).

- [ ] **Step 3: Implement**

Ensure `preference_list.py` imports `DeskullEngine` and `GlobalPrefCategoryList` (both already used in the file). Define a small helper tooltip constants, then:

1. Add `pref_requirement` to the existing `bet_bias_correction` entry (T13D — shared with FLAIR3D/MDC) and to each of the four `bet_thr` entries:

```python
    pref_requirement={
        GlobalPrefCategoryList.SYNTH: [("deskull_engine", DeskullEngine.BET)]
    },
    pref_requirement_fail_tooltip="Only used when the brain extraction engine is FSL BET",
```

2. After each `bet_thr` block (all four categories), add:

```python
WF_PREFERENCES[category]["antspynet_thr"] = PreferenceEntry(
    input_type=InputTypes.FLOAT,
    label="antspynet brain-extraction threshold",
    default=0.5,
    tooltip="Probability threshold for the antspynet brain mask (0 to 1)",
    range=[0, 1],
    pref_requirement={
        GlobalPrefCategoryList.SYNTH: [
            ("deskull_engine", DeskullEngine.ANTSPYNET)
        ]
    },
    pref_requirement_fail_tooltip="Only used when the brain extraction engine is antspynet",
)
```

(Set it while `category` is each of `DataInputList.T13D`, `FLAIR3D`, `MDC`, `VENOUS_MR`, next to that category's `bet_thr`.)

Note: `bet_bias_correction` is a shared object for T13D/FLAIR3D/MDC, so setting its `pref_requirement` once on the T13D object covers all three; do not set it on VENOUS_MR (it has none).

- [ ] **Step 4: Run tests**

Run: `/media/Dati/venv/bin/python -m pytest swane/tests/config/test_deskull_threshold_pref.py swane/tests/config/test_preferences.py swane/tests/config/test_deskull_engine_pref.py -v`
Expected: PASS.

- [ ] **Step 5: Manual UI smoke check (optional but recommended)**

If a Mac/Linux display is available: open the workflow preferences window with `deskull_engine=ANTSPYNET` and confirm `bet_thr`/`bet_bias_correction` are greyed and `antspynet_thr` editable; switch the global engine to BET, reopen, confirm the inverse. (Grey-out is evaluated at window open, by design — the engine is a global preference in a separate window.)

- [ ] **Step 6: Black + commit**

```bash
/media/Dati/venv/bin/python -m black swane/config/preference_list.py swane/tests/config/test_deskull_threshold_pref.py
git add swane/config/preference_list.py swane/tests/config/test_deskull_threshold_pref.py
git commit -m "feat: antspynet_thr preference and engine-aware grey-out of deskull options"
```

---

### Task C: wire `antspynet_thr` through the three config-driven workflows

**Model:** opus4.8

**Files:**
- Modify: `swane/nipype_pipeline/workflows/ref_workflow.py`, `linear_reg_workflow.py`, `venous_mr_workflow.py`
- Test: `swane/tests/nipype_pipeline/` (extend a workflow-construction test, or add one, asserting the antspynet node gets the configured threshold)

- [ ] **Step 1: Failing test**

Add a test (reuse the fixtures of an existing workflow-construction test that sets `deskull_engine=ANTSPYNET`) asserting the deskull node's `threshold` equals the configured `antspynet_thr`. Example shape for `ref_workflow`:

```python
# in a suitable swane/tests/nipype_pipeline/ module
def test_ref_forwards_antspynet_threshold(<fixtures>):
    config[<T13D>]["antspynet_thr"] = "0.6"   # subject config section
    wf = ref_workflow(name=..., dicom_dir=..., config=config[<T13D>],
                      synth_config=<synth with deskull_engine=ANTSPYNET>, ...)
    assert wf.get_node("ref_deskull_biased_antspynet").inputs.threshold == 0.6
```

(Confirm the exact deskull node name from `ref_workflow`: it builds `get_deskull_node(name="ref_deskull_biased", ...)`, so the antspynet node is `ref_deskull_biased_antspynet`.)

- [ ] **Step 2: Run to verify failure**

Run: `/media/Dati/venv/bin/python -m pytest <new test> -v`
Expected: FAIL (threshold not forwarded).

- [ ] **Step 3: Implement**

In each of the three workflows, read `antspynet_thr` next to where `bet_thr` is read and pass it to `get_deskull_node(..., antspynet_thr=...)`:

- `ref_workflow.py` (`config` is always set):
  ```python
  antspynet_thr = config.getfloat_safe("antspynet_thr")
  ...
  get_deskull_node(..., bet_thr=config.getfloat_safe("bet_thr"),
                   antspynet_thr=antspynet_thr, ...)
  ```
- `linear_reg_workflow.py` (`config` may be `None`, mirror the existing `bet_thr` guard):
  ```python
  antspynet_thr = None if not config else config.getfloat_safe("antspynet_thr")
  ...
  get_deskull_node(..., bet_thr=bet_thr, antspynet_thr=antspynet_thr, ...)
  ```
- `venous_mr_workflow.py`:
  ```python
  get_deskull_node(..., bet_thr=config.getfloat_safe("bet_thr"),
                   antspynet_thr=config.getfloat_safe("antspynet_thr"), ...)
  ```

Leave `dti_preproc_workflow.py` and `fMRI_preproc_workflow.py` unchanged (no `bet_thr` preference; antspynet threshold stays at the node default 0.5).

- [ ] **Step 4: Run tests**

Run: `/media/Dati/venv/bin/python -m pytest swane/tests/nipype_pipeline/ -k "deskull or reg or venous" -v`
Expected: PASS. Then run the deskull-surface suites and the matrix suite:
`/media/Dati/venv/bin/python -m pytest swane/tests/nipype_pipeline/matrix -v` — if any golden snapshot now carries a `threshold` input on an antspynet node, regenerate it per `swane/tests/nipype_pipeline/matrix/README.md` and review the diff (only the threshold input should change).

- [ ] **Step 5: Black + commit**

```bash
/media/Dati/venv/bin/python -m black swane/nipype_pipeline/workflows/ref_workflow.py \
    swane/nipype_pipeline/workflows/linear_reg_workflow.py \
    swane/nipype_pipeline/workflows/venous_mr_workflow.py
git add swane/nipype_pipeline/workflows/ref_workflow.py \
        swane/nipype_pipeline/workflows/linear_reg_workflow.py \
        swane/nipype_pipeline/workflows/venous_mr_workflow.py \
        swane/tests/nipype_pipeline/
git commit -m "feat: forward antspynet_thr from config in ref/linear_reg/venous_mr"
```

---

## Self-review

- **Coverage:** threshold input (Task A) + preference & grey-out (Task B) + config wiring (Task C) cover both requested behaviors.
- **Scope:** DTI/fMRI intentionally excluded (no `bet_thr` preference there); documented.
- **Grey-out limitation:** evaluated at workflow-preferences-window open, not live, because `deskull_engine` is a global preference in a separate window — consistent with the existing cross-preference mechanism. If live grey-out within a single window is later required, that is a larger change (surfacing the engine in the workflow window) and is out of scope here.
- **Type consistency:** `antspynet_thr` (float) and node `threshold` (traits.Float, default 0.5) match across tasks; `get_deskull_node(..., antspynet_thr=...)` matches between Task A definition and Task C callers.
