import os
import glob

from nipype import Node, IdentityInterface, MapNode, JoinNode, Merge, Rename
from nipype.interfaces.fsl import ApplyWarp, ImageMaths

from swane.nipype_pipeline.engine.CustomWorkflow import CustomWorkflow
from swane.nipype_pipeline.nodes.RandomSeedGenerator import RandomSeedGenerator
from swane.nipype_pipeline.nodes.CustomProbTrackX2 import CustomProbTrackX2
from swane.nipype_pipeline.nodes.MergeTargets import MergeTargets
from swane.nipype_pipeline.nodes.SumMultiTracks import SumMultiTracks
from swane.utils.ConfigManager import ConfigManager

SIDES = ["lh", "rh"]


def tractography_workflow(name: str, threads: int, base_dir: str = "/") -> CustomWorkflow:
    """
    Executes tractography for chosen tract using xtract protocols.

    Parameters
    ----------
    name : str
        The workflow and tract name.
    threads : int
        The number of parallel threads to use for the analysis.
    base_dir : path, optional
        The base directory path relative to parent workflow. The default is "/".

    Input Node Fields
    ----------
    fsamples : path
        Samples from the distribution of anysotropic volume fraction.
    phsamples : path
        Samples from the distribution on phi.
    thsamples : path
        Samples from the distribution on theta.
    ref_brain : path
        Betted T13D.
    diff2ref_mat : path
        Linear registration matrix from diffusion to T13D reference space.
    ref2diff_mat : path
        Linear registration inverse matrix from T13D reference to diffusion space.
    mni2ref_warp : path
        Nonlinear registration warp from MNI atlas to T13D reference space.

    Returns
    -------
    workflow : CustomWorkflow
        The xtract workflow.
        
    Output Node Fields
    ----------
    fdt_paths_rh : path
        RH connectivity distribution in T13D reference space.
    fdt_paths_lh : path
        LH connectivity distribution in T13D reference space.
    waytotal_rh : path
        Text file containing a single number corresponding to the total number
        of generated tracts that have not been rejected by inclusion/exclusion
        mask criteria for RH side.
    waytotal_lh : path
        Text file containing a single number corresponding to the total number
        of generated tracts that have not been rejected by inclusion/exclusion
        mask criteria for LH side.

    """

    # Check if tract is in configuration list
    if name not in ConfigManager.TRACTS:
        return None

    # Check for existance of xtract data directory and protocol name dicrectory
    if not os.path.exists(os.path.join(ConfigManager.XTRACT_DATA_DIR, name + "_l")):
        return None

    workflow = CustomWorkflow(name='tract_' + name, base_dir=base_dir)
    
    inputnode = Node(
        IdentityInterface(fields=['fsamples', 'mask', 'phsamples', 'thsamples', 'ref_brain',
                                  'diff2ref_mat', "ref2diff_mat", "mni2ref_warp",
                                  ]),
        name='inputnode')

    outputnode = Node(
        IdentityInterface(fields=['fdt_paths_rh', 'fdt_paths_lh', 'waytotal_rh', 'waytotal_lh']),
        name='outputnode')

    # NODE 1: Random seed genration for cache preservation
    random_seed = Node(RandomSeedGenerator(), name='random_seed')
    random_seed.inputs.seeds_n = threads
    workflow.connect(inputnode, "mask", random_seed, "mask")

    try:
        n_samples = int(ConfigManager.TRACTS[name][2] / threads)
    except:
        n_samples = int(ConfigManager.DEFAULT_N_SAMPLES / threads)

    for side in SIDES:
        # Xtract protocol loading
        protocol_dir = os.path.join(ConfigManager.XTRACT_DATA_DIR, name + "_" + side[0])

        seed_file = os.path.join(protocol_dir, "seed.nii.gz")
        exclude_file = os.path.join(protocol_dir, "exclude.nii.gz")
        stop_file = os.path.join(protocol_dir, "stop.nii.gz")
        target_files = glob.glob(os.path.join(protocol_dir, "target*"))

        invert_file = os.path.join(protocol_dir, "invert")
        wayorder_file = os.path.join(protocol_dir, "wayorder")

        is_invert = False
        is_wayorder = False

        if os.path.exists(invert_file):
            is_invert = True
        elif os.path.exists(wayorder_file):
            is_wayorder = True

        if not os.path.exists(seed_file):
            return None
        if len(target_files) == 0:
            return None
        
        # NODE 2: Seed ROI nonlinear transformation in T13D reference space
        seed_2_ref = Node(ApplyWarp(), name="seed_2_ref_%s_%s" % (name, side))
        seed_2_ref.long_name = side + " seed ROI %s"
        seed_2_ref.inputs.out_file = "r-seed_%s_%s.nii.gz" % (name, side)
        seed_2_ref.inputs.in_file = seed_file
        workflow.connect(inputnode, "ref_brain", seed_2_ref, "ref_file")
        workflow.connect(inputnode, "mni2ref_warp", seed_2_ref, "field_file")
        
        # NODE 3: Seed ROI bynarization
        seed_bin = Node(ImageMaths(), name="seed_bin_%s_%s" % (name, side))
        seed_bin.long_name = side + " seed ROI binarization"
        seed_bin.inputs.op_string = "-thr 0.1 -bin"
        seed_bin.inputs.out_data_type = "char"
        seed_bin.inputs.suffix = "_bin"
        workflow.connect(seed_2_ref, "out_file", seed_bin, "in_file")
        
        # NODE 4: Target ROIs nonlinear transformation in T13D reference space
        targets_2_ref = Node(ApplyWarp(), name="targets_2_ref_%s_%s" % (name, side))
        targets_2_ref.long_name = side + " target ROIs %s"
        if len(target_files) > 1:
            targets_2_ref.iterables = ("in_file", target_files)
        else:
            targets_2_ref.inputs.in_file = target_files[0]
        workflow.connect(inputnode, "ref_brain", targets_2_ref, "ref_file")
        workflow.connect(inputnode, "mni2ref_warp", targets_2_ref, "field_file")
        
        # NODE 5: Target ROIs bynarization
        targets_bin = Node(ImageMaths(), name="targets_bin_%s_%s" % (name, side))
        targets_bin.long_name = side + " target ROIs binarization"
        targets_bin.inputs.op_string = "-thr 0.1 -bin"
        targets_bin.inputs.out_data_type = "char"
        targets_bin.inputs.suffix = "_bin"
        workflow.connect(targets_2_ref, "out_file", targets_bin, "in_file")
        
        # NODE 10: Tractography
        probtrackx = MapNode(CustomProbTrackX2(), name="probtrackx_%s_%s" % (name, side), iterfield=["rseed"], mem_gb=4)
        probtrackx.long_name = side + " %s"
        probtrackx.inputs.n_samples = n_samples
        probtrackx.inputs.loop_check = True
        probtrackx.inputs.wayorder = is_wayorder
        probtrackx.inputs.rand_fib = 1
        probtrackx.inputs.sample_random_points = 1
        # TODO argomento --ompl che fa??
        probtrackx.inputs.opd = True
        workflow.connect(inputnode, "fsamples", probtrackx, "fsamples")
        workflow.connect(inputnode, "mask", probtrackx, "mask")
        workflow.connect(inputnode, "ref_brain", probtrackx, "seed_ref")
        workflow.connect(inputnode, "phsamples", probtrackx, "phsamples")
        workflow.connect(inputnode, "thsamples", probtrackx, "thsamples")
        workflow.connect(inputnode, "ref2diff_mat", probtrackx, "xfm")
        workflow.connect(inputnode, "diff2ref_mat", probtrackx, "inv_xfm")
        workflow.connect(seed_bin, "out_file", probtrackx, "seed")
        workflow.connect(random_seed, "seeds", probtrackx, "rseed")
        
        # Check the number of target ROIs
        if len(target_files) > 1:
            merge_targets = JoinNode(MergeTargets(), name="merge_targets_%s_%s" % (name, side),
                                     joinsource=targets_2_ref, joinfield="target_files")
            merge_targets.long_name = side + " targets ROI merging"

            workflow.connect(targets_bin, "out_file", merge_targets, "target_files")

            workflow.connect(merge_targets, "out_file", probtrackx, "waypoints")
        else:
            workflow.connect(targets_bin, "out_file", probtrackx, "waypoints")
        
        # Check if inverted run is required in protocol
        if is_invert:
            # NODE 11: Inverted tractography
            probtrackx_inverted = MapNode(CustomProbTrackX2(), name="probtrackx_inverted_%s_%s" % (name, side), iterfield=["rseed"], mem_gb=4)
            probtrackx_inverted.long_name = side + " inverse %s"
            probtrackx_inverted.inputs.n_samples = n_samples
            probtrackx_inverted.inputs.loop_check = True
            probtrackx_inverted.inputs.wayorder = is_wayorder
            probtrackx_inverted.inputs.rand_fib = 1
            probtrackx_inverted.inputs.sample_random_points = 1
            probtrackx_inverted.inputs.opd = True
            workflow.connect(inputnode, "fsamples", probtrackx_inverted, "fsamples")
            workflow.connect(inputnode, "mask", probtrackx_inverted, "mask")
            workflow.connect(inputnode, "ref_brain", probtrackx_inverted, "seed_ref")
            workflow.connect(inputnode, "phsamples", probtrackx_inverted, "phsamples")
            workflow.connect(inputnode, "thsamples", probtrackx_inverted, "thsamples")
            workflow.connect(inputnode, "ref2diff_mat", probtrackx_inverted, "xfm")
            workflow.connect(inputnode, "diff2ref_mat", probtrackx_inverted, "inv_xfm")
            workflow.connect(targets_bin, "out_file", probtrackx_inverted, "seed")
            workflow.connect(seed_bin, "out_file", probtrackx_inverted, "waypoints")
            workflow.connect(random_seed, "seeds", probtrackx_inverted, "rseed")
        
        # Check for exclusion ROI in protocol
        if os.path.exists(exclude_file):
            # NODE 6: Exclusion ROI nonlinear transformation in T13D reference space
            exclude_2_ref = Node(ApplyWarp(), name="exclude_2_ref_%s_%s" % (name, side))
            exclude_2_ref.long_name = side + " exclusion ROI %s"
            exclude_2_ref.inputs.out_file = "r-exclude_%s_%s.nii.gz" % (name, side)
            exclude_2_ref.inputs.in_file = exclude_file
            workflow.connect(inputnode, "ref_brain", exclude_2_ref, "ref_file")
            workflow.connect(inputnode, "mni2ref_warp", exclude_2_ref, "field_file")

            # NODE 7: Exclusion ROI bynarization
            exclude_bin = Node(ImageMaths(), name="exclude_bin_%s_%s" % (name, side))
            exclude_bin.long_name = side + " exclusion ROI binarization"
            exclude_bin.inputs.op_string = "-thr 0.1 -bin"
            exclude_bin.inputs.out_data_type = "char"
            exclude_bin.inputs.suffix = "_bin"
            workflow.connect(exclude_2_ref, "out_file", exclude_bin, "in_file")

            workflow.connect(exclude_bin, "out_file", probtrackx, "avoid_mp")

            if is_invert:
                workflow.connect(exclude_bin, "out_file", probtrackx_inverted, "avoid_mp")

        # Check for stop ROI in protocol
        if os.path.exists(stop_file):
            # NODE 8: stop ROI nonlinear transformation in T13D reference space
            stop_2_ref = Node(ApplyWarp(), name="stop_2_ref_%s_%s" % (name, side))
            stop_2_ref.long_name = side + " stop ROI %s"
            stop_2_ref.inputs.out_file = "r-stop_%s_%s.nii.gz" % (name, side)
            stop_2_ref.inputs.in_file = stop_file
            workflow.connect(inputnode, "ref_brain", stop_2_ref, "ref_file")
            workflow.connect(inputnode, "mni2ref_warp", stop_2_ref, "field_file")

            # NODE 9: stop ROI bynarization
            stop_bin = Node(ImageMaths(), name="stop_bin_%s_%s" % (name, side))
            stop_bin.long_name = side + " stop ROI binarization"
            stop_bin.inputs.op_string = "-thr 0.1 -bin"
            stop_bin.inputs.out_data_type = "char"
            stop_bin.inputs.suffix = "_bin"
            workflow.connect(stop_2_ref, "out_file", stop_bin, "in_file")

            workflow.connect(stop_bin, "out_file", probtrackx, "stop_mask")

            if is_invert:
                workflow.connect(stop_bin, "out_file", probtrackx_inverted, "stop_mask")

        # NODE 14: Sum tractography and inverted tractography results
        sum_multi_tracks = Node(SumMultiTracks(), name='sumTrack_%s_%s' % (name, side))
        sum_multi_tracks.long_name = side + " %s"
        sum_multi_tracks.inputs.out_file = "r-%s_%s.nii.gz" % (name, side)

        if is_invert:
            # NODE 12: Merge tractography and inverted tractography fdt_paths
            merge_paths = Node(Merge(2), name="merge_paths_%s_%s" % (name, side))
            merge_paths.long_name = side + " Direct and inverse tractography merging"
            workflow.connect(probtrackx, 'fdt_paths', merge_paths, 'in1')
            workflow.connect(probtrackx_inverted, 'fdt_paths', merge_paths, 'in2')

            # NODE 13: Merge tractography and inverted tractography way_total
            merge_waytotals = Node(Merge(2), name="merge_waytotals_%s_%s" % (name, side))
            merge_waytotals.long_name = side + " Direct and inverse waytotal merging"
            workflow.connect(probtrackx, 'way_total', merge_waytotals, 'in1')
            workflow.connect(probtrackx_inverted, 'way_total', merge_waytotals, 'in2')

            workflow.connect(merge_paths, "out", sum_multi_tracks, "path_files")
            workflow.connect(merge_waytotals, "out", sum_multi_tracks, "waytotal_files")

        else:
            workflow.connect(probtrackx, "fdt_paths", sum_multi_tracks, "path_files")
            workflow.connect(probtrackx, "way_total", sum_multi_tracks, "waytotal_files")

        workflow.connect(sum_multi_tracks, "out_file", outputnode, "fdt_paths_%s" % side)
        workflow.connect(sum_multi_tracks, "waytotal_sum", outputnode, "waytotal_%s" % side)

    return workflow
