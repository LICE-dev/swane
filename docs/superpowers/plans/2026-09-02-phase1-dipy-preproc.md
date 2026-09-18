# Phase 1 — dipy preprocessing to global tractogram Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Each executor also runs superpowers:test-driven-development and superpowers:verification-before-completion.

**Goal:** Build the dipy tractography engine's preprocessing-through-tracking half — engine preference, dependency/licence plumbing, the new dipy Nipype nodes, `dipy_dti_preproc_workflow`, the `MainWorkflow` branch, and matrix snapshots — producing a global `.trx` tractogram, its atlas-aligned copy, and the inverse transform for both oracle subjects.

**Architecture:** A second, parallel DTI pair. `dti_preproc_workflow` and `tractography_workflow` are left **bit-for-bit untouched**; `dipy_dti_preproc_workflow` is added (Phase 2 adds `dipy_bundle_workflow`), and `MainWorkflow.launch_dti_analysis` branches on a new `TractographyEngine` enum. The ~4-node shared head (dcm2niix → ForceOrient → b0 extract → deskull) is duplicated, not extracted, so the validated FSL path and its golden snapshots do not churn. Every dipy node is a thin custom Nipype interface over a documented dipy call, declares HARD_CAP resources, and pins its BLAS/OMP thread count.

**Tech Stack:** Python 3.12, nipype 1.12.0, dipy 1.12.0 (+ `trx-python`), antspyx (N4), nibabel/numpy, pytest. FSL is **not** invoked anywhere in this workflow.

**Spec:** `docs/superpowers/specs/2026-09-02-dipy-recobundles-tractography-design.md` — the plan argues from it; executors read both. Sections most load-bearing here: 1, 2, 4, 5, 8, 9, 10, Validation, Measurements. **Read section 2's "MP-PCA is dropped" decision and the Phase-1-orchestrator note before starting: there is no MP-PCA, no `fast_dwi_preproc` preference, no adaptive `patch_radius`, and no slab-parallel denoise oracle.**

## Global Constraints

- Start from branch `claude/dipy-recobundles`; do not commit, push, merge or open a PR unless explicitly asked.
- Every part of SWANe code and documentation is written in English.
- Never use "patient" — always "subject". SWANe is a research tool, never described as clinical or medical.
- Any Python command must use `/media/Dati/venv/bin/python`, never FSL's or FreeSurfer's bundled interpreter. Verify with `python -c "import sys; print(sys.executable)"` when unsure.
- Format changed Python with Black; do not reformat unrelated files.
- Preserve existing "derived from Nipype" disclaimer comments; every new node carries them (spec section 9).
- Persisted preference keys, enum member names, workflow/node names, Traits fields, signals and result filenames are stable contracts. The three consumed by Phase 2 — `outputnode.tractogram`, `outputnode.tractogram_atlas`, `outputnode.atlas2native` — must be named exactly that.
- Real subject data, the HCP842 atlas and every derived artefact stay outside the repository. Before each commit, `git diff --name-only` must list only source, tests and docs — never a path under `test_swane`, never a binary imaging format.
- `CoreLimit.NO_LIMIT` and `SOFT_CAP` are being removed; do not add new behaviour branches for them. New dipy nodes and the new workflow factory assume **HARD_CAP only** and take no `multicore_node_limit` parameter.
- The FSL path stays bit-identical: `dti_preproc_workflow`, `tractography_workflow`, and every existing snapshot outside the new `dipy_dti_preproc` one must be byte-identical. Phase 0's five regenerated `snapshots/dti_preproc/*.txt` are already committed (`ab0828b`) and are the only permitted pre-existing delta.

---

## State of the tree (verified at plan time)

Phase 0 is **committed**, not uncommitted as the orchestrator prompt assumed: `ab0828b fix: feed eddy's rotated b-vectors to dtifit and bedpostx` is in the log and `git status --short snapshots/` is clean. Nothing about Phase 1 changes as a result — the FSL branch is simply already sealed. A pile of untracked dotfiles (`.bashrc`, `.claude/…`, `.gitconfig`, `.mcp.json`, …) sit in the working tree; they are environment files, not part of this work — never `git add` them, and keep every commit's `git diff --name-only` limited to SWANe source/tests/docs.

## Verified live-code anchors (rely on these)

| Fact | Location |
|---|---|
| `is_antspynet()` / `check_antspynet()` pattern to copy for dipy | `swane/utils/DependencyManager.py:194,398` |
| Instance dep attrs set in `__init__`; version consts; `SLICER_MODULES` | `DependencyManager.py:109-112,96-106` |
| `check_dep_antspynet_*` strings; `node_names` dict | `swane/strings.py:389-400,479` |
| `RegistrationEngine` / `DeskullEngine` enum pattern | `swane/config/config_enums.py:70,76` |
| `option_dependency` + `option_pref_requirement` (RAM message) pattern | `swane/config/preference_list.py:699-767` |
| DTI `WF_PREFERENCES` block; `TRACTS` dict (20 keys, `str`/`atr`/`cbd`/`cbp`/`cbt` present) | `preference_list.py:381-419,27-48` |
| WF pref gating on a **global** SYNTH pref (precedent) | `preference_list.py:88-113` (`deskull_engine`) |
| `LicenseReference` `TOOL_IDS` / `LICENSES` / bundled dir | `swane/utils/LicenseReference.py:18,134,20` |
| `MainWorkflow.launch_dti_analysis`; `self.is_tractography` | `swane/nipype_pipeline/MainWorkflow.py:981,214,63` |
| Shared head + node interface pattern (disclaimers, Base/Traited specs) | `dti_preproc_workflow.py:137-173`; `nodes/ExtractVolumes.py` |
| Thread-pinning precedent (ITK env var in `_run_interface`) | `nodes/AntsN4BiasFieldCorrection.py:40,109-110` |
| Matrix harness (`graph_snapshot` fixture, `SCENARIOS`, `config_echo`) | `tests/nipype_pipeline/matrix/test_dti_matrix.py`, `conftest.py`, `_snapshot.py` |
| `setup.py` pins; `NOTICE.md` third-party structure; home-screen dep rows | `setup.py:32-52`; `NOTICE.md`; `swane/ui/MainWindow.py:939-945,988` |
| `ToolReference` registry | `swane/utils/ToolReference.py:17,41` |

**dipy call signatures are not pinned in this plan.** SWANe must not invent external-tool behaviour (`CLAUDE.md`). Each node task pins the SWANe-side contract (node name, traits, output fields) and **requires the executor to confirm the exact dipy 1.12.0 call from the installed `/media/Dati/venv` package** (`python -c "import dipy; help(dipy.<...>)"`) before wiring, citing the spec's named function.

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `swane/utils/DependencyManager.py` | `is_dipy()` / `check_dipy()`, instance attr, `MIN_DIPY_VERSION` | Modify |
| `swane/strings.py` | `check_dep_dipy_*` messages; `node_names` for every new node | Modify |
| `swane/ui/MainWindow.py` | dipy home-screen dependency row | Modify |
| `swane/utils/LicenseReference.py` | `DIPY` `TOOL_IDS`/`LICENSES` entry | Modify |
| `swane/licenses/dipy.txt` | bundled dipy BSD-3 text | Create |
| `swane/utils/ToolReference.py` | citations for new dipy nodes (Tournier 2007, Coupé 2008, Girard 2014, Garyfallidis 2017, Yeh 2018) | Modify |
| `setup.py` | `dipy==1.12.0` pin | Modify |
| `NOTICE.md` | dipy BSD-3 **and** HCP842 atlas CC BY 4.0 attribution | Modify |
| `swane/config/config_enums.py` | `TractographyEngine` enum | Modify |
| `swane/config/preference_list.py` | `tractography_engine` global pref; per-engine gating; `cingulum`/`seed_density`/`max_angle`/`step_size` | Modify |
| `swane/nipype_pipeline/nodes/DipyDenoise.py` | nlmeans + estimate_sigma node | Create |
| `swane/nipype_pipeline/nodes/DipyTensorFit.py` | tensor fit → FA node | Create |
| `swane/nipype_pipeline/nodes/DipyTissueClassifier.py` | HMRF → 3 PVE maps node | Create |
| `swane/nipype_pipeline/nodes/DwiBiasCorrection.py` | N4 on mean b0, field applied to all volumes | Create |
| `swane/nipype_pipeline/nodes/DipyMotionCorrection.py` | parallel motion correction + `reorient_bvecs` | Create |
| `swane/nipype_pipeline/nodes/DipyCsdFit.py` | CSD with adaptive `sh_order_max` | Create |
| `swane/nipype_pipeline/nodes/DipyTracking.py` | PFT + CMC, WM-mask seeding, `.trx` | Create |
| `swane/nipype_pipeline/nodes/DipyAtlasSLR.py` | whole-brain SLR against atlas + atlas fetch (file lock) | Create |
| `swane/nipype_pipeline/workflows/dipy_dti_preproc_workflow.py` | the dipy DTI graph | Create |
| `swane/nipype_pipeline/MainWorkflow.py` | engine branch in `launch_dti_analysis` | Modify |
| `swane/tests/nipype_pipeline/nodes/test_dipy_*.py` | node unit + oracle tests | Create |
| `swane/tests/nipype_pipeline/matrix/test_dipy_dti_matrix.py` + `snapshots/dipy_dti_preproc/` | golden graph snapshots | Create |
| `swane/tests/config/…` | per-engine gating test | Create/modify |

Confirm every consumer before editing:
```bash
grep -rn "tractography_engine\|TractographyEngine\|is_dipy\|check_dipy" --include=*.py swane/ | grep -v docs/superpowers
```

---

## Executor split and ordering

The nine executors below map to the orchestrator's suggested split; the model rationale is fixed. **Ordering constraints** (from the Interfaces blocks): Task 1 (`is_dipy`) precedes Task 2's `option_dependency`; Tasks 3–8 (nodes) precede Task 9 (workflow wiring); Task 9 precedes Task 10 (matrix snapshots + `MainWorkflow` branch); Task 11 (oracle) is last and needs the whole chain. Tasks 3–8 are mutually independent and fan out in parallel.

| # | Executor | Model |
|---|---|---|
| 1 | Dependency + licence plumbing | Sonnet 5 |
| 2 | `TractographyEngine` enum + preference gating | Sonnet 5 |
| 3 | `DipyDenoise`, `DipyTensorFit`, `DipyTissueClassifier` | Sonnet 5 |
| 4 | `DwiBiasCorrection` | Opus 4.8 |
| 5 | `DipyMotionCorrection` + three-layer oracle | Opus 4.8 |
| 6 | `DipyCsdFit` (adaptive `sh_order_max`) | Opus 4.8 |
| 7 | `DipyTracking` (PFT/CMC/WM seed/`.trx`) + `DipyAtlasSLR` + atlas fetch lock | Opus 4.8 |
| 9 | `dipy_dti_preproc_workflow`, `MainWorkflow` branch, matrix snapshots | Sonnet 5 |
| 11 | Oracle runs (subj1 + subj2), isolated `_mem_gb`, FSL comparison | Opus 4.8 |

(Task numbers below are the plan's execution order; the table's `#` is the orchestrator label.)

---

### Task 1: Dependency + licence plumbing (Sonnet 5)

**Files:**
- Modify: `swane/utils/DependencyManager.py` (add near `:96-112,194,398`)
- Modify: `swane/strings.py:389-400` (new `check_dep_dipy_*` block), `:479+` (`node_names`)
- Modify: `swane/ui/MainWindow.py:945` (add dipy row after antspynet)
- Modify: `swane/utils/LicenseReference.py:18,134`
- Create: `swane/licenses/dipy.txt` (dipy BSD-3 text, copied verbatim from the installed distribution's licence file)
- Modify: `swane/utils/ToolReference.py`, `setup.py:32-52`, `NOTICE.md`
- Test: `swane/tests/utils/test_dipy_dependency.py` (create)

**Interfaces:**
- Produces: `DependencyManager.is_dipy() -> bool` and `DependencyManager.check_dipy() -> Dependence` (static, `find_spec`/metadata pattern of `check_antspynet`); `DependencyManager.MIN_DIPY_VERSION = "1.12.0"`; instance attr `self.dipy` set in `__init__`; `LicenseReference.DIPY = "dipy"` in `TOOL_IDS` and `LICENSES`. Task 2 consumes `is_dipy` by name (string) in `option_dependency`.

- [ ] **Step 1: Write the failing test**
```python
# swane/tests/utils/test_dipy_dependency.py
from swane.utils.DependencyManager import DependencyManager
from swane.config.dependence_status import DependenceStatus  # confirm import path


def test_check_dipy_detects_installed_package():
    dep = DependencyManager.check_dipy()
    assert dep.state == DependenceStatus.DETECTED
    assert DependencyManager.is_dipy() is True


def test_dipy_license_registered():
    from swane.utils.LicenseReference import TOOL_IDS, LICENSES, DIPY, bundled_license_path
    import os
    assert DIPY in TOOL_IDS
    assert LICENSES[DIPY].display_name  # non-empty
    assert os.path.exists(bundled_license_path(LICENSES[DIPY]))
```
(Confirm `DependenceStatus`'s real import path with a quick grep before running.)

- [ ] **Step 2: Run to verify it fails**
```bash
/media/Dati/venv/bin/python -m pytest swane/tests/utils/test_dipy_dependency.py -v
```
Expected: FAIL (`check_dipy` undefined, `DIPY` not importable).

- [ ] **Step 3: Implement `check_dipy`/`is_dipy`**, copying `check_antspynet`/`is_antspynet` verbatim in shape: `importlib.util.find_spec("dipy")` presence probe, `importlib.metadata.version("dipy")`, compare to `MIN_DIPY_VERSION`, return `Dependence(...)` with the new strings. Add `self.dipy = DependencyManager.check_dipy()` in `__init__` beside `self.antspynet`. Add the `check_dep_dipy_error/no_version/wrong_version/found` strings mirroring `:389-400`.

- [ ] **Step 4: Register the licence and attribution.** Add `DIPY = "dipy"` to `TOOL_IDS`; add a `LICENSES[DIPY] = LicenseInfo(...)` entry (BSD-3; `bundled_filename="dipy.txt"`; `installed_path_candidates` following `_antspyx_candidates` PEP-639 recovery, since dipy ships its licence in `.dist-info`; `online_is_official` per whether a canonical raw URL exists). Create `swane/licenses/dipy.txt` from the installed distribution. In `NOTICE.md` add two third-party entries: **dipy** (BSD 3-clause) and the **HCP842 atlas** (CC BY 4.0, © Eleftherios Garyfallidis) — the atlas gets attribution here, deliberately **no** license-acceptance entry (spec section 8). Add `ToolReference` citations for the new nodes (Tournier 2007, Coupé 2008, Girard 2014, Garyfallidis 2017, Yeh 2018). Add `dipy==1.12.0` to `setup.py` `install_requires`. Add the home-screen row at `MainWindow.py` after antspynet: `x = self.add_home_entry(self.dependency_manager.dipy, x)`. Add `node_names` entries for every node created in Tasks 3–8 (readable labels, e.g. `node_names["DipyDenoise"] = "diffusion denoising"`).

- [ ] **Step 5: Run to verify it passes**, then `black` the changed files.
```bash
/media/Dati/venv/bin/python -m pytest swane/tests/utils/test_dipy_dependency.py -v
```
Expected: PASS.

- [ ] **Step 6: Commit** (`feat: add dipy dependency detection, licence and attribution`).

---

### Task 2: `TractographyEngine` enum + preference gating (Sonnet 5)

**Files:**
- Modify: `swane/config/config_enums.py:70-79` (add enum after `DeskullEngine`)
- Modify: `swane/config/preference_list.py:381-419` (DTI block) and `:697+` (SYNTH global block)
- Test: `swane/tests/config/test_tractography_engine_gating.py` (create)

**Interfaces:**
- Consumes: `DependencyManager.is_dipy` (Task 1) by string name.
- Produces: `TractographyEngine` enum `{FSL_XTRACT = "FSL (XTRACT/probtrackx2)", DIPY_RECOBUNDLES = "dipy (CSD + RecoBundles)"}`; global pref `GLOBAL_PREFERENCES[GlobalPrefCategoryList.SYNTH]["tractography_engine"]`, default `DIPY_RECOBUNDLES`; new DTI prefs `cingulum` (bool), `seed_density` (int), `max_angle` (float), `step_size` (float). Task 9/Task 10 read the pref via `synth_config`/`getenum_safe`.

- [ ] **Step 1: Write the failing test** — assert (a) the enum members and their exact string values; (b) `tractography_engine` exists in SYNTH with default `DIPY_RECOBUNDLES` and `option_dependency[DIPY_RECOBUNDLES]` naming `"is_dipy"`; (c) gating table from spec section 2 resolves correctly. Use the live gating evaluator, not a re-implementation — locate how `pref_requirement`/`option_dependency` are evaluated (grep `pref_requirement` consumers under `swane/config` and `swane/ui`) and assert through it. Minimum concrete assertions:
```python
from swane.config.config_enums import TractographyEngine, GlobalPrefCategoryList
from swane.config.preference_list import GLOBAL_PREFERENCES, WF_PREFERENCES
from swane.utils.DataInputList import DataInputList


def test_engine_enum_values():
    assert TractographyEngine.FSL_XTRACT.value == "FSL (XTRACT/probtrackx2)"
    assert TractographyEngine.DIPY_RECOBUNDLES.value == "dipy (CSD + RecoBundles)"


def test_engine_pref_default_and_dependency():
    entry = GLOBAL_PREFERENCES[GlobalPrefCategoryList.SYNTH]["tractography_engine"]
    assert entry.default == TractographyEngine.DIPY_RECOBUNDLES
    assert entry.option_dependency[TractographyEngine.DIPY_RECOBUNDLES][0] == "is_dipy"


def test_new_dipy_prefs_exist():
    dti = WF_PREFERENCES[DataInputList.DTI]
    for key in ("cingulum", "seed_density", "max_angle", "step_size"):
        assert key in dti
```

- [ ] **Step 2: Run to verify it fails.**
- [ ] **Step 3: Add the enum** after `DeskullEngine` (`config_enums.py`).
- [ ] **Step 4: Add the SYNTH global pref** mirroring `engine`/`deskull_engine` at `:734-767`: `value_enum=TractographyEngine`, `default=TractographyEngine.DIPY_RECOBUNDLES`, `option_dependency={TractographyEngine.DIPY_RECOBUNDLES: ["is_dipy", "dipy tractography requires the dipy package"]}`, `section=True`, plus the RAM `option_pref_requirement`/`fail_tooltip` for `DIPY_RECOBUNDLES` if a floor is set (spec calls for a RAM-requirement message analogous to antspynet's). FSL_XTRACT needs no dependency clause (FSL is the global hard requirement).
- [ ] **Step 5: Add gating in the DTI block** (`preference_list.py:381-419`) exactly per spec §2 table, using the existing `pref_requirement` mechanism and the SYNTH-global precedent at `:88-113`. Concretely, for each affected pref add a `pref_requirement={GlobalPrefCategoryList.SYNTH: [("tractography_engine", TractographyEngine.<X>)]}` (combined with the existing `tractography=True` DTI requirement where present) and a matching `pref_requirement_fail_tooltip`:
  - `atr`,`str`,`cbd`,`cbp`,`cbt` → require `FSL_XTRACT` ("no RecoBundles atlas counterpart").
  - `tractography_threshold`,`track_procs`,`old_eddy_correct` → require `FSL_XTRACT` (`old_eddy_correct` tooltip: "dipy always uses nlmeans").
  - new `cingulum` (bool) → require `DIPY_RECOBUNDLES`.
  - new `seed_density` (int), `max_angle` (float), `step_size` (float) → require `DIPY_RECOBUNDLES`; choose defaults/ranges consistent with the tracking node's traits in Task 7 (keep them in sync — see Task 7 Interfaces). The 16 active tract checkboxes and `tractography` itself stay active on both engines (do not add an engine requirement to them).
- [ ] **Step 6: Run to verify it passes; `black`; commit** (`feat: add TractographyEngine preference and per-engine DTI gating`).

**Contract note:** `old_eddy_correct` keeps its key, FSL-only meaning, and default — it is only greyed on dipy. Do not rename it or give it a dipy meaning (spec §2, Phase-0 Task 1 cancellation).

---

### Task 3: `DipyDenoise`, `DipyTensorFit`, `DipyTissueClassifier` (Sonnet 5)

**Files:**
- Create: `swane/nipype_pipeline/nodes/DipyDenoise.py`, `DipyTensorFit.py`, `DipyTissueClassifier.py`
- Test: `swane/tests/nipype_pipeline/nodes/test_dipy_denoise.py`, `test_dipy_tensorfit.py`, `test_dipy_tissue.py`

**Interfaces (SWANe-side, pinned):**
- `DipyDenoise`: in `in_file`(4D DWI), `bval`, `bvec`, `num_threads`(Int, nohash), `out_file`; out `out_file`. Calls `estimate_sigma` on the passed data, then `nlmeans` (spec §5). Pins `OMP_NUM_THREADS`/`OPENBLAS_NUM_THREADS` to `num_threads` in `_run_interface` (ITK-env pattern, `AntsN4BiasFieldCorrection.py:109`). Preserves shape, affine, volume count.
- `DipyTensorFit`: in `in_file`, `bval`, `bvec`, `mask`, `out_fa`; out `fa` (and any tensor outputs the workflow needs). Cheap, `n_procs=1`, still pins OMP=1.
- `DipyTissueClassifier`: in `in_file`(T1 `reference_brain`), `out_prefix`; out `pve_csf`, `pve_gm`, `pve_wm` (three PVE maps, HMRF). `n_procs=1`, OMP pinned.

**Confirm before wiring:** exact dipy calls (`dipy.denoise.nlmeans.nlmeans`, `dipy.denoise.noise_estimate.estimate_sigma`, `dipy.reconst.dti.TensorModel`/`fractional_anisotropy`, `dipy.segment.tissue.TissueClassifierHMRF`) against installed dipy 1.12.0.

Each node: Nipype disclaimer header + three class disclaimers (spec §9). TDD per node, e.g. `DipyDenoise`:

- [ ] **Step 1: Failing test** — synthetic 4D fixture (small, in-repo synthetic array, no subject data): assert `estimate_sigma` is called on the data actually passed to `nlmeans` (patch/monkeypatch dipy to record args), output preserves `shape`, `affine`, and volume count, and that `_run_interface` sets `OMP_NUM_THREADS == str(num_threads)`.
- [ ] **Step 2: Run to verify it fails.**
- [ ] **Step 3: Implement the node** (disclaimers, InputSpec/OutputSpec/BaseInterface mirroring `ExtractVolumes.py`; env pinning in `_run_interface`).
- [ ] **Step 4: Run to verify it passes.**
- [ ] **Step 5: Repeat Steps 1–4 for `DipyTensorFit` and `DipyTissueClassifier`** (tensor: FA shape/finiteness on a synthetic tensor; tissue: three PVE maps summing ~1 per brain voxel on a synthetic 3-tissue phantom).
- [ ] **Step 6: `black`; commit** (`feat: add DipyDenoise, DipyTensorFit, DipyTissueClassifier nodes`).

---

### Task 4: `DwiBiasCorrection` (Opus 4.8)

**Files:** Create `swane/nipype_pipeline/nodes/DwiBiasCorrection.py`; Test `swane/tests/nipype_pipeline/nodes/test_dwi_bias.py`.

**Interfaces:** in `in_file`(4D DWI), `bval` (to locate b0s), `num_threads`; out `out_file`(4D, all volumes bias-corrected), `bias_field`. **Scientific contract:** estimate the N4 field **once** on the mean b0, then divide **all** volumes by that single field. Re-estimating the field per volume, or applying only to b0, is a silent scientific error (orchestrator rationale).

- [ ] **Step 1: Failing test** — the load-bearing assertion: with a synthetic 4D DWI whose volumes differ only by a known multiplicative field, mock/observe the N4 estimator to prove it is invoked **exactly once**, on the mean-b0 image, and that the correction applied to volume *k* is that same field (not a per-volume re-estimate). Also assert output volume count == input and the field has DWI spatial shape.
- [ ] **Step 2: Run to verify it fails.**
- [ ] **Step 3: Implement** — reuse the existing `AntsN4BiasFieldCorrection` node/antspyx N4 for the single estimate on the mean b0; broadcast-divide all volumes; pin OMP/ITK threads to `num_threads`. Disclaimers per §9.
- [ ] **Step 4: Run to verify it passes.**
- [ ] **Step 5: `black`; commit** (`feat: add DwiBiasCorrection (single N4 field applied to all DWI volumes)`).

---

### Task 5: `DipyMotionCorrection` + three-layer oracle (Opus 4.8)

**Files:** Create `swane/nipype_pipeline/nodes/DipyMotionCorrection.py`; Test `swane/tests/nipype_pipeline/nodes/test_dipy_motion.py` (unit + `@pytest.mark.heavy` oracle).

**Interfaces:** in `in_file`(4D DWI), `bval`, `bvec`, `num_threads`; out `out_file`(4D, registered), `out_bvec`(reoriented), `out_bval`(passthrough). The node runs `dipy.align` `motion_correction` per volume over **our own pool** (spec §10), then reorients gradients with `dipy.core.gradients.reorient_bvecs`.

**Implement serial first** (spec Validation): a serial path calling dipy directly, behind the final interface, kept permanently reachable as reference/fallback; the parallel path must match it bit-for-bit with BLAS threads pinned.

The three oracle layers (spec Validation "DipyMotionCorrection equivalence") — all three are mandatory:

- [ ] **Step 1a (reassembly by index):** unit test with **mocked** registration returning identifiable per-volume payloads **out of order**; assert volume *i* lands at position *i*. Run → fail → implement index-keyed reassembly → pass.
- [ ] **Step 1b (bvec reorientation + indexing trap):** unit test applying a known rigid rotation; assert the reoriented bvec matches the analytic expectation, b0 rows stay `[0,0,0]`, norms preserved. **The call must pass `affines[..., ~gtab.b0s_mask]`** (non-b0 volumes only) to `reorient_bvecs`, while `motion_correction` returns affines for **all** volumes — passing the full array silently misaligns every gradient. Run → fail → implement → pass.
- [ ] **Step 1c (serial-vs-parallel oracle, `@pytest.mark.heavy`):** pin `OMP_NUM_THREADS=1` on both sides; assert exact (bit-for-bit) equality of serial vs parallel output; do **not** loosen the tolerance. Cheap guards: output volume count == input; no volume entirely zero. Run → (serial baseline green first) → implement parallel → pass.
- [ ] **Step 2: `black`; commit** (`feat: add DipyMotionCorrection with reorient_bvecs and serial/parallel equivalence oracle`). Disclaimers per §9; OMP pinned to `num_threads`.

---

### Task 6: `DipyCsdFit` with adaptive `sh_order_max` (Opus 4.8)

**Files:** Create `swane/nipype_pipeline/nodes/DipyCsdFit.py`; Test `swane/tests/nipype_pipeline/nodes/test_dipy_csd.py`.

**Interfaces:** in `in_file`, `bval`, `bvec`, `mask`, `num_threads`; out `peaks`/`shm_coeff` (the field the tracking node consumes — pin the exact name and keep it in sync with Task 7). Uses `auto_response_ssst` for the response, `peaks_from_model(num_processes=…)` (spec §10). OMP pinned to `num_threads`.

**Adaptive `sh_order_max`** — the off-by-one here silently over-fits sparse data, so the direction→lmax mapping is tested directly against the spec §5 table:

| Directions | lmax |
|---|---|
| ≥45 | 8 |
| ≥28 | 6 |
| ≥15 | 4 |
| ≥6 | 2 |

- [ ] **Step 1: Failing test** — factor the mapping into a pure helper `sh_order_for_directions(n_dirs) -> int` and assert every boundary exactly: `44→6, 45→8, 27→4, 28→6, 15→4, 14→2, 6→2` (direction count = number of non-b0 gradient directions; confirm whether the spec counts unique directions or non-b0 volumes and assert the same definition the node uses). Run → fail.
- [ ] **Step 2: Implement** the helper + node; derive `n_dirs` from the gtab (non-b0 mask), never from total volume count. Run → pass.
- [ ] **Step 3: `black`; commit** (`feat: add DipyCsdFit with adaptive sh_order_max`). Disclaimers per §9.

---

### Task 7: `DipyTracking` + `DipyAtlasSLR` + atlas fetch lock (Opus 4.8)

**Files:** Create `swane/nipype_pipeline/nodes/DipyTracking.py`, `DipyAtlasSLR.py`; Test `test_dipy_tracking.py`, `test_dipy_slr.py`, `test_atlas_fetch_lock.py`.

**Interfaces:**
- `DipyTracking`: in `shm_coeff`/`peaks` (from Task 6 — match the name), `pve_wm`,`pve_gm`,`pve_csf` (from Task 3), `affine_diff2ref`, `seed_density`(Int), `max_angle`(Float), `step_size`(Float), `random_seed`(Int), `num_threads`; out `tractogram`(`.trx`, reference space). **Seeds from the WM PVE mask only** (whole-brain seeding cost 7 GB / 5× runtime — spec Measurements). PFT (`pft_tracking`) with `CmcStoppingCriterion` built from the 3 PVE maps; streamlines moved to reference space via `transform_streamlines` and the `dif2ref` affine (no FSL `.mat`). Writes `.trx` (memory-mappable), never a Python list.
  - **Keep `seed_density`/`max_angle`/`step_size` trait defaults/ranges identical to the Task 2 preferences** — they are the same knobs surfaced two ways.
- `DipyAtlasSLR`: in `tractogram`(reference space), `atlas_dir`; out `tractogram_atlas`(aligned to atlas), `atlas2native`(inverse transform). Whole-brain SLR against the atlas, **run once** (spec §6). Includes the atlas fetch (`fetch_bundle_atlas_hcp842`) guarded by a **file lock** (parallel subjects both finding `~/.dipy` empty must not both fetch 649 MB), a readable offline failure instead of a raw traceback, and cleanup of a partial directory on retry (spec §8). Address atlas bundles by explicit name, never glob (the misspelled `IF0F_R.trk` trap).

- [ ] **Step 1: `DipyTracking` failing tests** — on a small synthetic fODF/PVE fixture: (a) seeds come from the WM PVE mask (assert seed coordinates lie within WM, none in CSF/cortex); (b) output is a `.trx` file that loads and is non-empty; (c) **streamline-order reproducibility** — two runs at equal `random_seed` give identical trajectories even if file bytes differ (compare sorted/ふcanonicalised streamline sets); (d) OMP pinned. Run → fail → implement → pass.
- [ ] **Step 2: `DipyAtlasSLR` failing tests** — SLR produces `tractogram_atlas` + `atlas2native`; `atlas2native` composed with the SLR maps a streamline back to native within tolerance. Bundle addressed by explicit name; assert `IF0F_R.trk` is never selected. Run → fail → implement → pass.
- [ ] **Step 3: atlas-fetch lock failing test** — two concurrent fetches against an empty temp `DIPY_HOME` result in exactly one download and no corruption (use a lock file; simulate concurrency); offline → readable error; partial dir removed on retry. Run → fail → implement → pass.
- [ ] **Step 4: `black`; commit** (`feat: add DipyTracking (PFT/CMC/WM-seed/.trx), DipyAtlasSLR and locked atlas fetch`). Disclaimers per §9.

---

### Task 8: `dipy_dti_preproc_workflow` + `MainWorkflow` branch (Sonnet 5)

**Files:**
- Create: `swane/nipype_pipeline/workflows/dipy_dti_preproc_workflow.py`
- Modify: `swane/nipype_pipeline/MainWorkflow.py:981` (`launch_dti_analysis` branch)
- Test: `swane/tests/nipype_pipeline/workflows/test_dipy_dti_wiring.py`

**Interfaces:**
- Consumes: every node from Tasks 3–7 and the `tractography_engine`/new prefs from Task 2.
- Produces the factory:
```python
def dipy_dti_preproc_workflow(
    name: str,
    dti_dir: str,
    config: SectionProxy,
    synth_config: SectionProxy,
    base_dir: str = "/",
    deskull_modality: DeskullModality = DeskullModality.NODIF,
    max_cpu: int = 0,
    test_run: bool = False,
) -> CustomWorkflow: ...
```
**No `multicore_node_limit` parameter** (HARD_CAP only). `inputnode` fields `reference_brain`, `reference` (matching the FSL factory boundary). `outputnode` fields: `FA`, `tractogram`, `tractogram_atlas`, `atlas2native` — the last three named **exactly** for Phase 2.

**Graph** (spec §5): shared head duplicated from `dti_preproc_workflow.py:137-173` — `CustomDcm2niix` (`dipy_conv`) → `ForceOrient` (`dipy_reOrient`) → `ExtractVolumes` b0 (`dipy_nodif`) → `get_deskull_node` (`dipy_deskull`, `deskull_modality=NODIF`) — then `DipyDenoise → DipyMotionCorrection → DwiBiasCorrection → DipyTensorFit → FA → apply_registration_node → outputnode.FA`; `DipyCsdFit → DipyTracking`; `DipyAtlasSLR` once. Side branch `DipyTissueClassifier` on the T1 `reference_brain` → 3 PVE → `apply_registration_node` ref→diff → into tracking. Every node declares real `n_procs` (`max_cpu` where parallel, else 1) and its measured `_mem_gb` (placeholder pending Task 11, but each node MUST carry an explicit `_mem_gb`). Each node carries the §9 disclaimers.

- [ ] **Step 1: Failing wiring test** — build the workflow with a synthetic config; assert node presence, the four `outputnode` fields, WM-mask (not whole-brain) seeding wiring into tracking, PVE maps reaching both CMC and tracking, and that **no FSL interface** appears in the graph (`assert not any FSL iface`). Mirror the `_iface`/`_incoming`/`_node_by_name` helpers from `test_dti_matrix.py`.
- [ ] **Step 2: Run to verify it fails.**
- [ ] **Step 3: Implement the factory**, then the `MainWorkflow.launch_dti_analysis` branch: read `TractographyEngine` from `self.global_config[GlobalPrefCategoryList.SYNTH]` (`getenum_safe`), and when `DIPY_RECOBUNDLES` build `dipy_dti_preproc_workflow` (no `multicore_node_limit`), else the existing `dti_preproc_workflow`. Sink `FA` as today; sink `tractogram`/`tractogram_atlas`/`atlas2native` to `<Result_DIR>/dti/` (result filenames are Phase-2 contracts — Phase 2 wires the per-tract `.trk`; Phase 1 sinks the global tractogram outputs only). Keep the FSL branch's code path unchanged.
- [ ] **Step 4: Run to verify it passes.**
- [ ] **Step 5: `black`; commit** (`feat: add dipy_dti_preproc_workflow and branch launch_dti_analysis on the engine`).

---

### Task 9: Matrix snapshots for the dipy workflow (Sonnet 5)

**Files:** Create `swane/tests/nipype_pipeline/matrix/test_dipy_dti_matrix.py` and `snapshots/dipy_dti_preproc/`.

**Interfaces:** Consumes the Task 8 factory. Produces new golden snapshots under a **new** subdir; touches no existing snapshot.

- [ ] **Step 1: Write the snapshot test** mirroring `test_dti_matrix.py` structure (`graph_snapshot` fixture, `config_echo`, `SUBDIR="dipy_dti_preproc"`). Scenarios covering the engine's axes: tractography on/off, and any HARD_CAP thread axis. Set `synth["tractography_engine"] = TractographyEngine.DIPY_RECOBUNDLES.name`.
- [ ] **Step 2: Run** — expected: snapshot-missing failures for the new subdir only.
```bash
/media/Dati/venv/bin/python -m pytest swane/tests/nipype_pipeline/matrix/test_dipy_dti_matrix.py -v
```
- [ ] **Step 3: Generate snapshots** `SWANE_SNAPSHOT_UPDATE=1 … test_dipy_dti_matrix.py`, then **review the diff by eye**.
- [ ] **Step 4: Prove FSL snapshots untouched:**
```bash
/media/Dati/venv/bin/python -m pytest swane/tests/nipype_pipeline/matrix -v
git status --short swane/tests/nipype_pipeline/matrix/snapshots/
```
Expected: all pass; `git status` shows **only** the new `dipy_dti_preproc/` files added, nothing under `dti_preproc/` (or any other) modified.
- [ ] **Step 5: `black`; commit** (`test: add dipy_dti_preproc matrix snapshots`).

---

### Task 10: Per-engine gating UI/config test sweep (Sonnet 5, foldable into Task 2)

**Files:** `swane/tests/config/test_tractography_engine_gating.py` (extend Task 2's).

- [ ] Assert, through the live gating evaluator, that on `DIPY_RECOBUNDLES` the greyed set is exactly `{atr,str,cbd,cbp,cbt,tractography_threshold,track_procs,old_eddy_correct}` and the active-new set is `{cingulum,seed_density,max_angle,step_size}`; on `FSL_XTRACT` the inverse. Run → pass → commit. (If Task 2's test already covers the full table, mark this done and note it.)

---

### Task 11: Oracle runs, isolated `_mem_gb`, FSL comparison (Opus 4.8) — the gate to Phase 2

**Not committed to the repo** beyond aggregate numbers. All data stays under `~/test_swane/dipy_test/`.

- [ ] **Run the dipy workflow end-to-end on subj1 (15 dir) and subj2 (64 dir).** subj2 has never completed (old probe died in MP-PCA); with `nlmeans` it must finish — that is part of the point.
- [ ] **Measure per-node `_mem_gb` in isolation** — nipype runs each node in its own process, so chained `ru_maxrss` high-water marks are not usable; measure each node alone. Write the measured `_mem_gb` back into `dipy_dti_preproc_workflow.py`.
- [ ] **Streamline-order reproducibility** — two runs at equal `random_seed`, trajectories identical even if bytes differ.
- [ ] **CST + AF comparison against the FSL branch** on both subjects, via a **throwaway local RecoBundles probe** under `~/test_swane/` (never committed, not the Phase 2 node). Extract CST and AF from the Phase 1 tractogram ad hoc and compare to the FSL result. Do **not** grow Phase 1 into Phase 2 to satisfy this.
- [ ] **Surface the numbers to the user; do not decide the consequence.** If the comparison is poor, whether the default engine should depend on direction count is the user's call (spec "Accepted risk").
- [ ] Record aggregate timings/memory/streamline-count/direction-count in the spec's Measurements section (numbers only — never a path under `test_swane`, never an imaging file).

---

## Self-Review (run before handing off)

**Spec coverage** — mapped: §1 engine selection → Task 2; §2 gating + no-MP-PCA + `old_eddy_correct` unchanged → Task 2; §4 two-parallel-pairs → Tasks 8–9; §5 pipeline nodes + order + adaptive lmax → Tasks 3–8; §6 SLR-once → Task 7 (`DipyAtlasSLR`); §8 deps/atlas/licence/fetch-lock → Tasks 1, 7; §9 disclaimers → every node task; §10 HARD_CAP/thread-pin/`_mem_gb` → every node + Task 8 + Task 11; Validation (motion oracle, denoise contract, reproducibility, matrix, gating) → Tasks 3–9; Measurements/gate → Task 11. **Out of scope, deliberately deferred:** `DipyRecoBundles`, `dipy_bundle_workflow`, fornix split, `SlicerDMRI`, the `.trk` per-tract result contract, phantom v9 — all Phase 2/3.

**Placeholder scan** — the one deliberate deferral is exact dipy call signatures, each flagged "confirm against installed dipy 1.12.0" because inventing external-tool behaviour is forbidden; and `_mem_gb` values, filled by Task 11. Neither is a hidden TODO.

**Type/name consistency** — node output field names shared across tasks: `DipyCsdFit` output (`shm_coeff`/`peaks`) ↔ `DipyTracking` input must match (flagged in Tasks 6 & 7); `seed_density`/`max_angle`/`step_size` exist both as Task 2 prefs and Task 7 traits (flagged to keep in sync); the three Phase-2 outputs (`tractogram`, `tractogram_atlas`, `atlas2native`) named identically in Tasks 7, 8, 9.

---

## Report-back contract (Phase 1 → global orchestrator)

1. Actual output of the new node/workflow tests **and** the full `swane/tests/nipype_pipeline/matrix` suite.
2. Proof the FSL snapshots are untouched — `git status --short` over `snapshots/`, with Phase 0's already-committed state the baseline (no pending snapshot delta expected outside the new `dipy_dti_preproc/`).
3. The measured table: per-node isolated `_mem_gb`, subj1 + subj2 end-to-end timings, streamline counts, cores actually used per node.
4. The CST/AF comparison against FSL, with numbers, on both subjects.
5. Contracts touched, deviations from this plan, and what was deliberately not done.
6. macOS status, stated plainly — do not imply coverage not held.

A phase reported "done" without actual test output and actual numbers is not verifiable and will be sent back.
