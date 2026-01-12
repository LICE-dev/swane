from nipype import Node
from nipype.interfaces.fsl import BET, FLIRT, FNIRT, InvWarp, ConvertXFM, ApplyWarp, ApplyXFM

from swane.nipype_pipeline.engine.CustomWorkflow import CustomWorkflow
from swane.nipype_pipeline.nodes.SynthMorphApply import SynthMorphApply
from swane.nipype_pipeline.nodes.SynthStrip import SynthStrip
from swane.nipype_pipeline.nodes.SynthMorphReg import SynthMorphReg
from nipype.utils.filemanip import fname_presuffix


def getn(result_list, index):
    """
    Extracts an element from a list for a single input of a Node (eg. aparcaseg from reconAll).

    """

    return result_list[index]


def get_deskull_node(
        name: str,
        use_synth: bool,
        mask: bool=False,
        bet_thr: float=None,
        bet_bias_correction:bool=False,
        bet_robust:bool=False,
        bet_threshold:bool=False,
        bet_surfaces:bool=False,
        synth_exclude_csf:bool=False,
        out_file:str=None,

)->Node:
    if use_synth:
        deskull_node = Node(SynthStrip(), name=name + "_synthstrip", mem_gb=5)
        if mask:
            mask_name = "brain_mask.nii.gz"
            if out_file:
                mask_name= fname_presuffix(out_file, suffix="_brain", use_ext=True)
            deskull_node.inputs.mask_file = mask_name
        deskull_node.inputs.exclude_csf = synth_exclude_csf
        if bet_surfaces:
            deskull_node.inskull_out_name = "mask_file"
    else:
        deskull_node = Node(BET(), name=name + "_bet")
        deskull_node.inputs.mask = mask
        deskull_node.inputs.threshold = bet_threshold
        if bet_thr:
            deskull_node.inputs.frac = bet_thr
        if bet_bias_correction:
            deskull_node.inputs.reduce_bias = True
        elif bet_surfaces:
            deskull_node.inputs.surfaces = True
            deskull_node.inskull_out_name = "inskull_mask_file"
        elif bet_robust:
            deskull_node.inputs.robust = True

    if out_file:
        deskull_node.inputs.out_file = out_file

    return deskull_node

class RegistrationNodeWrapper:
    def __init__(
            self,
            input_node:Node,
            out_registered_node:Node,
            out_registered_image:str,
            warp:str,
            inv_warp_node:Node,
            inv_warp:str


    ):
        self.input_node=input_node
        self.out_registered_node=out_registered_node
        self.out_registered_image=out_registered_image
        self.warp = warp
        self.inv_warp_node = warp
        self.inv_warp = warp


def get_registration_node(
        name: str,
        use_synth: bool,
        workflow:CustomWorkflow,
        moving:str|list[Node|str],
        moving_brain:str|list[Node|str],
        reference:str|list[Node|str],
        non_linear: bool=False,
        inverse:bool=False,
        out_file:str|list[Node|str]=None,
        is_volumetric:bool=True,
        flirt_cost:str="mutualinfo",
)->RegistrationNodeWrapper:

    # Sometimes we want to use flirt on unbetted images to take advantage of skull for registration
    if moving_brain is None:
        moving_brain=moving

    if use_synth:
        # Prepare node inputs value
        if non_linear:
            mem_gb = 13
            model = "joint"
        else:
            mem_gb = 9
            model = "rigid"

        synth_morph_reg = Node(SynthMorphReg(), name=name+"_synthmorphreg", mem_gb=mem_gb)
        synth_morph_reg.long_name = "%s to reference space"
        synth_morph_reg.inputs.model = model
        if out_file:
            if type(out_file) == str:
                synth_morph_reg.inputs.out_file = out_file
            else:
                workflow.connect(out_file[0], out_file[1], synth_morph_reg, "out_file")
        if type(moving) == str:
            synth_morph_reg.inputs.in_file = moving
        else:
            workflow.connect(moving[0], moving[1], synth_morph_reg, "in_file")
        if type(reference) == str:
            synth_morph_reg.inputs.reference = reference
        else:
            workflow.connect(reference[0], reference[1], synth_morph_reg, "reference")

        return RegistrationNodeWrapper(
            input_node=synth_morph_reg,
            out_registered_node=synth_morph_reg,
            out_registered_image="out_file",
            warp="warp_file",
            inv_warp_node=synth_morph_reg,
            inv_warp="inv_warp_file"
        )

    else:
        if non_linear:
            flirt = Node(FLIRT(), name=name+"_flirt")
            flirt.inputs.searchr_x = [-90, 90]
            flirt.inputs.searchr_y = [-90, 90]
            flirt.inputs.searchr_z = [-90, 90]
            flirt.inputs.dof = 12
            # TODO consider switch to same-modality cost function
            flirt.inputs.cost = flirt_cost
            if type(moving_brain)==str:
                flirt.inputs.in_file = moving_brain
            else:
                workflow.connect(moving_brain[0], moving_brain[1], flirt, "in_file")
            if type(reference)==str:
                flirt.inputs.reference = reference
            else:
                workflow.connect(reference[0], reference[1], flirt, "reference")

            fnirt = Node(FNIRT(), name=name+"_fnirt")
            fnirt.long_name = "%s to atlas"
            fnirt.inputs.fieldcoeff_file = True
            workflow.connect(flirt, "out_matrix_file", fnirt, "affine_file")
            if out_file:
                if type(out_file) == str:
                    fnirt.inputs.warped_file = out_file
                else:
                    workflow.connect(out_file[0], out_file[1], fnirt, "warped_file")
            if type(moving) == str:
                fnirt.inputs.in_file = moving
            else:
                workflow.connect(moving[0], moving[1], fnirt, "in_file")
            if type(reference) == str:
                fnirt.inputs.ref_file = reference
            else:
                workflow.connect(reference[0], reference[1], fnirt, "ref_file")

            invwarp = None
            if inverse:
                invwarp = Node(InvWarp(), name=name+"_invwarp")
                workflow.connect(fnirt, "fieldcoeff_file", invwarp, "warp")
                if type(moving) == str:
                    invwarp.inputs.ref_file = moving
                else:
                    workflow.connect(moving[0], moving[1], invwarp, "reference")

            return RegistrationNodeWrapper(
                input_node=flirt,
                out_registered_node=fnirt,
                out_registered_image="warped_file",
                warp="fieldcoeff_file",
                inv_warp_node=invwarp,
                inv_warp="inverse_warp"
            )
        else:
            flirt = Node(FLIRT(), name=name+"_flirt")
            if is_volumetric:
                flirt.inputs.cost = flirt_cost
                flirt.inputs.searchr_x = [-90, 90]
                flirt.inputs.searchr_y = [-90, 90]
                flirt.inputs.searchr_z = [-90, 90]
                flirt.inputs.dof = 6
                flirt.inputs.interp = "trilinear"
            if out_file:
                if type(out_file) == str:
                    flirt.inputs.out_file = out_file
                else:
                    workflow.connect(out_file[0], out_file[1], flirt, "out_file")
            if type(moving_brain)==str:
                flirt.inputs.in_file = moving_brain
            else:
                workflow.connect(moving_brain[0], moving_brain[1], flirt, "in_file")
            if type(reference) == str:
                flirt.inputs.reference = reference
            else:
                workflow.connect(reference[0], reference[1], flirt, "reference")

            inv_xfm = None
            if inverse:
                inv_xfm = Node(InvWarp(), name=name+"_invwarp")
                inv_xfm.inputs.invert_xfm = True
                workflow.connect(flirt, "out_matrix_file", inv_xfm, "in_file")


            return RegistrationNodeWrapper(
                input_node=flirt,
                out_registered_node=flirt,
                out_registered_image="out_file",
                warp="out_matrix_file",
                inv_warp_node=inv_xfm,
                inv_warp="out_file"
            )

def apply_registration_node(
        name:str,
        use_synth:bool,
        workflow:CustomWorkflow,
        warp:list[Node|str],
        moving:str|list[Node|str],
        reference:str|list[Node|str],
        out_file:str|list[Node|str],
        non_linear:bool=False,
        pre_mat:list[Node|str]=None,
)->Node:
    if use_synth:
        apply_node = Node(SynthMorphApply(), name=name+"_morph_apply")
        workflow.connect(warp[0], warp[1], apply_node, "warp_file")
    elif non_linear:
        apply_node = Node(ApplyWarp(), name=name+"_apply_warp")
        workflow.connect(warp[0], warp[1], apply_node, "field_file")
        if type(reference) == str:
            apply_node.inputs.ref_file = reference
        else:
            workflow.connect(reference[0], reference[1], apply_node, "ref_file")
    else:
        apply_node = Node(ApplyXFM(), name=name + "_apply_xfm")
        workflow.connect(warp[0], warp[1], apply_node, "in_matrix_file")
        if type(reference) == str:
            apply_node.inputs.reference = reference
        else:
            workflow.connect(reference[0], reference[1], apply_node, "reference")

    if out_file:
        if type(out_file) == str:
            apply_node.inputs.out_file = out_file
        else:
            workflow.connect(out_file[0], out_file[1], apply_node, "out_file")
    if type(moving) == str:
        apply_node.inputs.in_file = moving
    else:
        workflow.connect(moving[0], moving[1], apply_node, "in_file")

    return apply_node



