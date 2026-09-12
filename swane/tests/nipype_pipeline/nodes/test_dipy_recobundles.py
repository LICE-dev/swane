"""Unit tests for the RecoBundles bundle nodes.

Phase 1 aligned the whole subject tractogram to the HCP842 atlas once
(``tractogram_atlas``). Phase 2's RecoBundles cost -- the whole-tractogram
QuickBundlesX clustering -- is the ``RecoBundles.__init__`` build, while
``recognize`` is cheap. So the work is split across four nodes (spec section 6,
user design 2026-09-07):

* :class:`~swane.nipype_pipeline.nodes.DipyRecoBundles.DipyRecoBundlesBuild`
  builds ``RecoBundles(streamlines)`` on one (sub-)tractogram and saves a
  **lightweight** pickle -- only the QBx ``cluster_map`` and the post-clustering
  RNG state, never the streamlines (they already live in the input ``.trx``);
* :class:`~swane.nipype_pipeline.nodes.DipyRecoBundles.DipyRecoBundlesRecognize`
  reloads that pickle *plus* the same ``.trx`` streamlines, reconstructs the
  built object and runs ``recognize`` for one explicitly named model bundle,
  producing the recognised streamlines in atlas space as a ``.trx``;
* :class:`~swane.nipype_pipeline.nodes.DipyTractogramChunker.DipyTractogramChunker`
  splits the tractogram into 1..N **representative** sub-tractograms;
* :class:`~swane.nipype_pipeline.nodes.DipyBundleUnion.DipyBundleUnion`
  concatenates N per-chunk recognitions back into one bundle;
* :class:`~swane.nipype_pipeline.nodes.DipyBundlesToRef.DipyBundlesToRef`
  transforms a recognised bundle to reference space and writes a ``.vtp``.

The load-bearing behaviours exercised here:

* the model bundle is addressed by its **explicit filename**, never by a glob --
  so an atlas directory holding both ``IFOF_R.trk`` and the misspelled duplicate
  ``IF0F_R.trk`` resolves to ``IFOF_R.trk`` and never the misspelling;
* a **pickled build reloaded** in a separate node recognises **bit-identically**
  to an in-process build (the RNG state carried in the pickle is what makes this
  exact -- a fresh-seeded RNG would diverge);
* the build pickle is **lightweight**: it does not carry the streamlines, so it
  is far smaller than the tractogram it was built from (minimises disk and RAM,
  per the user's 2026-09-07 note);
* the chunker partitions the tractogram exactly once into non-contiguous
  (representative) chunks; the union conserves counts; and the to-ref node writes
  a reference-space ``.vtp`` via ``vtk`` (never ``fury``, which is not installed).
"""

import os
import pickle

import numpy as np
import pytest

from swane.nipype_pipeline.nodes.DipyRecoBundles import (
    DipyRecoBundlesBuild,
    DipyRecoBundlesRecognize,
    bundle_path,
    recognition_params,
    BUNDLES_SUBDIR,
    OMP_THREADS_VAR,
    CLUST_THR,
    NB_PTS,
    RECOBUNDLES_RNG_SEED,
    RECOGNITION_DEFAULTS,
    RECOGNITION_OVERRIDES,
    tract_of,
    REFINE_SLR_X0,
    REFINE_SLR_BOUNDS,
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


def _load_streamlines(trx_path):
    from dipy.io.streamline import load_tractogram

    return load_tractogram(trx_path, "same", bbox_valid_check=False).streamlines


def _n_streamlines(trx_path):
    return len(_load_streamlines(trx_path))


# --------------------------------------------------------------------------- #
# Build + recognise helpers (the split monolith replacement).
# --------------------------------------------------------------------------- #
def _build(chunk_path, out_pickle, num_threads=1):
    node = DipyRecoBundlesBuild()
    node.inputs.tractogram_chunk = chunk_path
    node.inputs.num_threads = num_threads
    node.inputs.out_pickle = out_pickle
    node.run()
    return node._list_outputs()["recobundles_pickle"]


def _recognize(pickle_path, chunk_path, atlas_dir, model, out_bundle, **extra):
    node = DipyRecoBundlesRecognize()
    node.inputs.recobundles_pickle = pickle_path
    node.inputs.tractogram_chunk = chunk_path
    node.inputs.atlas_dir = atlas_dir
    node.inputs.model_bundle_name = model
    node.inputs.num_threads = 1
    node.inputs.out_bundle = out_bundle
    for k, v in extra.items():
        setattr(node.inputs, k, v)
    node.run()
    return node._list_outputs()["recognized_bundle"]


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
        subject = _subject_with_ifof(tmp_path)
        pkl = _build(subject, str(tmp_path / "build.pkl"))
        out = _recognize(pkl, subject, atlas_dir, "IFOF_R", str(tmp_path / "rec.trx"))

        assert os.path.exists(out)
        assert out.endswith(".trx")
        assert _n_streamlines(out) > 0


# --------------------------------------------------------------------------- #
# Output contract: non-empty on a match, empty-but-valid on a miss.
# --------------------------------------------------------------------------- #
class TestOutputContract:
    def test_empty_but_valid_when_shape_absent(self, workspace, atlas_dir, tmp_path):
        subject = _subject_without_ifof(tmp_path)
        pkl = _build(subject, str(tmp_path / "build.pkl"))
        out = _recognize(pkl, subject, atlas_dir, "IFOF_R", str(tmp_path / "rec.trx"))

        assert os.path.exists(out)
        # A valid, loadable, empty tractogram -- not a crash, not a missing file.
        assert _n_streamlines(out) == 0

    def test_reproducible_across_two_runs(self, workspace, atlas_dir, tmp_path):
        subject = _subject_with_ifof(tmp_path)
        counts = []
        for i in range(2):
            pkl = _build(subject, str(tmp_path / f"build_{i}.pkl"))
            out = _recognize(
                pkl, subject, atlas_dir, "IFOF_R", str(tmp_path / f"rec_{i}.trx")
            )
            counts.append(_n_streamlines(out))
        assert counts[0] == counts[1] > 0


# --------------------------------------------------------------------------- #
# The lightweight build -> recognise handoff (user's 2026-09-07 note): the
# pickle carries the QBx clustering + RNG state, never the streamlines, and a
# reloaded build recognises bit-identically to an in-process one.
# --------------------------------------------------------------------------- #
class TestBuildRecognizeHandoff:
    def _in_process_recognition(self, subject, atlas_dir, out_bundle, slr):
        """A single-process ``RecoBundles(streamlines).recognize(...)`` written
        to ``.trx`` exactly the way the recognise node writes it, so the two are
        directly comparable."""
        from dipy.io.streamline import load_tractogram, save_tractogram
        from dipy.io.stateful_tractogram import StatefulTractogram
        from dipy.segment.bundles import RecoBundles
        from dipy.tracking.streamline import Streamlines

        subject_sft = load_tractogram(subject, "same", bbox_valid_check=False)
        subject_sft.to_rasmm()
        model_sft = load_tractogram(
            bundle_path(atlas_dir, "IFOF_R"), "same", bbox_valid_check=False
        )
        model_sft.to_rasmm()

        rb = RecoBundles(
            subject_sft.streamlines,
            clust_thr=CLUST_THR,
            nb_pts=NB_PTS,
            rng=np.random.default_rng(RECOBUNDLES_RNG_SEED),
            verbose=False,
        )
        recognized, labels = rb.recognize(
            model_sft.streamlines,
            RECOGNITION_DEFAULTS["model_clust_thr"],
            reduction_thr=RECOGNITION_DEFAULTS["reduction_thr"],
            pruning_thr=RECOGNITION_DEFAULTS["pruning_thr"],
            slr=slr,
            num_threads=1,
        )
        # The shipped node refines by default, and refine consumes the RNG too,
        # so the reference must run the whole shipped path -- which makes this a
        # stronger contract than recognise alone: the pickled post-clustering RNG
        # state has to survive BOTH passes for the outputs to match bit for bit.
        if RECOGNITION_DEFAULTS["refine"] and len(recognized) >= 2:
            recognized, labels = rb.refine(
                model_sft.streamlines,
                recognized,
                RECOGNITION_DEFAULTS["model_clust_thr"],
                reduction_thr=RECOGNITION_DEFAULTS["r_reduction_thr"],
                pruning_thr=RECOGNITION_DEFAULTS["r_pruning_thr"],
                slr=True,
                slr_x0=REFINE_SLR_X0,
                slr_bounds=REFINE_SLR_BOUNDS,
            )
        bundle = Streamlines(subject_sft.streamlines[i] for i in labels)
        sft = StatefulTractogram.from_sft(bundle, model_sft)
        save_tractogram(sft, out_bundle, bbox_valid_check=False)
        return out_bundle

    def test_reloaded_build_recognizes_bit_identically_to_in_process(
        self, workspace, atlas_dir, tmp_path
    ):
        """The whole point of splitting build from recognise: a build pickled in
        one process and reloaded in another must recognise *exactly* what a
        single in-process ``RecoBundles`` build would -- same streamline
        trajectories, same count. This holds only because the pickle carries the
        post-clustering RNG state; the local SLR (``slr=True``) consumes the RNG,
        so a fresh seed would diverge."""
        subject = _subject_with_ifof(tmp_path)

        pkl = _build(subject, str(tmp_path / "build.pkl"))
        node_out = _recognize(
            pkl, subject, atlas_dir, "IFOF_R", str(tmp_path / "node.trx"), slr=True
        )
        ref_out = self._in_process_recognition(
            subject, atlas_dir, str(tmp_path / "ref.trx"), slr=True
        )

        node_sl = _load_streamlines(node_out)
        ref_sl = _load_streamlines(ref_out)
        assert len(node_sl) == len(ref_sl) > 0
        assert all(np.array_equal(a, b) for a, b in zip(node_sl, ref_sl))

    def test_pickle_is_lightweight_not_the_streamlines(
        self, workspace, atlas_dir, tmp_path
    ):
        """The pickle stores the QBx clustering + RNG only, never the
        streamlines (they stay in the input ``.trx``), so it must be far smaller
        than the tractogram it was built from -- the disk/RAM minimisation the
        user asked for."""
        subject = _subject_with_ifof(tmp_path)
        pkl = _build(subject, str(tmp_path / "build.pkl"))

        pickle_bytes = os.path.getsize(pkl)
        trx_bytes = os.path.getsize(subject)
        assert pickle_bytes < 0.25 * trx_bytes, (
            f"build pickle {pickle_bytes} B is not lightweight vs the tractogram "
            f"{trx_bytes} B -- it probably carries the streamlines"
        )

        # And prove it structurally: the stored object holds the cluster map and
        # an RNG, and does not embed a RecoBundles/Streamlines payload.
        with open(pkl, "rb") as fh:
            stored = pickle.load(fh)
        assert set(stored) == {"cluster_map", "rng"}
        assert isinstance(stored["rng"], np.random.Generator)


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
        real = mod._run_recognize

        def _spy(*args, **kwargs):
            seen["omp"] = os.environ.get(OMP_THREADS_VAR)
            return real(*args, **kwargs)

        monkeypatch.setattr(mod, "_run_recognize", _spy)

        subject = _subject_with_ifof(tmp_path)
        pkl = _build(subject, str(tmp_path / "build.pkl"))

        node = DipyRecoBundlesRecognize()
        node.inputs.recobundles_pickle = pkl
        node.inputs.tractogram_chunk = subject
        node.inputs.atlas_dir = atlas_dir
        node.inputs.model_bundle_name = "IFOF_R"
        node.inputs.num_threads = 2
        node.run()

        assert seen["omp"] == "2"
        assert OMP_THREADS_VAR not in os.environ


# --------------------------------------------------------------------------- #
# The written bundle carries the subject's own streamline geometry.
# --------------------------------------------------------------------------- #
def _streamline_key(streamline):
    return np.asarray(streamline, dtype=np.float32).tobytes()


class TestWrittenBundleGeometry:
    """RecoBundles returns its selection already moved into the model frame by
    the per-bundle local SLR; the node writes the selected subject streamlines
    instead, so every written streamline occurs verbatim in the input."""

    def test_written_streamlines_occur_verbatim_in_the_input(
        self, atlas_dir, tmp_path
    ):
        subject = _subject_with_ifof(tmp_path)
        pickle_path = _build(subject, str(tmp_path / "build.pkl"))
        out = _recognize(
            pickle_path,
            subject,
            atlas_dir,
            "IFOF_R",
            str(tmp_path / "bundle.trx"),
            slr=True,
            refine=False,
        )
        written = _load_streamlines(out)
        assert len(written) > 0
        source = {_streamline_key(s) for s in _load_streamlines(subject)}
        missing = [s for s in written if _streamline_key(s) not in source]
        assert not missing, "%d written streamlines are not input streamlines" % len(
            missing
        )

    def test_holds_with_the_refine_pass_too(self, atlas_dir, tmp_path):
        subject = _subject_with_ifof(tmp_path, name="subject_refine.trx")
        pickle_path = _build(subject, str(tmp_path / "build_refine.pkl"))
        out = _recognize(
            pickle_path,
            subject,
            atlas_dir,
            "IFOF_R",
            str(tmp_path / "bundle_refine.trx"),
            slr=True,
            refine=True,
        )
        written = _load_streamlines(out)
        source = {_streamline_key(s) for s in _load_streamlines(subject)}
        assert all(_streamline_key(s) in source for s in written)


# --------------------------------------------------------------------------- #
# DipyTractogramChunker: representative 1..N split.
# --------------------------------------------------------------------------- #
def _indexed_streamlines(n, tmp_path, name="indexed.trx"):
    """A tractogram of ``n`` streamlines whose i-th streamline is tagged by a
    constant x == i, so a chunk's original indices are recoverable."""
    from dipy.tracking.streamline import Streamlines

    lines = []
    for i in range(n):
        line = np.zeros((10, 3), dtype=np.float32)
        line[:, 0] = float(i)  # x encodes the original index
        line[:, 2] = np.linspace(0, 20, 10)  # non-degenerate geometry
        lines.append(line)
    path = tmp_path / name
    _save(Streamlines(lines), str(path))
    return str(path)


def _chunk(tractogram, n_chunks, tmp_path):
    from swane.nipype_pipeline.nodes.DipyTractogramChunker import DipyTractogramChunker

    node = DipyTractogramChunker()
    node.inputs.tractogram_atlas = tractogram
    node.inputs.n_chunks = n_chunks
    node.inputs.out_prefix = str(tmp_path / "chunk")
    node.run()
    return node._list_outputs()["chunks"]


class TestTractogramChunker:
    def test_single_chunk_returns_the_whole_tractogram(self, workspace, tmp_path):
        tractogram = _indexed_streamlines(50, tmp_path)
        chunks = _chunk(tractogram, 1, tmp_path)
        assert len(chunks) == 1
        assert _n_streamlines(chunks[0]) == 50

    def test_n_chunks_partition_exactly_once(self, workspace, tmp_path):
        n, N = 47, 4
        tractogram = _indexed_streamlines(n, tmp_path)
        chunks = _chunk(tractogram, N, tmp_path)

        assert len(chunks) == N
        # Every streamline appears in exactly one chunk -- counts sum, and the
        # union of recovered original indices is the full set with no repeats.
        assert sum(_n_streamlines(c) for c in chunks) == n
        seen = []
        for c in chunks:
            for sl in _load_streamlines(c):
                seen.append(int(round(sl[0, 0])))
        assert sorted(seen) == list(range(n))

    def test_each_chunk_is_representative_not_contiguous(self, workspace, tmp_path):
        n, N = 47, 4
        tractogram = _indexed_streamlines(n, tmp_path)
        chunks = _chunk(tractogram, N, tmp_path)

        for c, chunk in enumerate(chunks):
            idx = sorted(int(round(sl[0, 0])) for sl in _load_streamlines(chunk))
            # A strided partition: chunk c holds indices c, c+N, c+2N, ...
            assert idx == list(range(c, n, N))
            # ... which is emphatically not a contiguous block.
            assert idx != list(range(idx[0], idx[0] + len(idx)))

    def test_single_chunk_output_stays_a_list_through_the_node_trait(
        self, workspace, tmp_path
    ):
        """``_list_outputs`` alone (used by ``_chunk`` above) bypasses nipype's
        output trait, which is where a real workflow connection actually reads
        ``chunks`` from. ``OutputMultiPath`` unwraps a length-1 list to a bare
        string on read (nipype.interfaces.base.traits_extension.OutputMultiObject.get),
        so a downstream ``("chunks", _first)`` connection transform (see
        dipy_bundle_workflow) would index into that string's characters instead
        of the one-element list, e.g. picking off the leading ``"/"``."""
        from nipype import Node
        from swane.nipype_pipeline.nodes.DipyTractogramChunker import (
            DipyTractogramChunker,
        )

        tractogram = _indexed_streamlines(5, tmp_path)
        node = Node(
            DipyTractogramChunker(), name="dipy_chunker", base_dir=str(tmp_path)
        )
        node.inputs.tractogram_atlas = tractogram
        node.inputs.n_chunks = 1
        result = node.run()

        assert isinstance(result.outputs.chunks, list)
        assert result.outputs.chunks == [tractogram]


# --------------------------------------------------------------------------- #
# DipyBundleUnion: concatenate N per-chunk recognitions.
# --------------------------------------------------------------------------- #
def _union(recognized_bundles, tmp_path, name="union.trx"):
    from swane.nipype_pipeline.nodes.DipyBundleUnion import DipyBundleUnion

    node = DipyBundleUnion()
    node.inputs.recognized_bundles = list(recognized_bundles)
    node.inputs.out_bundle = str(tmp_path / name)
    node.run()
    return node._list_outputs()["bundle"]


class TestBundleUnion:
    def test_passthrough_at_n_equals_one(self, workspace, tmp_path):
        one = _indexed_streamlines(12, tmp_path, name="one.trx")
        out = _union([one], tmp_path)
        assert _n_streamlines(out) == 12

    def test_count_conserved_over_partials(self, workspace, tmp_path):
        a = _indexed_streamlines(12, tmp_path, name="a.trx")
        b = _indexed_streamlines(20, tmp_path, name="b.trx")
        c = _indexed_streamlines(7, tmp_path, name="c.trx")
        out = _union([a, b, c], tmp_path)
        assert _n_streamlines(out) == 12 + 20 + 7


# --------------------------------------------------------------------------- #
# DipyBundlesToRef: atlas-space bundle -> reference-space .vtp via vtk.
# --------------------------------------------------------------------------- #
def _to_ref(bundle, atlas2native, out_name, tmp_path):
    from swane.nipype_pipeline.nodes.DipyBundlesToRef import DipyBundlesToRef

    node = DipyBundlesToRef()
    node.inputs.bundle = bundle
    node.inputs.atlas2native = atlas2native
    node.inputs.out_name = out_name
    node.inputs.out_vtp = str(tmp_path / (out_name + ".vtp"))
    node.run()
    return node._list_outputs()["bundle_vtp"]


def _read_vtp_points(path):
    from vtkmodules.vtkIOXML import vtkXMLPolyDataReader
    from vtkmodules.util.numpy_support import vtk_to_numpy

    reader = vtkXMLPolyDataReader()
    reader.SetFileName(path)
    reader.Update()
    pd = reader.GetOutput()
    return pd, vtk_to_numpy(pd.GetPoints().GetData())


class TestBundlesToRef:
    def _write_atlas2native(self, tmp_path, matrix):
        path = str(tmp_path / "atlas2native.txt")
        np.savetxt(path, matrix)
        return path

    def test_writes_reference_space_vtp_via_vtk(self, workspace, tmp_path):
        # A known atlas->native transform: translate x by +100, scale nothing.
        matrix = np.eye(4)
        matrix[0, 3] = 100.0
        atlas2native = self._write_atlas2native(tmp_path, matrix)

        bundle = _indexed_streamlines(5, tmp_path, name="bundle.trx")
        atlas_pts = np.vstack([np.asarray(sl) for sl in _load_streamlines(bundle)])

        out = _to_ref(bundle, atlas2native, "r-af_lh", tmp_path)
        assert out.endswith(".vtp")
        assert os.path.exists(out)

        pd, ref_pts = _read_vtp_points(out)
        assert pd.GetNumberOfLines() == 5
        # Points landed in reference space (x shifted by +100, y/z unchanged),
        # then converted from RASMM to the LPS millimetres a plain VTK model
        # file carries (x, y negated).
        expected = atlas_pts.copy()
        expected[:, 0] += 100.0
        expected[:, 0] *= -1
        expected[:, 1] *= -1
        assert np.allclose(
            np.sort(ref_pts, axis=0), np.sort(expected, axis=0), atol=1e-3
        )

    def test_written_points_are_lps(self, workspace, tmp_path):
        atlas2native = self._write_atlas2native(tmp_path, np.eye(4))
        bundle = _indexed_streamlines(3, tmp_path, name="bundle.trx")
        atlas_pts = np.vstack([np.asarray(sl) for sl in _load_streamlines(bundle)])

        out = _to_ref(bundle, atlas2native, "r-cst_lh", tmp_path)
        _, ras_lps_pts = _read_vtp_points(out)

        # x, y negated (RAS -> LPS), z unchanged.
        recovered_rasmm = ras_lps_pts.copy()
        recovered_rasmm[:, 0] *= -1
        recovered_rasmm[:, 1] *= -1
        assert np.allclose(
            np.sort(recovered_rasmm, axis=0), np.sort(atlas_pts, axis=0), atol=1e-3
        )

    def test_written_without_fury(self, workspace, tmp_path, monkeypatch):
        """``fury`` is not installed; the node must write PolyData with ``vtk``
        directly. Poison the import so any accidental ``fury`` use fails loudly."""
        import builtins

        real_import = builtins.__import__

        def _no_fury(name, *args, **kwargs):
            if name == "fury" or name.startswith("fury."):
                raise ImportError("fury must not be used to write .vtp")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _no_fury)

        atlas2native = self._write_atlas2native(tmp_path, np.eye(4))
        bundle = _indexed_streamlines(3, tmp_path, name="bundle.trx")
        out = _to_ref(bundle, atlas2native, "r-cst_rh", tmp_path)
        assert os.path.exists(out)

    def test_empty_bundle_writes_valid_empty_vtp(self, workspace, tmp_path):
        from dipy.tracking.streamline import Streamlines

        empty = tmp_path / "empty.trx"
        _save(Streamlines([]), str(empty))
        atlas2native = self._write_atlas2native(tmp_path, np.eye(4))

        out = _to_ref(str(empty), atlas2native, "r-af_rh", tmp_path)
        pd, _ = _read_vtp_points(out)
        assert pd.GetNumberOfLines() == 0


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
# Recognition parameters.
# --------------------------------------------------------------------------- #
class TestRecognitionParameters:
    def test_unlisted_tract_gets_the_default_configuration(self):
        params = recognition_params("ILF_L")
        assert params["model_clust_thr"] == 2.5
        assert params["reduction_thr"] == 15.0
        assert params["pruning_thr"] == 5.0
        assert params["refine"] is True
        assert params["r_reduction_thr"] == 12.0
        assert params["r_pruning_thr"] == 4.0

    @pytest.mark.parametrize("name", ["AF_L", "AF_R", "OR_L", "OR_R", "F_L", "F_R"])
    def test_tract_of_strips_the_side_suffix(self, name):
        assert tract_of(name) == name.rsplit("_", 1)[0]

    @pytest.mark.parametrize(
        "tract, sides",
        [("OR", ("OR_L", "OR_R")), ("F", ("F_L", "F_R")), ("CST", ("CST_L", "CST_R"))],
    )
    def test_both_sides_of_an_overridden_tract_get_identical_parameters(
        self, tract, sides
    ):
        """Overrides are keyed by tract, never by bundle: the two sides of one
        tract must never be recognised with different parameters, or any
        left-right difference in the result is partly our own doing."""
        left, right = (recognition_params(name) for name in sides)
        assert left == right
        assert left != RECOGNITION_DEFAULTS

    def test_every_tract_has_identical_parameters_on_both_sides(self):
        from swane.nipype_pipeline.workflows.dipy_bundle_workflow import (
            DIPY_TRACT_ATLAS,
            SIDES,
            _SIDE_SUFFIX,
        )

        for base in DIPY_TRACT_ATLAS.values():
            params = [
                recognition_params("%s_%s" % (base, _SIDE_SUFFIX[side]))
                for side in SIDES
            ]
            assert params[0] == params[1], base

    def test_result_is_a_copy_not_the_shared_table(self):
        """Callers mutate the returned dict (the workflow does); the module
        table must not drift."""
        params = recognition_params("ILF_L")
        params["reduction_thr"] = 999.0
        assert RECOGNITION_DEFAULTS["reduction_thr"] == 15.0
        assert recognition_params("ILF_L")["reduction_thr"] == 15.0

    def test_every_override_names_a_real_atlas_tract(self):
        """A typo in the override table would silently ship the defaults."""
        from swane.nipype_pipeline.workflows.dipy_bundle_workflow import (
            DIPY_TRACT_ATLAS,
        )

        assert set(RECOGNITION_OVERRIDES) <= set(DIPY_TRACT_ATLAS.values())

    def test_node_defaults_match_the_default_table(self):
        """The node must be usable standalone at the shipped configuration."""
        node = DipyRecoBundlesRecognize()
        for trait, value in RECOGNITION_DEFAULTS.items():
            assert getattr(node.inputs, trait) == value


class TestRefinePass:
    """dipy's auto-calibration pass rebuilds the search space from the bundle
    recognised in this subject instead of the atlas model."""

    def test_refine_runs_after_recognize_when_enabled(
        self, workspace, atlas_dir, tmp_path, monkeypatch
    ):
        subject = _subject_with_ifof(tmp_path)
        pkl = _build(subject, str(tmp_path / "build.pkl"))

        calls = []
        from dipy.segment.bundles import RecoBundles

        original = RecoBundles.refine

        def spy(self, model_bundle, pruned_streamlines, model_clust_thr, **kwargs):
            calls.append(
                (
                    model_clust_thr,
                    kwargs.get("reduction_thr"),
                    kwargs.get("pruning_thr"),
                )
            )
            return original(
                self, model_bundle, pruned_streamlines, model_clust_thr, **kwargs
            )

        monkeypatch.setattr(RecoBundles, "refine", spy)
        _recognize(
            pkl,
            subject,
            atlas_dir,
            "IFOF_R",
            str(tmp_path / "out.trx"),
            refine=True,
            r_reduction_thr=12.0,
            r_pruning_thr=4.0,
        )
        assert calls == [(2.5, 12.0, 4.0)]

    def test_refine_is_skipped_when_disabled(
        self, workspace, atlas_dir, tmp_path, monkeypatch
    ):
        subject = _subject_with_ifof(tmp_path)
        pkl = _build(subject, str(tmp_path / "build.pkl"))

        from dipy.segment.bundles import RecoBundles

        def boom(self, *args, **kwargs):
            raise AssertionError("refine must not run when refine=False")

        monkeypatch.setattr(RecoBundles, "refine", boom)
        out = _recognize(
            pkl,
            subject,
            atlas_dir,
            "IFOF_R",
            str(tmp_path / "out.trx"),
            refine=False,
        )
        assert os.path.exists(out)

    def test_refine_is_skipped_on_an_empty_first_pass(
        self, workspace, atlas_dir, tmp_path, monkeypatch
    ):
        """dipy's refine clusters the first-pass bundle, which is meaningless
        with nothing (or one streamline) recognised."""
        subject = _subject_without_ifof(tmp_path)
        pkl = _build(subject, str(tmp_path / "build.pkl"))

        from dipy.segment.bundles import RecoBundles

        def boom(self, *args, **kwargs):
            raise AssertionError("refine must not run on an empty first pass")

        monkeypatch.setattr(RecoBundles, "refine", boom)
        out = _recognize(
            pkl,
            subject,
            atlas_dir,
            "IFOF_R",
            str(tmp_path / "out.trx"),
            refine=True,
            reduction_thr=1.0,
            pruning_thr=1.0,
        )
        assert _n_streamlines(out) <= 1
