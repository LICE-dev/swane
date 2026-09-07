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
# Fornix split (spec section 3's "fx" special case).
#
# The atlas ships the fornix as one side-combined model file, ``F_L_R.trk``.
# Unlike every other bilateral tract (which already has separate ``<NAME>_L``/
# ``<NAME>_R`` atlas files), the fornix has to be lateralised by hand -- once,
# on the atlas's own model bundle, in the atlas's own RASMM world space, the
# same space every other atlas model bundle already lives in (e.g. spec
# section 3's verified ``AST_L`` spans x[-56,-8]: negative x is left). The
# result is cached as ``F_L.trk``/``F_R.trk`` beside the atlas's other bundle
# files so every subsequent fornix recognition -- for every subject -- reuses
# them exactly like any other named atlas bundle, with no special-casing left
# in ``DipyRecoBundles`` itself.
#
# This is valid only for a genuinely paired structure shipped as one combined
# file; a commissure (e.g. ``AC``) has no left/right identity and the split is
# refused for it.
# --------------------------------------------------------------------------- #
def _save_fornix_combined(atlas_dir, n=40, x_left=-25.0, x_right=25.0, seed=5):
    """Write a synthetic ``F_L_R.trk`` (atlas RASMM space) with ``n`` streamlines
    on each side of x=0."""
    from swane.nipype_pipeline.nodes.DipyFornixSplit import FORNIX_COMBINED_NAME

    rng = np.random.default_rng(seed)
    left = _bundle(rng, n, [x_left, 0, 0], [0, 0, 1], 2)
    right = _bundle(rng, n, [x_right, 0, 0], [0, 1, 0], 2)
    path = bundle_path(atlas_dir, FORNIX_COMBINED_NAME)
    _save(_streamlines(left, right), path)
    return path


class TestSplitBySignX:
    """The pure sign-of-x split, independent of file caching."""

    def test_splits_by_sign_of_x_conserving_count(self):
        from swane.nipype_pipeline.nodes.DipyFornixSplit import (
            split_by_sign_x,
            FORNIX_COMBINED_NAME,
        )

        rng = np.random.default_rng(1)
        left = _bundle(rng, 37, [-30, 0, 0], [0, 0, 1], 3)
        right = _bundle(rng, 41, [25, 0, 0], [0, 1, 0], 3)
        streamlines = _streamlines(left, right)

        lh_idx, rh_idx = split_by_sign_x(streamlines, FORNIX_COMBINED_NAME)

        assert len(lh_idx) + len(rh_idx) == len(streamlines)
        assert len(lh_idx) == 37
        assert len(rh_idx) == 41
        assert all(np.mean(streamlines[i][:, 0]) < 0 for i in lh_idx)
        assert all(np.mean(streamlines[i][:, 0]) >= 0 for i in rh_idx)

    def test_zero_mean_x_goes_to_the_right(self):
        from swane.nipype_pipeline.nodes.DipyFornixSplit import (
            split_by_sign_x,
            FORNIX_COMBINED_NAME,
        )

        streamlines = [np.zeros((10, 3), dtype=np.float32)]
        lh_idx, rh_idx = split_by_sign_x(streamlines, FORNIX_COMBINED_NAME)
        assert list(lh_idx) == []
        assert list(rh_idx) == [0]

    def test_refuses_a_commissure(self):
        from swane.nipype_pipeline.nodes.DipyFornixSplit import (
            split_by_sign_x,
            FornixSplitRefusedError,
        )

        streamlines = [np.zeros((5, 3), dtype=np.float32)]
        with pytest.raises(FornixSplitRefusedError):
            split_by_sign_x(streamlines, "AC")


class TestEnsureFornixLateralized:
    """The cached, create-once-per-atlas behaviour."""

    def test_creates_lateralized_files_once(self, tmp_path):
        from swane.nipype_pipeline.nodes.DipyFornixSplit import (
            ensure_fornix_lateralized,
        )
        from dipy.io.streamline import load_tractogram

        atlas_dir = str(tmp_path / "atlas")
        _save_fornix_combined(atlas_dir, n=40)

        path_lh, path_rh = ensure_fornix_lateralized(atlas_dir)

        assert os.path.exists(path_lh)
        assert os.path.exists(path_rh)
        lh = load_tractogram(path_lh, "same", bbox_valid_check=False)
        rh = load_tractogram(path_rh, "same", bbox_valid_check=False)
        assert len(lh.streamlines) == 40
        assert len(rh.streamlines) == 40

    def test_second_call_reuses_existing_files_without_recreating(self, tmp_path):
        from swane.nipype_pipeline.nodes.DipyFornixSplit import (
            ensure_fornix_lateralized,
        )

        atlas_dir = str(tmp_path / "atlas")
        _save_fornix_combined(atlas_dir, n=10)

        path_lh, path_rh = ensure_fornix_lateralized(atlas_dir)
        mtime_lh = os.path.getmtime(path_lh)
        mtime_rh = os.path.getmtime(path_rh)

        path_lh_2, path_rh_2 = ensure_fornix_lateralized(atlas_dir)

        assert (path_lh_2, path_rh_2) == (path_lh, path_rh)
        assert os.path.getmtime(path_lh_2) == mtime_lh
        assert os.path.getmtime(path_rh_2) == mtime_rh

    def test_missing_combined_bundle_raises(self, tmp_path):
        from swane.nipype_pipeline.nodes.DipyFornixSplit import (
            ensure_fornix_lateralized,
        )

        atlas_dir = str(tmp_path / "empty_atlas")
        os.makedirs(atlas_dir, exist_ok=True)
        with pytest.raises(FileNotFoundError):
            ensure_fornix_lateralized(atlas_dir)

    def test_split_uses_world_rasmm_space_not_raw_voxel_storage(self, tmp_path):
        """The atlas's left/right convention is defined in RASMM world space
        (spec section 3's verified ``AST_L`` x[-56,-8]). A fixture whose voxel
        storage disagrees in sign with world space -- voxel x>0 maps to world
        x<0 and vice versa -- proves the split reads world/RASMM coordinates,
        never raw voxel indices: getting this space wrong would silently swap
        every streamline to the wrong side."""
        import nibabel as nib
        from dipy.io.stateful_tractogram import StatefulTractogram, Space
        from dipy.io.streamline import save_tractogram, load_tractogram
        from swane.nipype_pipeline.nodes.DipyFornixSplit import (
            ensure_fornix_lateralized,
            FORNIX_COMBINED_NAME,
        )

        # world = affine @ voxel; x is flipped and offset.
        affine = np.array(
            [
                [-1, 0, 0, 90],
                [0, 1, 0, -126],
                [0, 0, 1, -72],
                [0, 0, 0, 1],
            ],
            dtype=float,
        )
        ref = nib.Nifti1Image(np.zeros((181, 217, 181), dtype=np.float32), affine)

        rng = np.random.default_rng(9)
        # voxel x=110 -> world x=-20 (world-left); voxel x=70 -> world x=+20
        # (world-right). Raw voxel-index sign would say the opposite.
        left_world = _bundle(rng, 22, [110, 100, 90], [0, 0, 1], 2)
        right_world = _bundle(rng, 26, [70, 100, 90], [0, 0, 1], 2)
        streamlines = _streamlines(left_world, right_world)

        sft = StatefulTractogram(streamlines, ref, Space.VOX)
        atlas_dir = str(tmp_path / "atlas")
        path = bundle_path(atlas_dir, FORNIX_COMBINED_NAME)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        save_tractogram(sft, path, bbox_valid_check=False)

        path_lh, path_rh = ensure_fornix_lateralized(atlas_dir)

        lh = load_tractogram(path_lh, "same", bbox_valid_check=False)
        rh = load_tractogram(path_rh, "same", bbox_valid_check=False)
        assert len(lh.streamlines) == 22
        assert len(rh.streamlines) == 26


class TestDipyFornixSplitNode:
    """The thin Nipype node wrapping :func:`ensure_fornix_lateralized`, so a
    bundle workflow can depend on it before running two ordinary
    ``DipyRecoBundles`` recognitions (``F_L``/``F_R``) for the fornix."""

    def test_node_ensures_files_and_passes_atlas_dir_through(self, workspace, tmp_path):
        from swane.nipype_pipeline.nodes.DipyFornixSplit import (
            DipyFornixSplit,
            FORNIX_LEFT_NAME,
            FORNIX_RIGHT_NAME,
        )

        atlas_dir = str(tmp_path / "atlas")
        _save_fornix_combined(atlas_dir, n=15)

        node = DipyFornixSplit()
        node.inputs.atlas_dir = atlas_dir
        node.run()

        out = node._list_outputs()
        assert out["atlas_dir"] == atlas_dir
        assert os.path.exists(bundle_path(atlas_dir, FORNIX_LEFT_NAME))
        assert os.path.exists(bundle_path(atlas_dir, FORNIX_RIGHT_NAME))


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
