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

* **Single chunk** (the default): one recognise :class:`nipype.Node` reads the
  single build pickle and its ``.trx`` chunk (element 0 of the shared lists) and
  runs with ``slr=True`` -- the per-bundle local SLR is valid on a whole
  tractogram. :class:`DipyBundleUnion` is a pass-through of the one partial.
* **Chunked build** (``n_chunks > 1``): a recognise :class:`nipype.MapNode`
  iterates the build pickles and their chunks in lockstep, and ``slr`` is forced
  **off** -- a union of per-chunk local SLRs is not a valid registration.
  :class:`DipyBundleUnion` concatenates the N partials.

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


# Return element 0 of a list -- the single build/chunk of an unchunked run.
# Used as an inline connection transform so a single recognise Node consumes the
# one-element ``recobundles_builds``/``recobundles_chunks`` lists the preproc
# always publishes (the chunker and build MapNode emit lists even for
# ``n_chunks == 1``). Kept docstring-free so its captured source stays a stable
# one-liner in the golden connection snapshots (a docstring would be dumped
# verbatim on every edge, unlike a comment, which the snapshot's AST round-trip
# drops).
def _first(items):
    return items[0]


def dipy_bundle_workflow(
    name: str,
    n_chunks: int = 1,
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
    n_chunks : int, optional
        The number of representative sub-tractograms the shared build was split
        into (the length of ``recobundles_builds``/``recobundles_chunks``). 1
        (the default) recognises with a single Node and ``slr=True``; more than 1
        recognises with a MapNode over the builds and ``slr=False``.
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

    # A chunked build's per-chunk local SLRs cannot be unioned into one valid
    # registration, so recognition runs with slr off; a single (whole) chunk
    # keeps the per-bundle local SLR on.
    chunked = n_chunks > 1
    slr = not chunked

    # The fornix is the one tract the atlas ships side-combined: split it once
    # (on the shared atlas) and take atlas_dir from the split's passthrough so
    # the two fornix recognitions run only after F_L.trk/F_R.trk exist.
    is_fornix = name == _FORNIX_TRACT
    if is_fornix:
        fornix_split = Node(DipyFornixSplit(), name="fornix_split")
        workflow.connect(inputnode, "atlas_dir", fornix_split, "atlas_dir")
        atlas_dir_source = (fornix_split, "atlas_dir")
    else:
        atlas_dir_source = (inputnode, "atlas_dir")

    for side in SIDES:
        model_bundle_name = "%s_%s" % (atlas_base, _SIDE_SUFFIX[side])

        if chunked:
            # A MapNode over the shared build pickles and their chunks, iterated
            # in lockstep (nipype zips multiple iterfields by index).
            recognize = MapNode(
                DipyRecoBundlesRecognize(),
                name="recognize_%s" % side,
                iterfield=["recobundles_pickle", "tractogram_chunk"],
            )
            workflow.connect(
                inputnode, "recobundles_builds", recognize, "recobundles_pickle"
            )
            workflow.connect(
                inputnode, "recobundles_chunks", recognize, "tractogram_chunk"
            )
        else:
            # A single recognise Node reads the one build/chunk (element 0 of the
            # one-element shared lists the preproc always publishes).
            recognize = Node(DipyRecoBundlesRecognize(), name="recognize_%s" % side)
            workflow.connect(
                inputnode,
                ("recobundles_builds", _first),
                recognize,
                "recobundles_pickle",
            )
            workflow.connect(
                inputnode,
                ("recobundles_chunks", _first),
                recognize,
                "tractogram_chunk",
            )

        recognize.inputs.model_bundle_name = model_bundle_name
        recognize.inputs.num_threads = num_threads
        recognize.inputs.slr = slr

        # The recognition parameters for this tract (both sides share them).
        # A chunked build forces the refine pass off for the same reason it
        # forces the per-bundle local SLR off -- refine registers the model to
        # the subject's own first-pass bundle, and a union of per-chunk
        # registrations is not a valid one. The shipped thresholds assume both
        # are on, so a chunked path must re-derive them rather than inherit
        # these.
        params = recognition_params(model_bundle_name)
        if chunked:
            params["refine"] = False
        for trait, value in params.items():
            setattr(recognize.inputs, trait, value)
        workflow.connect(
            atlas_dir_source[0], atlas_dir_source[1], recognize, "atlas_dir"
        )

        # Union the per-chunk partials (pass-through for a single chunk). A single
        # recognise Node's scalar output coerces to a one-element list on the
        # union's InputMultiPath; a MapNode already emits the list.
        union = Node(DipyBundleUnion(), name="union_%s" % side)
        workflow.connect(recognize, "recognized_bundle", union, "recognized_bundles")

        # Transform the recognised (atlas-space) bundle back to reference space
        # and write the .vtp result contract.
        to_ref = Node(DipyBundlesToRef(), name="to_ref_%s" % side)
        to_ref.inputs.out_name = "r-%s_%s" % (name, side)
        workflow.connect(union, "bundle", to_ref, "bundle")
        workflow.connect(inputnode, "atlas2native", to_ref, "atlas2native")

        workflow.connect(to_ref, "bundle_vtp", outputnode, "bundle_%s" % side)

    return workflow
