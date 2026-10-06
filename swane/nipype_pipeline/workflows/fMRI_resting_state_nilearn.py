from nipype import Node, MapNode, IdentityInterface, Merge
from nipype.interfaces.fsl import ConvertWarp, ConvertXFM, InvWarp
from nipype.interfaces.utility import Function
from configparser import SectionProxy
from ica_aroma_py import aroma_mask_csf
from swane.nipype_pipeline.interfaces.fmri.NilearnAutoDim import NilearnAutoDim
from swane.nipype_pipeline.interfaces.fmri.NilearnCanICA import NilearnCanICA
from swane.nipype_pipeline.interfaces.fmri.DualRegressionZStat import (
    DualRegressionZStat,
)
from swane.nipype_pipeline.interfaces.fmri.GgmThreshold import GgmThreshold
from swane.nipype_pipeline.interfaces.fmri.IcaDenoise import IcaDenoise
from swane.nipype_pipeline.interfaces.fmri.NuisanceRegression import (
    NuisanceRegression,
)
from swane.nipype_pipeline.interfaces.fmri.FastIcaIcasso import FastIcaIcasso
from swane.nipype_pipeline.interfaces.fmri.ClusterExtentMC import ClusterExtentMC
from swane.nipype_pipeline.interfaces.fmri.SpatialZThreshold import (
    SpatialZThreshold,
)
from swane.nipype_pipeline.interfaces.fmri.MaskedResampleCombine import (
    MaskedResampleCombine,
)
from swane.nipype_pipeline.interfaces.niimath import ImageMaths
from swane.nipype_pipeline.interfaces.ram_estimators import (
    ClusterExtentMCRamEstimator,
    DualRegressionRamEstimator,
    FastIcaIcassoRamEstimator,
    InvWarpRamEstimator,
    NilearnAutoDimRamEstimator,
    NilearnCanICARamEstimator,
    NuisanceRegressionRamEstimator,
)
from swane.nipype_pipeline.interfaces.utils import (
    apply_registration_node,
    getn,
)
from swane.nipype_pipeline.engine.CustomWorkflow import CustomWorkflow
from swane.nipype_pipeline.workflows.fMRI_preproc_workflow import highpass_op_string
from swane.nipype_pipeline.workflows.fMRI_resting_state_aroma import (
    build_aroma_classification,
    build_ref_2_mni,
)
from swane.config.config_enums import RegistrationEngine

# High-pass cutoff (seconds) of the preprocessing and of the cleaned data.
HP_CUTOFF = 100
# Subject tissue posterior threshold, applied in reference space.
TISSUE_PROB_THR = 0.95
# Threshold that re-binarises the masks after linear resampling.
RESAMPLED_MASK_THR = 0.5
# Mixture-model threshold of the ICA-AROMA pass maps (not a preference).
AROMA_MM_THRESH = 0.5


def n_hp_columns(T, TR, cutoff=100.0):
    """
    Number of discrete cosine regressors of a high-pass filter with the given
    cutoff (seconds): min(floor(2 * T * TR / cutoff), T - 1), never negative.
    It is the number of temporal degrees of freedom the high-pass removes.
    """
    import math

    order = min(int(math.floor(2.0 * T * TR / cutoff)), T - 1)
    return max(order, 0)


def count_motion_ics(motion_ics):
    """Number of components classified as motion by ICA-AROMA."""
    return len(motion_ics)


def removed_rank(rank, n_aroma):
    """Rank removed before the model order: design rank (constant included)
    plus the non-aggressively removed motion components."""
    return rank + n_aroma


def compute_dof(in_file, TR, rank, n_aroma):
    """Degrees of freedom left in the cleaned data: T - rank - n_HP - n_AROMA."""
    import nibabel as nib
    from swane.nipype_pipeline.workflows.fMRI_resting_state_nilearn import (
        n_hp_columns,
    )

    T = int(nib.load(in_file).shape[3])
    return T - int(rank) - n_hp_columns(T, TR) - int(n_aroma)


def split_zstats(in_file):
    """Write each volume of a 4D z map as ``zstatNN.nii.gz`` (1-based)."""
    import os
    import nibabel as nib
    import numpy as np

    img = nib.load(in_file)
    data = img.get_fdata(dtype=np.float32)
    out_files = []
    for k in range(data.shape[3]):
        header = img.header.copy()
        header.set_data_dtype(np.float32)
        path = os.path.abspath("zstat%02d.nii.gz" % (k + 1))
        nib.save(nib.Nifti1Image(data[..., k], img.affine, header), path)
        out_files.append(path)
    return out_files


def get_wm_prior():
    """Path of the binary white-matter prior on the MNI152NLin6Asym 2 mm grid
    (built and cached on first use)."""
    from swane.utils.wm_prior import nlin6_wm_prior

    return nlin6_wm_prior()


def reserve_ram(node: Node, estimator_class) -> Node:
    """Size the node's RAM reservation from its 4D inputs at run time, with
    the estimator's static value as fallback when the estimate cannot run."""
    node._mem_gb = estimator_class.STATIC_FALLBACK_GB
    node.ram_estimator = estimator_class()
    return node


def dof_node(name: str = "dof") -> Node:
    """Function node computing ``dof`` from the cleaned data, TR, design
    rank and number of motion components (see `compute_dof`)."""
    node = Node(
        Function(
            input_names=["in_file", "TR", "rank", "n_aroma"],
            output_names=["dof"],
            function=compute_dof,
        ),
        name=name,
    )
    node.long_name = "Residual degrees of freedom"
    return node


def zstat_split_node(name: str = "ica_zstat_split") -> Node:
    """Function node splitting a 4D z map into ``zstatNN.nii.gz`` files."""
    node = Node(
        Function(
            input_names=["in_file"],
            output_names=["out_files"],
            function=split_zstats,
        ),
        name=name,
    )
    node.long_name = "Component maps split"
    return node


def build_nilearn_resting(
    workflow: CustomWorkflow,
    name: str,
    config: SectionProxy,
    synth_config: SectionProxy,
    engine: RegistrationEngine,
    test_run: bool = False,
    max_cpu: int = 0,
) -> Node:
    """
    Add the Python (nilearn/scikit-learn) resting-state analysis to a
    preprocessed workflow.

    Chain (Pruim et al. 2015a NeuroImage 112:267; 2015b NeuroImage 112:278
    for the order smoothing -> ICA-AROMA -> nuisance regression -> high-pass):

    1. Unsmoothed twin: the motion-corrected data in the dilated mask,
       scaled like the smoothed intensity-normalised data. It is never
       smoothed, decomposed or thresholded and only feeds the model order.
    2. ICA-AROMA pass (AROMA enabled): MDL model order on the
       motion-corrected data (tight mask), CanICA on the unfiltered
       intensity-normalised data (tight mask), dual regression, mixture-model
       maps for the spatial features, AROMA classification, then
       non-aggressive removal of the motion components from the smoothed
       data and from the twin, with the same mixing matrix.
    3. Nuisance ROIs: subject tissue posterior > 0.95 (Atropos or FAST, from
       the shared reference segmentation ``inputnode.tissue_pve``) in
       reference space, moved to functional space; MNI152NLin6Asym CSF
       (ICA-AROMA) and WM priors moved to functional space; both with linear
       interpolation, re-binarised at 0.5 and intersected with the tight
       mask.
    4. Nuisance regression of [linear trend, mean WM, mean CSF] (plus the
       Friston-24 motion regressors when AROMA is disabled; Friston et al.
       1996 MRM 35:346), sampled from the smoothed data, applied to the
       smoothed data and to the twin; then the temporal high-pass of the
       smoothed data.
    5. Final ICA: MDL model order on the regressed twin with the removed rank
       (Li, Adali & Calhoun 2007 HBM 28:1251), or ``ic_dim`` when > 0;
       FastICA with ICASSO run selection in the dilated mask; dual regression
       with the residual degrees of freedom; spatial z threshold with the
       Monte Carlo cluster extent estimated from the dual-regression
       residuals.

    Parameters
    ----------
    workflow : CustomWorkflow
        The workflow built by ``fMRI_preproc_workflow``.
    name : str
        The workflow name (the prefix of the preprocessing node names).
    config : SectionProxy
        The resting-state workflow settings (``aroma``, ``ic_dim``,
        ``spatial_z_thr``).
    synth_config : SectionProxy
        The Synth-tools configuration section, forwarded to the
        reference-to-atlas registration.
    engine : RegistrationEngine
        The resolved EPI registration engine (ANTS or FSL).
    test_run : bool, optional
        If True, speed up the registration. The default is False.
    max_cpu : int, optional
        Per-subject CPU budget. The default is 0.

    Returns
    -------
    Node
        The final ICA output node, with fields ``thresh_zstat_files``
        (thresholded maps in functional space), ``ic_mix`` (mixing matrix),
        ``zstat_file`` (unthresholded 4D z), ``survivor_pos_files`` and
        ``survivor_neg_files`` (native survivor masks); see
        `build_nilearn_output_space`.

    """
    run_aroma = config.getboolean_safe("aroma")
    ic_dim = config.getint_safe("ic_dim")
    spatial_z_thr = config.getfloat_safe("spatial_z_thr")

    # Per-node core budget of the BLAS-bound Python nodes: each sets
    # num_threads (the interfaces cap their OpenMP/BLAS pools at it), from
    # which Nipype derives the n_procs reservation. max_cpu == 0 means
    # "auto/all cores" upstream, so it must clamp to 1 here, never 0. Nodes
    # whose work is (almost) single-threaded are pinned to 1 thread.
    parallel_cpu = max_cpu if max_cpu and max_cpu > 0 else 1

    getTR = workflow.get_node("%s_getTR" % name)
    meanfuncmask = workflow.meanfuncmask
    motion_correct = workflow.get_node("%s_motion_correct" % name)
    dilatemask = workflow.get_node("%s_dilatemask" % name)
    meanfunc2 = workflow.get_node("%s_meanfunc2" % name)
    medianval = workflow.medianval_node
    intnorm = workflow.intnorm_node
    inputnode = workflow.get_node("inputnode")

    # This chain high-passes after the nuisance regression (highpass_clean):
    # the preprocessing high-pass and its mean/TR setup have no consumer.
    workflow.remove_nodes(
        [
            workflow.get_node("%s_%s" % (name, suffix))
            for suffix in ("highpass", "merge_tr_meanfunc3", "meanfunc3")
        ]
    )

    # ------------------------------------------------------------------
    # Unsmoothed twin: motion-corrected data in the dilated mask, scaled by
    # the same 10000 / median as the smoothed intensity normalisation.
    # ------------------------------------------------------------------
    maskfunc_unsmoothed = Node(ImageMaths(), name="%s_maskfunc_unsmoothed" % name)
    maskfunc_unsmoothed.long_name = "unsmoothed images masking"
    maskfunc_unsmoothed.inputs.suffix = "_mask"
    maskfunc_unsmoothed.inputs.op_string = "-mas"
    workflow.connect(motion_correct, "out_file", maskfunc_unsmoothed, "in_file")
    workflow.connect(dilatemask, "out_file", maskfunc_unsmoothed, "in_file2")

    intnorm_unsmoothed = Node(ImageMaths(), name="%s_intnorm_unsmoothed" % name)
    intnorm_unsmoothed.long_name = "unsmoothed intensity normalization"
    intnorm_unsmoothed.inputs.suffix = "_intnorm"

    # Same function as the preprocessing intensity normalisation.
    def get_inorm_scale(percentile_values):
        return "-mul %.10f" % (10000.0 / percentile_values[0])

    workflow.connect(maskfunc_unsmoothed, "out_file", intnorm_unsmoothed, "in_file")
    workflow.connect(
        medianval,
        ("percentile_values", get_inorm_scale),
        intnorm_unsmoothed,
        "op_string",
    )

    smoothed_node, smoothed_field = intnorm, "out_file"
    twin_node, twin_field = intnorm_unsmoothed, "out_file"

    # ------------------------------------------------------------------
    # ICA-AROMA pass on the unfiltered data.
    # ------------------------------------------------------------------
    count_ics = None
    if run_aroma:
        preproc_auto_dim = Node(NilearnAutoDim(), name="preproc_ica_auto_dim")
        preproc_auto_dim.inputs.num_threads = parallel_cpu
        reserve_ram(preproc_auto_dim, NilearnAutoDimRamEstimator)
        workflow.connect(motion_correct, "out_file", preproc_auto_dim, "in_file")
        workflow.connect(meanfuncmask, "mask_file", preproc_auto_dim, "mask_file")

        preproc_canica = Node(NilearnCanICA(), name="preproc_ica_canica")
        preproc_canica.inputs.num_threads = parallel_cpu
        reserve_ram(preproc_canica, NilearnCanICARamEstimator)
        workflow.connect(
            preproc_auto_dim, "n_components", preproc_canica, "n_components"
        )
        workflow.connect(intnorm, "out_file", preproc_canica, "preproc_file")
        workflow.connect(meanfuncmask, "mask_file", preproc_canica, "mask_file")

        preproc_dual_reg = Node(DualRegressionZStat(), name="preproc_ica_dual_reg")
        preproc_dual_reg.inputs.num_threads = parallel_cpu
        reserve_ram(preproc_dual_reg, DualRegressionRamEstimator)
        # The AROMA pass uses uncentred maps and keeps the t statistics.
        preproc_dual_reg.inputs.centre_maps = False
        preproc_dual_reg.inputs.t_to_z = False
        # Only the final pass feeds its residuals to the cluster-extent estimate.
        preproc_dual_reg.inputs.write_residuals = False
        workflow.connect(intnorm, "out_file", preproc_dual_reg, "preproc_file")
        workflow.connect(meanfuncmask, "mask_file", preproc_dual_reg, "mask_file")
        workflow.connect(
            preproc_canica, "components_file", preproc_dual_reg, "components_file"
        )

        # ICA-AROMA spatial features are defined on mixture-model maps.
        preproc_ggm = Node(GgmThreshold(), name="preproc_ica_ggm")
        preproc_ggm.inputs.mm_thresh = AROMA_MM_THRESH
        # Mostly serial EM; the brief OpenMP k-means initialisation is capped.
        preproc_ggm.inputs.num_threads = 1
        workflow.connect(preproc_dual_reg, "zstat_file", preproc_ggm, "zstat_file")
        workflow.connect(meanfuncmask, "mask_file", preproc_ggm, "mask_file")

        # The AROMA module reads the mixing matrix as ``mel_mix``.
        preproc_ica_output = Node(
            IdentityInterface(
                fields=["IC", "mel_mix", "mel_ft_mix", "thresh_zstat_files"]
            ),
            name="preproc_ica_output",
        )
        workflow.connect(preproc_canica, "components_file", preproc_ica_output, "IC")
        workflow.connect(preproc_dual_reg, "ic_mix", preproc_ica_output, "mel_mix")
        workflow.connect(
            preproc_dual_reg, "ic_ft_mix", preproc_ica_output, "mel_ft_mix"
        )
        workflow.connect(
            preproc_ggm, "thresh_zstat_files", preproc_ica_output, "thresh_zstat_files"
        )

        aroma_classification, reg_2_mni = build_aroma_classification(
            workflow=workflow,
            ica_output=preproc_ica_output,
            mask_node=meanfuncmask,
            mask_field="mask_file",
            motion_correct=motion_correct,
            getTR=getTR,
            inputnode=inputnode,
            engine=engine,
            synth_config=synth_config,
            test_run=test_run,
            max_cpu=max_cpu,
        )

        # The same mixing matrix and motion components clean the smoothed
        # data and the unsmoothed twin.
        denoised = []
        for den_name, in_node in (
            ("nonaggr_denoising", intnorm),
            ("nonaggr_denoising_unsmoothed", intnorm_unsmoothed),
        ):
            den = Node(IcaDenoise(), name=den_name, mem_gb=5)
            den.inputs.aggressive = False
            den.inputs.num_threads = parallel_cpu
            workflow.connect(in_node, "out_file", den, "in_file")
            workflow.connect(dilatemask, "out_file", den, "mask_file")
            workflow.connect(preproc_ica_output, "mel_mix", den, "ic_mix")
            workflow.connect(aroma_classification, "motion_ics", den, "motion_ics")
            denoised.append(den)
        smoothed_node, smoothed_field = denoised[0], "denoised_file"
        twin_node, twin_field = denoised[1], "denoised_file"

        count_ics = Node(
            Function(
                input_names=["motion_ics"],
                output_names=["n_aroma"],
                function=count_motion_ics,
            ),
            name="count_motion_ics",
        )
        count_ics.long_name = "Motion components count"
        workflow.connect(aroma_classification, "motion_ics", count_ics, "motion_ics")
    else:
        reg_2_mni, _ = build_ref_2_mni(
            workflow=workflow,
            inputnode=inputnode,
            engine=engine,
            synth_config=synth_config,
            test_run=test_run,
            max_cpu=max_cpu,
        )

    # ------------------------------------------------------------------
    # Nuisance ROIs in functional space.
    # ------------------------------------------------------------------
    # Subject tissue posteriors [CSF, GM, WM] come from the shared reference
    # segmentation (inputnode.tissue_pve): Atropos on the N4-corrected
    # reference_brain, or FAST on the uncorrected brain (FAST runs its own
    # bias correction).

    wm_prior = Node(
        Function(input_names=[], output_names=["prior_file"], function=get_wm_prior),
        name="wm_prior_mni",
    )
    wm_prior.long_name = "White matter prior"

    if engine == RegistrationEngine.ANTS:
        inv_xfm = None
        mni_2_func = None
    else:
        # Inverse FSL stack: ref <- MNI (inverse of the FNIRT warp), func <-
        # ref (inverse of the FLIRT matrix), composed into one warp.
        inv_xfm = Node(ConvertXFM(), name="%s_2_ref_invwarp" % name)
        inv_xfm.long_name = "reference to functional matrix"
        inv_xfm.inputs.invert_xfm = True
        workflow.connect(
            workflow.reg_2_ref.out_registered_node,
            workflow.reg_2_ref.warp,
            inv_xfm,
            "in_file",
        )

        inv_warp = Node(InvWarp(), name="ref_2_mni_invwarp")
        inv_warp.long_name = "atlas to reference warp"
        inv_warp.ram_estimator = InvWarpRamEstimator()
        workflow.connect(
            reg_2_mni.out_registered_node, reg_2_mni.warp, inv_warp, "warp"
        )
        workflow.connect(inputnode, "reference_brain", inv_warp, "reference")

        mni_2_func = Node(ConvertWarp(), name="mni_2_func_warp")
        mni_2_func.long_name = "atlas to functional warp combination"
        workflow.connect(inv_warp, "inverse_warp", mni_2_func, "warp1")
        workflow.connect(inv_xfm, "out_file", mni_2_func, "postmat")
        workflow.connect(meanfunc2, "out_file", mni_2_func, "reference")

    rois = {}
    for tissue, index, prior in (
        ("csf", 0, aroma_mask_csf),
        ("wm", 2, [wm_prior, "prior_file"]),
    ):
        subject_thr = Node(ImageMaths(), name="%s_subject_thr" % tissue)
        subject_thr.long_name = "%s posterior threshold" % tissue.upper()
        subject_thr.inputs.op_string = "-thr %g -bin" % TISSUE_PROB_THR
        subject_thr.inputs.suffix = "_thr"
        workflow.connect(inputnode, ("tissue_pve", getn, index), subject_thr, "in_file")

        if engine == RegistrationEngine.ANTS:
            subject_2_func = apply_registration_node(
                name="%s_subject_2_func" % tissue,
                engine=engine,
                workflow=workflow,
                warp=None,
                registration=workflow.reg_2_ref,
                inverse=True,
                moving=[subject_thr, "out_file"],
                reference=[meanfunc2, "out_file"],
                name_prefix="%s mask" % tissue.upper(),
                name_suffix="to functional",
            )
            # Output (func) -> input (MNI) order: func <- ref, then ref <- MNI.
            prior_2_func = apply_registration_node(
                name="%s_prior_2_func" % tissue,
                engine=engine,
                workflow=workflow,
                warp=None,
                registration_stack=[workflow.reg_2_ref, reg_2_mni],
                inverse=True,
                moving=prior,
                reference=[meanfunc2, "out_file"],
                name_prefix="%s prior" % tissue.upper(),
                name_suffix="to functional",
            )
        else:
            subject_2_func = apply_registration_node(
                name="%s_subject_2_func" % tissue,
                engine=engine,
                workflow=workflow,
                warp=[inv_xfm, "out_file"],
                moving=[subject_thr, "out_file"],
                reference=[meanfunc2, "out_file"],
                non_linear=False,
                name_prefix="%s mask" % tissue.upper(),
                name_suffix="to functional",
            )
            prior_2_func = apply_registration_node(
                name="%s_prior_2_func" % tissue,
                engine=engine,
                workflow=workflow,
                warp=[mni_2_func, "out_file"],
                moving=prior,
                reference=[meanfunc2, "out_file"],
                non_linear=True,
                name_prefix="%s prior" % tissue.upper(),
                name_suffix="to functional",
            )
            # Keep the linear interpolation continuous (FSL writes the input
            # data type otherwise).
            subject_2_func.inputs.datatype = "float"
            prior_2_func.inputs.datatype = "float"

        # Binarise the prior at the resampling threshold and intersect
        # with the tight BOLD mask: (prior >= thr) & mask, dtype uint8.
        # niimath's -thr keeps values >= thr (not strictly > thr); on
        # interpolated values the difference is negligible.
        prior_thr_bin = Node(ImageMaths(), name="%s_prior_thr_bin" % tissue)
        prior_thr_bin.long_name = "%s prior threshold and mask" % tissue.upper()
        prior_thr_bin.inputs.op_string = "-thr %g -bin -mas" % RESAMPLED_MASK_THR
        prior_thr_bin.inputs.out_data_type = "char"
        prior_thr_bin.inputs.suffix = "_thr"
        workflow.connect(prior_2_func, "out_file", prior_thr_bin, "in_file")
        workflow.connect(meanfuncmask, "mask_file", prior_thr_bin, "in_file2")

        # Binarise the resampled subject posterior at the same threshold
        # and intersect with the binarised prior:
        # (subject >= thr) & (prior >= thr) & mask, dtype uint8.
        roi = Node(ImageMaths(), name="%s_roi" % tissue)
        roi.long_name = "%s nuisance ROI" % tissue.upper()
        roi.inputs.op_string = "-thr %g -bin -mas" % RESAMPLED_MASK_THR
        roi.inputs.out_data_type = "char"
        roi.inputs.suffix = "_roi"
        workflow.connect(subject_2_func, "out_file", roi, "in_file")
        workflow.connect(prior_thr_bin, "out_file", roi, "in_file2")
        rois[tissue] = roi

    # ------------------------------------------------------------------
    # Nuisance regression and temporal high-pass.
    # ------------------------------------------------------------------
    nuisance = Node(NuisanceRegression(), name="nuisance_regression")
    reserve_ram(nuisance, NuisanceRegressionRamEstimator)
    nuisance.long_name = "Nuisance regression"
    nuisance.inputs.motion24 = not run_aroma
    nuisance.inputs.num_threads = parallel_cpu
    workflow.connect(smoothed_node, smoothed_field, nuisance, "in_file")
    workflow.connect(twin_node, twin_field, nuisance, "twin_file")
    workflow.connect(dilatemask, "out_file", nuisance, "mask_file")
    workflow.connect(rois["wm"], "out_file", nuisance, "wm_roi_file")
    workflow.connect(rois["csf"], "out_file", nuisance, "csf_roi_file")
    if not run_aroma:
        workflow.connect(motion_correct, "par_file", nuisance, "par_file")

    meanfunc_clean = Node(ImageMaths(), name="meanfunc_clean")
    meanfunc_clean.long_name = "mean image calculation"
    meanfunc_clean.inputs.op_string = "-Tmean"
    meanfunc_clean.inputs.suffix = "_mean"
    workflow.connect(nuisance, "out_file", meanfunc_clean, "in_file")

    merge_tr_mean = Node(Merge(2), name="merge_tr_meanfunc_clean")
    merge_tr_mean.long_name = "Highpass filtering setup"
    workflow.connect(getTR, "TR", merge_tr_mean, "in1")
    workflow.connect(meanfunc_clean, "out_file", merge_tr_mean, "in2")

    highpass_clean = Node(ImageMaths(), name="highpass_clean")
    highpass_clean.long_name = "Highpass temporal filtering"
    highpass_clean.inputs.suffix = "_tempfilt"
    workflow.connect(
        merge_tr_mean,
        ("out", highpass_op_string, HP_CUTOFF),
        highpass_clean,
        "op_string",
    )
    workflow.connect(nuisance, "out_file", highpass_clean, "in_file")

    # ------------------------------------------------------------------
    # Final ICA, dual regression and threshold.
    # ------------------------------------------------------------------
    ica = Node(FastIcaIcasso(), name="ica_fastica_icasso")
    reserve_ram(ica, FastIcaIcassoRamEstimator)
    ica.long_name = "FastICA with ICASSO"
    ica.inputs.num_threads = parallel_cpu
    workflow.connect(highpass_clean, "out_file", ica, "in_file")
    workflow.connect(dilatemask, "out_file", ica, "mask_file")

    if ic_dim > 0:
        ica.inputs.n_components = ic_dim
    else:
        n_removed = Node(
            Function(
                input_names=["rank", "n_aroma"],
                output_names=["n_removed"],
                function=removed_rank,
            ),
            name="n_removed",
        )
        n_removed.long_name = "Removed rank"
        workflow.connect(nuisance, "rank", n_removed, "rank")
        if count_ics is not None:
            workflow.connect(count_ics, "n_aroma", n_removed, "n_aroma")
        else:
            n_removed.inputs.n_aroma = 0

        auto_dim = Node(NilearnAutoDim(), name="ica_auto_dim")
        auto_dim.long_name = "Model order estimation"
        auto_dim.inputs.num_threads = parallel_cpu
        reserve_ram(auto_dim, NilearnAutoDimRamEstimator)
        workflow.connect(nuisance, "twin_out_file", auto_dim, "in_file")
        workflow.connect(meanfuncmask, "mask_file", auto_dim, "mask_file")
        workflow.connect(n_removed, "n_removed", auto_dim, "n_removed")
        workflow.connect(auto_dim, "n_components", ica, "n_components")

    dof = dof_node()
    workflow.connect(highpass_clean, "out_file", dof, "in_file")
    workflow.connect(getTR, "TR", dof, "TR")
    workflow.connect(nuisance, "rank", dof, "rank")
    if count_ics is not None:
        workflow.connect(count_ics, "n_aroma", dof, "n_aroma")
    else:
        dof.inputs.n_aroma = 0

    dual_reg = Node(DualRegressionZStat(), name="ica_dual_reg")
    dual_reg.long_name = "Dual regression"
    dual_reg.inputs.num_threads = parallel_cpu
    reserve_ram(dual_reg, DualRegressionRamEstimator)
    workflow.connect(highpass_clean, "out_file", dual_reg, "preproc_file")
    workflow.connect(dilatemask, "out_file", dual_reg, "mask_file")
    workflow.connect(ica, "components_file", dual_reg, "components_file")
    workflow.connect(dof, "dof", dual_reg, "dof")

    cluster_extent = Node(ClusterExtentMC(), name="ica_cluster_extent")
    cluster_extent.long_name = "Cluster extent estimation"
    # FFT filtering and labelling of the null fields are single-threaded.
    cluster_extent.inputs.num_threads = 1
    reserve_ram(cluster_extent, ClusterExtentMCRamEstimator)
    # The null fields are thresholded at the same |z| as the maps.
    cluster_extent.inputs.z_thr = spatial_z_thr
    workflow.connect(dual_reg, "residual_file", cluster_extent, "residual_file")
    workflow.connect(dilatemask, "out_file", cluster_extent, "mask_file")

    spatialz = Node(SpatialZThreshold(), name="ica_spatialz")
    spatialz.long_name = "Spatial z threshold"
    spatialz.inputs.z_thr = spatial_z_thr
    workflow.connect(dual_reg, "zstat_file", spatialz, "zstat_file")
    workflow.connect(dilatemask, "out_file", spatialz, "mask_file")
    workflow.connect(
        cluster_extent, "min_cluster_voxels", spatialz, "min_cluster_voxels"
    )

    ica_output = Node(
        IdentityInterface(
            fields=[
                "thresh_zstat_files",
                "ic_mix",
                "zstat_file",
                "survivor_pos_files",
                "survivor_neg_files",
            ]
        ),
        name="ica_output",
    )
    workflow.connect(spatialz, "thresh_zstat_files", ica_output, "thresh_zstat_files")
    workflow.connect(dual_reg, "ic_mix", ica_output, "ic_mix")
    workflow.connect(dual_reg, "zstat_file", ica_output, "zstat_file")
    workflow.connect(spatialz, "survivor_pos_files", ica_output, "survivor_pos_files")
    workflow.connect(spatialz, "survivor_neg_files", ica_output, "survivor_neg_files")

    return ica_output


def build_nilearn_output_space(
    workflow: CustomWorkflow,
    ica_output: Node,
    engine: RegistrationEngine,
    inputnode: Node,
    out_file_name,
) -> Node:
    """
    Move the thresholded component maps to the reference space.

    The threshold stays decided in functional space. The unthresholded z and
    the positive and negative survivor masks are resampled to the reference
    with linear interpolation, and the output is the resampled z where the
    resampled mask of the same sign is > 0.5 (`MaskedResampleCombine`): no
    sub-threshold ramp is created around the clusters.

    Parameters
    ----------
    workflow : CustomWorkflow
        The resting-state workflow (it must expose ``workflow.reg_2_ref``).
    ica_output : Node
        The node returned by `build_nilearn_resting`.
    engine : RegistrationEngine
        The resolved EPI registration engine.
    inputnode : Node
        The workflow input node (``reference_brain``).
    out_file_name : function
        Maps the list of thresholded map paths to the output file names.

    Returns
    -------
    Node
        The ``zstats_combine`` MapNode (field ``out_file``).

    """
    split = zstat_split_node()
    workflow.connect(ica_output, "zstat_file", split, "in_file")

    applied = {}
    for stem, moving, label in (
        ("zstats_unthr_2_ref", [split, "out_files"], "Z maps"),
        ("survivors_pos_2_ref", [ica_output, "survivor_pos_files"], "Positive masks"),
        ("survivors_neg_2_ref", [ica_output, "survivor_neg_files"], "Negative masks"),
    ):
        node = apply_registration_node(
            name=stem,
            engine=engine,
            workflow=workflow,
            warp=[workflow.reg_2_ref.out_registered_node, workflow.reg_2_ref.warp],
            registration=workflow.reg_2_ref,
            moving=moving,
            reference=[inputnode, "reference_brain"],
            non_linear=False,
            name_prefix=label,
            name_suffix="to reference",
            iterfield=["in_file"],
        )
        if engine != RegistrationEngine.ANTS:
            node.inputs.datatype = "float"
        applied[stem] = node

    combine = MapNode(
        MaskedResampleCombine(),
        name="zstats_combine",
        iterfield=["z_file", "pos_mask_file", "neg_mask_file", "out_file"],
    )
    combine.long_name = "Thresholded maps in reference space"
    combine.inputs.mask_thr = RESAMPLED_MASK_THR
    workflow.connect(applied["zstats_unthr_2_ref"], "out_file", combine, "z_file")
    workflow.connect(
        applied["survivors_pos_2_ref"], "out_file", combine, "pos_mask_file"
    )
    workflow.connect(
        applied["survivors_neg_2_ref"], "out_file", combine, "neg_mask_file"
    )
    workflow.connect(
        ica_output, ("thresh_zstat_files", out_file_name), combine, "out_file"
    )
    return combine
