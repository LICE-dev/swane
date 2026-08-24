from nipype import Node, IdentityInterface
from swane.nipype_pipeline.engine.CustomWorkflow import CustomWorkflow
from configparser import SectionProxy
from swane.nipype_pipeline.nodes.utils import (
    get_registration_node,
    apply_registration_node,
    resolve_registration_engine,
)
from swane.config.config_enums import CoreLimit


# TODO check base_dir = "./"
def nonlinear_reg_workflow(
    name: str,
    synth_config: SectionProxy,
    base_dir: str = "/",
    max_cpu: int = 0,
    multicore_node_limit: CoreLimit = CoreLimit.SOFT_CAP,
    test_run: bool = False,
) -> CustomWorkflow:
    """
    Transforms input images in a reference space through a nonlinear registration.
    For symmetric atlas, make a RL swapped to unswapped nonlinear registration.

    Parameters
    ----------
    name : str
        The workflow name.
    synth_config: SectionProxy
        FreeSurfer Synth tools settings.
    base_dir : path, optional
        The base directory path relative to parent workflow. The default is "/".
    max_cpu : int, optional
        If greater than 0, limit the core usage of Synth tools. The default is 0.
    multicore_node_limit : CoreLimit, optional
        Preference for Synth tools core usage. The default is CoreLimit.SOFT_CAP.
    test_run : bool, optional
        If True, speed up the underlying nonlinear registration for
        prerelease test runs at the cost of accuracy. The default is False.

    Input Node Fields
    ----------
    atlas : path
        The standard atlas for the registration.
    in_file : path
        The input image for the registration.

    Returns
    -------
    workflow : CustomWorkflow
        The nonlinear registration workflow.

    Output Node Fields
    ----------
    fieldcoeff_file : path
        Nonlinear registration warp to atlas space.
    inverse_warp : path
        Nonlinear inverse registration warp from atlas space.
    out_matrix_file : path
        Linear registration matrix to atlas space.
    warped_file : path
        Input image transformed in atlas space.

    """

    workflow = CustomWorkflow(name=name, base_dir=base_dir)

    # Phase 1 scope decision (docs/superpowers/specs/2026-08-24-ants-phase1-callsite-audit.md):
    # nonlinear_reg's fieldcoeff_file/inverse_warp are read FSL-specifically by
    # flat1, func_map and tractography (FSL ApplyWarp), none of which are ported
    # to the ANTs transform-list/which_to_invert contract in Phase 1. Pin this
    # workflow to FSL regardless of the configured engine until those consumers
    # are ported (Phase 2/3); only linear_reg_workflow follows the ANTs default.
    engine = resolve_registration_engine(synth_config, allow_ants=False)

    # Input Node
    inputnode = Node(IdentityInterface(fields=["atlas", "in_file"]), name="inputnode")

    # Output Node
    outputnode = Node(
        IdentityInterface(fields=["fieldcoeff_file", "inverse_warp", "warped_file"]),
        name="outputnode",
    )

    reg_wrap = get_registration_node(
        name=name,
        name_prefix="reference",
        name_suffix="to atlas",
        engine=engine,
        workflow=workflow,
        moving=[inputnode, "in_file"],
        moving_brain=[inputnode, "in_file"],
        reference=[inputnode, "atlas"],
        flirt_cost="corratio",
        inverse=True,
        non_linear=True,
        test_run=test_run,
        max_cpu=max_cpu,
        multicore_node_limit=multicore_node_limit,
        limit_synth_cores=synth_config.getboolean_safe("limit_cores"),
    )

    unbetted_2_atlas = apply_registration_node(
        name=name,
        name_prefix="Unbetted image",
        name_suffix="to atlas",
        engine=engine,
        workflow=workflow,
        warp=[reg_wrap.out_registered_node, reg_wrap.warp],
        registration=reg_wrap,
        moving=[inputnode, "in_file"],
        reference=[inputnode, "atlas"],
        non_linear=True,
    )

    workflow.connect(unbetted_2_atlas, "out_file", outputnode, "warped_file")
    workflow.connect(
        reg_wrap.out_registered_node, reg_wrap.warp, outputnode, "fieldcoeff_file"
    )
    workflow.connect(
        reg_wrap.inv_warp_node, reg_wrap.inv_warp, outputnode, "inverse_warp"
    )

    return workflow
