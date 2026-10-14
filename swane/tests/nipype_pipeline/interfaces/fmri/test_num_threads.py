"""Thread budget of the fMRI Python interfaces.

Every interface whose numeric work runs through BLAS/OpenMP exposes a
``num_threads`` input (nohash, like the dipy interfaces) and runs that work
inside ``threadpoolctl.threadpool_limits(limits=num_threads)``; an undefined
``num_threads`` means 1, which is also what Nipype reserves for the node.
Interfaces doing only single-threaded ndimage/IO work have no such input.
"""

import pytest
import threadpoolctl
from nipype.interfaces.base import traits

from swane.nipype_pipeline.interfaces.fmri.NilearnFirstLevel import (
    NilearnFirstLevel,
)
from swane.nipype_pipeline.interfaces.fmri.NilearnSmooth import NilearnSmooth

THREADED = [
    NilearnFirstLevel,
]

SINGLE_THREADED = [
    NilearnSmooth,
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


@pytest.mark.parametrize("num_threads, expected", [(2, [2]), (None, [1])])
def test_threadpool_limit_applied(monkeypatch, num_threads, expected):
    """The BLAS pools seen by the numeric code are capped at num_threads."""
    if not _blas_threads():
        pytest.skip("no BLAS library loaded by numpy")
    seen = []

    def spy(self, runtime):
        seen.append(_blas_threads())
        return runtime

    monkeypatch.setattr(NilearnFirstLevel, "_run_numeric", spy)
    interface = NilearnFirstLevel()
    if num_threads is not None:
        interface.inputs.num_threads = num_threads
    before = _blas_threads()
    interface._run_interface(runtime=None)
    assert seen == [expected]
    # The limit is lifted when the interface returns.
    assert _blas_threads() == before
