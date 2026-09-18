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

``DipyRecoBundlesRecognize`` -> ``DipyBundleUnion`` -> ``DipyBundleRecovery`` ->
``DipyBundlesToRef`` -> ``outputnode.bundle_lh``/``bundle_rh`` (``.vtp``,
reference space), with ``outputnode.flag_lh``/``flag_rh`` a sidecar written only
for a low-confidence bundle.

The recognise node is always a :class:`nipype.MapNode` over the shared build
pickles and their ``.trx`` chunks, iterated in lockstep with the same
recognition parameters. The number of chunks is decided at scheduling time by
the preproc chunker's RAM estimator, so the shared ``recobundles_builds`` /
``recobundles_chunks`` lists have a runtime length the MapNode fans out over: a
single chunk yields a one-element MapNode, a chunked build an N-element one.
:class:`DipyBundleUnion` concatenates the partials (a pass-through for one).
:class:`DipyBundleRecovery` then scores the concatenated bundle against the atlas
model and, when it looks contaminated or scarce, retries recognition once with an
adjusted configuration, keeping whichever result matches the model better.

The fornix is the one tract the atlas ships side-combined (``F_L_R.trk``);
it is processed as a single bilateral bundle (``bundle_bilateral``), unlike
other tracts which are processed per side.

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
from swane.nipype_pipeline.nodes.DipyBundleRecovery import DipyBundleRecovery
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
}

# lh/rh -> the atlas's left/right model-file suffix.
SIDES = ["lh", "rh"]
_SIDE_SUFFIX = {"lh": "L", "rh": "R"}

# The SWANe tract key -> the atlas model-bundle basename (spec section 3,
# verified against the downloaded HCP842 atlas). Every value is bilateral: the
# per-side model file is ``<base>_L`` / ``<base>_R``. ``fx`` maps to ``F`` and is
# the one tract processed as a single bilateral bundle (the atlas ships F_L_R
# combined); ``cingulum`` is dipy-only. Tracts with no atlas counterpart
# (``atr``/``str``/``cbd``/``cbp``/``cbt`` -- greyed on dipy -- and the
# non-bilateral ``fma``/``fmi``/``mcp``/``ac``) are deliberately absent, so
# :func:`dipy_bundle_workflow` returns ``None`` for them. ``ar`` (acoustic
# radiation) *has* an atlas counterpart (``AR_L``/``AR_R``) but is excluded too:
# RecoBundles has poor performance on acoustic radiation, so it is FSL-only.
DIPY_TRACT_ATLAS = {
    "af": "AF",
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

# The one tract processed as a single bilateral bundle.
_FORNIX_TRACT = "fx"


def _add_recovery(
    workflow,
    inputnode,
    union,
    suffix,
    model_bundle_name,
    params,
    num_threads,
    out_bundle_name,
):
    """Insert the per-bundle recovery node after ``union``.

    Scores the union's default bundle against the atlas model and, when it looks
    contaminated or scarce, retries recognition once from the same chunks/builds
    with an adjusted configuration (see :class:`DipyBundleRecovery`). Returns the
    node so the caller wires ``bundle`` to ``to_ref`` and ``confidence_flag`` to
    the outputnode. It may re-run recognition, so it reserves the same static RAM
    as the recognise node.
    """
    recovery = Node(DipyBundleRecovery(), name="recovery_%s" % suffix)
    recovery._mem_gb = RecoBundlesRamEstimator.STATIC_FALLBACK_GB
    recovery.inputs.model_bundle_name = model_bundle_name
    recovery.inputs.num_threads = num_threads
    recovery.inputs.out_bundle = out_bundle_name + ".trx"
    for trait, value in params.items():
        setattr(recovery.inputs, trait, value)
    workflow.connect(union, "bundle", recovery, "default_bundle")
    workflow.connect(inputnode, "recobundles_builds", recovery, "recobundles_pickles")
    workflow.connect(inputnode, "recobundles_chunks", recovery, "tractogram_chunks")
    workflow.connect(inputnode, "atlas_dir", recovery, "atlas_dir")
    return recovery


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
    bundle_bilateral : path
        The bilateral recognised bundle in reference space (``.vtp``), for tracts
        like the fornix that are not split by side.
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
        IdentityInterface(
            fields=[
                "bundle_lh",
                "bundle_rh",
                "bundle_bilateral",
                "flag_lh",
                "flag_rh",
                "flag_bilateral",
            ]
        ),
        name="outputnode",
    )

    is_fornix = name == _FORNIX_TRACT

    if is_fornix:
        # The fornix is the one tract the atlas ships side-combined. We process
        # it as a single bilateral bundle.
        model_bundle_name = "F_L_R"
        node_suffix = "bilateral"

        recognize = MapNode(
            DipyRecoBundlesRecognize(),
            name="recognize_%s" % node_suffix,
            iterfield=["recobundles_pickle", "tractogram_chunk"],
        )
        recognize._mem_gb = RecoBundlesRamEstimator.STATIC_FALLBACK_GB
        recognize.ram_estimator = RecoBundlesRamEstimator()
        workflow.connect(
            inputnode, "recobundles_builds", recognize, "recobundles_pickle"
        )
        workflow.connect(inputnode, "recobundles_chunks", recognize, "tractogram_chunk")

        recognize.inputs.model_bundle_name = model_bundle_name
        recognize.inputs.num_threads = num_threads

        params = recognition_params(model_bundle_name)
        for trait, value in params.items():
            setattr(recognize.inputs, trait, value)
        workflow.connect(inputnode, "atlas_dir", recognize, "atlas_dir")

        union = Node(DipyBundleUnion(), name="union_%s" % node_suffix)
        union._mem_gb = _MEM_GB["union"]
        workflow.connect(recognize, "recognized_bundle", union, "recognized_bundles")

        recovery = _add_recovery(
            workflow,
            inputnode,
            union,
            node_suffix,
            model_bundle_name,
            params,
            num_threads,
            out_bundle_name="r-%s" % name,
        )

        to_ref = Node(DipyBundlesToRef(), name="to_ref_%s" % node_suffix)
        to_ref._mem_gb = _MEM_GB["to_ref"]
        to_ref.inputs.out_name = "r-%s" % name
        workflow.connect(recovery, "bundle", to_ref, "bundle")
        workflow.connect(inputnode, "atlas2native", to_ref, "atlas2native")

        workflow.connect(to_ref, "bundle_vtp", outputnode, "bundle_bilateral")
        workflow.connect(recovery, "confidence_flag", outputnode, "flag_bilateral")

    else:
        for side in SIDES:
            model_bundle_name = "%s_%s" % (atlas_base, _SIDE_SUFFIX[side])

            recognize = MapNode(
                DipyRecoBundlesRecognize(),
                name="recognize_%s" % side,
                iterfield=["recobundles_pickle", "tractogram_chunk"],
            )
            recognize._mem_gb = RecoBundlesRamEstimator.STATIC_FALLBACK_GB
            recognize.ram_estimator = RecoBundlesRamEstimator()
            workflow.connect(
                inputnode, "recobundles_builds", recognize, "recobundles_pickle"
            )
            workflow.connect(
                inputnode, "recobundles_chunks", recognize, "tractogram_chunk"
            )

            recognize.inputs.model_bundle_name = model_bundle_name
            recognize.inputs.num_threads = num_threads

            params = recognition_params(model_bundle_name)
            for trait, value in params.items():
                setattr(recognize.inputs, trait, value)
            workflow.connect(inputnode, "atlas_dir", recognize, "atlas_dir")

            union = Node(DipyBundleUnion(), name="union_%s" % side)
            union._mem_gb = _MEM_GB["union"]
            workflow.connect(
                recognize, "recognized_bundle", union, "recognized_bundles"
            )

            recovery = _add_recovery(
                workflow,
                inputnode,
                union,
                side,
                model_bundle_name,
                params,
                num_threads,
                out_bundle_name="r-%s_%s" % (name, side),
            )

            to_ref = Node(DipyBundlesToRef(), name="to_ref_%s" % side)
            to_ref._mem_gb = _MEM_GB["to_ref"]
            to_ref.inputs.out_name = "r-%s_%s" % (name, side)
            workflow.connect(recovery, "bundle", to_ref, "bundle")
            workflow.connect(inputnode, "atlas2native", to_ref, "atlas2native")

            workflow.connect(to_ref, "bundle_vtp", outputnode, "bundle_%s" % side)
            workflow.connect(recovery, "confidence_flag", outputnode, "flag_%s" % side)

    return workflow
