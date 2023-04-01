import sys
import os
import subprocess


def load_anat(scene_dir, volume_name):
    file = os.path.join(scene_dir, volume_name + ".nii.gz")
    node = None
    if os.path.exists(file):
        try:
            print("SLICERLOADER: Loading " + volume_name)
            node = slicer.util.loadVolume(file)
        except:
            pass
    return node


def lesion_segment(scene_dir):
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


def load_freesurfer_surf(scene_dir, node_name, ref_node):
    file = os.path.join(scene_dir, node_name)
    if os.path.exists(file):
        try:
            print("SLICERLOADER: Loading surface " + node_name)
            surf_node = slicer.util.loadNodeFromFile(file, 'FreeSurferModelFile',
                                                    {"referenceVolumeID": ref_node.GetID()})
            surf_node.GetDisplayNode().SetColor(0.82, 0.82, 0.82)
            return surf_node
        except:
            pass
    return None


def load_freesurfer_overlay(scene_dir, node_name, surf_node):
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


def load_freesurfer_segmentation_file(seg_file):
    if os.path.exists(seg_file):
        try:
            slicer.util.loadNodeFromFile(seg_file, 'FreeSurferSegmentationFile')
        except:
            pass


def load_freesurfer(scene_dir, ref_node):
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


def load_vein(scene_dir):
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
    slicer.mrmlScene.RemoveNode(vein_node)


def tract_model(segmentation_node, dti_dir, tract, side):
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


def load_fmri(scene_dir):
    fmri_path = os.path.join(scene_dir, "fMRI")
    if not os.path.exists(fmri_path):
        return
    print("SLICERLOADER: Loading fMRI")
    for file in os.listdir(fmri_path):
        if file.endswith('.nii.gz'):
            func_node = load_anat(fmri_path, file.replace(".nii.gz", ""))
            if func_node is not None:
                func_node.GetDisplayNode().SetAndObserveColorNodeID('vtkMRMLPETProceduralColorNodePET-Rainbow2')


def main_tract(dti_dir, scene_dir):
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

        baseList = ['ref_brain', 'r-flair_brain', 'r-mdc_brain', 'r-pet', 'r-pet_ai', 'r-pet_zscore', 'r-asl',
                    'r-asl_ai', 'r-asl_zscore', 'r-FA', 'r-flair2d_tra_brain', 'r-flair2d_cor_brain',
                    'r-flair2d_sag_brain', 'r-binary_flair', 'r-junction_z', 'r-extension_z']

        for volume in baseList:
            load_anat(sceneDir, volume)

        load_fmri(sceneDir)

        load_vein(sceneDir)

        load_freesurfer(sceneDir, refNode)

        ext = "mrb"
        # Saving in MRML doesn't work well, disable extension choice for now
        # if sys.argv[1] is not None and sys.argv[1] == "1":
        #     ext = "mrml"

        print("SLICERLOADER: Saving multimodale scene (some minutes)")
        slicer.util.saveScene(os.path.join(sceneDir, "scene." + ext))

sys.exit(0)
