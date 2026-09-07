"""Unit tests for
:class:`swane.nipype_pipeline.nodes.DipyRecoBundles.DipyRecoBundles`.

RecoBundles recognises a named atlas bundle inside the subject tractogram that
Phase 1 already aligned to the atlas (``tractogram_atlas``). The load-bearing
behaviours exercised here:

* the model bundle is addressed by its **explicit filename**, never by a glob --
  so an atlas directory holding both ``IFOF_R.trk`` and the misspelled duplicate
  ``IF0F_R.trk`` resolves to ``IFOF_R.trk`` and never the misspelling;
* the node produces a valid ``.trx`` output: non-empty when the subject contains
  the model shape, empty-but-valid when it does not;
* recognition is reproducible across two runs at a fixed seed;
* the memmapped **chunk-and-union** path (a RAM lever) approximates the
  single-pass result, and disables the (invalid) local SLR automatically.

The chunk-and-union union is only *scientifically* valid with ``slr=False``
(each chunk would otherwise compute a different local SLR), so the tests assert
that union count is *close to* the single-pass count, never bit-equality.
"""

import os

import numpy as np
import pytest

from swane.nipype_pipeline.nodes.DipyRecoBundles import (
    DipyRecoBundles,
    bundle_path,
    BUNDLES_SUBDIR,
    OMP_THREADS_VAR,
)


# --------------------------------------------------------------------------- #
# Synthetic atlas + subject tractogram helpers.
#
# Fixtures must be non-degenerate (hundreds of varied streamlines): dipy's
# ``qbx_and_merge`` raises on tiny/collapsed inputs where QuickBundlesX yields a
# single level.
# --------------------------------------------------------------------------- #
def _bundle(rng, n, base, direction, jitter, length=80, npts=40):
    base = np.asarray(base, float)
    direction = np.asarray(direction, float)
    direction /= np.linalg.norm(direction)
    out = []
    t = np.linspace(0, length, npts)[:, None]
    for _ in range(n):
        off = base + rng.normal(0, jitter, 3)
        curve = off + t * direction + rng.normal(0, 0.5, (npts, 3))
        out.append(curve.astype(np.float32))
    return out


def _streamlines(*groups):
    from dipy.tracking.streamline import Streamlines

    lines = []
    for g in groups:
        lines.extend(g)
    return Streamlines(lines)


def _save(streamlines, path):
    import nibabel as nib
    from dipy.io.stateful_tractogram import StatefulTractogram, Space
    from dipy.io.streamline import save_tractogram

    ref = nib.Nifti1Image(np.zeros((200, 200, 200), dtype=np.float32), np.eye(4))
    sft = StatefulTractogram(streamlines, ref, Space.RASMM)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    save_tractogram(sft, path, bbox_valid_check=False)


# Distinct geometric shapes so that recognising the wrong file (the misspelled
# duplicate) yields a measurably different result.
_IFOF_R_SHAPE = ([-20, 0, 0], [0, 0, 1])  # supero-inferior around x=-20
_IF0F_R_SHAPE = ([40, 40, 0], [0, 1, 0])  # antero-posterior, far away
_CST_L_SHAPE = ([0, -30, 20], [1, 0, 0])  # left-right, elsewhere


@pytest.fixture
def atlas_dir(tmp_path):
    """An atlas tree whose ``bundles`` directory holds ``IFOF_R.trk``, the
    misspelled duplicate ``IF0F_R.trk`` (a *different* shape) and ``CST_L.trk``."""
    base = tmp_path / "atlas"
    rng = np.random.default_rng(7)
    _save(
        _streamlines(_bundle(rng, 120, *_IFOF_R_SHAPE, 3)),
        bundle_path(str(base), "IFOF_R"),
    )
    _save(
        _streamlines(_bundle(rng, 120, *_IF0F_R_SHAPE, 3)),
        bundle_path(str(base), "IF0F_R"),
    )
    _save(
        _streamlines(_bundle(rng, 120, *_CST_L_SHAPE, 3)),
        bundle_path(str(base), "CST_L"),
    )
    return str(base)


def _subject_with_ifof(tmp_path, name="subject.trx"):
    """A subject tractogram containing the IFOF_R shape plus unrelated noise."""
    rng = np.random.default_rng(11)
    streamlines = _streamlines(
        _bundle(rng, 250, *_IFOF_R_SHAPE, 3),  # matches IFOF_R model
        _bundle(rng, 400, [60, -40, 10], [1, 1, 0], 5),  # noise A
        _bundle(rng, 350, [10, 50, -20], [0, 1, 1], 5),  # noise B
    )
    path = tmp_path / name
    _save(streamlines, str(path))
    return str(path)


def _subject_without_ifof(tmp_path, name="subject_noise.trx"):
    """A subject tractogram with only shapes unrelated to the IFOF_R model."""
    rng = np.random.default_rng(13)
    streamlines = _streamlines(
        _bundle(rng, 400, [60, -40, 10], [1, 1, 0], 5),
        _bundle(rng, 400, [10, 50, -20], [0, 1, 1], 5),
    )
    path = tmp_path / name
    _save(streamlines, str(path))
    return str(path)


def _n_streamlines(trx_path):
    from dipy.io.streamline import load_tractogram

    return len(load_tractogram(trx_path, "same", bbox_valid_check=False).streamlines)


# --------------------------------------------------------------------------- #
# The model bundle is addressed by explicit name, never by glob.
# --------------------------------------------------------------------------- #
class TestExplicitBundleAddressing:
    def test_bundle_path_is_the_explicit_filename(self, tmp_path):
        p = bundle_path(str(tmp_path / "atlas"), "IFOF_R")
        assert os.path.basename(p) == "IFOF_R.trk"
        assert BUNDLES_SUBDIR in p
        assert "IF0F" not in p

    def test_if0f_and_ifof_are_distinct_files(self, atlas_dir):
        ifof = bundle_path(atlas_dir, "IFOF_R")
        if0f = bundle_path(atlas_dir, "IF0F_R")
        assert os.path.exists(ifof) and os.path.exists(if0f)
        assert ifof != if0f
        assert os.path.basename(ifof) == "IFOF_R.trk"

    def test_recognition_uses_ifof_not_the_misspelled_duplicate(
        self, workspace, atlas_dir, tmp_path
    ):
        """The subject contains only the IFOF_R shape. Addressing ``IFOF_R``
        recognises streamlines; had the node globbed and picked ``IF0F_R.trk``
        (a different, absent shape) the result would be empty."""
        from dipy.io.streamline import load_tractogram

        subject = _subject_with_ifof(tmp_path)

        node = DipyRecoBundles()
        node.inputs.tractogram_atlas = subject
        node.inputs.atlas_dir = atlas_dir
        node.inputs.model_bundle_name = "IFOF_R"
        node.inputs.num_threads = 1
        node.run()

        out = node._list_outputs()["recognized_bundle"]
        assert os.path.exists(out)
        assert out.endswith(".trx")
        recognized = load_tractogram(out, "same", bbox_valid_check=False)
        assert len(recognized.streamlines) > 0


# --------------------------------------------------------------------------- #
# Output contract: non-empty on a match, empty-but-valid on a miss.
# --------------------------------------------------------------------------- #
class TestOutputContract:
    def test_empty_but_valid_when_shape_absent(self, workspace, atlas_dir, tmp_path):
        from dipy.io.streamline import load_tractogram

        subject = _subject_without_ifof(tmp_path)

        node = DipyRecoBundles()
        node.inputs.tractogram_atlas = subject
        node.inputs.atlas_dir = atlas_dir
        node.inputs.model_bundle_name = "IFOF_R"
        node.inputs.num_threads = 1
        node.run()

        out = node._list_outputs()["recognized_bundle"]
        assert os.path.exists(out)
        # A valid, loadable, empty tractogram -- not a crash, not a missing file.
        recognized = load_tractogram(out, "same", bbox_valid_check=False)
        assert len(recognized.streamlines) == 0

    def test_reproducible_across_two_runs(self, workspace, atlas_dir, tmp_path):
        from dipy.io.streamline import load_tractogram

        subject = _subject_with_ifof(tmp_path)
        counts = []
        for i in range(2):
            node = DipyRecoBundles()
            node.inputs.tractogram_atlas = subject
            node.inputs.atlas_dir = atlas_dir
            node.inputs.model_bundle_name = "IFOF_R"
            node.inputs.num_threads = 1
            node.inputs.out_bundle = f"rec_{i}.trx"
            node.run()
            out = node._list_outputs()["recognized_bundle"]
            counts.append(
                len(load_tractogram(out, "same", bbox_valid_check=False).streamlines)
            )
        assert counts[0] == counts[1] > 0


# --------------------------------------------------------------------------- #
# Chunk-and-union RAM lever.
# --------------------------------------------------------------------------- #
class TestChunkAndUnion:
    def test_chunked_union_approximates_single_pass(
        self, workspace, atlas_dir, tmp_path
    ):
        from dipy.io.streamline import load_tractogram

        subject = _subject_with_ifof(tmp_path)

        def _recognized_count(**extra):
            node = DipyRecoBundles()
            node.inputs.tractogram_atlas = subject
            node.inputs.atlas_dir = atlas_dir
            node.inputs.model_bundle_name = "IFOF_R"
            node.inputs.num_threads = 1
            for k, v in extra.items():
                setattr(node.inputs, k, v)
            node.run()
            out = node._list_outputs()["recognized_bundle"]
            return len(load_tractogram(out, "same", bbox_valid_check=False).streamlines)

        single = _recognized_count(slr=False)
        chunked = _recognized_count(slr=False, chunk_size=200)

        assert single > 0 and chunked > 0
        # Same order of magnitude -- clustering-boundary shifts move a few
        # streamlines, but not the bulk of the bundle.
        assert abs(chunked - single) <= 0.2 * single

    def test_chunk_size_at_or_above_total_behaves_like_single_pass(
        self, workspace, atlas_dir, tmp_path
    ):
        from dipy.io.streamline import load_tractogram

        subject = _subject_with_ifof(tmp_path)
        n = _n_streamlines(subject)

        node = DipyRecoBundles()
        node.inputs.tractogram_atlas = subject
        node.inputs.atlas_dir = atlas_dir
        node.inputs.model_bundle_name = "IFOF_R"
        node.inputs.num_threads = 1
        node.inputs.slr = False
        node.inputs.chunk_size = n + 100  # >= total -> single chunk
        node.run()
        out = node._list_outputs()["recognized_bundle"]
        assert len(load_tractogram(out, "same", bbox_valid_check=False).streamlines) > 0

    def test_chunking_disables_local_slr_automatically(
        self, workspace, atlas_dir, tmp_path, monkeypatch
    ):
        """Setting ``chunk_size`` is the only lever the caller sets; the node
        forces the local SLR off (a union of per-chunk SLRs is invalid) even when
        ``slr`` is left at its default ``True`` -- and never raises for it."""
        import swane.nipype_pipeline.nodes.DipyRecoBundles as mod
        from dipy.io.streamline import load_tractogram

        subject = _subject_with_ifof(tmp_path)

        seen_slr = []
        real = mod._recognize

        def _spy(*args, **kwargs):
            seen_slr.append(kwargs["slr"])
            return real(*args, **kwargs)

        monkeypatch.setattr(mod, "_recognize", _spy)

        node = DipyRecoBundles()
        node.inputs.tractogram_atlas = subject
        node.inputs.atlas_dir = atlas_dir
        node.inputs.model_bundle_name = "IFOF_R"
        node.inputs.num_threads = 1
        node.inputs.slr = True  # left at default; chunking overrides it
        node.inputs.chunk_size = 200
        node.run()  # must not raise

        assert seen_slr, "recognition was never invoked"
        assert all(v is False for v in seen_slr)
        out = node._list_outputs()["recognized_bundle"]
        assert len(load_tractogram(out, "same", bbox_valid_check=False).streamlines) > 0


# --------------------------------------------------------------------------- #
# Thread pinning, mirroring DipyAtlasSLR.
# --------------------------------------------------------------------------- #
class TestThreadPinning:
    def test_omp_pinned_during_recognition(
        self, workspace, atlas_dir, tmp_path, monkeypatch
    ):
        import swane.nipype_pipeline.nodes.DipyRecoBundles as mod

        monkeypatch.delenv(OMP_THREADS_VAR, raising=False)
        seen = {}
        real = mod._recognize

        def _spy(*args, **kwargs):
            seen["omp"] = os.environ.get(OMP_THREADS_VAR)
            return real(*args, **kwargs)

        monkeypatch.setattr(mod, "_recognize", _spy)

        subject = _subject_with_ifof(tmp_path)
        node = DipyRecoBundles()
        node.inputs.tractogram_atlas = subject
        node.inputs.atlas_dir = atlas_dir
        node.inputs.model_bundle_name = "IFOF_R"
        node.inputs.num_threads = 2
        node.run()

        assert seen["omp"] == "2"
        assert OMP_THREADS_VAR not in os.environ
