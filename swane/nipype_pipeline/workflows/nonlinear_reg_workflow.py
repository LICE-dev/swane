from nipype import Node, IdentityInterface
from swane.nipype_pipeline.engine.CustomWorkflow import CustomWorkflow
from configparser import SectionProxy
from swane.nipype_pipeline.nodes.utils import get_registration_node


# TODO check base_dir = "./"
def nonlinear_reg_workflow(
    name: str, synth_config: SectionProxy, base_dir: str = "/"
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
        use_synth=synth_config.getboolean_safe("morph"),
        workflow=workflow,
        moving=[inputnode, "in_file"],
        moving_brain=[inputnode, "in_file"],
        reference=[inputnode, "atlas"],
        flirt_cost="corratio",
        inverse=True,
        non_linear=True,
    )

    workflow.connect(
        reg_wrap.out_registered_node,
        reg_wrap.out_registered_image,
        outputnode,
        "warped_file",
    )
    workflow.connect(
        reg_wrap.out_registered_node, reg_wrap.warp, outputnode, "fieldcoeff_file"
    )
    workflow.connect(
        reg_wrap.inv_warp_node, reg_wrap.inv_warp, outputnode, "inverse_warp"
    )

    return workflow
