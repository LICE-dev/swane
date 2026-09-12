"""Wiring assertions for
:func:`swane.nipype_pipeline.workflows.dipy_bundle_workflow.dipy_bundle_workflow`.

The bundle workflow is instantiated **once per selected tract** and consumes the
shared RecoBundles build(s) the preproc workflow produced once per subject. It
must therefore never re-run the whole-brain SLR or the build/clustering: per side
it only *recognises* one atlas model bundle from a pre-built pickle, unions the
per-chunk partials, and transforms the result back to reference space as ``.vtp``.

These are graph-shape checks (independent of the golden byte snapshots): the
per-side recognise -> union -> to-ref chain, the recognition parameters staying
the same for any number of chunks (a single chunk recognises with a plain Node,
a chunked build with a MapNode over the builds), the tract->atlas model
mapping (``af``->``AF_L``/``AF_R``, ``fx``->``F_L``/``F_R``, ``cingulum``->
``C_L``/``C_R``), the fornix split ordered before the fornix recognitions, and the
``r-<tract>_<side>.vtp`` result names on ``outputnode.bundle_lh``/``bundle_rh``.
"""

import pytest

from swane.nipype_pipeline.workflows.dipy_bundle_workflow import dipy_bundle_workflow


# --------------------------------------------------------------------------- #
# Helpers mirroring test_dipy_dti_wiring.py.
# --------------------------------------------------------------------------- #
def _iface(node):
    return type(node.interface).__name__


def _incoming(wf, dst_node):
    conns = []
    for src, dst, data in wf._graph.edges(data=True):
        if dst is dst_node:
            for src_field, dst_field in data.get("connect", []):
                conns.append((src, src_field, dst_field))
    return conns


def _nodes_by_iface(wf, iface_name):
    return [n for n in wf._graph.nodes() if _iface(n) == iface_name]


def _node_by_name(wf, name):
    return next(n for n in wf._graph.nodes() if n.name == name)


def _src_field_name(src_field):
    """The source field of a connection, whether plain or an inline-transform.

    A single-chunk connection picks element 0 of a list via an inline function,
    so nipype stores the source endpoint as ``(field, func_source, args)``; a
    MapNode connection carries the whole list, so it is the plain field name.
    """
    return src_field[0] if isinstance(src_field, tuple) else src_field


def _is_indexed(src_field):
    return isinstance(src_field, tuple)


# --------------------------------------------------------------------------- #
# af: a plain bilateral tract, single chunk (the default).
# --------------------------------------------------------------------------- #
class TestBilateralSingleChunk:
    @pytest.fixture
    def af_wf(self):
        return dipy_bundle_workflow("af", n_chunks=1, num_threads=4)

    def test_inputnode_fields(self, af_wf):
        inputnode = _node_by_name(af_wf, "inputnode")
        fields = set(inputnode.interface._fields)
        assert {
            "recobundles_builds",
            "recobundles_chunks",
            "atlas2native",
            "atlas_dir",
        } <= fields

    def test_outputnode_advertises_both_sides(self, af_wf):
        outputnode = _node_by_name(af_wf, "outputnode")
        fields = set(outputnode.interface._fields)
        assert {"bundle_lh", "bundle_rh"} <= fields

    def test_no_build_chunker_or_slr_nodes(self, af_wf):
        """The build/clustering and whole-brain SLR ran once in preproc; the
        bundle workflow must not repeat them."""
        assert _nodes_by_iface(af_wf, "DipyRecoBundlesBuild") == []
        assert _nodes_by_iface(af_wf, "DipyTractogramChunker") == []
        assert _nodes_by_iface(af_wf, "DipyAtlasSLR") == []

    def test_one_recognize_union_toref_per_side(self, af_wf):
        assert len(_nodes_by_iface(af_wf, "DipyRecoBundlesRecognize")) == 2
        assert len(_nodes_by_iface(af_wf, "DipyBundleUnion")) == 2
        assert len(_nodes_by_iface(af_wf, "DipyBundlesToRef")) == 2

    def test_recognize_is_a_plain_node_with_slr_on(self, af_wf):
        for recog in _nodes_by_iface(af_wf, "DipyRecoBundlesRecognize"):
            # single chunk -> a plain Node, not a MapNode
            assert not getattr(recog, "iterfield", None)
            assert recog.inputs.slr is True

    def test_side_model_mapping(self, af_wf):
        names = {
            r.inputs.model_bundle_name
            for r in _nodes_by_iface(af_wf, "DipyRecoBundlesRecognize")
        }
        assert names == {"AF_L", "AF_R"}

    def test_no_fornix_split_node(self, af_wf):
        assert _nodes_by_iface(af_wf, "DipyFornixSplit") == []

    def test_recognize_consumes_first_build_and_chunk_and_inputnode_atlas_dir(
        self, af_wf
    ):
        inputnode = _node_by_name(af_wf, "inputnode")
        for recog in _nodes_by_iface(af_wf, "DipyRecoBundlesRecognize"):
            inc = _incoming(af_wf, recog)
            pickle_edges = [c for c in inc if c[2] == "recobundles_pickle"]
            chunk_edges = [c for c in inc if c[2] == "tractogram_chunk"]
            atlas_edges = [c for c in inc if c[2] == "atlas_dir"]
            assert len(pickle_edges) == 1
            assert len(chunk_edges) == 1
            assert len(atlas_edges) == 1
            (src, sf, _) = pickle_edges[0]
            assert src is inputnode
            assert _src_field_name(sf) == "recobundles_builds"
            # single chunk -> picks element 0 of the list
            assert _is_indexed(sf)
            (src, sf, _) = chunk_edges[0]
            assert src is inputnode
            assert _src_field_name(sf) == "recobundles_chunks"
            assert _is_indexed(sf)
            # non-fornix: atlas_dir straight from inputnode
            (src, sf, _) = atlas_edges[0]
            assert src is inputnode
            assert _src_field_name(sf) == "atlas_dir"

    def test_recognize_union_toref_outputnode_chain(self, af_wf):
        outputnode = _node_by_name(af_wf, "outputnode")
        for side, model in (("lh", "AF_L"), ("rh", "AF_R")):
            recog = next(
                r
                for r in _nodes_by_iface(af_wf, "DipyRecoBundlesRecognize")
                if r.inputs.model_bundle_name == model
            )
            # recognize -> union
            union = next(
                u
                for u in _nodes_by_iface(af_wf, "DipyBundleUnion")
                if (recog, "recognized_bundle", "recognized_bundles")
                in _incoming(af_wf, u)
            )
            # union -> to_ref
            to_ref = next(
                t
                for t in _nodes_by_iface(af_wf, "DipyBundlesToRef")
                if (union, "bundle", "bundle") in _incoming(af_wf, t)
            )
            assert to_ref.inputs.out_name == "r-af_%s" % side
            # to_ref.atlas2native comes from inputnode
            inputnode = _node_by_name(af_wf, "inputnode")
            assert (inputnode, "atlas2native", "atlas2native") in _incoming(
                af_wf, to_ref
            )
            # to_ref -> outputnode.bundle_<side>
            assert (to_ref, "bundle_vtp", "bundle_%s" % side) in _incoming(
                af_wf, outputnode
            )


# --------------------------------------------------------------------------- #
# fx: the fornix special case (split before recognition).
# --------------------------------------------------------------------------- #
class TestFornix:
    @pytest.fixture
    def fx_wf(self):
        return dipy_bundle_workflow("fx", n_chunks=1, num_threads=4)

    def test_fornix_split_present(self, fx_wf):
        assert len(_nodes_by_iface(fx_wf, "DipyFornixSplit")) == 1

    def test_model_mapping_is_lateralised_fornix(self, fx_wf):
        names = {
            r.inputs.model_bundle_name
            for r in _nodes_by_iface(fx_wf, "DipyRecoBundlesRecognize")
        }
        assert names == {"F_L", "F_R"}

    def test_recognitions_ordered_after_the_split(self, fx_wf):
        """The fornix recognitions take atlas_dir from the split's passthrough
        output (so they run only once F_L.trk/F_R.trk exist), not from
        inputnode."""
        split = _nodes_by_iface(fx_wf, "DipyFornixSplit")[0]
        inputnode = _node_by_name(fx_wf, "inputnode")
        # the split takes atlas_dir from inputnode
        assert (inputnode, "atlas_dir", "atlas_dir") in _incoming(fx_wf, split)
        for recog in _nodes_by_iface(fx_wf, "DipyRecoBundlesRecognize"):
            atlas_edges = [c for c in _incoming(fx_wf, recog) if c[2] == "atlas_dir"]
            assert len(atlas_edges) == 1
            (src, sf, _) = atlas_edges[0]
            assert src is split
            assert _src_field_name(sf) == "atlas_dir"

    def test_result_names(self, fx_wf):
        names = {t.inputs.out_name for t in _nodes_by_iface(fx_wf, "DipyBundlesToRef")}
        assert names == {"r-fx_lh", "r-fx_rh"}


# --------------------------------------------------------------------------- #
# cingulum: a dipy-only bilateral tract mapping to C_L/C_R.
# --------------------------------------------------------------------------- #
class TestCingulum:
    @pytest.fixture
    def cing_wf(self):
        return dipy_bundle_workflow("cingulum", n_chunks=1, num_threads=4)

    def test_model_mapping(self, cing_wf):
        names = {
            r.inputs.model_bundle_name
            for r in _nodes_by_iface(cing_wf, "DipyRecoBundlesRecognize")
        }
        assert names == {"C_L", "C_R"}

    def test_no_fornix_split(self, cing_wf):
        assert _nodes_by_iface(cing_wf, "DipyFornixSplit") == []

    def test_result_names(self, cing_wf):
        names = {
            t.inputs.out_name for t in _nodes_by_iface(cing_wf, "DipyBundlesToRef")
        }
        assert names == {"r-cingulum_lh", "r-cingulum_rh"}


# --------------------------------------------------------------------------- #
# chunked build: a recognise MapNode over the builds, slr forced off.
# --------------------------------------------------------------------------- #
class TestChunkedBuild:
    @pytest.fixture
    def af_chunked(self):
        return dipy_bundle_workflow("af", n_chunks=3, num_threads=4)

    def test_recognize_is_a_mapnode_over_builds_and_chunks(self, af_chunked):
        recogs = _nodes_by_iface(af_chunked, "DipyRecoBundlesRecognize")
        assert len(recogs) == 2  # still one per side
        for recog in recogs:
            assert set(getattr(recog, "iterfield", [])) == {
                "recobundles_pickle",
                "tractogram_chunk",
            }

    def test_refine_stays_on_when_chunked(self, af_chunked):
        """The recognition parameters do not depend on the number of chunks."""
        for side in ("lh", "rh"):
            recog = af_chunked.get_node("recognize_%s" % side)
            assert recog.inputs.refine is True

    def test_slr_stays_on_when_chunked(self, af_chunked):
        for recog in _nodes_by_iface(af_chunked, "DipyRecoBundlesRecognize"):
            assert recog.inputs.slr is True

    def test_mapnode_consumes_the_whole_build_and_chunk_lists(self, af_chunked):
        inputnode = _node_by_name(af_chunked, "inputnode")
        for recog in _nodes_by_iface(af_chunked, "DipyRecoBundlesRecognize"):
            inc = _incoming(af_chunked, recog)
            (src, sf, _) = next(c for c in inc if c[2] == "recobundles_pickle")
            assert src is inputnode
            assert sf == "recobundles_builds"  # whole list, not indexed
            (src, sf, _) = next(c for c in inc if c[2] == "tractogram_chunk")
            assert src is inputnode
            assert sf == "recobundles_chunks"


# --------------------------------------------------------------------------- #
# an unmapped tract has no bundle workflow to build.
# --------------------------------------------------------------------------- #
class TestUnmappedTract:
    @pytest.mark.parametrize("tract", ["atr", "str", "cbd", "cbp", "cbt", "ac"])
    def test_unmapped_tract_returns_none(self, tract):
        assert dipy_bundle_workflow(tract, n_chunks=1) is None


# --------------------------------------------------------------------------- #
# The recognition parameters reach the recognise nodes, identically per side.
# --------------------------------------------------------------------------- #
class TestRecognitionParametersAreApplied:
    def test_default_configuration_on_an_unlisted_tract(self):
        wf = dipy_bundle_workflow("ilf", n_chunks=1, num_threads=4)
        for side in ("lh", "rh"):
            recog = wf.get_node("recognize_%s" % side)
            assert recog.inputs.model_clust_thr == 2.5
            assert recog.inputs.reduction_thr == 15.0
            assert recog.inputs.pruning_thr == 5.0
            assert recog.inputs.refine is True
            assert recog.inputs.r_reduction_thr == 12.0
            assert recog.inputs.r_pruning_thr == 4.0

    @pytest.mark.parametrize(
        "tract",
        ["af", "ar", "cst", "fa", "ifo", "ilf", "mdlf", "or", "uf", "vof", "fx"],
    )
    def test_both_sides_of_every_tract_share_one_configuration(self, tract):
        """Left and right are the same structure and are routinely compared, so
        they must never be recognised with different parameters."""
        wf = dipy_bundle_workflow(tract, n_chunks=1, num_threads=4)
        traits = (
            "model_clust_thr",
            "reduction_thr",
            "pruning_thr",
            "refine",
            "r_reduction_thr",
            "r_pruning_thr",
        )
        left = wf.get_node("recognize_lh").inputs
        right = wf.get_node("recognize_rh").inputs
        for trait in traits:
            assert getattr(left, trait) == getattr(right, trait), trait

    def test_overridden_tract_applies_to_both_sides(self):
        wf = dipy_bundle_workflow("or", n_chunks=1, num_threads=4)
        for side in ("lh", "rh"):
            recog = wf.get_node("recognize_%s" % side)
            assert (recog.inputs.r_reduction_thr, recog.inputs.r_pruning_thr) == (
                14.0,
                6.0,
            )
