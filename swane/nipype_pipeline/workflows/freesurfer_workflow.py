import os
import tempfile
from configparser import SectionProxy

from nipype.interfaces.freesurfer import ReconAll, ApplyVolTransform
from nipype.interfaces.fsl import BinaryMaths
from multiprocessing import cpu_count
from nipype.pipeline.engine import Node
from math import trunc

from swane.nipype_pipeline.nodes.SynthSeg import SynthSeg
from swane.nipype_pipeline.nodes.utils import (
    getn,
    get_synth_cpu_config,
    apply_synth_num_threads,
)
from swane.nipype_pipeline.engine.CustomWorkflow import CustomWorkflow
from swane.nipype_pipeline.nodes.SegmentHA import SegmentHA
from swane.nipype_pipeline.nodes.ThrROI import ThrROI
from swane.config.config_enums import CoreLimit, FreesurferStep
from nipype.interfaces.utility import IdentityInterface
from swane.utils.ResourceManager import ResourceManager

FS_DIR = "FS"

# recon-all top-level flags for test_run, appended to the existing args.
# -nuiterations 1 : halve NU intensity-correction iterations (default 2)
# -norm3diters 1  : cut mri_normalize 3D iterations (both runs)
# -no-fix-with-ga : drop the genetic-algorithm optimisation in the topology fixer
RECONALL_TEST_ARGS = "-nuiterations 1 -norm3diters 1 -no-fix-with-ga"

# Per-binary overrides for the -expert file. Moderate reductions (kept
# deliberately conservative, "let's not overdo it"). The synthseg line is only
# consulted when recon-all actually runs SynthSeg internally (FS v8 synth
# path); it is inert for the classic path, so including it unconditionally is
# safe.
#
# NOT included: "mris_register -N 10" -- would have been the biggest lever,
# but FreeSurfer 8.2.0's rca-surfreg (unrelated to, and not fixed by, the
# recon-all -expert patch below) splices xopts into the mris_register command
# BETWEEN the first positional arg and the rest (`mris_register ... lh.sphere
# -N 10 target.tif out.reg`), and mris_register does not accept a flag there --
# it reads "-N" itself as the target filename ("could not open template file
# -N"). mris_inflate/mris_fix_topology/mri_synthseg all place xopts safely (all
# flags first, or all positionals first), so only this one line is unsafe.
# fsr-getxopts's own comments date the current xopts-merging behaviour to
# 10/16/24, so this whole mechanism is young; re-add the line once FreeSurfer
# fixes rca-surfreg's argument ordering (see TODO.md).
RECONALL_TEST_EXPERT = (
    "mris_inflate -n 7\n"
    "mris_fix_topology -niters 2\n"
    "synthseg --fast\n"
    "mri_ca_register -tol 0.2 -N 100 -LEVELS 4 -A 125 -DT 0.1\n"
)


def _reconall_test_expert_file() -> str:
    """Write (idempotently) the test_run recon-all expert-options file.

    A deterministic path with fixed content keeps the nipype hash stable
    across runs, so an opt-in recon-all pass stays resumable. The same file
    is shared by the three sequential ReconAll nodes; recon2/pial pass
    xopts='overwrite' because recon1 has already copied it into the subject's
    scripts dir.
    """
    path = os.path.join(tempfile.gettempdir(), "swane_reconall_test_expert.txt")
    with open(path, "w") as handle:
        handle.write(RECONALL_TEST_EXPERT)
    return path


def freesurfer_workflow(
    name: str,
    step: FreesurferStep,
    is_hippo_amyg_labels: bool,
    synth_config: SectionProxy,
    base_dir: str = "/",
    max_cpu: int = 0,
    multicore_node_limit: CoreLimit = CoreLimit.SOFT_CAP,
    test_run: bool = False,
) -> CustomWorkflow:
    """
    Freesurfer cortical reconstruction, white matter ROI, basal ganglia and thalami ROI.
    If needed, segmentation of the hippocampal substructures and the nuclei of the amygdala.

    Parameters
    ----------
    name : str
        The workflow name.
    step : FreesurferStep
        Step to be executed.
    is_hippo_amyg_labels : bool
        Enable segmentation of the hippocampal substructures and the nuclei of the amygdala.
    synth_config: SectionProxy
        FreeSurfer Synth tools settings.
    base_dir : path, optional
        The base directory path relative to parent workflow. The default is "/".
    max_cpu : int, optional
        If greater than 0, limit the core usage of bedpostx. The default is 0.
    multicore_node_limit: CORE_LIMIT, optional
        Preference for bedpostX core usage. The default il CORE_LIMIT.SOFT_CAP
    test_run : bool, optional
        If True, speed up prerelease test runs at the cost of accuracy: for
        the SynthSeg step, enable --fast and drop the robust variant; for the
        recon-all steps, add lighter iteration counts via top-level flags and
        an -expert file of per-binary overrides. The default is False.

    Input Node Fields
    ----------
    ref : path
        T13D reference file.
    subjects_dir : path
        Directory for Freesurfer analysis.

    Returns
    -------
    workflow : CustomWorkflow
        The Freesurfer workflow.

    Output Node Fields
    ----------
    subject_id : string
        Subject name for Freesurfer (defined as FS_DIR="FS").
    subjects_dir : path
        Directory for Freesurfer analysis.
    bgROI : path
        Binary ROI for basal ganglia and thalamus.
    pial : list of strings
        Gray matter/pia mater rh and lh surfaces.
    white : list of strings
        White/gray matter rh and lh surfaces.
    vol_label_file : path
        Aparc parcellation projected into aseg volume in reference space.
    vol_label_file_nii : path
        Aparc parcellation projected into aseg volume in reference space and nifti format.
    lh_hippoAmygLabels : path
        Left side labels from segmentation of the hippocampal substructures and the nuclei of the amygdala.
    rh_hippoAmygLabels : path
        Right side labels from segmentation of the hippocampal substructures and the nuclei of the amygdala.

    """

    if step == FreesurferStep.DISABLED:
        # This should not be possible
        return None

    workflow = CustomWorkflow(name=name, base_dir=base_dir)

    # Input Node
    inputnode = Node(
        IdentityInterface(fields=["reference", "subjects_dir"]), name="inputnode"
    )

    # Output Node
    outputnode = Node(
        IdentityInterface(
            fields=[
                "subject_id",
                "subjects_dir",
                "bgROI",
                "pial",
                "white",
                "vol_label_file",
                "vol_label_file_nii",
                "lh_hippoAmygLabels",
                "rh_hippoAmygLabels",
            ]
        ),
        name="outputnode",
    )

    # Utility node to handle different paths of segmentation
    segmentation_holder = Node(
        IdentityInterface(fields=["seg_nii"]), name="segmentation_holder"
    )

    if step == FreesurferStep.SYNTHSEG:
        synth_seg = Node(SynthSeg(), name="synth_seg")
        synth_seg.inputs.parcellation = True
        if test_run:
            # Prerelease test runs: trade accuracy for speed by skipping
            # postprocessing (--fast) and dropping the slower robust variant.
            synth_seg.inputs.fast = True
            synth_seg.inputs.robust = False
            # With --fast/robust=False SynthSeg fits in less RAM; reserve the
            # same lowered figure the prerelease gate uses
            # (capabilities._probe_synth_ram), so a host sized for that gate can
            # actually schedule the node instead of tripping the plugin's prerun
            # resource check.
            synth_seg._mem_gb = (
                ResourceManager.synth_seg_ram_requirements()
                * ResourceManager.TEST_RUN_SYNTH_RAM_FACTOR
            )
        else:
            synth_seg.inputs.robust = True
            synth_seg._mem_gb = ResourceManager.synth_seg_ram_requirements()
        synth_seg.inputs.use_cpu = True
        synth_seg.inputs.keep_geometry = True
        # SynthSeg cannot be tricked into using more threads than nipype
        # believes it does (no separate env-var thread control), so it is
        # always a hard, nipype-visible cap regardless of multicore_node_limit.
        synth_seg_threads, _ = get_synth_cpu_config(
            max_cpu, multicore_node_limit, synth_config.getboolean_safe("limit_cores")
        )
        apply_synth_num_threads(synth_seg, synth_seg_threads, hard=True)
        synth_seg.inputs.out_file = "r-aparc_aseg.mgz"
        workflow.connect(inputnode, "reference", synth_seg, "in_file")
        workflow.connect(synth_seg, "out_file", outputnode, "vol_label_file")

        # NODE 3: Aparcaseg conversion mgz -> nifti
        synth_seg2nii = Node(ApplyVolTransform(), name="synth_seg2nii")
        synth_seg2nii.long_name = "Parcellation Nifti conversion"
        synth_seg2nii.inputs.transformed_file = "seg.nii.gz"
        synth_seg2nii.inputs.reg_header = True
        synth_seg2nii.inputs.interp = "nearest"
        workflow.connect(synth_seg, "out_file", synth_seg2nii, "source_file")
        workflow.connect(inputnode, "reference", synth_seg2nii, "target_file")
        workflow.connect(
            synth_seg2nii, "transformed_file", outputnode, "vol_label_file_nii"
        )
        workflow.connect(
            synth_seg2nii, "transformed_file", segmentation_holder, "seg_nii"
        )
    else:
        # Resources setup
        reconall_mem_gb = 5
        reconall_environ = {}
        reconall_parallel = False
        reconall_openmp = 1
        reconall_nprocs = 1

        if synth_config.getboolean_safe("reconall"):
            if test_run:
                reconall_mem_gb = (
                    ResourceManager.synth_reconall_ram_requirements()
                    * ResourceManager.TEST_RUN_SYNTH_RAM_FACTOR
                )
            else:
                reconall_mem_gb = ResourceManager.synth_reconall_ram_requirements()
        else:
            reconall_environ = {"FS_V8_XOPTS": "0"}

        # parallel option splits some steps in right and left
        if max_cpu > 1:
            reconall_parallel = True
        # openmp option apply max cpu tu some steps, resulting in twice cpu usage for rogh/left steps
        if multicore_node_limit == CoreLimit.NO_LIMIT:
            # no limit
            reconall_openmp = cpu_count()
        elif multicore_node_limit == CoreLimit.SOFT_CAP:
            # for soft cap we accept that parallelized steps use each max_cpu cores, resulting in twice the setting
            reconall_openmp = max_cpu
            reconall_nprocs = reconall_openmp
        elif max_cpu > 1:
            # for hard cap we use half of max_cpu setting, but at least 1
            reconall_openmp = max(trunc(max_cpu / 2), 1)
            reconall_nprocs = reconall_openmp * 2

        # test_run: speed up recon-all with lighter iteration counts, via
        # top-level flags plus an -expert file of per-binary overrides. The
        # same expert file feeds all three sequential nodes.
        reconall_args = "-no-isrunning"
        reconall_expert = None
        if test_run:
            reconall_args = "-no-isrunning " + RECONALL_TEST_ARGS
            reconall_expert = _reconall_test_expert_file()

        # NODE 1: Freesurfer autorecon1
        recon_all_recon1 = Node(ReconAll(), name="recon_all_recon1")
        recon_all_recon1.long_name = "%s: Preprocessing 1"
        recon_all_recon1.inputs.subject_id = FS_DIR
        recon_all_recon1._mem_gb = reconall_mem_gb
        recon_all_recon1.inputs.environ = reconall_environ
        recon_all_recon1.inputs.parallel = reconall_parallel
        recon_all_recon1.inputs.openmp = reconall_openmp
        recon_all_recon1.n_procs = reconall_nprocs
        recon_all_recon1.inputs.directive = "autorecon1"
        recon_all_recon1.inputs.args = reconall_args
        if reconall_expert is not None:
            recon_all_recon1.inputs.expert = reconall_expert
            recon_all_recon1.inputs.xopts = "overwrite"
        workflow.connect(inputnode, "reference", recon_all_recon1, "T1_files")
        workflow.connect(inputnode, "subjects_dir", recon_all_recon1, "subjects_dir")

        # outputnode.subject_id/subjects_dir are connected below, from the LAST
        # recon-all node in this chain (not recon1): consumers outside this
        # workflow (ASL/PET surface sampling in MainWorkflow) only get these two
        # plain strings, not a tracked dependency on the actual surface files --
        # they locate lh.white/lh.pial etc. on disk by FreeSurfer's own
        # subjects_dir/subject_id convention. Wiring from recon1 let nipype
        # consider them "ready" as soon as the FIRST node finished, so a slow
        # recon2/recon_pial (e.g. a resumed multi-hour run) let ASL/PET surface
        # sampling start and crash well before the files existed. Connecting
        # from the last node gives nipype a real edge to wait on.

        # NODE 2: Freesurfer autorecon2
        recon_all_recon2 = Node(ReconAll(), name="recon_all_recon2")
        recon_all_recon2.long_name = "%s: Preprocessing 2"
        recon_all_recon2._mem_gb = reconall_mem_gb
        recon_all_recon2.inputs.environ = reconall_environ
        recon_all_recon2.inputs.parallel = reconall_parallel
        recon_all_recon2.inputs.openmp = reconall_openmp
        recon_all_recon2.n_procs = reconall_nprocs
        recon_all_recon2.inputs.directive = "autorecon2"
        recon_all_recon2.inputs.args = reconall_args
        if reconall_expert is not None:
            recon_all_recon2.inputs.expert = reconall_expert
            recon_all_recon2.inputs.xopts = "overwrite"
        workflow.connect(
            recon_all_recon1, "subjects_dir", recon_all_recon2, "subjects_dir"
        )
        workflow.connect(recon_all_recon1, "subject_id", recon_all_recon2, "subject_id")

        # NODE 2: Freesurfer autorecon-pial
        recon_all_recon_pial = Node(ReconAll(), name="recon_all_recon_pial")
        recon_all_recon_pial.long_name = "%s: Surfaces + Cortical Parcellation"
        recon_all_recon_pial._mem_gb = reconall_mem_gb
        recon_all_recon_pial.inputs.environ = reconall_environ
        recon_all_recon_pial.inputs.parallel = reconall_parallel
        recon_all_recon_pial.inputs.openmp = reconall_openmp
        recon_all_recon_pial.n_procs = reconall_nprocs
        recon_all_recon_pial.inputs.directive = "autorecon-pial"
        recon_all_recon_pial.inputs.args = reconall_args
        if reconall_expert is not None:
            recon_all_recon_pial.inputs.expert = reconall_expert
            recon_all_recon_pial.inputs.xopts = "overwrite"
        workflow.connect(
            recon_all_recon2, "subjects_dir", recon_all_recon_pial, "subjects_dir"
        )
        workflow.connect(
            recon_all_recon2, "subject_id", recon_all_recon_pial, "subject_id"
        )

        workflow.connect(recon_all_recon_pial, "pial", outputnode, "pial")
        workflow.connect(recon_all_recon_pial, "white", outputnode, "white")

        # The actual last node in this chain: recon_all_recon_pial unless the
        # RECONALL step adds recon_all_recon3 below. outputnode.subject_id/
        # subjects_dir connect from whichever this ends up being (see the note
        # by recon_all_recon1's own subjects_dir connection, above).
        final_recon = recon_all_recon_pial

        # NODE 2: Aparcaseg linear transformation in reference space
        aparc_aseg2ref = Node(ApplyVolTransform(), name="aparc_aseg2ref")
        aparc_aseg2ref.long_name = "Parcellation in reference space"
        aparc_aseg2ref.inputs.transformed_file = "r-aparc_aseg.mgz"
        aparc_aseg2ref.inputs.reg_header = True
        aparc_aseg2ref.inputs.interp = "nearest"
        workflow.connect(
            [
                (
                    recon_all_recon_pial,
                    aparc_aseg2ref,
                    [(("aparc_aseg", getn, 0), "source_file")],
                )
            ]
        )
        workflow.connect(inputnode, "reference", aparc_aseg2ref, "target_file")
        workflow.connect(
            aparc_aseg2ref, "transformed_file", outputnode, "vol_label_file"
        )

        aparc_aseg2nii = Node(ApplyVolTransform(), name="aparc_aseg2nii")
        aparc_aseg2nii.long_name = "Parcellation Nifti conversion"
        aparc_aseg2nii.inputs.transformed_file = "r-aparc_aseg.nii.gz"
        aparc_aseg2nii.inputs.reg_header = True
        aparc_aseg2nii.inputs.interp = "nearest"
        workflow.connect(
            [
                (
                    recon_all_recon_pial,
                    aparc_aseg2nii,
                    [(("aparc_aseg", getn, 0), "source_file")],
                )
            ]
        )
        workflow.connect(inputnode, "reference", aparc_aseg2nii, "target_file")
        workflow.connect(
            aparc_aseg2nii, "transformed_file", outputnode, "vol_label_file_nii"
        )
        workflow.connect(
            aparc_aseg2nii, "transformed_file", segmentation_holder, "seg_nii"
        )

        if step == FreesurferStep.RECONALL:
            recon_all_recon3 = Node(ReconAll(), name="reconAll")
            recon_all_recon3.long_name = "%s: Finalization"
            recon_all_recon3._mem_gb = reconall_mem_gb
            recon_all_recon3.inputs.environ = reconall_environ
            recon_all_recon3.inputs.parallel = reconall_parallel
            recon_all_recon3.inputs.openmp = reconall_openmp
            recon_all_recon3.n_procs = reconall_nprocs
            recon_all_recon3.inputs.directive = "autorecon3"
            recon_all_recon3.inputs.args = "-no-isrunning"
            workflow.connect(
                recon_all_recon_pial, "subjects_dir", recon_all_recon3, "subjects_dir"
            )
            workflow.connect(
                recon_all_recon_pial, "subject_id", recon_all_recon3, "subject_id"
            )
            final_recon = recon_all_recon3

        workflow.connect(final_recon, "subject_id", outputnode, "subject_id")
        workflow.connect(final_recon, "subjects_dir", outputnode, "subjects_dir")

        if is_hippo_amyg_labels:
            # NODE 10: Segmentation of the hippocampal substructures and the nuclei of the amygdala
            segment_ha = Node(SegmentHA(), name="segment_ha")
            segment_ha._mem_gb = 5
            if multicore_node_limit == CoreLimit.NO_LIMIT:
                segment_ha.inputs.num_cpu = cpu_count()
            elif multicore_node_limit == CoreLimit.SOFT_CAP:
                segment_ha.inputs.num_cpu = max_cpu
            else:
                segment_ha.inputs.num_cpu = max_cpu
                segment_ha.n_procs = segment_ha.inputs.num_cpu
            workflow.connect(
                recon_all_recon_pial, "subjects_dir", segment_ha, "subjects_dir"
            )
            workflow.connect(
                recon_all_recon_pial, "subject_id", segment_ha, "subject_id"
            )

            rh_ha2ref = Node(ApplyVolTransform(), name="rh_ha2ref")
            rh_ha2ref.long_name = "Rh hippocampal subfield in reference space"
            rh_ha2ref.inputs.transformed_file = "r-rh_hippoAmygLabels.mgz"
            rh_ha2ref.inputs.reg_header = True
            rh_ha2ref.inputs.interp = "nearest"
            workflow.connect(segment_ha, "rh_hippoAmygLabels", rh_ha2ref, "source_file")
            workflow.connect(inputnode, "reference", rh_ha2ref, "target_file")

            lh_ha2ref = Node(ApplyVolTransform(), name="lh_ha2ref")
            lh_ha2ref.long_name = "Lh hippocampal subfield in reference space"
            lh_ha2ref.inputs.transformed_file = "r-lh_hippoAmygLabels.mgz"
            lh_ha2ref.inputs.reg_header = True
            lh_ha2ref.inputs.interp = "nearest"
            workflow.connect(segment_ha, "lh_hippoAmygLabels", lh_ha2ref, "source_file")
            workflow.connect(inputnode, "reference", lh_ha2ref, "target_file")

            workflow.connect(
                rh_ha2ref, "transformed_file", outputnode, "lh_hippoAmygLabels"
            )
            workflow.connect(
                lh_ha2ref, "transformed_file", outputnode, "rh_hippoAmygLabels"
            )

    if segmentation_holder is not None:
        # NODE 7: Left basal ganglia and thalamus binary ROI
        lhbgROI = Node(ThrROI(), name="lhbgROI")
        lhbgROI.long_name = "Lh Basal ganglia ROI"
        lhbgROI.inputs.seg_val_min = 11
        lhbgROI.inputs.seg_val_max = 13
        lhbgROI.inputs.out_file = "lhbgROI.nii.gz"
        workflow.connect(segmentation_holder, "seg_nii", lhbgROI, "in_file")

        # NODE 8: Right basal ganglia and thalamus binary ROI
        rhbgROI = Node(ThrROI(), name="rhbgROI")
        rhbgROI.long_name = "Rh Basal ganglia ROI"
        rhbgROI.inputs.seg_val_min = 50
        rhbgROI.inputs.seg_val_max = 52
        rhbgROI.inputs.out_file = "rhbgROI.nii.gz"
        workflow.connect(segmentation_holder, "seg_nii", rhbgROI, "in_file")

        # NODE 9: Basal ganglia and thalami binary ROI
        bgROI = Node(BinaryMaths(), name="bgROI")
        bgROI.long_name = "Basal ganglia ROI"
        bgROI.inputs.operation = "add"
        bgROI.inputs.out_file = "bgROI.nii.gz"
        workflow.connect(lhbgROI, "out_file", bgROI, "in_file")
        workflow.connect(rhbgROI, "out_file", bgROI, "operand_file")

        workflow.connect(bgROI, "out_file", outputnode, "bgROI")

        # TODO wmROI work in progress - Not used for now. Maybe useful for SUPERFLAIR
        # # NODE 4: Left cerebral white matter binary ROI
        # lhwmROI = Node(ThrROI(), name="lhwmROI")
        # lhwmROI.long_name = "Lh white matter ROI"
        # lhwmROI.inputs.seg_val_min = 2
        # lhwmROI.inputs.seg_val_max = 2
        # lhwmROI.inputs.out_file = "lhwmROI.nii.gz"
        # workflow.connect(segmentation_holder, "seg_nii", lhwmROI, "in_file")
        #
        # # NODE 5: Right cerebral white matter binary ROI
        # rhwmROI = Node(ThrROI(), name="rhwmROI")
        # rhwmROI.long_name = "Rh white matter ROI"
        # rhwmROI.inputs.seg_val_min = 41
        # rhwmROI.inputs.seg_val_max = 41
        # rhwmROI.inputs.out_file = "rhwmROI.nii.gz"
        # workflow.connect(segmentation_holder, "seg_nii", rhwmROI, "in_file")
        #
        # # NODE 4: Cerebral white matter binary ROI
        # wmROI = Node(BinaryMaths(), name="wmROI")
        # wmROI.long_name = "white matter ROI"
        # wmROI.inputs.operation = "add"
        # wmROI.inputs.out_file = "wmROI.nii.gz"
        # workflow.connect(lhwmROI, "out_file", wmROI, "in_file")
        # workflow.connect(rhwmROI, "out_file", wmROI, "operand_file")
        # workflow.connect(wmROI, "out_file", outputnode, "wmROI")

    return workflow
