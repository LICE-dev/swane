from nipype import Node, IdentityInterface
from nipype.interfaces.fsl import FLIRT, FNIRT, InvWarp, SwapDimensions

from swane.nipype_pipeline.engine.CustomWorkflow import CustomWorkflow


# TODO check base_dir = "./"
def nonlinear_reg_workflow(name: str, base_dir: str = "/") -> CustomWorkflow:
    """
    Transforms input images in a reference space through a nonlinear registration.
    For symmetric atlas, make a RL swapped to unswapped nonlinear registration.

    Parameters
    ----------
    name : str
        The workflow name.
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
    inputnode = Node(
        IdentityInterface(fields=['atlas', 'in_file']),
        name='inputnode')
    
    # Output Node
    outputnode = Node(
        IdentityInterface(
            fields=['fieldcoeff_file', 'inverse_warp', 'out_matrix_file', 'warped_file']),
        name='outputnode')

    # NODE 1: Linear registration
    flirt = Node(FLIRT(), name='ref_2_%s_flirt' % name)
    flirt.long_name = "%s to atlas"
    flirt.inputs.searchr_x = [-90, 90]
    flirt.inputs.searchr_y = [-90, 90]
    flirt.inputs.searchr_z = [-90, 90]
    flirt.inputs.dof = 12
    flirt.inputs.cost = "corratio"
    flirt.inputs.out_matrix_file = "ref_2_%s.mat" % name
    workflow.add_nodes([flirt])
    workflow.connect(inputnode, 'in_file', flirt, 'in_file')
    workflow.connect(inputnode, 'atlas', flirt, 'reference')

    # NODE 2: Nonlinear registration
    fnirt = Node(FNIRT(), name='ref_2_%s_fnirt' % name, mem_gb=7)
    fnirt.long_name = "%s to atlas"
    fnirt.inputs.fieldcoeff_file = True
    workflow.connect(flirt, "out_matrix_file", fnirt, "affine_file")
    workflow.connect(inputnode, 'in_file', fnirt, 'in_file')
    workflow.connect(inputnode, 'atlas', fnirt, 'ref_file')

    # NODE 3: Inverse matrix
    invwarp = Node(InvWarp(), name='ref_2_%s_invwarp' % name)
    invwarp.long_name = "%s from atlas"
    workflow.connect(fnirt, "fieldcoeff_file", invwarp, "warp")
    workflow.connect(inputnode, 'in_file', invwarp, 'reference')

    workflow.connect(flirt, 'out_matrix_file', outputnode, 'out_matrix_file')
    workflow.connect(fnirt, 'fieldcoeff_file', outputnode, 'fieldcoeff_file')
    workflow.connect(fnirt, 'warped_file', outputnode, 'warped_file')
    workflow.connect(invwarp, 'inverse_warp', outputnode, 'inverse_warp')
    
    return workflow
