# antspynet brain extraction as the default deskull engine

**Date:** 2026-08-31
**Branch:** `claude/antspynet-deskull` (off `dev`)
**Status:** design approved, pending spec review

## Problem and goal

SWANe currently skull-strips MR images with one of two backends, selected by a
single boolean preference `strip` ("Use SynthStrip for brain extraction"):

- FSL **BET** (`strip = false`, the default), or
- FreeSurfer **SynthStrip** (`strip = true`).

Both are dispatched by `get_deskull_node()` in
[`swane/nipype_pipeline/nodes/utils.py`](../../../swane/nipype_pipeline/nodes/utils.py)
via a `use_synth: bool` argument.

We want to add **antspynet** (ANTsPyNet deep-learning `brain_extraction`) as a
third engine and make it the **default**. Engine selection should mirror the
existing `RegistrationEngine` pattern (enum preference, dependency gate, license
consent, home-window row). Because antspynet's `brain_extraction` chooses a
network by **modality**, each deskulled input must be assigned a modality, and
`linear_reg_workflow` (which runs on several different contrasts) must receive
its modality from the caller.

This design does **not** touch the CT workflows: `venous_ct_workflow` and
`seeg_ct_workflow` deskull with `SegmentEndocranium` (3D Slicer), not BET, so
they are out of scope.

## Non-goals

- No change to registration engines or `RegistrationEngine`.
- No GPU/CUDA wiring for antspynet/tensorflow (CPU by default; revisit later).
- No change to the CT endocranium segmentation.
- The new node's RAM reservation is fixed at **5 GB** for now (revisit later).

## Key facts established from the live code and environment

- `get_deskull_node()` is called from exactly four MR workflows:
  - [`ref_workflow`](../../../swane/nipype_pipeline/workflows/ref_workflow.py) — T1 reference (`synth_exclude_csf=True`).
  - [`linear_reg_workflow`](../../../swane/nipype_pipeline/workflows/linear_reg_workflow.py) — used by MainWorkflow for FLAIR3D, FLAIR2D, T2_COR, MDC.
  - [`dti_preproc_workflow`](../../../swane/nipype_pipeline/workflows/dti_preproc_workflow.py) — nodif b0 (`bet_robust`, `bet_threshold`).
  - [`venous_mr_workflow`](../../../swane/nipype_pipeline/workflows/venous_mr_workflow.py) — phase-contrast anatomic phase (`bet_surfaces=True`, inskull mask).
- [`fMRI_preproc_workflow`](../../../swane/nipype_pipeline/workflows/fMRI_preproc_workflow.py)
  calls `BET` **directly** (`meanfuncmask`, mask-only, `frac=0.3`,
  `no_output=True`) rather than through `get_deskull_node()`. This workflow
  already excludes Synth registration engines (`resolve_registration_engine`
  then `SYNTH -> FSL`), and we will exclude SynthStrip from its deskull the same
  way.
- The antspyx scaffolding to mirror already exists on `dev`: `RegistrationEngine`
  (default `ANTS`), `accepted_license_antspyx`, `LicenseReference.ANTSPYX`,
  `DependencyManager.is_antspyx()`/`check_antspyx()`, the antspyx home row, and
  the lazy-import antspyx node `AntsN4BiasFieldCorrection` (`BaseInterface`,
  `import ants` inside `_run_interface`).
- In the dev environment, **antspyx 0.6.3 is installed but antspynet and
  tensorflow are not**. antspynet pulls in tensorflow (~1 GB) and downloads
  pretrained model weights from the network on first use.
- antspynet's `brain_extraction(image, modality=...)` returns a **probability
  image**, not a binary mask; the node must threshold it and apply it.

## Design

### 1. New Nipype node `AntsPyNetBrainExtraction`

New file `swane/nipype_pipeline/nodes/AntsPyNetBrainExtraction.py`, modeled on
`AntsN4BiasFieldCorrection`:

- `BaseInterface` subclass with the "extends a Nipype class" source disclaimers
  (it extends Nipype base classes; it is **not** derived from antspynet source).
- Lazy `import ants` and `import antspynet` inside `_run_interface` so importing
  the module never pulls tensorflow.
- **Input spec:**
  - `in_file` — `File(exists=True, mandatory=True)`.
  - `modality` — `traits.Str(mandatory=True)`, the antspynet key (e.g. `"t1"`,
    `"flair"`, `"t2"`, `"bold"`; nodif/venous values resolved by the oracle).
  - `out_file` — `File`, the skull-stripped brain (default derived from
    `in_file` like `AntsN4BiasFieldCorrection._gen_outfilename`).
  - `mask_file` — `File`, the binary brain mask (written when set).
  - `num_threads` — `traits.Int(nohash=True)`, exported as
    `ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS` around the call (same threads pattern
    as `AntsN4BiasFieldCorrection`).
  - `intracranial` — `traits.Bool(False, usedefault=True)`: when True, expand
    the mask toward the inner skull table to approximate the intracranial
    (inskull) volume. **Included only if the oracle shows a plain brain model
    cannot cover the intracranial space for the venous anatomic phase**;
    otherwise this trait is dropped from the design.
- **Run logic:**
  1. `img = ants.image_read(in_file, pixeltype="float")`.
  2. `prob = antspynet.brain_extraction(img, modality=self.inputs.modality)`.
  3. `mask = ants.threshold_image(prob, 0.5, 1.0, 1, 0)` (binary mask; exact
     antspynet return shape and threshold helper verified against the pinned
     version at implementation time).
  4. If `intracranial`: morphological fill/closing (implementation chosen during
     the oracle step).
  5. Write `mask_file` if defined; write `out_file = img * mask`.
- **Output spec:** `out_file`, `mask_file` — same fields SynthStrip/BET expose,
  so `get_deskull_node` callers are unchanged.
- Node created with `mem_gb=5` in `get_deskull_node`.

### 2. New enums in `swane/config/config_enums.py`

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
    NODIF = "<oracle>"    # b0 EPI; value set after the local oracle
    VENOUS = "<oracle>"   # intracranial coverage; value set after the local oracle
```

`DeskullEngine` is independent of `RegistrationEngine`: a subject may use ANTs
registration with BET deskull, etc. `DeskullModality.value` is the antspynet key
consumed only by the antspynet branch; the BET and SynthStrip branches ignore
the modality entirely.

### 3. `get_deskull_node` refactor (`utils.py`)

- Replace the `use_synth: bool` parameter with `deskull_engine: DeskullEngine`.
- Add `deskull_modality: DeskullModality = None`.
- Three branches:
  - `ANTSPYNET`: build `AntsPyNetBrainExtraction`, node name suffix
    `_antspynet`, `mem_gb=5`, `modality = deskull_modality.value`, `mask_file`
    when `mask`, threads via the existing `get_tool_cpu_config` /
    `apply_tool_num_threads` helpers (ANTs-style hard reservation: no soft
    env-var path, like the ANTs registration node). For `bet_surfaces` callers
    set `inskull_out_name = "mask_file"` (mask serves as the inskull mask, as
    SynthStrip already does).
  - `SYNTHSTRIP`: the current SynthStrip branch, unchanged (node suffix
    `_synthstrip`).
  - `BET`: the current BET branch, unchanged (node suffix `_bet`).
- Add `resolve_deskull_engine(synth_config, allow_synthstrip=True)` mirroring
  `resolve_registration_engine`: reads the `deskull_engine` preference; when
  `allow_synthstrip=False` and the configured engine is `SYNTHSTRIP`, falls back
  to the base default `ANTSPYNET` (the deskull analogue of fMRI's `SYNTH -> FSL`
  fallback). `ANTSPYNET` and `BET` are honoured either way.
- Every current `get_deskull_node` caller replaces
  `use_synth=synth_config.getboolean_safe("strip")` with
  `deskull_engine=resolve_deskull_engine(synth_config)` plus its
  `deskull_modality=...`.

### 4. Per-call-site modality assignment

| Call site | Sequence | `DeskullModality` |
|---|---|---|
| `ref_workflow` | T13D | `T1` |
| `linear_reg_workflow` → `flair` / `flair2d` | FLAIR3D / FLAIR2D | `FLAIR` |
| `linear_reg_workflow` → `t2_cor` | T2_COR | `T2` (partial-coverage path skips deskull anyway) |
| `linear_reg_workflow` → `mdc` | MDC (post-contrast T1) | `T1` |
| `venous_mr_workflow` | phase-contrast anatomic | `VENOUS` (oracle-decided, intracranial coverage) |
| `dti_preproc_workflow` | nodif b0 | `NODIF` (oracle-decided) |
| `fMRI_preproc_workflow` `meanfuncmask` | mean BOLD | `BOLD` |

`linear_reg_workflow`, `ref_workflow`, `venous_mr_workflow`, and
`dti_preproc_workflow` gain a `deskull_modality: DeskullModality` parameter.
`MainWorkflow` passes the right modality at each call site (e.g. `FLAIR` for the
FLAIR calls, `T2` for `t2_cor`, `T1` for `mdc`). `ref_workflow` may hard-code
`T1` internally, but taking it as a parameter keeps the four factories uniform.

### 5. `fMRI_preproc_workflow` rewrite

Replace the direct `meanfuncmask = Node(BET(), ...)` (mask-only, `frac=0.3`,
`no_output=True`) with:

```python
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
```

and consume `meanfuncmask.mask_file` exactly as today. `get_deskull_node` does
not expose BET's `no_output`, so both branches now also write a brain `out_file`
that the workflow simply ignores (harmless); only `mask_file` is consumed
downstream. If that extra write proves undesirable, a `mask_only` flag can be
added to `get_deskull_node` as a follow-up. Synth is excluded here just as
SynthMorph is excluded from registration in this workflow.

### 6. Preferences (`swane/config/preference_list.py`)

- **Remove** the `strip` boolean entry (SYNTH category).
- **Add** `deskull_engine` in the SYNTH category:
  - `input_type=InputTypes.ENUM`, `value_enum=DeskullEngine`,
    `default=DeskullEngine.ANTSPYNET`, `label="Brain extraction engine"`.
  - `option_dependency`:
    - `ANTSPYNET -> ["is_antspynet", "antspynet brain extraction requires the antspynet package"]`
    - `SYNTHSTRIP -> ["is_freesurfer_synth", "SynthStrip requires FreeSurfer 8.1.0"]`
    - `BET` has no dependency (FSL is a hard baseline).
  - `option_pref_requirement` / `option_pref_requirement_fail_tooltip`: RAM gate
    for `ANTSPYNET` (5 GB) and `SYNTHSTRIP`
    (`ResourceManager.synth_strip_ram_requirements()`), mirroring the `engine`
    entry's structure.
- **Add** `"antspynet"` to the hidden license-version loop so
  `accepted_license_antspynet` exists (the
  `for _license_tool in ("fsl", "freesurfer", "slicer", "dcm2niix", "antspyx")`
  tuple gains `"antspynet"`).

Persisted configs that still carry `strip` are unaffected: the key is simply no
longer read, and `deskull_engine` takes its `ANTSPYNET` default. (`force_pref_reset`
already defaults true.)

### 7. Dependency, license, home window

- **`setup.py`**: add `antspynet==<pin>` and `tensorflow==<pin>` to
  `install_requires` (exact pins chosen at implementation time against a working
  antspynet/tensorflow/antspyx combination).
- **`DependencyManager`**:
  - `MIN_ANTSPYNET_VERSION` constant, kept in sync with the `setup.py` pin.
  - `check_antspynet()` → `Dependence`, and `is_antspynet()`.
    To avoid importing tensorflow at every startup, detect presence with
    `importlib.util.find_spec("antspynet")` and read the version with
    `importlib.metadata.version("antspynet")` — no heavy import in the check.
  - `self.antspynet = DependencyManager.check_antspynet()` in `__init__`.
- **`LicenseReference`**:
  - New `ANTSPYNET = "antspynet"` id, added to `TOOL_IDS`.
  - `LicenseInfo`: Apache-2.0, official URL `ANTsX/ANTsPyNet` repository
    (`online_is_official=True`), bundled license file
    `swane/licenses/antspynet_license.txt`, plus a comment noting that the
    downloaded pretrained model weights carry their own upstream terms.
  - `setup.py` `package_data` already globs `licenses/*.txt`, so the new file
    ships automatically.
- **Strings** (`swane/strings.py`): `check_dep_antspynet_*` messages mirroring
  the `check_dep_antspyx_*` set.
- **Home window** (`MainWindow.home_tab_ui`): add
  `x = self.add_home_entry(self.dependency_manager.antspynet, x)` next to the
  antspyx row.
- **Consent flow**: `tools_needing_consent` / `detected_tool_versions` /
  `version_with_license` pick up the new tool id automatically once it is in
  `TOOL_IDS` and `DependencyManager`; verify the antspynet row appears in the
  consent gate.

### 8. Pre-cached model weights

antspynet downloads pretrained weights on first use; the prerelease sweep must
not hit the network mid-workflow and must be reproducible. Add a helper
`preload_antspynet_models(modalities)` (e.g. in the prerelease harness or a small
utility module) that fetches the pretrained network for each needed modality
using antspynet's own pretrained-network download API. Invoke it from the
**prerelease** setup before running the workflows. Runtime still downloads on
demand when a weight is absent; the helper only guarantees presence for the
sweep. No production auto-download step is added in this change.

### 9. nodif and venous oracle (local, uncommitted)

A throwaway local investigation in `/home/mau/test_swane/ant_deskull/` (contains
`nodif.nii.gz`, `nodif2.nii.gz`, `anatomicavenosa.nii.gz`). Requires a local
install of antspynet + tensorflow and one-time model download.

1. **nodif** (`nodif.nii.gz`, `nodif2.nii.gz`): compare antspynet `t2`, `bold`,
   and `fa` brain extraction on the two b0 EPI volumes; pick the modality that
   best matches the brain. Result sets `DeskullModality.NODIF`.
2. **anatomicavenosa** (`anatomicavenosa.nii.gz`): determine which modality
   (optionally plus the `intracranial` morphological post-step from §1) best
   fills the whole **intracranial (inskull) space**, matching what the previous
   SynthStrip (CSF included) / BET-surfaces path produced. Result sets
   `DeskullModality.VENOUS` and decides whether the node's `intracranial` trait
   is needed.

The oracle scripts, downloaded weights, and any outputs are **never committed**
and are not referenced from tracked code. The spec placeholders
(`DeskullModality.NODIF`, `DeskullModality.VENOUS`) are the only tracked
artifacts, filled with concrete antspynet keys once the oracle resolves.

### 10. Tests, matrices, prerelease

- **Unit / light suite:**
  - `AntsPyNetBrainExtraction`: trait defaults, output filenames, and mocked
    `ants`/`antspynet` so the threshold-and-apply logic and threads handling are
    exercised without the real libraries (mirrors the N4 node tests).
  - `get_deskull_node`: dispatch for all three `DeskullEngine` values, node
    names/suffixes, modality forwarding to the antspynet branch, and the
    `allow_synthstrip=False` fallback to `ANTSPYNET`.
  - `resolve_deskull_engine`: honours `ANTSPYNET`/`BET`, and folds `SYNTHSTRIP`
    to `ANTSPYNET` only when `allow_synthstrip=False`.
  - Preference: `deskull_engine` default is `ANTSPYNET`; `strip` is gone.
  - `DependencyManager.is_antspynet()` / `check_antspynet()` (mock
    `find_spec`/`importlib.metadata`).
  - `LicenseReference` has the `ANTSPYNET` entry and it is in `TOOL_IDS`.
- **Workflow graph / matrix snapshots:** the default deskull node names flip to
  `_antspynet`, so `nipype_pipeline/matrix/` golden snapshots change; regenerate
  and review them.
- **Prerelease (`swane/tests/prerelease/`):** default now exercises antspynet;
  call `preload_antspynet_models` in setup; verify RAM gating and that the sweep
  completes against the disposable `~/test_swane/prerelease` root.

## Contracts touched

- **Preference keys:** `strip` removed; `deskull_engine` and
  `accepted_license_antspynet` added (SYNTH / hidden-license categories).
- **Enums:** `DeskullEngine`, `DeskullModality` added (config_enums).
- **Workflow factory signatures:** `linear_reg_workflow`, `ref_workflow`,
  `venous_mr_workflow`, `dti_preproc_workflow` gain `deskull_modality`;
  `get_deskull_node` swaps `use_synth` for `deskull_engine` and gains
  `deskull_modality`.
- **Node names:** deskull nodes gain an `_antspynet` variant; default-config
  graphs rename their deskull node → matrix snapshots regenerate.
- **Dependency / license / UI:** new `is_antspynet`, `LicenseReference.ANTSPYNET`,
  `TOOL_IDS` entry, antspynet home row, `check_dep_antspynet_*` strings.
- **Packaging:** `setup.py` adds `antspynet` and `tensorflow`; new bundled
  `swane/licenses/antspynet_license.txt`.

## Risks

- **Footprint:** tensorflow adds ~1 GB to every install (accepted).
- **Model download:** antspynet fetches weights from the network on first use;
  offline first runs fail until weights are cached. Mitigated for the prerelease
  sweep by `preload_antspynet_models`; production runtime download behaviour is
  unchanged from antspynet's default (accepted).
- **Startup cost:** the dependency check must not import tensorflow; using
  `find_spec` + `importlib.metadata` avoids it.
- **Version compatibility:** antspynet/tensorflow/antspyx pins must be a working
  triple; verified at implementation time.
- **Oracle-dependent constants:** `DeskullModality.NODIF` and
  `DeskullModality.VENOUS` (and the venous `intracranial` post-step) are
  placeholders until the local oracle resolves them.
