"""Per-tract RecoBundles recognition workflow (the dipy engine's Phase-2 half).

One instance of this workflow is built **per selected tract** (spec section 6),
mirroring the FSL :func:`~swane.nipype_pipeline.workflows.tractography_workflow.
tractography_workflow`. Unlike the FSL path, the expensive work -- the
whole-brain SLR against the HCP842 atlas and the RecoBundles build (QuickBundlesX
clustering) -- has already run **once**, shared, in
:func:`~swane.nipype_pipeline.workflows.dipy_dti_preproc_workflow.
dipy_dti_preproc_workflow`. This workflow therefore only *recognises* the tract's
model bundle from the pre-built pickle(s), so each tract completes and reports
independently without repeating the clustering.

Per side (``lh``/``rh`` -> the atlas's ``_L``/``_R`` convention) the chain is:

``DipyRecoBundlesRecognize`` -> ``DipyBundleUnion`` -> ``DipyBundlesToRef`` ->
``outputnode.bundle_lh``/``bundle_rh`` (``.vtp``, reference space).

The recognise node is always a :class:`nipype.MapNode` over the shared build
pickles and their ``.trx`` chunks, iterated in lockstep with the same
recognition parameters. The number of chunks is decided at scheduling time by
the preproc chunker's RAM estimator, so the shared ``recobundles_builds`` /
``recobundles_chunks`` lists have a runtime length the MapNode fans out over: a
single chunk yields a one-element MapNode, a chunked build an N-element one.
:class:`DipyBundleUnion` concatenates the partials (a pass-through for one).

The fornix is the one tract the atlas ships side-combined (``F_L_R.trk``); a
:class:`~swane.nipype_pipeline.nodes.DipyFornixSplit.DipyFornixSplit` lateralises
it into ``F_L``/``F_R`` (once, on the shared atlas) and its ``atlas_dir``
passthrough orders the two fornix recognitions after it. Every other tract takes
``atlas_dir`` straight from the inputnode.

New dipy nodes implement HARD_CAP only, so this factory takes no
``multicore_node_limit`` parameter (spec section 10).
"""

from nipype import Node, MapNode, IdentityInterface

from swane.nipype_pipeline.engine.CustomWorkflow import CustomWorkflow
from swane.nipype_pipeline.nodes.DipyRecoBundles import (
    DipyRecoBundlesRecognize,
    recognition_params,
)
from swane.nipype_pipeline.nodes.DipyBundleUnion import DipyBundleUnion
from swane.nipype_pipeline.nodes.DipyBundlesToRef import DipyBundlesToRef
from swane.nipype_pipeline.nodes.DipyFornixSplit import DipyFornixSplit
from swane.nipype_pipeline.nodes.ram_estimators import RecoBundlesRamEstimator

# Fixed per-node memory reservations (GB), no estimator: all three nodes work
# on one recognised tract's streamlines (a small subset of the whole-brain
# tractogram RecoBundles selects from), never the whole tractogram, so their
# RAM does not scale with subject size the way the preproc nodes' does.
# Isolated tree-peak RSS on a real recognised bundle measured 0.15-0.2 GB for
# union/to_ref; both are rounded up to a 1 GB floor (RAM audit, 2026-09-12).
_MEM_GB = {
    "union": 1.0,
    "to_ref": 1.0,
    # fornix_split runs once per shared atlas directory, on the atlas's own
    # fixed-size F_L_R.trk (no subject data at all); measured 0.17 GB.
    "fornix_split": 0.5,
}

# lh/rh -> the atlas's left/right model-file suffix.
SIDES = ["lh", "rh"]
_SIDE_SUFFIX = {"lh": "L", "rh": "R"}

# The SWANe tract key -> the atlas model-bundle basename (spec section 3,
# verified against the downloaded HCP842 atlas). Every value is bilateral: the
# per-side model file is ``<base>_L`` / ``<base>_R``. ``fx`` maps to ``F`` and is
# the one tract needing DipyFornixSplit (the atlas ships F_L_R combined);
# ``cingulum`` is dipy-only. Tracts with no atlas counterpart
# (``atr``/``str``/``cbd``/``cbp``/``cbt`` -- greyed on dipy -- and the
# non-bilateral ``fma``/``fmi``/``mcp``/``ac``) are deliberately absent, so
# :func:`dipy_bundle_workflow` returns ``None`` for them.
DIPY_TRACT_ATLAS = {
    "af": "AF",
    "ar": "AR",
    "cst": "CST",
    "fa": "AST",
    "ifo": "IFOF",
    "ilf": "ILF",
    "mdlf": "MdLF",
    "or": "OR",
    "uf": "UF",
    "vof": "VOF",
    "fx": "F",
    "cingulum": "C",
}

# The one tract lateralised from a side-combined atlas file (see DipyFornixSplit).
_FORNIX_TRACT = "fx"


def dipy_bundle_workflow(
    name: str,
    num_threads: int = 1,
    base_dir: str = "/",
) -> CustomWorkflow:
    """
    Per-tract RecoBundles recognition to reference-space ``.vtp`` bundles.

    Parameters
    ----------
    name : str
        The SWANe tract key (e.g. ``"af"``, ``"fx"``, ``"cingulum"``). A tract
        with no HCP842 atlas counterpart returns ``None`` (no bundle workflow).
    num_threads : int, optional
        OpenMP/BLAS thread count the recognise nodes declare (HARD_CAP). The
        default is 1.
    base_dir : path, optional
        The base directory path relative to the parent workflow. The default is
        "/".

    Input Node Fields
    ----------
    recobundles_builds : list of path
        The shared per-chunk RecoBundles build pickles (from preproc).
    recobundles_chunks : list of path
        The shared per-chunk ``.trx`` (atlas space) the builds were made on; the
        recognise nodes reload their streamlines (they are not in the pickle).
    atlas2native : path
        The 4x4 atlas->native (reference) transform (from preproc's single SLR).
    atlas_dir : path
        Local DIPY_HOME holding the HCP842 atlas.

    Returns
    -------
    workflow : CustomWorkflow or None
        The per-tract bundle recognition workflow, or ``None`` when ``name`` has
        no atlas counterpart.

    Output Node Fields
    ----------
    bundle_lh : path
        The left recognised bundle in reference space (``.vtp``).
    bundle_rh : path
        The right recognised bundle in reference space (``.vtp``).
    """

    atlas_base = DIPY_TRACT_ATLAS.get(name)
    if atlas_base is None:
        return None

    workflow = CustomWorkflow(name="bundle_" + name, base_dir=base_dir)

    inputnode = Node(
        IdentityInterface(
            fields=[
                "recobundles_builds",
                "recobundles_chunks",
                "atlas2native",
                "atlas_dir",
            ]
        ),
        name="inputnode",
    )

    outputnode = Node(
        IdentityInterface(fields=["bundle_lh", "bundle_rh"]),
        name="outputnode",
    )

    # The fornix is the one tract the atlas ships side-combined: split it once
    # (on the shared atlas) and take atlas_dir from the split's passthrough so
    # the two fornix recognitions run only after F_L.trk/F_R.trk exist.
    is_fornix = name == _FORNIX_TRACT
    if is_fornix:
        fornix_split = Node(DipyFornixSplit(), name="fornix_split")
        fornix_split._mem_gb = _MEM_GB["fornix_split"]
        workflow.connect(inputnode, "atlas_dir", fornix_split, "atlas_dir")
        atlas_dir_source = (fornix_split, "atlas_dir")
    else:
        atlas_dir_source = (inputnode, "atlas_dir")

    for side in SIDES:
        model_bundle_name = "%s_%s" % (atlas_base, _SIDE_SUFFIX[side])

        # Always a MapNode over the shared build pickles and their chunks,
        # iterated in lockstep (nipype zips multiple iterfields by index). The
        # list length is a runtime property (the preproc chunker chooses the
        # chunk count from the RAM budget), so the MapNode fans out over however
        # many chunks exist -- one element for an unsplit build, N for a split.
        recognize = MapNode(
            DipyRecoBundlesRecognize(),
            name="recognize_%s" % side,
            iterfield=["recobundles_pickle", "tractogram_chunk"],
        )
        # RAM is reserved at scheduling time from each chunk's point count; the
        # MapNode propagates the estimator to every mapped subnode, so each is
        # priced from its own chunk. The static value is only the
        # negotiation-failed fail-safe.
        recognize._mem_gb = RecoBundlesRamEstimator.STATIC_FALLBACK_GB
        recognize.ram_estimator = RecoBundlesRamEstimator()
        workflow.connect(
            inputnode, "recobundles_builds", recognize, "recobundles_pickle"
        )
        workflow.connect(inputnode, "recobundles_chunks", recognize, "tractogram_chunk")

        recognize.inputs.model_bundle_name = model_bundle_name
        recognize.inputs.num_threads = num_threads

        # The recognition parameters for this tract (both sides share them), the
        # same for any number of chunks.
        params = recognition_params(model_bundle_name)
        for trait, value in params.items():
            setattr(recognize.inputs, trait, value)
        workflow.connect(
            atlas_dir_source[0], atlas_dir_source[1], recognize, "atlas_dir"
        )

        # Union the per-chunk partials (a pass-through for a single chunk); the
        # recognise MapNode emits the list the union's InputMultiPath consumes.
        union = Node(DipyBundleUnion(), name="union_%s" % side)
        union._mem_gb = _MEM_GB["union"]
        workflow.connect(recognize, "recognized_bundle", union, "recognized_bundles")

        # Transform the recognised (atlas-space) bundle back to reference space
        # and write the .vtp result contract.
        to_ref = Node(DipyBundlesToRef(), name="to_ref_%s" % side)
        to_ref._mem_gb = _MEM_GB["to_ref"]
        to_ref.inputs.out_name = "r-%s_%s" % (name, side)
        workflow.connect(union, "bundle", to_ref, "bundle")
        workflow.connect(inputnode, "atlas2native", to_ref, "atlas2native")

        workflow.connect(to_ref, "bundle_vtp", outputnode, "bundle_%s" % side)

    return workflow
