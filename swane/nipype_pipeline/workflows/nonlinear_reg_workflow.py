from nipype import Node, IdentityInterface
from swane.nipype_pipeline.engine.CustomWorkflow import CustomWorkflow
from configparser import SectionProxy
from swane.nipype_pipeline.nodes.utils import (
    get_registration_node,
    apply_registration_node,
    resolve_registration_engine,
)
from swane.nipype_pipeline.nodes.AntsComposeTransform import AntsComposeTransform
from swane.config.config_enums import CoreLimit, RegistrationEngine


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

    # Phase 2 (CP-D) lifted the Phase-1 FSL pin. flat1/func_map/tractography now
    # consume the nonlinear warp through the registration abstraction, and under
    # ANTS this workflow composes its ordered transform list into a single
    # directional displacement field per direction (see below), so the boundary
    # stays 1:1 with FSL's fieldcoeff_file/inverse_warp. The engine now follows
    # the configured preference, like linear_reg_workflow.
    engine = resolve_registration_engine(synth_config, allow_ants=True)

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

    if engine == RegistrationEngine.ANTS:
        # The boundary carries one directional field per direction, not the ANTs
        # ordered list + which_to_invert pair. Compose each direction into a
        # single displacement field sampled on the direction's target grid:
        # forward resamples INTO the atlas (reference=atlas), inverse INTO the
        # input image (reference=in_file). which_to_invert is baked in here and
        # never crosses the boundary (consumers apply the field with
        # transformlist=[field], no flags).
        #
        # reg_wrap.fwd_transforms/inv_transforms are single-entry lists of
        # (node, field); for one AntsRegistration node that field is already a
        # List(File) output, so it connects straight to transformlist (a List
        # trait) -- no Merge needed here (unlike the single-File boundary in
        # apply_registration_node). Stacking multiple sources would (Phase 3).
        fwd_node, fwd_field = reg_wrap.fwd_transforms[0]
        fwd_compose = Node(AntsComposeTransform(), name=name + "_fwd_compose")
        fwd_compose.long_name = "reference to atlas warp composition"
        workflow.connect(inputnode, "atlas", fwd_compose, "reference_image")
        workflow.connect(fwd_node, fwd_field, fwd_compose, "transformlist")
        workflow.connect(
            reg_wrap.fwd_which_to_invert[0],
            reg_wrap.fwd_which_to_invert[1],
            fwd_compose,
            "which_to_invert",
        )
        workflow.connect(fwd_compose, "out_field", outputnode, "fieldcoeff_file")

        inv_node, inv_field = reg_wrap.inv_transforms[0]
        inv_compose = Node(AntsComposeTransform(), name=name + "_inv_compose")
        inv_compose.long_name = "atlas to reference warp composition"
        workflow.connect(inputnode, "in_file", inv_compose, "reference_image")
        workflow.connect(inv_node, inv_field, inv_compose, "transformlist")
        workflow.connect(
            reg_wrap.inv_which_to_invert[0],
            reg_wrap.inv_which_to_invert[1],
            inv_compose,
            "which_to_invert",
        )
        workflow.connect(inv_compose, "out_field", outputnode, "inverse_warp")
    else:
        # FSL/Synth: fieldcoeff_file/inverse_warp are already single warp files.
        workflow.connect(
            reg_wrap.out_registered_node, reg_wrap.warp, outputnode, "fieldcoeff_file"
        )
        workflow.connect(
            reg_wrap.inv_warp_node, reg_wrap.inv_warp, outputnode, "inverse_warp"
        )

    return workflow
