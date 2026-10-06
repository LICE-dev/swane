"""Tests for the RAM estimators of the Python resting-state fMRI nodes.

These nodes load whole 4D series as float64 (plus masked copies), so their
peak RSS scales with the number of 4D elements (voxels x volumes), not with the
spatial voxel count the base ``RamEstimator`` uses. The ICA nodes add a term
per mask voxel per component (per run for ICASSO).

The conservative-bound guards pin peaks measured with ``/usr/bin/time -f %M``
on synthetic float32 series (smoothed Gaussian noise inside an ellipsoid mask,
3 BLAS threads): lowering a coefficient below what covers them must fail.
"""

import numpy as np
import nibabel as nib
import pytest

from swane.nipype_pipeline.interfaces.fmri.ClusterExtentMC import ClusterExtentMC
from swane.nipype_pipeline.interfaces.fmri.DualRegressionZStat import (
    DualRegressionZStat,
)
from swane.nipype_pipeline.interfaces.fmri.FastIcaIcasso import FastIcaIcasso
from swane.nipype_pipeline.interfaces.fmri.NilearnAutoDim import NilearnAutoDim
from swane.nipype_pipeline.interfaces.fmri.NilearnCanICA import NilearnCanICA
from swane.nipype_pipeline.interfaces.fmri.NuisanceRegression import (
    NuisanceRegression,
)
from swane.nipype_pipeline.interfaces.ram_estimators import (
    ClusterExtentMCRamEstimator,
    DualRegressionRamEstimator,
    FastIcaIcassoRamEstimator,
    NilearnAutoDimRamEstimator,
    NilearnCanICARamEstimator,
    NuisanceRegressionRamEstimator,
)
from swane.utils.ResourceManager import ResourceManager

SMALL = (64, 64, 40, 250)
LARGE = (80, 80, 48, 300)
# Mask voxel counts of the measured series (tight, dilated).
MASKS = {SMALL: (44088, 55488), LARGE: (83600, 101128)}

# Measured peak RSS (GiB): (node, shape, n_components) -> peak.
ORACLE_PEAKS = {
    ("auto_dim", SMALL, None): 1.215,
    ("auto_dim", LARGE, None): 2.592,
    ("dual_reg", SMALL, 30): 0.650,
    ("dual_reg", LARGE, 30): 1.177,
    ("fastica", SMALL, 30): 1.079,
    ("fastica", SMALL, 120): 2.570,
    ("fastica", LARGE, 30): 2.012,
    ("nuisance", SMALL, None): 1.407,
    ("nuisance", LARGE, None): 2.905,
    ("cluster_extent", SMALL, None): 0.436,
    ("cluster_extent", LARGE, None): 0.816,
    ("canica", SMALL, 30): 0.715,
    ("canica", SMALL, 120): 1.022,
    ("canica", LARGE, 30): 1.384,
}


def _image(tmp_path, name, shape, n_set=None):
    """Zero uint8 image of ``shape`` (only the header matters to the
    estimators, except for masks, whose first ``n_set`` voxels are set)."""
    data = np.zeros(shape, dtype=np.uint8)
    if n_set is not None:
        data.reshape(-1)[:n_set] = 1
    path = str(tmp_path / ("%s.nii.gz" % name))
    nib.save(nib.Nifti1Image(data, np.eye(4)), path)
    return path


def _inputs(tmp_path, node, shape, k):
    tight, dil = MASKS.get(tuple(shape), (8, 8))
    space = tuple(shape[:3])
    series = _image(tmp_path, "series", shape)
    if node == "auto_dim":
        iface = NilearnAutoDim()
        iface.inputs.in_file = series
        iface.inputs.mask_file = _image(tmp_path, "tight", space, tight)
    elif node == "dual_reg":
        iface = DualRegressionZStat()
        iface.inputs.preproc_file = series
        iface.inputs.mask_file = _image(tmp_path, "dil", space, dil)
        iface.inputs.components_file = _image(tmp_path, "comp", space + (k,))
    elif node == "fastica":
        iface = FastIcaIcasso()
        iface.inputs.in_file = series
        iface.inputs.mask_file = _image(tmp_path, "dil", space, dil)
        iface.inputs.n_components = k
    elif node == "nuisance":
        iface = NuisanceRegression()
        iface.inputs.in_file = series
        iface.inputs.twin_file = series
        mask = _image(tmp_path, "dil", space, dil)
        iface.inputs.mask_file = mask
        iface.inputs.wm_roi_file = mask
        iface.inputs.csf_roi_file = mask
    elif node == "cluster_extent":
        iface = ClusterExtentMC()
        iface.inputs.residual_file = series
        iface.inputs.mask_file = _image(tmp_path, "dil", space, dil)
    elif node == "canica":
        iface = NilearnCanICA()
        iface.inputs.preproc_file = series
        iface.inputs.mask_file = _image(tmp_path, "tight", space, tight)
        iface.inputs.n_components = k
    return iface.inputs


ESTIMATORS = {
    "auto_dim": NilearnAutoDimRamEstimator,
    "dual_reg": DualRegressionRamEstimator,
    "fastica": FastIcaIcassoRamEstimator,
    "nuisance": NuisanceRegressionRamEstimator,
    "cluster_extent": ClusterExtentMCRamEstimator,
    "canica": NilearnCanICARamEstimator,
}
K_DEFAULT = {"dual_reg": 30, "fastica": 30, "canica": 30}


@pytest.mark.parametrize("node", sorted(ESTIMATORS))
def test_estimate_counts_volumes(tmp_path, node):
    """Doubling the number of volumes raises the estimate: the time axis is
    counted, unlike the spatial-only base estimator."""
    est = ESTIMATORS[node]()
    k = K_DEFAULT.get(node)
    short = tmp_path / "short"
    long_ = tmp_path / "long"
    short.mkdir()
    long_.mkdir()
    shape = (64, 64, 40)
    few, _ = est(_inputs(short, node, shape + (100,), k))
    many, _ = est(_inputs(long_, node, shape + (200,), k))
    assert many > few


@pytest.mark.parametrize("node", sorted(ESTIMATORS))
def test_estimator_is_not_clamped_down(node):
    est = ESTIMATORS[node]()
    assert est.max_gb is None


@pytest.mark.parametrize("node", sorted(ESTIMATORS))
def test_static_fallback_fits_the_engine_minimum(node):
    """The static reservation must not exceed the RAM required to select the
    engine, or Nipype's pre-run check would reject the workflow."""
    fallback = ESTIMATORS[node].STATIC_FALLBACK_GB
    assert 0 < fallback <= min(ResourceManager.NILEARN_FMRI_RAM_REQUIREMENT.values())


@pytest.mark.parametrize("key, measured", ORACLE_PEAKS.items())
def test_estimate_exceeds_the_measured_peak(tmp_path, key, measured):
    node, shape, k = key
    mem_gb, debug = ESTIMATORS[node]()(_inputs(tmp_path, node, shape, k))
    assert mem_gb > measured, debug


def test_fastica_estimate_grows_with_components_and_runs(tmp_path):
    est = FastIcaIcassoRamEstimator()
    inputs = _inputs(tmp_path, "fastica", SMALL, 30)
    base, _ = est(inputs)
    inputs.n_components = 60
    more_k, _ = est(inputs)
    inputs.n_runs = 20
    more_runs, _ = est(inputs)
    assert base < more_k < more_runs
