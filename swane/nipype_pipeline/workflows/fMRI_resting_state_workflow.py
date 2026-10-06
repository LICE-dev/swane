from nipype import Node, IdentityInterface
from configparser import SectionProxy
from swane.nipype_pipeline.engine.CustomWorkflow import CustomWorkflow
from swane.nipype_pipeline.workflows.fMRI_preproc_workflow import fMRI_preproc_workflow
from swane.nipype_pipeline.workflows.fMRI_resting_state_fsl import build_fsl_resting
from swane.nipype_pipeline.workflows.fMRI_resting_state_nilearn import (
    build_nilearn_resting,
    build_nilearn_output_space,
)
from swane.nipype_pipeline.interfaces.utils import (
    apply_registration_node,
    resolve_registration_engine,
    resolve_fmri_engine,
)
from swane.config.config_enums import SliceTiming, FmriEngine


def fMRI_resting_state_workflow(
    name: str,
    dicom_dir: str,
    config: SectionProxy,
    synth_config: SectionProxy,
    base_dir: str = "/",
    max_cpu: int = 0,
    test_run: bool = False,
) -> CustomWorkflow:
    """
    fMRI resting state anlysis

    Parameters
    ----------
    name : str
        The workflow name.
    dicom_dir : path
        The directory path of the DICOM files.
    config: SectionProxy
        workflow settings.
    synth_config: SectionProxy
        The Synth-tools configuration section used to resolve the registration
        engine. EPI avoids SynthMorph, so SYNTH falls back to ANTS; the resolved
        engine drives the shared func->ref registration, the ref->atlas
        registration and every apply below.
    base_dir : path, optional
        The base directory path relative to parent workflow. The default is "/".
    max_cpu : int, optional
        Per-subject CPU budget passed to the registration nodes. The default is 0.
    test_run : bool, optional
        If True, speed up the ref-to-atlas registration for prerelease test
        runs at the cost of accuracy. ic_dim is never touched: the
        phantom dataset used for testing is built to yield a specific
        component count. The default is False.

    Input Node Fields
    ----------
    reference_brain : path
        Betted T13D.
    tissue_pve : list of path
        Tissue partial volume / posterior maps of the T13D ordered
        [CSF, GM, WM], from the shared reference segmentation (NILEARN engine
        only).

    Output Node Fields
    ----------
    thresh_zstat_files : path
        Thresholded component maps in reference space
        (``r-thresh_zstatNN``). FSL resamples MELODIC's thresholded maps;
        NILEARN resamples the unthresholded z and the survivor masks of the
        threshold decided in functional space
        (``fMRI_resting_state_nilearn.build_nilearn_output_space``).
    aroma_classification : path
        ICA-AROMA classification overview (AROMA enabled only).
    ic_mix : path
        Mixing matrix of the final ICA.

    Returns
    -------
    workflow : CustomWorkflow
        The fMRI workflow. This function builds the shared preprocessing and
        dispatches the analysis to the builder of the resolved fMRI engine
        (``fMRI_resting_state_fsl.build_fsl_resting`` or
        ``fMRI_resting_state_nilearn.build_nilearn_resting``); both use the
        shared ICA-AROMA module ``fMRI_resting_state_aroma``.

    """

    TR = config.getfloat_safe("tr")
    n_vols = config.getint_safe("n_vols")
    del_start_vols = config.getint_safe("del_start_vols")
    del_end_vols = config.getint_safe("del_end_vols")
    run_aroma = config.getboolean_safe("aroma")
    fmri_engine = resolve_fmri_engine(synth_config)
    hpcutoff = 100

    # The EPI registration engine, resolved once for the shared func->ref
    # registration built by fMRI_preproc_workflow, the ref->atlas registration
    # and every apply below. EPI avoids SynthMorph, so SYNTH falls back to
    # ANTS.
    engine = resolve_registration_engine(synth_config, allow_synth=False)

    workflow = fMRI_preproc_workflow(
        name=name,
        dicom_dir=dicom_dir,
        TR=TR,
        slice_timing=SliceTiming.UNKNOWN,
        n_vols=n_vols,
        hpcutoff=hpcutoff,
        del_start_vols=del_start_vols,
        del_end_vols=del_end_vols,
        synth_config=synth_config,
        base_dir=base_dir,
        max_cpu=max_cpu,
        test_run=test_run,
        # The NILEARN nuisance ROIs consume the shared reference segmentation.
        extra_input_fields=(
            ("tissue_pve",) if fmri_engine == FmriEngine.NILEARN else ()
        ),
    )

    # Output Node
    outputnode = Node(
        IdentityInterface(
            fields=["thresh_zstat_files", "aroma_classification", "ic_mix"]
        ),
        name="outputnode",
    )

    inputnode = workflow.get_node("inputnode")

    if fmri_engine == FmriEngine.NILEARN:
        ica_output = build_nilearn_resting(
            workflow=workflow,
            name=name,
            config=config,
            synth_config=synth_config,
            engine=engine,
            test_run=test_run,
            max_cpu=max_cpu,
        )
    else:
        ica_output = build_fsl_resting(
            workflow=workflow,
            name=name,
            config=config,
            synth_config=synth_config,
            engine=engine,
            test_run=test_run,
            max_cpu=max_cpu,
            hpcutoff=hpcutoff,
        )

    if run_aroma:
        workflow.connect(
            workflow.get_node("aroma_classification"),
            "classification_overview",
            outputnode,
            "aroma_classification",
        )

    if fmri_engine == FmriEngine.NILEARN:
        # The threshold is decided in functional space; the unthresholded z
        # and the survivor masks are resampled and recombined.
        zstats_combine = build_nilearn_output_space(
            workflow=workflow,
            ica_output=ica_output,
            engine=engine,
            inputnode=inputnode,
            out_file_name=registered_file_name,
        )
        workflow.connect(zstats_combine, "out_file", outputnode, "thresh_zstat_files")
    else:
        zstats_2_ref = apply_registration_node(
            name="zstats",
            engine=engine,
            workflow=workflow,
            # The func->ref transform comes from the wrapper fMRI_preproc exposes:
            # on ANTs registration= feeds the whole ordered transform list plus its
            # which_to_invert flags (wire_transforms), while the FSL/Synth paths
            # keep reading the single-file .mat view.
            warp=[workflow.reg_2_ref.out_registered_node, workflow.reg_2_ref.warp],
            registration=workflow.reg_2_ref,
            moving=[ica_output, "thresh_zstat_files"],
            reference=[inputnode, "reference_brain"],
            out_file=[ica_output, ("thresh_zstat_files", registered_file_name)],
            non_linear=False,
            name_prefix="Zstat maps",
            name_suffix="to reference",
            iterfield=["in_file", "out_file"],
        )

        workflow.connect(zstats_2_ref, "out_file", outputnode, "thresh_zstat_files")
    workflow.connect(ica_output, "ic_mix", outputnode, "ic_mix")

    return workflow


# Function to generate the name for the file of registered output zstats
def registered_file_name(in_file_names):
    """
    Adds prefix 'r-' and use 2 digid number at end.
    Example: 'zstat1.nii.gz' -> 'r-zstat01.nii.gz'
    """
    from os.path import basename
    import re

    out_files = []
    for f in in_file_names:
        base_name = basename(f)
        # Search for a number before the .nii or .nii.gz extension
        m = re.search(r"(\d+)(\.nii(?:\.gz)?)$", base_name)
        if m:
            num = int(m.group(1))
            ext = m.group(2)
            new_name = re.sub(r"\d+(\.nii(?:\.gz)?)$", f"{num:02d}{ext}", base_name)
        else:
            new_name = base_name
        out_files.append("r-" + new_name)
    return out_files
