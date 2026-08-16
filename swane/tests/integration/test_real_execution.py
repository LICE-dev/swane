"""Real-execution smoke tests on out-of-tree de-identified data.

These exercise swane's *actual* code paths end to end — dcm2niix conversion
(``CustomDcm2niix``), the structural reference pipeline (``ref_workflow``) and
DTI preprocessing (``dti_preproc_workflow``) — against real DICOM series, and
validate the produced NIfTI geometry, the DTI ``bval``/``bvec`` and the FSL /
SimpleITK outputs. Unlike the ``nipype_pipeline/matrix`` construction snapshots,
here the tools really run.

They are opt-in and self-skipping, so the light suite and tool-less CI stay green:

* the neuroimaging tools must be present (``requires_dcm2niix`` / ``requires_fsl``);
* the DICOM data is supplied **out of tree** via the ``SWANE_TEST_DICOM_DIR``
  environment variable — a folder holding ``t13d/``, ``flair3d/`` and ``dti/``
  subseries. Real DICOM is never committed (see ``AGENTS.md``); any series that
  is absent/empty simply skips its test;
* the heavy structural + DTI execution additionally needs ``--run-heavy``.

Run it in a suitable environment (e.g. WSL with FSL/FreeSurfer)::

    SWANE_TEST_DICOM_DIR=/path/to/dicom \
        pytest swane/tests/integration/test_real_execution.py --run-heavy
"""

import glob
import os

import numpy as np
import nibabel as nib
import pytest
from nipype import Node

from swane.config.ConfigManager import ConfigManager
from swane.config.config_enums import GlobalPrefCategoryList, CoreLimit
from swane.utils.DataInputList import DataInputList
from swane.nipype_pipeline.nodes.CustomDcm2niix import CustomDcm2niix
from swane.nipype_pipeline.workflows.ref_workflow import ref_workflow
from swane.nipype_pipeline.workflows.dti_preproc_workflow import dti_preproc_workflow

DATA_ENV = "SWANE_TEST_DICOM_DIR"


def _series_dir(name):
    """Return the DICOM folder for ``name`` or skip if data is unavailable."""
    root = os.environ.get(DATA_ENV)
    if not root or not os.path.isdir(root):
        pytest.skip("set %s to a folder with t13d/flair3d/dti subseries" % DATA_ENV)
    path = os.path.join(root, name)
    if not os.path.isdir(path) or not os.listdir(path):
        pytest.skip("series %r missing or empty under %s" % (name, DATA_ENV))
    return path


def _find(base, filename):
    hits = glob.glob(os.path.join(base, "**", filename), recursive=True)
    assert hits, "expected %s under %s" % (filename, base)
    return sorted(hits, key=len)[0]


@pytest.fixture
def configs(tmp_path, monkeypatch):
    """A (subject, global) ConfigManager pair with the Synth backend disabled."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    subject = ConfigManager(subject_folder=str(tmp_path / "subject"))
    (tmp_path / "global").mkdir()
    glob_cfg = ConfigManager(global_base_folder=str(tmp_path / "global"))
    glob_cfg[GlobalPrefCategoryList.SYNTH]["strip"] = "false"
    glob_cfg[GlobalPrefCategoryList.SYNTH]["morph"] = "false"
    return subject, glob_cfg


def _convert(series_dir, out_name, tmp_path, *, request_dti=False):
    node = Node(CustomDcm2niix(), name=out_name, base_dir=str(tmp_path / out_name))
    node.inputs.source_dir = series_dir
    node.inputs.out_filename = out_name
    node.inputs.bids_format = False
    node.inputs.name_conflicts = 1
    node.inputs.merge_imgs = 2
    node.inputs.request_dti = request_dti
    return node.run()


@pytest.mark.requires_dcm2niix
class TestConversion:
    """Stage A: dcm2niix conversion of the real series (fast)."""

    @pytest.mark.parametrize("series", ["t13d", "flair3d"])
    def test_anatomical_is_single_volume_3d(self, series, tmp_path):
        res = _convert(_series_dir(series), series, tmp_path)
        nii = res.outputs.converted_files
        nii = nii[0] if isinstance(nii, list) else nii
        img = nib.load(nii)
        assert img.ndim == 3, "%s should convert to a single 3D volume" % series
        assert all(d > 1 for d in img.shape), "degenerate shape %s" % (img.shape,)

    def test_dti_is_4d_with_bvals_bvecs(self, tmp_path):
        res = _convert(_series_dir("dti"), "dti", tmp_path, request_dti=True)
        nii = res.outputs.converted_files
        nii = nii[0] if isinstance(nii, list) else nii
        bvals = res.outputs.bvals
        bvecs = res.outputs.bvecs
        bvals = bvals[0] if isinstance(bvals, list) else bvals
        bvecs = bvecs[0] if isinstance(bvecs, list) else bvecs

        img = nib.load(nii)
        assert img.ndim == 4, "DTI should convert to a 4D volume"
        n_vols = img.shape[3]

        bv = np.atleast_1d(np.loadtxt(bvals))
        vec = np.loadtxt(bvecs)
        assert bv.size == n_vols, "one b-value per volume (%d vs %d)" % (
            bv.size,
            n_vols,
        )
        assert vec.shape == (3, n_vols), "bvec should be 3x%d, got %s" % (
            n_vols,
            vec.shape,
        )
        assert (bv < 50).sum() >= 1, "expected at least one b0 volume"
        assert (bv >= 50).sum() >= 6, "expected at least 6 diffusion directions"


@pytest.mark.heavy
@pytest.mark.requires_fsl
@pytest.mark.requires_dcm2niix
class TestStructuralAndDtiExecution:
    """Stage B: run the real structural + DTI workflows (slow: BET/N4/eddy/dtifit)."""

    def test_reference_and_fa_are_produced(self, configs, tmp_path):
        subject, glob_cfg = configs
        synth = glob_cfg[GlobalPrefCategoryList.SYNTH]
        work = str(tmp_path / "wf")

        # Structural reference: conversion -> crop -> BET -> N4 -> masked brain.
        ref_wf = ref_workflow(
            "ref",
            dicom_dir=_series_dir("t13d"),
            config=subject[DataInputList.T13D],
            synth_config=synth,
            base_dir=work,
        )
        ref_wf.run(plugin="Linear")
        reference = _find(work, "ref.nii.gz")
        reference_brain = _find(work, "ref_brain.nii.gz")

        brain = np.asanyarray(nib.load(reference_brain).dataobj)
        assert (brain > 0).sum() > 100000, "skull-stripped brain looks empty"
        # Skull stripping must remove a substantial part of the full FOV.
        full = np.asanyarray(nib.load(reference).dataobj)
        assert (brain > 0).sum() < (full != 0).sum(), "BET removed nothing"

        # DTI preprocessing (CPU eddy for portability) registered to the reference.
        section = subject[DataInputList.DTI]
        section["cuda"] = "false"
        section["old_eddy_correct"] = "false"
        section["tractography"] = "false"
        dti_wf = dti_preproc_workflow(
            "dti",
            dti_dir=_series_dir("dti"),
            config=section,
            synth_config=synth,
            base_dir=work,
            max_cpu=4,
            multicore_node_limit=CoreLimit.SOFT_CAP,
        )
        inputnode = dti_wf.get_node("inputnode")
        inputnode.inputs.reference = reference
        inputnode.inputs.reference_brain = reference_brain
        dti_wf.run(plugin="Linear")

        fa = _find(work, "r-FA.nii.gz")
        fa_data = np.asanyarray(nib.load(fa).dataobj).astype(float)
        finite = fa_data[np.isfinite(fa_data)]
        assert finite.min() >= 0.0, "FA must be non-negative"
        # Allow a small interpolation overshoot above 1 from resampling to reference.
        assert finite.max() <= 1.3, "FA out of range (max %.3f)" % finite.max()
        assert (fa_data > 0.2).sum() > 10000, "no white-matter-like FA voxels found"
