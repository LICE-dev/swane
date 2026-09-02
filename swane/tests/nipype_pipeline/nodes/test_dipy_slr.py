"""Unit tests for
:class:`swane.nipype_pipeline.nodes.DipyAtlasSLR.DipyAtlasSLR`.

The whole-brain SLR runs once (spec section 6) and publishes two Phase-2
contracts: ``tractogram_atlas`` (the subject tractogram aligned to the atlas)
and ``atlas2native`` (the inverse transform used to bring recognised bundles
back). The load-bearing behaviours:

* the SLR aligns the subject tractogram to the atlas and the saved
  ``atlas2native`` maps a streamline back to native within tolerance;
* the whole-brain tractogram is addressed by its explicit filename
  (``whole_brain_MNI.trk``), never by globbing the bundles directory -- so the
  misspelled duplicate ``IF0F_R.trk`` in the atlas is never selected.
"""

import os

import numpy as np
import pytest

from swane.nipype_pipeline.nodes.DipyAtlasSLR import (
    DipyAtlasSLR,
    atlas_wholebrain_path,
    WHOLE_BRAIN_FILENAME,
    OMP_THREADS_VAR,
)


# --------------------------------------------------------------------------- #
# Synthetic whole-brain atlas + subject tractogram helpers.
# --------------------------------------------------------------------------- #
def _make_streamlines(seed):
    from dipy.tracking.streamline import Streamlines

    rng = np.random.default_rng(seed)

    def bundle(n, base, direction, jitter):
        out = []
        for _ in range(n):
            t = np.linspace(0, 80, 40)[:, None]
            off = np.asarray(base, float) + rng.normal(0, jitter, 3)
            out.append(
                (
                    off + t * np.asarray(direction, float) + rng.normal(0, 0.5, (40, 3))
                ).astype(np.float32)
            )
        return out

    return Streamlines(
        bundle(60, [0, 0, 0], [0, 0, 1], 3) + bundle(60, [20, 0, 0], [0, 1, 0], 3)
    )


def _save_trk(streamlines, path):
    import nibabel as nib
    from dipy.io.stateful_tractogram import StatefulTractogram, Space
    from dipy.io.streamline import save_tractogram

    ref = nib.Nifti1Image(np.zeros((200, 200, 200), dtype=np.float32), np.eye(4))
    sft = StatefulTractogram(streamlines, ref, Space.RASMM)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    save_tractogram(sft, path, bbox_valid_check=False)


@pytest.fixture
def atlas_dir(tmp_path):
    """A ready atlas tree: the whole-brain tractogram at its canonical path,
    plus a bundles directory containing both ``IFOF_R.trk`` and the misspelled
    duplicate ``IF0F_R.trk`` to prove neither is ever selected."""
    base = tmp_path / "atlas"
    wb = atlas_wholebrain_path(str(base))
    _save_trk(_make_streamlines(0), str(wb))

    bundles = wb.parent.parent / "bundles"
    bundles.mkdir(parents=True, exist_ok=True)
    for name in ("IFOF_R.trk", "IF0F_R.trk", "CST_L.trk"):
        _save_trk(_make_streamlines(1), str(bundles / name))
    return str(base)


@pytest.fixture
def subject_tractogram(tmp_path):
    """A subject tractogram in native space: the atlas streamlines under a known
    native->atlas rotation+translation, saved as ``.trx``."""
    import nibabel as nib
    from dipy.io.stateful_tractogram import StatefulTractogram, Space
    from dipy.io.streamline import save_tractogram
    from dipy.tracking.streamline import transform_streamlines

    theta = np.deg2rad(10.0)
    rot = np.array(
        [
            [np.cos(theta), -np.sin(theta), 0],
            [np.sin(theta), np.cos(theta), 0],
            [0, 0, 1],
        ]
    )
    native2atlas = np.eye(4)
    native2atlas[:3, :3] = rot
    native2atlas[:3, 3] = [5.0, -3.0, 2.0]
    atlas2native = np.linalg.inv(native2atlas)

    native = transform_streamlines(_make_streamlines(0), atlas2native)
    ref = nib.Nifti1Image(np.zeros((200, 200, 200), dtype=np.float32), np.eye(4))
    sft = StatefulTractogram(native, ref, Space.RASMM)
    path = tmp_path / "subject_tractogram.trx"
    save_tractogram(sft, str(path), bbox_valid_check=False)
    return str(path), native


# --------------------------------------------------------------------------- #
# The whole-brain tractogram is addressed by explicit name, never by glob.
# --------------------------------------------------------------------------- #
class TestExplicitBundleAddressing:
    def test_wholebrain_path_is_the_explicit_filename(self, tmp_path):
        wb = atlas_wholebrain_path(str(tmp_path / "atlas"))
        assert os.path.basename(str(wb)) == WHOLE_BRAIN_FILENAME
        assert WHOLE_BRAIN_FILENAME == "whole_brain_MNI.trk"

    def test_if0f_duplicate_is_never_selected(self, atlas_dir):
        wb = str(atlas_wholebrain_path(atlas_dir))
        # the resolved path is the whole-brain file, and the misspelled
        # duplicate that lives in the bundles directory is never reached
        assert os.path.basename(wb) == WHOLE_BRAIN_FILENAME
        assert "IF0F" not in wb
        assert os.path.exists(wb)


# --------------------------------------------------------------------------- #
# The node produces both Phase-2 outputs and a correct inverse transform.
# --------------------------------------------------------------------------- #
class TestSlrOutputs:
    def test_produces_atlas_tractogram_and_invertible_transform(
        self, workspace, atlas_dir, subject_tractogram
    ):
        from dipy.io.streamline import load_tractogram
        from dipy.tracking.streamline import transform_streamlines

        tract_path, native_streamlines = subject_tractogram

        node = DipyAtlasSLR()
        node.inputs.tractogram = tract_path
        node.inputs.atlas_dir = atlas_dir
        node.run()

        outputs = node._list_outputs()
        assert os.path.exists(outputs["tractogram_atlas"])
        assert os.path.exists(outputs["atlas2native"])

        atlas2native = np.loadtxt(outputs["atlas2native"])
        assert atlas2native.shape == (4, 4)

        moved = load_tractogram(
            outputs["tractogram_atlas"], "same", bbox_valid_check=False
        )
        back = transform_streamlines(moved.streamlines, atlas2native)
        # atlas2native brings the aligned tractogram back onto the native input
        err = np.mean([np.linalg.norm(b - n) for b, n in zip(back, native_streamlines)])
        assert err < 2.0

    def test_no_fetch_when_atlas_present(
        self, workspace, atlas_dir, subject_tractogram, monkeypatch
    ):
        import swane.nipype_pipeline.nodes.DipyAtlasSLR as mod

        def _boom(*a, **k):
            raise AssertionError("fetch must not run when the atlas is present")

        monkeypatch.setattr(mod, "_default_fetch", _boom)

        tract_path, _ = subject_tractogram
        node = DipyAtlasSLR()
        node.inputs.tractogram = tract_path
        node.inputs.atlas_dir = atlas_dir
        node.run()  # must not raise

        assert os.path.exists(node._list_outputs()["tractogram_atlas"])


class TestSlrThreadPinning:
    def test_omp_pinned_to_num_threads(
        self, workspace, atlas_dir, subject_tractogram, monkeypatch
    ):
        import swane.nipype_pipeline.nodes.DipyAtlasSLR as mod

        monkeypatch.delenv(OMP_THREADS_VAR, raising=False)
        seen = {}
        real = mod._run_whole_brain_slr

        def _spy(static, moving, num_threads):
            seen["omp"] = os.environ.get(OMP_THREADS_VAR)
            seen["num_threads"] = num_threads
            return real(static, moving, num_threads)

        monkeypatch.setattr(mod, "_run_whole_brain_slr", _spy)

        tract_path, _ = subject_tractogram
        node = DipyAtlasSLR()
        node.inputs.tractogram = tract_path
        node.inputs.atlas_dir = atlas_dir
        node.inputs.num_threads = 2
        node.run()

        assert seen["omp"] == "2"
        assert seen["num_threads"] == 2
        assert OMP_THREADS_VAR not in os.environ
