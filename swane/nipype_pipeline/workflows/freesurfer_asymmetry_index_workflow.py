from nipype.interfaces.freesurfer import ReconAll
from nipype.interfaces.fsl import ImageMaths, ImageStats, ApplyMask, BinaryMaths

from nipype import Node, Merge

from swane.nipype_pipeline.engine.CustomWorkflow import CustomWorkflow
from swane.nipype_pipeline.nodes.TTest import TTest
from swane.nipype_pipeline.nodes.SumMultiVols import SumMultiVols

from nipype.interfaces.utility import IdentityInterface


lh_labels = [
    17,      # Left-Hippocampus                        220 216 20  0
    18,      # Left-Amygdala                           103 255 255 0
    1000,    # ctx-lh-unknown                      25  5   25  0
    1001,    # ctx-lh-bankssts                     25  100 40  0
    # 1002,    # ctx-lh-caudalanteriorcingulate      125 100 160 0
    # 1003,    # ctx-lh-caudalmiddlefrontal          100 25  0   0
    # 1004,    # ctx-lh-corpuscallosum               120 70  50  0
    # 1005,    # ctx-lh-cuneus                       220 20  100 0
    # 1006,    # ctx-lh-entorhinal                   220 20  10  0
    # 1007,    # ctx-lh-fusiform                     180 220 140 0
    # 1008,    # ctx-lh-inferiorparietal             220 60  220 0
    # 1009,    # ctx-lh-inferiortemporal             180 40  120 0
    # 1010,    # ctx-lh-isthmuscingulate             140 20  140 0
    # 1011,    # ctx-lh-lateraloccipital             20  30  140 0
    # 1012,    # ctx-lh-lateralorbitofrontal         35  75  50  0
    # 1013,    # ctx-lh-lingual                      225 140 140 0
    # 1014,    # ctx-lh-medialorbitofrontal          200 35  75  0
    # 1015,    # ctx-lh-middletemporal               160 100 50  0
    # 1016,    # ctx-lh-parahippocampal              20  220 60  0
    # 1017,    # ctx-lh-paracentral                  60  220 60  0
    # 1018,    # ctx-lh-parsopercularis              220 180 140 0
    # 1019,    # ctx-lh-parsorbitalis                20  100 50  0
    # 1020,    # ctx-lh-parstriangularis             220 60  20  0
    # 1021,    # ctx-lh-pericalcarine                120 100 60  0
    # 1022,    # ctx-lh-postcentral                  220 20  20  0
    # 1023,    # ctx-lh-posteriorcingulate           220 180 220 0
    # 1024,    # ctx-lh-precentral                   60  20  220 0
    # 1025,    # ctx-lh-precuneus                    160 140 180 0
    # 1026,    # ctx-lh-rostralanteriorcingulate     80  20  140 0
    # 1027,    # ctx-lh-rostralmiddlefrontal         75  50  125 0
    # 1028,    # ctx-lh-superiorfrontal              20  220 160 0
    # 1029,    # ctx-lh-superiorparietal             20  180 140 0
    # 1030,    # ctx-lh-superiortemporal             140 220 220 0
    # 1031,    # ctx-lh-supramarginal                80  160 20  0
    # 1032,    # ctx-lh-frontalpole                  100 0   100 0
    # 1033,    # ctx-lh-temporalpole                 70  70  70  0
    # 1034,    # ctx-lh-transversetemporal           150 150 200 0
    # 1035,    # ctx-lh-insula                       255 192 32  0
]

labels_rh = [
    53,     # Right - Hippocampus                       220 216 20  0
    54,     # Right - Amygdala                          103 255 255 0
    2000,   # ctx-rh-unknown                      25  5   25  0
    2001,   #    ctx-rh-bankssts                     25  100 40  0
    2002,   #    ctx-rh-caudalanteriorcingulate      125 100 160 0
    2003,   #    ctx-rh-caudalmiddlefrontal          100 25  0   0
    2004,   #    ctx-rh-corpuscallosum               120 70  50  0
    2005,   #    ctx-rh-cuneus                       220 20  100 0
    2006,   #    ctx-rh-entorhinal                   220 20  10  0
    2007,   #   ctx-rh-fusiform                     180 220 140 0
    2008,   #    ctx-rh-inferiorparietal             220 60  220 0
    2009,   #    ctx-rh-inferiortemporal             180 40  120 0
    2010,   #    ctx-rh-isthmuscingulate             140 20  140 0
    2011,   #    ctx-rh-lateraloccipital             20  30  140 0
    2012,   #    ctx-rh-lateralorbitofrontal         35  75  50  0
    2013,   #    ctx-rh-lingual                      225 140 140 0
    2014,   #    ctx-rh-medialorbitofrontal          200 35  75  0
    2015,   #    ctx-rh-middletemporal               160 100 50  0
    2016,   #   ctx-rh-parahippocampal              20  220 60  0
    2017,   #    ctx-rh-paracentral                  60  220 60  0
    2018,   #    ctx-rh-parsopercularis              220 180 140 0
    2019,   #    ctx-rh-parsorbitalis                20  100 50  0
    2020,   #    ctx-rh-parstriangularis             220 60  20  0
    2021,   #    ctx-rh-pericalcarine                120 100 60  0
    2022,   #    ctx-rh-postcentral                  220 20  20  0
    2023,   #    ctx-rh-posteriorcingulate           220 180 220 0
    2024,   #    ctx-rh-precentral                   60  20  220 0
    2025,   #    ctx-rh-precuneus                    160 140 180 0
    2026,   #    ctx-rh-rostralanteriorcingulate     80  20  140 0
    2027,   #    ctx-rh-rostralmiddlefrontal         75  50  125 0
    2028,   #    ctx-rh-superiorfrontal              20  220 160 0
    2029,   #    ctx-rh-superiorparietal             20  180 140 0
    2030,   #    ctx-rh-superiortemporal             140 220 220 0
    2031,   #    ctx-rh-supramarginal                80  160 20  0
    2032,   #    ctx-rh-frontalpole                  100 0   100 0
    2033,   #    ctx-rh-temporalpole                 70  70  70  0
    2034,   #    ctx-rh-transversetemporal           150 150 200 0
    2035,   #    ctx-rh-insula                       255 192 32  0
]


def get_symmetric(index):
    if index >= 1000:
        return index+1000
    if index == 17:
        return 53
    if index == 18:
        return 54
    return -1


def freesurfer_asymmetry_index_workflow(name: str, base_dir: str = "/") -> CustomWorkflow:
    """
    Freesurfer cortical reconstruction, white matter ROI, basal ganglia and thalami ROI.
    If needed, segmentation of the hippocampal substructures and the nuclei of the amygdala.

    Parameters
    ----------
    name : str
        The workflow name.
    base_dir : path, optional
        The base directory path relative to parent workflow. The default is "/".

    Input Node Fields
    ----------
    in_file : path
        The input file to use for AI calculation.
    seg_file : path
        Freesurfer segmentation file.

    Returns
    -------
    workflow : CustomWorkflow
        The Freesurfer workflow.

    Output Node Fields
    ----------
    asymmetry_index_file : string
        The asymmetry index map.

    """

    workflow = CustomWorkflow(name=name, base_dir=base_dir)

    # Input Node
    inputnode = Node(
        IdentityInterface(fields=['in_file', 'seg_file']),
        name='inputnode')

    # Output Node
    outputnode = Node(
        IdentityInterface(fields=['asymmetry_index_file']),
        name='outputnode')

    merge_node = Node(Merge(len(lh_labels)*2), name="merge_node")
    index = 1

    for lh_label in lh_labels:

        rh_label = get_symmetric(lh_label)
        if rh_label == -1:
            continue

        lh_mask = Node(ImageMaths(), name='lh_mask_%d' % lh_label)
        lh_mask.inputs.op_string = '-thr %d -uthr %d -bin' % (lh_label, lh_label)
        workflow.add_nodes([lh_mask])
        workflow.connect(inputnode, "seg_file", lh_mask, "in_file")

        lh_apply_mask = Node(ApplyMask(), name="lh_applymask_%d" % lh_label)
        workflow.connect(inputnode, "in_file", lh_apply_mask, "in_file")
        workflow.connect(lh_mask, "out_file", lh_apply_mask, "mask_file")

        lh_stats = Node(ImageStats(), name="lh_stats_%d" % lh_label)
        lh_stats.inputs.op_string = "-M -S -V"
        workflow.connect(lh_apply_mask, "out_file", lh_stats, "in_file")

        rh_mask = Node(ImageMaths(), name='rh_mask_%d' % rh_label)
        rh_mask.inputs.op_string = '-thr %d -uthr %d -bin' % (rh_label, rh_label)
        workflow.add_nodes([rh_mask])
        workflow.connect(inputnode, "seg_file", rh_mask, "in_file")

        rh_apply_mask = Node(ApplyMask(), name="rh_applymask_%d" % rh_label)
        workflow.connect(inputnode, "in_file", rh_apply_mask, "in_file")
        workflow.connect(rh_mask, "out_file", rh_apply_mask, "mask_file")

        rh_stats = Node(ImageStats(), name="rh_stats_%d" % rh_label)
        rh_stats.inputs.op_string = "-M -S -V"
        workflow.connect(rh_apply_mask, "out_file", rh_stats, "in_file")

        t_test = Node(TTest(), name="ttest_%d" % lh_label)
        workflow.connect(lh_stats, "out_stat", t_test, "stats_lh")
        workflow.connect(rh_stats, "out_stat", t_test, "stats_rh")

        lh_value = Node(BinaryMaths(), name="lh_value_%d" % lh_label)
        lh_value.inputs.operation = "mul"
        workflow.connect(lh_mask, "out_file", lh_value, "in_file")
        workflow.connect(t_test, "stat_t", lh_value, "operand_value")

        rh_value = Node(BinaryMaths(), name="rh_value_%d" % lh_label)
        rh_value.inputs.operation = "mul"
        workflow.connect(rh_mask, "out_file", rh_value, "in_file")
        workflow.connect(t_test, "stat_t", rh_value, "operand_value")

        workflow.connect(lh_value, "out_file", merge_node, 'in%d' % index)
        index += 1
        workflow.connect(rh_value, "out_file", merge_node, 'in%d' % index)
        index += 1

    sum_maks = Node(SumMultiVols(), name="sum_masks")
    workflow.connect(merge_node, "out", sum_maks, "vol_files")

    workflow.connect(sum_maks, "out_file", outputnode, "asymmetry_index_file")

    return workflow
