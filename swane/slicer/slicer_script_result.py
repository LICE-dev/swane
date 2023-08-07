# slicerpython script for module checking
# Warning: slicer library is not required beacuse the script is executed in Slicer environment

import sys
import os
import subprocess

def load_anat(scene_dir: str, volume_name: str, color_node_ID: str = None):
    """
    Creates a scalar node from a NIFTI file.

    Parameters
    ----------
    scene_dir : str
        The scene directory.
    volume_name : str
        The NIFTI file name (without extension).
    color_node_ID : str, optional
        The colorNodeID to apply to Slicer node. The default is None.

    Returns
    -------
    node : MRMLCore.vtkMRMLScalarVolumeNode
        The scalar node generated from the NIFTI file.

    """
    
    file = os.path.join(scene_dir, volume_name + ".nii.gz")
    node = None
    if os.path.exists(file):
        try:
            print("SLICERLOADER: Loading " + volume_name)
            node = slicer.util.loadVolume(file)
        except:
            pass

        if node is not None and color_node_ID is not None:
            node.GetDisplayNode().SetAndObserveColorNodeID(color_node_ID)
            return
        
    return node


def lesion_segment(scene_dir: str):
    """
    Prepares an empty segment for optional manual segmentation.

    Parameters
    ----------
    scene_dir : str
        The scene directory.

    Returns
    -------
    None.

    """
    
    file = os.path.join(scene_dir, "seg_lesions.seg.nrrd")
    if os.path.exists(file):
        print("SLICERLOADER: Loading existing lesion segment")
        slicer.util.loadSegmentation(file)
    else:
        print("SLICERLOADER: Creating lesion segment")
        seg_node = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLSegmentationNode', "seg_lesions")
        seg_node.CreateDefaultDisplayNodes()
        seg_node.GetSegmentation().AddEmptySegment("Lesion", "Lesion", [1, 0, 0])
        seg_node.CreateClosedSurfaceRepresentation()
        my_storage_node = seg_node.CreateDefaultStorageNode()
        my_storage_node.SetFileName(file)
        my_storage_node.WriteData(seg_node)


def load_freesurfer_surf(scene_dir: str, node_name: str, ref_node):
    """
    Loads the FreeSurfer surface.

    Parameters
    ----------
    scene_dir : str
        The scene directory.
    node_name : str
        The surface file.
    ref_node : MRMLCore.vtkMRMLScalarVolumeNode
        The reference node for surface positioning.

    Returns
    -------
    #TODO specificare tipo di surf_node
    surf_node : TYPE
        The slicer node with loaded surface.

    """
    
    file = os.path.join(scene_dir, node_name)
    surf_node = None
    
    if os.path.exists(file):
        try:
            print("SLICERLOADER: Loading surface " + node_name)
            surf_node = slicer.util.loadNodeFromFile(file, 'FreeSurferModelFile',
                                                    {"referenceVolumeID": ref_node.GetID()})
            surf_node.GetDisplayNode().SetColor(0.82, 0.82, 0.82)
        except:
            pass
        
    return surf_node


def load_freesurfer_overlay(scene_dir: str, node_name: str, surf_node):
    """
    Applies an overlay on the FreeSurfer surface.

    Parameters
    ----------
    scene_dir : str
        The scene directory.
    node_name : str
        The surface file.
    #TODO specificare tipo di surf_node
    surf_node : TYPE
        The slicer node with loaded surface.

    Returns
    -------
    None.

    """
    
    file = os.path.join(scene_dir, node_name)
    if os.path.exists(file):
        try:
            print("SLICERLOADER: Loading surface overlay " + node_name)
            overlay_node = slicer.util.loadNodeFromFile(file, 'FreeSurferScalarOverlayFile',
                                                       {"modelNodeId": surf_node.GetID()})
            overlay_node.GetDisplayNode().SetAndObserveColorNodeID('vtkMRMLColorTableNodeFileColdToHotRainbow.txt')
            overlay_node.GetDisplayNode().SetScalarVisibility(False)
        except:
            pass


def load_freesurfer_segmentation_file(seg_file: str):
    """
    Loads the FreeSurfer segmentation file.

    Parameters
    ----------
    seg_file : str
        The segmentation file name.

    Returns
    -------
    None.

    """
    
    if os.path.exists(seg_file):
        try:
            slicer.util.loadNodeFromFile(seg_file, 'FreeSurferSegmentationFile')
        except:
            pass


def load_freesurfer(scene_dir: str, ref_node):
    """
    Loads the FreeSurfer output.

    Parameters
    ----------
    scene_dir : str
        The scene directory.
    ref_node : MRMLCore.vtkMRMLScalarVolumeNode
        The reference node for surface positioning.

    Returns
    -------
    None.

    """
    
    seg_list = ["r-aparc_aseg.mgz", "segmentHA/lh.hippoAmygLabels.mgz", "segmentHA/rh.hippoAmygLabels.mgz"]
    for file in seg_list:
        seg_file = os.path.join(scene_dir, file)
        load_freesurfer_segmentation_file(seg_file)

    lh_pial = load_freesurfer_surf(scene_dir, "lh.pial", ref_node)
    rh_pial = load_freesurfer_surf(scene_dir, "rh.pial", ref_node)

    surfs = ["lh.white", "rh.white"]
    for surf in surfs:
        load_freesurfer_surf(scene_dir, surf, ref_node)

    overlays = ['pet_surf', 'pet_ai_surf', 'pet_zscore_surf', 'asl_surf', 'asl_ai_surf', 'asl_zscore_surf']
    for overlay in overlays:
        load_freesurfer_overlay(scene_dir, overlay + "_lh.mgz", lh_pial)
        load_freesurfer_overlay(scene_dir, overlay + "_rh.mgz", rh_pial)


def load_vein(scene_dir: str, remove_vein: bool = False):
    """
    Loads the veins files and creates their 3d model.

    Parameters
    ----------
    scene_dir : str
        The scene directory.
    remove_vein : bool, optional
        True if the model must remove the original veins images. The default is False.

    Returns
    -------
    None.

    """
    
    vein_volume_name = "r-veins_inskull"
    vein_node = load_anat(scene_dir, vein_volume_name)
    if vein_node is None:
        return
    print("SLICERLOADER: Creating 3D model: Veins")

    try:
        command = "fslstats " + os.path.join(scene_dir, vein_volume_name+".nii.gz") + " -P 97.5"
        output = subprocess.run(command, shell=True,
                                stdout=subprocess.PIPE).stdout.decode('utf-8')
        thr = float(output)
    except:
        thr = 6

    vein_model = slicer.vtkMRMLModelNode()
    slicer.mrmlScene.AddNode(vein_model)

    parameters = {
        "InputVolume": vein_node.GetID(),
        "Threshold": thr,
        "OutputGeometry": vein_model.GetID(),
    }

    gray_maker = slicer.modules.grayscalemodelmaker
    slicer.cli.runSync(gray_maker, None, parameters)
    vein_model.GetDisplayNode().SetColor(0, 0, 1)
    vein_model.SetName("Veins")
    my_storage_node = vein_model.CreateDefaultStorageNode()
    my_storage_node.SetFileName(os.path.join(scene_dir, "veins.vtk"))
    my_storage_node.WriteData(vein_model)
    
    if remove_vein:
        slicer.mrmlScene.RemoveNode(vein_node)


def tract_model(segmentation_node, dti_dir: str, tract: [], side: str):
    """
    Creates the 3d model of a tract.

    Parameters
    ----------
    #TODO verificare tipo
    segmentation_node : TYPE
        DESCRIPTION.
    dti_dir : str
        The DTI directory.
    tract : []
        The array with the tract information.
    side : str
        The side of the tract:
            - LH for left side
            - RH for right side

    Returns
    -------
    None.

    """
    
    tract_file = os.path.join(dti_dir, "r-" + tract['name'] + "_" + side + ".nii.gz")
    if not os.path.exists(tract_file):
        return

    waytotal_file = os.path.join(dti_dir, "r-" + tract['name'] + "_" + side + "_waytotal")
    waytotal = 0
    if os.path.exists(waytotal_file):
        try:
            with open(waytotal_file, 'r') as file:
                for line in file.readlines():
                    waytotal = int(line)
        except:
            pass

    if waytotal > 0:
        thr = waytotal * 0.0035
    else:
        thr = tract['thr']

    tract_node = slicer.util.loadVolume(tract_file)
    segmentation_node.SetReferenceImageGeometryParameterFromVolumeNode(tract_node)

    # Create temporary segment editor to get access to effects
    segment_editor_widget = slicer.qMRMLSegmentEditorWidget()
    segment_editor_widget.setMRMLScene(slicer.mrmlScene)
    segment_editor_node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentEditorNode")
    segment_editor_widget.setMRMLSegmentEditorNode(segment_editor_node)
    segment_editor_widget.setSegmentationNode(segmentation_node)
    segment_editor_widget.setMasterVolumeNode(tract_node)

    # Create segment
    tract_segment_id = segmentation_node.GetSegmentation().AddEmptySegment(tract['name'], tract['name'], tract['color'])
    segment_editor_node.SetSelectedSegmentID(tract_segment_id)
    
    # Fill by thresholding
    segment_editor_widget.setActiveEffectByName("Threshold")
    effect = segment_editor_widget.activeEffect()
    effect.setParameter("MinimumThreshold", thr)
    effect.self().onApply()

    # Delete temporary segment editor
    segment_editor_widget = None
    slicer.mrmlScene.RemoveNode(segment_editor_node)
    slicer.mrmlScene.RemoveNode(tract_node)


def load_fmri(scene_dir: str):
    """
    Loads the fMRI results.

    Parameters
    ----------
    scene_dir : str
        The scene directory.

    Returns
    -------
    None.

    """
    
    fmri_path = os.path.join(scene_dir, "fMRI")
    if not os.path.exists(fmri_path):
        return
    print("SLICERLOADER: Loading fMRI")
    for file in os.listdir(fmri_path):
        if file.endswith('.nii.gz'):
            func_node = load_anat(fmri_path, file.replace(".nii.gz", ""), 'vtkMRMLPETProceduralColorNodePET-Rainbow2')

def main_tract(dti_dir: str, scene_dir: str):
    sides = ["rh", "lh"]
    tracts = [
        {"name": "cst", "thr": "500", "color": [0, 1, 0]},
        {"name": "af", "thr": "1500", "color": [1, 0, 1]},
        {"name": "or", "thr": "500", "color": [1, 1, 0]}
    ]

    print("SLICERLOADER: Creating DTI tracts 3D models (some minutes!)")

    for side in sides:
        # Create segmentation
        segmentation_node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode", "tracts_" + side)
        segmentation_node.CreateDefaultDisplayNodes()  # only needed for display
        
        for tract in tracts:
            tract_model(segmentation_node, dti_dir, tract, side)
            
        segmentation_node.CreateClosedSurfaceRepresentation()
        my_storage_node = segmentation_node.CreateDefaultStorageNode()
        my_storage_node.SetFileName(os.path.join(scene_dir, "tracts_" + side + ".seg.nrrd"))
        my_storage_node.WriteData(segmentation_node)

###############################################################################

# slicerpython execution code
slicer.mrmlScene.Clear(0)
sceneDir = os.path.join(os.getcwd(), "scene")

if not os.path.isdir(sceneDir):
    print("SLICERLOADER: Results folder not found")
else:
    refNode = load_anat(sceneDir, "ref")
    if refNode is not None:

        dtiDir = os.path.join(sceneDir, "dti")
        if os.path.isdir(dtiDir):
            main_tract(dtiDir, sceneDir)

        lesion_segment(sceneDir)

        baseList = ['ref_brain', 'r-flair_brain', 'r-mdc_brain', 'r-FA', 'r-flair2d_tra_brain', 'r-flair2d_cor_brain',
                    'r-flair2d_sag_brain', 'r-binary_flair', 'r-junction_z', 'r-extension_z']

        for volume in baseList:
            load_anat(sceneDir, volume)

        colorList = [('r-asl_ai', 'vtkMRMLColorTableNodeFileDivergingBlueRed.txt'),
                     ('r-pet_ai', 'vtkMRMLColorTableNodeFileDivergingBlueRed.txt'),
                     ('r-pet', 'vtkMRMLColorTableNodeFileColdToHotRainbow.txt'),
                     ('r-pet_zscore', 'vtkMRMLColorTableNodeFileColdToHotRainbow.txt'),
                     ('r-asl', 'vtkMRMLColorTableNodeFileColdToHotRainbow.txt'),
                     ('r-asl_zscore', 'vtkMRMLColorTableNodeFileColdToHotRainbow.txt'),
                     ]

        for volume in colorList:
            load_anat(sceneDir, volume[0], volume[1])

        load_fmri(sceneDir)

        load_vein(sceneDir)

        load_freesurfer(sceneDir, refNode)

        ext = "mrb"
        
        #TODO valutare
        # Saving in MRML doesn't work well, disable extension choice for now
        # if sys.argv[1] is not None and sys.argv[1] == "1":
        #     ext = "mrml"

        print("SLICERLOADER: Saving multimodale scene (some minutes)")
        slicer.util.saveScene(os.path.join(sceneDir, "scene." + ext))

sys.exit(0)
