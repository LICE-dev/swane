"""Thread budget of the fMRI Python interfaces.

Every interface whose numeric work runs through BLAS/OpenMP exposes a
``num_threads`` input (nohash, like the dipy interfaces) and runs that work
inside ``threadpoolctl.threadpool_limits(limits=num_threads)``; an undefined
``num_threads`` means 1, which is also what Nipype reserves for the node.
Interfaces doing only single-threaded ndimage/IO work have no such input.
"""

import numpy as np
import nibabel as nib
import pytest
import threadpoolctl
from nipype.interfaces.base import traits

from swane.nipype_pipeline.interfaces.fmri import NilearnAutoDim as auto_dim_module
from swane.nipype_pipeline.interfaces.fmri.ClusterExtentMC import ClusterExtentMC
from swane.nipype_pipeline.interfaces.fmri.DualRegressionZStat import (
    DualRegressionZStat,
)
from swane.nipype_pipeline.interfaces.fmri.FastIcaIcasso import FastIcaIcasso
from swane.nipype_pipeline.interfaces.fmri.GgmThreshold import GgmThreshold
from swane.nipype_pipeline.interfaces.fmri.IcaDenoise import IcaDenoise
from swane.nipype_pipeline.interfaces.fmri.MaskedResampleCombine import (
    MaskedResampleCombine,
)
from swane.nipype_pipeline.interfaces.fmri.NilearnAutoDim import NilearnAutoDim
from swane.nipype_pipeline.interfaces.fmri.NilearnCanICA import NilearnCanICA
from swane.nipype_pipeline.interfaces.fmri.NilearnFirstLevel import (
    NilearnFirstLevel,
)
from swane.nipype_pipeline.interfaces.fmri.NilearnSmooth import NilearnSmooth
from swane.nipype_pipeline.interfaces.fmri.NuisanceRegression import (
    NuisanceRegression,
)
from swane.nipype_pipeline.interfaces.fmri.SpatialZThreshold import (
    SpatialZThreshold,
)

THREADED = [
    NilearnAutoDim,
    NilearnCanICA,
    DualRegressionZStat,
    GgmThreshold,
    IcaDenoise,
    NuisanceRegression,
    FastIcaIcasso,
    ClusterExtentMC,
    NilearnFirstLevel,
]

SINGLE_THREADED = [
    NilearnSmooth,
    SpatialZThreshold,
    MaskedResampleCombine,
]


@pytest.mark.parametrize("cls", THREADED, ids=lambda c: c.__name__)
def test_num_threads_input(cls):
    trait = cls.input_spec().trait("num_threads")
    assert trait is not None
    assert isinstance(trait.trait_type, traits.Int)
    # Like the dipy interfaces: the thread count never invalidates the cache.
    assert trait.nohash


@pytest.mark.parametrize("cls", SINGLE_THREADED, ids=lambda c: c.__name__)
def test_no_num_threads_input(cls):
    # class_traits(), not input_spec().trait(): a hasattr(inputs, "num_threads")
    # check (Nipype's Node makes one) caches a dynamic trait that the latter
    # would then report for every later instance.
    assert "num_threads" not in cls.input_spec.class_traits()


def _blas_threads():
    return sorted(
        {
            info["num_threads"]
            for info in threadpoolctl.threadpool_info()
            if info["user_api"] == "blas"
        }
    )


def _auto_dim_inputs(tmp_path):
    data = np.random.RandomState(0).randn(4, 4, 4, 30)
    in_file = tmp_path / "in.nii.gz"
    mask_file = tmp_path / "mask.nii.gz"
    nib.save(nib.Nifti1Image(data, np.eye(4)), str(in_file))
    nib.save(nib.Nifti1Image(np.ones((4, 4, 4)), np.eye(4)), str(mask_file))
    return str(in_file), str(mask_file)


@pytest.mark.parametrize("num_threads, expected", [(2, [2]), (None, [1])])
def test_threadpool_limit_applied(tmp_path, monkeypatch, num_threads, expected):
    """The BLAS pools seen by the numeric code are capped at num_threads."""
    monkeypatch.chdir(tmp_path)
    if not _blas_threads():
        pytest.skip("no BLAS library loaded by numpy")
    seen = []
    real = auto_dim_module.estimate_dim_mdl

    def spy(*args, **kwargs):
        seen.append(_blas_threads())
        return real(*args, **kwargs)

    monkeypatch.setattr(auto_dim_module, "estimate_dim_mdl", spy)
    in_file, mask_file = _auto_dim_inputs(tmp_path)
    interface = NilearnAutoDim(in_file=in_file, mask_file=mask_file)
    if num_threads is not None:
        interface.inputs.num_threads = num_threads
    before = _blas_threads()
    interface.run()
    assert seen == [expected]
    # The limit is lifted when the interface returns.
    assert _blas_threads() == before


def test_canica_single_job(tmp_path, monkeypatch):
    """CanICA runs its restarts in-process (n_jobs=1): the only parallelism is
    the BLAS pool capped at num_threads."""
    monkeypatch.chdir(tmp_path)
    import nilearn.decomposition

    captured = {}

    class Stop(Exception):
        pass

    class FakeCanICA:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def fit(self, _):
            captured["blas"] = _blas_threads()
            raise Stop

    monkeypatch.setattr(nilearn.decomposition, "CanICA", FakeCanICA)
    in_file, mask_file = _auto_dim_inputs(tmp_path)
    interface = NilearnCanICA(
        preproc_file=in_file, mask_file=mask_file, n_components=2, num_threads=2
    )
    with pytest.raises(Stop):
        interface.run()
    assert captured["n_jobs"] == 1
    if _blas_threads():
        assert captured["blas"] == [2]
