"""Settings matrix for
:func:`swane.nipype_pipeline.workflows.tractography_workflow.tractography_workflow`.

The baseline is a fully-equipped FSL install: with the XTRACT protocol data
present (``$FSLDIR/data/xtract_data/.../<tract>_l|_r``) the builder assembles
the real per-hemisphere probtrackx graph, which is what we snapshot. On a box
without that data the *known-tract* scenario degrades to a skip (never a
failure). The *unknown-tract* scenario is genuinely tool-independent — a name
that is not in ``TRACTS`` always returns ``None`` regardless of what is
installed — so it is asserted directly. Snapshots under ``snapshots/tractography/``.

Phase 2 (CP-E) lifted this workflow's Phase-1 FSL pin: it now resolves its
engine with ``allow_ants=True``. Fixing this pin lift also surfaced a real
bug: for a tract with exactly one target ROI (e.g. ``cst``), the builder set
``targets_2_ref.inputs.in_file`` directly -- FSL/Synth's moving-image field
name -- which does not exist on ``AntsApplyTransforms`` (its moving-image
field is ``input_image``); the multi-target ``.iterables`` path had the same
FSL-specific field name baked in. Both now resolve the field name from the
engine. The seed/exclude applies already passed ``moving=<path>`` through
``apply_registration_node`` itself, so those needed no change. The FSL
snapshots below are pinned explicitly and stay byte-identical. Session G
(CP-G) added ``cst_real_graph_ants_backend`` as the golden ANTS-default
snapshot, eye-reviewed alongside the pre-existing node/edge construction test
(``test_tractography_ants_construction``), which keeps asserting the graph
SHAPE independently of the byte snapshot.
"""

import os

import pytest

from swane.config.config_enums import GlobalPrefCategoryList
from swane.config.preference_list import XTRACT_DATA_DIR
from swane.utils.DataInputList import DataInputList
from swane.tests.nipype_pipeline.matrix.conftest import import_workflow_or_skip

tractography_workflow = import_workflow_or_skip(
    "swane.nipype_pipeline.workflows.tractography_workflow", "tractography_workflow"
)
from swane.tests.nipype_pipeline.matrix.conftest import require_fsl_data

SUBDIR = "tractography"


def test_unknown_tract_returns_none(subject_config, global_config):
    """A tract name not in ``TRACTS`` is rejected before any FSL data is read."""
    wf = tractography_workflow(
        "definitely_not_a_tract",
        config=subject_config[DataInputList.DTI],
        synth_config=global_config[GlobalPrefCategoryList.SYNTH],
    )
    assert wf is None, "an unknown tract name must return None on any box"


def test_known_tract_real_graph(subject_config, global_config, graph_snapshot):
    """With XTRACT data present (the norm), the real cst graph is built and snapshotted."""
    require_fsl_data(os.path.join(XTRACT_DATA_DIR, "cst_l"))

    section = subject_config[DataInputList.DTI]
    section["cuda"] = "false"
    synth = global_config[GlobalPrefCategoryList.SYNTH]
    # tractography is not yet exercised under ANTS in this matrix; pin FSL so
    # this scenario keeps matching its existing golden snapshot.
    synth["engine"] = "FSL"

    wf = tractography_workflow(
        "cst",
        config=section,
        synth_config=synth,
    )
    assert wf is not None, "cst graph should build when XTRACT data is present"

    graph_snapshot(
        wf,
        subdir=SUBDIR,
        name="cst_real_graph",
        config={"tract": "cst", "cuda": "false", "xtract_data": "present"},
        title="tractography / cst_real_graph",
    )


def test_known_tract_real_graph_test_run(subject_config, global_config, graph_snapshot):
    """test_run=True: n_samples is halved from the xtract-protocol value.
    Unvalidated end-to-end yet -- see prerelease/TODO.md.
    """
    require_fsl_data(os.path.join(XTRACT_DATA_DIR, "cst_l"))

    section = subject_config[DataInputList.DTI]
    section["cuda"] = "false"
    synth = global_config[GlobalPrefCategoryList.SYNTH]
    # tractography is not yet exercised under ANTS in this matrix; pin FSL so
    # this scenario keeps matching its existing golden snapshot.
    synth["engine"] = "FSL"

    wf = tractography_workflow(
        "cst",
        config=section,
        synth_config=synth,
        test_run=True,
    )
    assert wf is not None, "cst graph should build when XTRACT data is present"

    graph_snapshot(
        wf,
        subdir=SUBDIR,
        name="cst_real_graph_test_run",
        config={
            "tract": "cst",
            "cuda": "false",
            "xtract_data": "present",
            "test_run": True,
        },
        title="tractography / cst_real_graph_test_run",
    )


def test_known_tract_real_graph_ants_backend(
    subject_config, global_config, graph_snapshot
):
    """ANTS-default backend on the cst protocol -- the Phase 2 engine flip.
    See ``test_tractography_ants_construction`` below for the graph-shape
    assertions this golden snapshot locks in.
    """
    require_fsl_data(os.path.join(XTRACT_DATA_DIR, "cst_l"))

    section = subject_config[DataInputList.DTI]
    section["cuda"] = "false"
    synth = global_config[GlobalPrefCategoryList.SYNTH]
    synth["engine"] = "ANTS"

    wf = tractography_workflow(
        "cst",
        config=section,
        synth_config=synth,
    )
    assert wf is not None, "cst graph should build when XTRACT data is present"

    graph_snapshot(
        wf,
        subdir=SUBDIR,
        name="cst_real_graph_ants_backend",
        config={
            "tract": "cst",
            "cuda": "false",
            "xtract_data": "present",
            "registration_engine": "ANTS",
        },
        title="tractography / cst_real_graph_ants_backend",
    )


# --------------------------------------------------------------------------- #
# Externalized-tractography construction (Phase 3, Session E / Task 6).
#
# probtrackx now runs natively in diffusion space: no xfm/inv_xfm, seed_ref =
# nodif_brain, and every ROI is warped MNI -> reference (nonlinear) then
# reference -> diffusion (linear) before tracking; the summed density is warped
# diffusion -> reference afterwards. These are graph-shape asserts, independent
# of the byte snapshots (regenerated in Session F).
#
# The "cst" protocol has exactly one target ROI (target.nii.gz) and an exclude
# ROI (exclude.nii.gz), no stop/invert.
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


def _node_by_name(wf, name):
    return next(n for n in wf._graph.nodes() if n.name == name)


def _node_by_prefix(wf, prefix):
    # apply_registration_node appends an engine suffix (_ants_apply/_apply_xfm),
    # so result apply nodes are matched by their stable prefix.
    return next(n for n in wf._graph.nodes() if n.name.startswith(prefix))


def _probtrackx_nodes(wf):
    return [n for n in wf._graph.nodes() if _iface(n) == "CustomProbTrackX2"]


def _assert_probtrackx_externalized(wf, inputnode):
    """probtrackx runs in diffusion space: no xfm/inv_xfm, seed_ref<-nodif_brain."""
    probs = _probtrackx_nodes(wf)
    assert len(probs) == 2  # one per side (cst has no inverted run)
    for prob in probs:
        incoming = _incoming(wf, prob)
        dst_fields = {df for _, _, df in incoming}
        assert "xfm" not in dst_fields
        assert "inv_xfm" not in dst_fields
        assert (inputnode, "nodif_brain", "seed_ref") in incoming
        # mask stays the diffusion-space brain mask
        assert (inputnode, "mask", "mask") in incoming


def test_tractography_ants_construction(subject_config, global_config):
    from nipype.interfaces.base import isdefined

    require_fsl_data(os.path.join(XTRACT_DATA_DIR, "cst_l"))

    section = subject_config[DataInputList.DTI]
    section["cuda"] = "false"
    synth = global_config[GlobalPrefCategoryList.SYNTH]
    synth["engine"] = "ANTS"

    wf = tractography_workflow("cst", config=section, synth_config=synth)
    assert wf is not None

    inputnode = _node_by_name(wf, "inputnode")
    _assert_probtrackx_externalized(wf, inputnode)

    ifaces = [_iface(n) for n in wf._graph.nodes()]
    assert "ApplyWarp" not in ifaces
    ants_applies = [n for n in wf._graph.nodes() if _iface(n) == "AntsApplyTransforms"]
    # per side: 3 MNI->ref (seed/targets/exclude) + 3 ref->diff + 1 diff->ref
    assert len(ants_applies) == 14

    diff_to_ref = [n for n in ants_applies if n.name.startswith("sum_2_ref_")]
    mni_to_ref = [
        n
        for n in ants_applies
        if "_2_ref_" in n.name and not n.name.startswith("sum_2_ref_")
    ]
    ref_to_diff = [n for n in ants_applies if "_2_diff_" in n.name]
    assert len(mni_to_ref) == 6
    assert len(ref_to_diff) == 6
    assert len(diff_to_ref) == 2

    # MNI->ref: nonlinear label resample fed by the mni2ref_warp boundary field
    # (single-file Merge(1) path, no which_to_invert).
    for node in mni_to_ref:
        assert node.inputs.interpolator == "nearestNeighbor"
        assert not isdefined(node.inputs.which_to_invert)
        tl = [c for c in _incoming(wf, node) if c[2] == "transformlist"]
        assert len(tl) == 1
        merge_node, _, _ = tl[0]
        assert _iface(merge_node) == "Merge"
        merge_in = _incoming(wf, merge_node)
        assert len(merge_in) == 1
        src, src_field, _ = merge_in[0]
        assert src is inputnode and src_field == "mni2ref_warp"

    # ref->diff: nearest-neighbour label resample carrying the ref2diff transform
    # list + which_to_invert straight from the inputnode (wire_transforms path).
    for node in ref_to_diff:
        assert node.inputs.interpolator == "nearestNeighbor"
        incoming = _incoming(wf, node)
        assert (inputnode, "ref2diff_transforms", "transformlist") in incoming
        assert (inputnode, "ref2diff_which_to_invert", "which_to_invert") in incoming
        # resampled onto the diffusion grid
        assert (inputnode, "nodif_brain", "reference_image") in incoming

    # diff->ref: LINEAR resample of the density (not a label map), carrying the
    # diff2ref transform list + which_to_invert, back onto the reference grid.
    for node in diff_to_ref:
        assert node.inputs.interpolator == "linear"
        incoming = _incoming(wf, node)
        assert (inputnode, "diff2ref_transforms", "transformlist") in incoming
        assert (inputnode, "diff2ref_which_to_invert", "which_to_invert") in incoming
        assert (inputnode, "reference_brain", "reference_image") in incoming

    # the single-target-file path still sets the moving image on the ANTs field.
    targets_2_ref_nodes = [n for n in mni_to_ref if "targets_2_ref" in n.name]
    assert len(targets_2_ref_nodes) == 2
    for node in targets_2_ref_nodes:
        assert isdefined(node.inputs.input_image)
        assert not hasattr(node.inputs, "in_file")

    _assert_filenames_preserved(wf)


def test_tractography_fsl_construction(subject_config, global_config):
    """FSL externalization: ApplyWarp (MNI->ref) + ApplyXFM (ref<->diff),
    still no xfm/inv_xfm on probtrackx."""
    require_fsl_data(os.path.join(XTRACT_DATA_DIR, "cst_l"))

    section = subject_config[DataInputList.DTI]
    section["cuda"] = "false"
    synth = global_config[GlobalPrefCategoryList.SYNTH]
    synth["engine"] = "FSL"

    wf = tractography_workflow("cst", config=section, synth_config=synth)
    assert wf is not None

    inputnode = _node_by_name(wf, "inputnode")
    _assert_probtrackx_externalized(wf, inputnode)

    ifaces = [_iface(n) for n in wf._graph.nodes()]
    assert "AntsApplyTransforms" not in ifaces
    # MNI->ref nonlinear applies (seed/targets/exclude per side)
    assert ifaces.count("ApplyWarp") == 6
    # ref->diff (seed/targets/exclude per side) + diff->ref (per side) = 8
    assert ifaces.count("ApplyXFM") == 8

    # ref->diff applies read the single-file ref2diff transform view; diff->ref
    # applies read diff2ref_transforms.
    apply_xfm = [n for n in wf._graph.nodes() if _iface(n) == "ApplyXFM"]
    ref_to_diff = [n for n in apply_xfm if "_2_diff_" in n.name]
    diff_to_ref = [n for n in apply_xfm if n.name.startswith("sum_2_ref_")]
    assert len(ref_to_diff) == 6
    assert len(diff_to_ref) == 2
    for node in ref_to_diff:
        assert node.inputs.interp == "nearestneighbour"
        assert (inputnode, "ref2diff_transforms", "in_matrix_file") in _incoming(
            wf, node
        )
    for node in diff_to_ref:
        assert node.inputs.interp != "nearestneighbour"
        assert (inputnode, "diff2ref_transforms", "in_matrix_file") in _incoming(
            wf, node
        )

    targets_2_ref_nodes = [n for n in wf._graph.nodes() if "targets_2_ref" in n.name]
    assert len(targets_2_ref_nodes) == 2
    for node in targets_2_ref_nodes:
        assert node.inputs.in_file

    _assert_filenames_preserved(wf)


def _assert_filenames_preserved(wf):
    """The sinked density and its derived waytotal keep their r-<tract>_<side>
    filenames after externalization."""
    for side in ("lh", "rh"):
        sum_2_ref = _node_by_prefix(wf, "sum_2_ref_cst_%s" % side)
        assert sum_2_ref.inputs.out_file == "r-cst_%s.nii.gz" % side
        sum_multi = _node_by_name(wf, "sumTrack_cst_%s" % side)
        assert sum_multi.inputs.out_file == "r-cst_%s.nii.gz" % side
        outputnode = _node_by_name(wf, "outputnode")
        inc = _incoming(wf, outputnode)
        assert (sum_2_ref, "out_file", "fdt_paths_%s" % side) in inc
        assert (sum_multi, "waytotal_sum", "waytotal_%s" % side) in inc


# --------------------------------------------------------------------------- #
# Heavy equivalence guard (opt in with --run-heavy; needs a real FSL install).
#
# The externalization applies the ref->diff FSL .mat to a reference-space ROI
# OURSELVES (apply_registration_node, FSL path, nearest-neighbour) to land it in
# diffusion space -- work probtrackx previously did internally via its
# seeds_to_dti ``--xfm`` (the same FLIRT matrix, same FSL resampling). This guard
# confirms our abstraction reproduces a raw ``flirt -applyxfm`` with that matrix
# voxel-for-voxel: same direction (ref->diff), same target grid (nodif), same NN
# interpolation. A regression in that wiring (wrong reference, dropped interp,
# transposed matrix) would move the seed and silently corrupt the tract.
# --------------------------------------------------------------------------- #
def _sphere(shape, center, radius):
    import numpy as np

    grid = np.mgrid[0 : shape[0], 0 : shape[1], 0 : shape[2]].astype(float)
    distance = sum((grid[i] - center[i]) ** 2 for i in range(3))
    return (distance < radius**2).astype(np.float32)


@pytest.mark.heavy
def test_externalized_roi_matches_mat_path_fsl(workspace, make_nifti):
    import glob
    import os

    import numpy as np
    import nibabel as nib
    from nipype import Node
    from nipype.interfaces.fsl import FLIRT, ConvertXFM, ApplyXFM
    from nipype.interfaces.utility import IdentityInterface

    from swane.config.config_enums import RegistrationEngine
    from swane.nipype_pipeline.engine.CustomWorkflow import CustomWorkflow
    from swane.nipype_pipeline.nodes.utils import apply_registration_node

    os.chdir(str(workspace))

    # Two phantoms with a real geometric offset so FLIRT finds a non-identity
    # diffusion<->reference affine (mimicking b0 vs T1 misalignment).
    nodif = make_nifti("nodif.nii.gz", data=_sphere((32, 32, 32), (16, 16, 16), 9))
    reference = make_nifti(
        "reference.nii.gz", data=_sphere((32, 32, 32), (18, 15, 17), 9)
    )

    # dif2ref (diffusion -> reference), then invert for ref -> diffusion, exactly
    # as dti_preproc builds them (FLIRT + ConvertXFM on the FSL branch).
    flirt = Node(FLIRT(), name="dif2ref")
    flirt.inputs.in_file = nodif
    flirt.inputs.reference = reference
    flirt.inputs.dof = 6
    flirt.base_dir = str(workspace / "flirt")
    dif2ref_mat = flirt.run().outputs.out_matrix_file

    inv = Node(ConvertXFM(), name="ref2dif")
    inv.inputs.in_file = dif2ref_mat
    inv.inputs.invert_xfm = True
    inv.base_dir = str(workspace / "inv")
    ref2diff_mat = inv.run().outputs.out_file

    # A label ROI in reference space (what the MNI->ref apply produces).
    ref_roi = make_nifti("ref_roi.nii.gz", data=_sphere((32, 32, 32), (20, 14, 18), 4))

    # Path A -- the externalized abstraction (apply_registration_node, FSL).
    wf = CustomWorkflow(name="ext")
    wf.base_dir = str(workspace / "ext_run")
    src = Node(IdentityInterface(fields=["roi", "xfm", "reference"]), name="src")
    src.inputs.roi = ref_roi
    src.inputs.xfm = ref2diff_mat
    src.inputs.reference = nodif
    apply_registration_node(
        name="roi_2_diff",
        engine=RegistrationEngine.FSL,
        workflow=wf,
        warp=[src, "xfm"],
        moving=[src, "roi"],
        reference=[src, "reference"],
        non_linear=False,
        labelmap=True,
        out_file="roi_diff_abstraction.nii.gz",
    )
    wf.run()
    os.chdir(str(workspace))
    matches = glob.glob(
        os.path.join(wf.base_dir, "**", "roi_diff_abstraction.nii.gz"), recursive=True
    )
    assert matches, "the abstraction apply produced no output file"
    abstraction = nib.load(matches[0]).get_fdata()

    # Path B -- the prior ".mat path": a raw flirt -applyxfm with the same matrix
    # onto the diffusion grid (what probtrackx's seeds_to_dti xfm does).
    raw = Node(ApplyXFM(), name="roi_2_diff_raw")
    raw.inputs.in_file = ref_roi
    raw.inputs.reference = nodif
    raw.inputs.in_matrix_file = ref2diff_mat
    raw.inputs.apply_xfm = True
    raw.inputs.interp = "nearestneighbour"
    raw.base_dir = str(workspace / "raw_run")
    raw_out = raw.run().outputs.out_file
    os.chdir(str(workspace))
    reference_path = nib.load(raw_out).get_fdata()

    # The ROI actually moved into diffusion space (transform applied, not a no-op)
    # and both paths agree voxel-for-voxel.
    ref_space = nib.load(ref_roi).get_fdata()
    assert np.count_nonzero(reference_path) > 0
    assert not np.array_equal(reference_path, ref_space)
    assert abstraction.shape == reference_path.shape
    assert np.array_equal(abstraction, reference_path)
