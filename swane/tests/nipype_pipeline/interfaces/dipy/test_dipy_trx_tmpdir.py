"""trx-python's temporary memmaps live in the running node's own directory.

trx creates its memmaps in ``$TRX_TMPDIR`` (``tempfile.gettempdir()`` when
unset). On a host with a tmpfs ``/tmp`` that would put a whole tractogram in RAM
outside the node reservations, so every SWANe interface touching ``.trx`` runs
with ``TRX_TMPDIR=use_working_dir`` -- whatever the caller set -- and the
previous value is restored afterwards. Synthetic streamlines only.
"""

import glob
import os
import tempfile

import numpy as np
import pytest
from nipype.interfaces.base import BaseInterface, BaseInterfaceInputSpec, TraitedSpec

from swane.nipype_pipeline.interfaces.dipy import (
    TRX_TMPDIR_VAR,
    TrxWorkingDirMixin,
    trx_tmpdir_in_working_dir,
)


class TestContextManager:
    def test_forces_working_dir_and_restores_unset(self, monkeypatch):
        monkeypatch.delenv(TRX_TMPDIR_VAR, raising=False)
        with trx_tmpdir_in_working_dir():
            assert os.environ[TRX_TMPDIR_VAR] == "use_working_dir"
        assert TRX_TMPDIR_VAR not in os.environ

    def test_overrides_a_caller_value_and_restores_it(self, monkeypatch):
        monkeypatch.setenv(TRX_TMPDIR_VAR, "/somewhere/else")
        with trx_tmpdir_in_working_dir():
            assert os.environ[TRX_TMPDIR_VAR] == "use_working_dir"
        assert os.environ[TRX_TMPDIR_VAR] == "/somewhere/else"

    def test_restores_on_error(self, monkeypatch):
        monkeypatch.delenv(TRX_TMPDIR_VAR, raising=False)
        with pytest.raises(RuntimeError):
            with trx_tmpdir_in_working_dir():
                raise RuntimeError("boom")
        assert TRX_TMPDIR_VAR not in os.environ


@pytest.mark.parametrize(
    "module, name",
    [
        ("DipyTracking", "DipyTracking"),
        ("DipyAtlasSLR", "DipyAtlasSLR"),
        ("DipyTractogramChunker", "DipyTractogramChunker"),
        ("DipyRecoBundles", "DipyRecoBundlesBuild"),
        ("DipyRecoBundles", "DipyRecoBundlesRecognize"),
        ("DipyBundleUnion", "DipyBundleUnion"),
        ("DipyBundleRecovery", "DipyBundleRecovery"),
        ("DipyBundlesToRef", "DipyBundlesToRef"),
    ],
)
def test_every_trx_interface_runs_in_its_working_dir(module, name):
    import importlib

    cls = getattr(
        importlib.import_module("swane.nipype_pipeline.interfaces.dipy." + module),
        name,
    )
    assert issubclass(cls, TrxWorkingDirMixin)
    # the mixin must wrap BaseInterface.run, so it comes first in the MRO
    mro = cls.__mro__
    assert mro.index(TrxWorkingDirMixin) < mro.index(BaseInterface)


class _TrxWriterInputSpec(BaseInterfaceInputSpec):
    pass


class _TrxWriterOutputSpec(TraitedSpec):
    pass


class _TrxWriter(TrxWorkingDirMixin, BaseInterface):
    """Streams and saves a tractogram the way DipyTracking does, recording
    where trx put its temporary directories while the node ran."""

    input_spec = _TrxWriterInputSpec
    output_spec = _TrxWriterOutputSpec
    seen = []

    def _run_interface(self, runtime):
        import nibabel as nib
        from nibabel.streamlines import LazyTractogram
        from trx.trx_file_memmap import TrxFile, save as trx_save

        ref = nib.Nifti1Image(np.zeros((20, 20, 20), np.float32), np.eye(4))
        rng = np.random.default_rng(0)
        lines = [rng.random((30, 3)).astype(np.float32) * 15 for _ in range(2500)]
        trx = TrxFile.from_lazy_tractogram(
            LazyTractogram(streamlines=lambda: iter(lines), affine_to_rasmm=np.eye(4)),
            ref,
            chunk_size=1000,
        )
        _TrxWriter.seen.append(
            (os.getcwd(), glob.glob(os.path.join(os.getcwd(), "trx_*")))
        )
        trx_save(trx, "out.trx")
        return runtime

    def _list_outputs(self):
        return {}


def test_trx_memmaps_are_created_and_removed_in_the_node_dir(tmp_path, monkeypatch):
    system_tmp = tmp_path / "system_tmp"
    system_tmp.mkdir()
    node_dir = tmp_path / "node"
    node_dir.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(system_tmp))
    monkeypatch.setenv(TRX_TMPDIR_VAR, str(system_tmp))  # ignored inside the node
    _TrxWriter.seen = []

    _TrxWriter().run(cwd=str(node_dir))

    ((cwd, during),) = _TrxWriter.seen
    assert cwd == str(node_dir)
    assert during  # trx did use a temporary directory, in the node dir
    assert not list(system_tmp.iterdir())
    assert glob.glob(str(node_dir / "trx_*")) == []  # removed once released
    assert (node_dir / "out.trx").exists()
    assert os.environ[TRX_TMPDIR_VAR] == str(system_tmp)  # restored
