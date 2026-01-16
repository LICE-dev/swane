#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Slicer Python Script for Multi-Modal Data Import and Visualization

This script is designed to run inside 3D Slicer. It imports multiple imaging modalities,
creates segmentations, 3D models, and loads FreeSurfer surfaces and overlays.

Features:
- Load anatomical and functional MRI volumes
- Load DTI tracts and create 3D models
- Load veins and sEEG electrodes
- Load FreeSurfer surfaces, segmentations, and overlays
- Save the Slicer scene

Note:
- This script is intended to run within Slicer's Python environment.
- External libraries: SimpleITK, subprocess, os, glob, argparse
"""

import os
import sys
import glob
import subprocess
import argparse
import SimpleITK as sitk

os.environ["QT_LOGGING_RULES"] = "*.warning=false"

# -----------------------------
# Utility Functions
# -----------------------------


def load_anat(
    scene_dir: str,
    volume_name: str,
    color_node_id: str = None,
    hide_zero: bool = False,
):
    """
    Load an anatomical volume (NIfTI) into Slicer.

    Parameters
    ----------
    scene_dir : str
        Directory containing the NIfTI files.
    volume_name : str
        Name of the NIfTI file (with or without ".nii.gz" extension).
    color_node_id : str, optional
        Slicer color node ID to assign to the loaded volume.
    hide_zero : bool, optional
        If True, hide voxels with value == 0 (display only).

    Returns
    -------
    node : vtkMRMLScalarVolumeNode or vtkMRMLMultiVolumeNode
    """
    file_path = os.path.join(scene_dir, volume_name)
    if not file_path.endswith(".nii.gz"):
        file_path += ".nii.gz"

    if not os.path.exists(file_path):
        print(f"SLICERLOADER: File not found: {file_path}")
        return None

    try:
        print(f"SLICERLOADER: Loading {volume_name}")
        reader = sitk.ImageFileReader()
        reader.SetFileName(file_path)
        reader.ReadImageInformation()

        # --- Load ---
        if reader.GetDimension() == 4:
            node = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLMultiVolumeNode", volume_name
            )
            slicer.modules.multivolumeimporter.widgetRepresentation().self().read4DNIfTI(
                node, file_path
            )
        else:
            node = slicer.util.loadVolume(file_path)

        if not node:
            return None

        # --- Display ---
        node.CreateDefaultDisplayNodes()
        dn = node.GetDisplayNode()

        if color_node_id:
            dn.SetAndObserveColorNodeID(color_node_id)

        # --- Hide zero (display-only) ---
        if hide_zero:
            node.SetAttribute("HideZero", "True")

        return node

    except Exception as e:
        print(f"SLICERLOADER: Failed to load {volume_name}: {e}")
        return None


def lesion_segment(scene_dir: str):
    """
    Create or load an empty lesion segmentation.

    Parameters
    ----------
    scene_dir : str
        Directory for saving or loading the lesion segmentation.

    Returns
    -------
    None
    """
    seg_file = os.path.join(scene_dir, "seg_lesions.seg.nrrd")
    if os.path.exists(seg_file):
        print("SLICERLOADER: Loading existing lesion segment")
        slicer.util.loadSegmentation(seg_file)
    else:
        print("SLICERLOADER: Creating new lesion segment")
        seg_node = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLSegmentationNode", "seg_lesions"
        )
        seg_node.CreateDefaultDisplayNodes()
        seg_node.GetSegmentation().AddEmptySegment("Lesion", "Lesion", [1, 0, 0])
        seg_node.CreateClosedSurfaceRepresentation()
        storage_node = seg_node.CreateDefaultStorageNode()
        storage_node.SetFileName(seg_file)
        storage_node.WriteData(seg_node)


# -----------------------------
# FreeSurfer Loader Functions
# -----------------------------


def load_freesurfer_surf(scene_dir: str, node_name: str, ref_node):
    """
    Load a FreeSurfer surface into Slicer.

    Parameters
    ----------
    scene_dir : str
        Directory containing FreeSurfer files.
    node_name : str
        Surface filename.
    ref_node : vtkMRMLScalarVolumeNode
        Reference volume node for spatial registration.

    Returns
    -------
    surf_node : vtkMRMLModelNode or None
        Loaded surface node, or None if loading failed.
    """
    file_path = os.path.join(scene_dir, node_name)
    if not os.path.exists(file_path):
        return None
    try:
        print(f"SLICERLOADER: Loading surface {node_name}")
        loaded_nodes = vtk.vtkCollection()
        slicer.app.ioManager().loadNodes(
            "FreeSurfer model",
            {"fileName": file_path, "referenceVolumeID": ref_node.GetID()},
            loaded_nodes,
        )
        surf_node = (
            list(loaded_nodes)[0] if loaded_nodes.GetNumberOfItems() > 0 else None
        )
        if surf_node:
            surf_node.GetDisplayNode().SetColor(0.82, 0.82, 0.82)
        return surf_node
    except Exception as e:
        print(f"SLICERLOADER: Failed to load surface {node_name}: {e}")
        return None


def load_freesurfer_overlay(scene_dir: str, node_name: str, surf_node):
    """
    Apply a FreeSurfer scalar overlay to a surface.

    Parameters
    ----------
    scene_dir : str
        Directory containing overlay files.
    node_name : str
        Overlay filename.
    surf_node : vtkMRMLModelNode
        Target surface node.

    Returns
    -------
    None
    """
    file_path = os.path.join(scene_dir, node_name)
    if not os.path.exists(file_path) or surf_node is None:
        return
    try:
        print(f"SLICERLOADER: Loading surface overlay {node_name}")
        overlay_node = slicer.util.loadNodeFromFile(
            file_path, "FreeSurferScalarOverlayFile", {"modelNodeId": surf_node.GetID()}
        )
        overlay_node.GetDisplayNode().SetAndObserveColorNodeID(
            "vtkMRMLColorTableNodeFileColdToHotRainbow.txt"
        )
        overlay_node.GetDisplayNode().SetScalarVisibility(False)
    except Exception as e:
        print(f"SLICERLOADER: Failed to load overlay {node_name}: {e}")


# -----------------------------
# Argparse for Input Handling
# -----------------------------


def parse_arguments():
    """
    Parse command-line arguments for the Slicer Python script.

    Returns
    -------
    argparse.Namespace
        Parsed arguments.
    """
    parser = argparse.ArgumentParser(description="Load multi-modal data into Slicer")
    parser.add_argument(
        "--results_folder",
        type=str,
        default=os.getcwd(),
        help="Directory containing results and imaging data",
    )
    parser.add_argument(
        "--dti_threshold",
        type=float,
        default=0.0035,
        help="Threshold for DTI tractography",
    )
    parser.add_argument(
        "--vein_threshold_mr",
        type=float,
        default=97.5,
        help="Threshold for vein detection",
    )
    parser.add_argument(
        "--vein_threshold_ct",
        type=float,
        default=97.5,
        help="Threshold for vein detection",
    )
    return parser.parse_args()


# -----------------------------
# FMRI Loader Functions
# -----------------------------


def load_fmri_task(scene_dir: str):
    """
    Load task-based fMRI results into Slicer.

    Parameters
    ----------
    scene_dir : str
        Directory containing fMRI results.

    Returns
    -------
    None
    """
    fmri_path = os.path.join(scene_dir, "fMRI")
    if not os.path.exists(fmri_path):
        return

    print("SLICERLOADER: Loading task-based fMRI")
    for file in os.listdir(fmri_path):
        if file.endswith(".nii.gz"):
            load_anat(
                fmri_path,
                file.replace(".nii.gz", ""),
                "vtkMRMLPETProceduralColorNodePET-Rainbow2",
            )


def load_fmri_resting_state(scene_dir: str):
    """
    Load resting-state fMRI volumes.

    Parameters
    ----------
    scene_dir : str
        Directory containing resting-state fMRI results.

    Returns
    -------
    None
    """
    fmri_dir = os.path.join(scene_dir, "fMRI_resting_state")
    if not os.path.exists(fmri_dir):
        return

    pattern = "r-*[0-9].nii.gz"
    zstat_files = glob.glob(pattern, root_dir=fmri_dir)
    for zstat_file in sorted(zstat_files):
        load_anat(fmri_dir, zstat_file, "vtkMRMLColorTableNodeFileColdToHotRainbow.txt")


def create_grayscale_model(
    orig_node,
    model_name: str,
    threshold: float,
    scene_dir: str,
    file_name: str,
    model_color: list = None,
):
    """
    Create a 3D surface model from a grayscale volume using a threshold.

    Parameters
    ----------
    orig_node : vtkMRMLScalarVolumeNode
        The source volume node.
    model_name : str
        Name of the 3D model node.
    threshold : float
        Intensity threshold for surface extraction.
    scene_dir : str
        Directory where the 3D model will be saved.
    file_name : str
        Name of the output file (usually ends with .vtk).
    model_color : list, optional
        RGB color for the model (values between 0 and 1). Default is None (uses Slicer default).

    Returns
    -------
    None
    """
    if orig_node is None:
        print(f"SLICERLOADER: Source node for model '{model_name}' is None, skipping.")
        return

    print(f"SLICERLOADER: Creating 3D model '{model_name}' with threshold {threshold}")
    new_model = slicer.vtkMRMLModelNode()
    new_model.SetName(model_name)
    slicer.mrmlScene.AddNode(new_model)

    # Run the grayscale model maker CLI
    parameters = {
        "InputVolume": orig_node.GetID(),
        "Threshold": threshold,
        "OutputGeometry": new_model.GetID(),
    }
    gray_maker = slicer.modules.grayscalemodelmaker
    slicer.cli.runSync(gray_maker, None, parameters)

    # Configure display properties
    new_model.CreateDefaultDisplayNodes()
    if model_color is not None:
        display_node = new_model.GetDisplayNode()
        display_node.SetScalarVisibility(False)
        display_node.SetColor(model_color)
        display_node.SetOpacity(1.0)

    # Save the model to file
    storage_node = new_model.CreateDefaultStorageNode()
    storage_node.SetFileName(os.path.join(scene_dir, file_name))
    storage_node.WriteData(new_model)


# -----------------------------
# Vein Loader Functions
# -----------------------------


def load_vein(
    scene_dir: str, vein_threshold_mr: float = 97.5, vein_threshold_ct: float = 97.5
):
    """
    Load veins and create 3D models using thresholding.

    Parameters
    ----------
    scene_dir : str
        Directory containing vein volumes.
    vein_threshold_mr : float
        Threshold for creating 3D vein models from MR.
    vein_threshold_ct : float
        Threshold for creating 3D vein models fropm CT.

    Returns
    -------
    None
    """
    veins = {
        "mra": {
            "file_name": "r-veins_mra_inskull",
            "threshold": vein_threshold_mr,
            "color": [0, 0, 1],
        },
        "ct": {
            "file_name": "r-veins_ct_inskull",
            "threshold": vein_threshold_ct,
            "color": [0, 0, 1],
        },
    }

    for vein in veins.values():
        vein_node = load_anat(scene_dir, vein["file_name"])
        if vein_node is None:
            continue

        print(f"SLICERLOADER: Creating 3D model for {vein['file_name']}")
        # Attempt to compute threshold using FSL stats if available
        try:
            command = f"fslstats {os.path.join(scene_dir, vein['file_name'] + '.nii.gz')} -P {vein['threshold']}"
            output = subprocess.run(
                command, shell=True, stdout=subprocess.PIPE
            ).stdout.decode("utf-8")
            thr = float(output)
        except Exception:
            thr = 6  # fallback threshold

        create_grayscale_model(
            vein_node,
            "Veins",
            thr,
            scene_dir,
            vein["file_name"] + ".vtk",
            vein["color"],
        )


# -----------------------------
# FreeSurfer Loader Functions
# -----------------------------


def load_freesurfer_segmentation_file(seg_file: str):
    """
    Load a FreeSurfer segmentation file into Slicer.

    Handles differences between Linux and other platforms to avoid plugin crashes.

    Parameters
    ----------
    seg_file : str
        Full path to the FreeSurfer segmentation file (.mgz).

    Returns
    -------
    None
    """
    if not os.path.exists(seg_file):
        print(f"SLICERLOADER: Segmentation file not found: {seg_file}")
        return

    try:
        # On Linux, use the old method to prevent Slicer FreeSurfer plugin crashes
        if "linux" in sys.platform:
            slicer.util.loadVolume(
                seg_file, {"labelmap": True, "colorNodeID": "vtkMRMLColorTableNodeFile"}
            )
        else:
            # On Windows/macOS, use FreeSurferImporter plugin logic
            slicer.util.getModuleLogic("FreeSurferImporter").LoadFreeSurferSegmentation(
                seg_file
            )
        print(
            f"SLICERLOADER: Loaded FreeSurfer segmentation: {os.path.basename(seg_file)}"
        )
    except Exception as e:
        print(f"SLICERLOADER: Failed to load segmentation {seg_file}: {e}")


def load_freesurfer(scene_dir: str, ref_node):
    """
    Load FreeSurfer segmentations, surfaces, and overlays.

    Parameters
    ----------
    scene_dir : str
        Directory containing FreeSurfer output.
    ref_node : vtkMRMLScalarVolumeNode
        Reference volume for surface registration.

    Returns
    -------
    None
    """
    # Load segmentations
    seg_files = [
        "r-aparc_aseg.mgz",
        "segmentHA/lh.hippoAmygLabels.mgz",
        "segmentHA/rh.hippoAmygLabels.mgz",
    ]
    for seg_file in seg_files:
        seg_path = os.path.join(scene_dir, seg_file)
        load_freesurfer_segmentation_file(seg_path)

    # Load surfaces
    lh_pial = load_freesurfer_surf(scene_dir, "lh.pial", ref_node)
    rh_pial = load_freesurfer_surf(scene_dir, "rh.pial", ref_node)
    for surf in ["lh.white", "rh.white"]:
        load_freesurfer_surf(scene_dir, surf, ref_node)

    # Load overlays
    overlays = [
        "pet_surf",
        "pet_ai_surf",
        "pet_zscore_surf",
        "asl_surf",
        "asl_ai_surf",
        "asl_zscore_surf",
    ]
    for overlay in overlays:
        load_freesurfer_overlay(scene_dir, overlay + "_lh.mgz", lh_pial)
        load_freesurfer_overlay(scene_dir, overlay + "_rh.mgz", rh_pial)


# -----------------------------
# Scene Viewer / Display
# -----------------------------


def show_node(node):
    """
    Set the provided node as background in all slice views (Red, Yellow, Green).

    Parameters
    ----------
    node : vtkMRMLScalarVolumeNode
        Node to show in slice views.

    Returns
    -------
    None
    """
    orientations = {"Red": "Sagittal", "Yellow": "Coronal", "Green": "Axial"}

    for name, orientation in orientations.items():
        slice_node = slicer.mrmlScene.GetFirstNodeByName(name)
        if not slice_node:
            slice_node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSliceNode", name)
            slice_node.SetSingletonTag(name)
            slice_node.SetOrientation(orientation)

        comp_node = slicer.mrmlScene.GetFirstNodeByName(f"{name} Composite")
        if not comp_node:
            comp_node = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLSliceCompositeNode", f"{name} Composite"
            )
            comp_node.SetSingletonTag(name)

        comp_node.SetBackgroundVolumeID(node.GetID())


def tract_model(
    segmentation_node,
    dti_dir: str,
    tract: dict,
    side: str,
    dti_threshold: float = 0.0035,
):
    """
    Create a single DTI tract segment using a probabilistic tractography map.

    This implementation uses the Segment Editor "Threshold" effect via a temporary
    qMRMLSegmentEditorWidget. Although not multi-threaded, this approach is robust
    and compatible with all Slicer versions where CLI-based solutions may fail.

    Workflow:
    ----------
    1. Load the tract probability map (NIfTI)
    2. Compute an adaptive threshold using the corresponding 'waytotal' file, if available
    3. Create a temporary Segment Editor environment
    4. Apply thresholding to generate a new segment
    5. Perform strict and ordered cleanup to avoid Qt lifecycle errors

    Parameters
    ----------
    segmentation_node : vtkMRMLSegmentationNode
        Segmentation node where the tract segment will be added.

    dti_dir : str
        Directory containing DTI tractography outputs.

    tract : dict
        Dictionary describing the tract with the following keys:
            - 'name' (str): tract name (e.g. 'cst', 'af')
            - 'thr' (float): fallback threshold value
            - 'color' (list): RGB color in range [0–1]

    side : str
        Hemisphere side identifier:
            - 'lh' for left hemisphere
            - 'rh' for right hemisphere

    dti_threshold : float, optional
        Multiplicative factor applied to the 'waytotal' value to compute
        the final threshold. Default is 0.0035.

    Notes
    -----
    - This method is NOT multi-threaded.
    - It blocks the Python main thread during execution.
    - The cleanup order is critical to prevent Qt-related crashes.
    - Recommended only when CLI-based thresholding is unreliable.
    """

    # ------------------------------------------------------------------
    # Locate tract probability map
    # ------------------------------------------------------------------
    tract_file = os.path.join(dti_dir, f"r-{tract['name']}_{side}.nii.gz")
    if not os.path.exists(tract_file):
        print(f"SLICERLOADER: Tract file not found: {tract_file}")
        return

    # ------------------------------------------------------------------
    # Read waytotal file (if present) to compute adaptive threshold
    # ------------------------------------------------------------------
    waytotal_file = os.path.join(dti_dir, f"r-{tract['name']}_{side}_waytotal")
    waytotal = None

    if os.path.exists(waytotal_file):
        try:
            with open(waytotal_file, "r") as f:
                waytotal = int(f.readline().strip())
        except Exception:
            waytotal = None

    # Compute threshold value
    if waytotal and waytotal > 0:
        threshold = waytotal * dti_threshold
    else:
        threshold = float(tract["thr"])

    print(
        f"SLICERLOADER: Creating tract '{tract['name']}' "
        f"({side.upper()}), threshold={threshold:.2f}"
    )

    # ------------------------------------------------------------------
    # Load tract volume and set segmentation geometry
    # ------------------------------------------------------------------
    tract_node = slicer.util.loadVolume(tract_file)
    segmentation_node.SetReferenceImageGeometryParameterFromVolumeNode(tract_node)

    # ------------------------------------------------------------------
    # Create TEMPORARY Segment Editor environment
    # ------------------------------------------------------------------
    segment_editor_widget = slicer.qMRMLSegmentEditorWidget()
    segment_editor_widget.setMRMLScene(slicer.mrmlScene)

    segment_editor_node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentEditorNode")

    segment_editor_widget.setMRMLSegmentEditorNode(segment_editor_node)
    segment_editor_widget.setSegmentationNode(segmentation_node)
    segment_editor_widget.setSourceVolumeNode(tract_node)

    # ------------------------------------------------------------------
    # Create new empty segment for this tract
    # ------------------------------------------------------------------
    segment_id = segmentation_node.GetSegmentation().AddEmptySegment(
        tract["name"], tract["name"], tract["color"]
    )
    segment_editor_node.SetSelectedSegmentID(segment_id)

    # ------------------------------------------------------------------
    # Apply Threshold effect
    # ------------------------------------------------------------------
    segment_editor_widget.setActiveEffectByName("Threshold")
    effect = segment_editor_widget.activeEffect()
    effect.setParameter("MinimumThreshold", threshold)
    effect.self().onApply()

    # ==================================================================
    # CRITICAL CLEANUP SECTION
    # The order of operations below is REQUIRED to avoid Qt lifecycle
    # errors such as:
    # "Trying to call 'parameterSetNode' on a destroyed object"
    # ==================================================================

    # 1. Disable active effect FIRST
    segment_editor_widget.setActiveEffect(None)

    # 2. Disconnect MRML nodes from the widget
    segment_editor_widget.setSegmentationNode(None)
    segment_editor_widget.setSourceVolumeNode(None)

    # 3. Remove the Segment Editor MRML node
    slicer.mrmlScene.RemoveNode(segment_editor_node)

    # 4. Safely schedule widget deletion
    segment_editor_widget.deleteLater()

    # 5. Remove temporary tract volume
    slicer.mrmlScene.RemoveNode(tract_node)


def main_tract(dti_dir: str, scene_dir: str, dti_threshold: float = 0.0035):
    """
    Create DTI tractography segmentations and export them as 3D models.

    For each hemisphere (LH, RH), this function:
    - Creates a segmentation node
    - Loads tract probability maps
    - Thresholds them to generate segments
    - Saves the resulting segmentation to disk

    Parameters
    ----------
    dti_dir : str
        Directory containing DTI tract files.
    scene_dir : str
        Directory where output segmentations will be saved.
    dti_threshold : float, optional
        Multiplicative threshold factor for tract probability maps.
        Default is 0.0035.

    Returns
    -------
    None
    """
    if not os.path.isdir(dti_dir):
        print(f"SLICERLOADER: DTI directory not found: {dti_dir}")
        return

    sides = ["rh", "lh"]
    tracts = [
        {"name": "cst", "thr": 500, "color": [0, 1, 0]},
        {"name": "af", "thr": 1500, "color": [1, 0, 1]},
        {"name": "or", "thr": 500, "color": [1, 1, 0]},
    ]

    print("SLICERLOADER: Creating DTI tract 3D models (this may take a few minutes)")

    for side in sides:
        # Create a segmentation node for the current hemisphere
        segmentation_node = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLSegmentationNode", f"tracts_{side}"
        )
        segmentation_node.CreateDefaultDisplayNodes()

        for tract in tracts:
            tract_model(
                segmentation_node=segmentation_node,
                dti_dir=dti_dir,
                tract=tract,
                side=side,
                dti_threshold=dti_threshold,
            )

        # Generate 3D surface representation
        segmentation_node.CreateClosedSurfaceRepresentation()

        # Save segmentation to disk
        storage_node = segmentation_node.CreateDefaultStorageNode()
        output_file = os.path.join(scene_dir, f"tracts_{side}.seg.nrrd")
        storage_node.SetFileName(output_file)
        storage_node.WriteData(segmentation_node)

        print(f"SLICERLOADER: Saved tract segmentation: {output_file}")


def load_seeg(scene_dir: str, threshold: float = 900):
    """
    Creates the 3d model of a tract.

    Parameters
    ----------
    scene_dir : str
        The result directory.
    threshold : float
        The threshold for the model

    Returns
    -------
    None.

    """

    seeg_volume_name = "r-seeg_electrodes"
    seeg_node = load_anat(scene_dir, seeg_volume_name)
    if seeg_node is None:
        return

    steel_blue = [70 / 255.0, 130 / 255.0, 180 / 255.0]
    create_grayscale_model(
        seeg_node,
        "sEEG electrodes",
        threshold,
        scene_dir,
        "seeg_electrodes.vtk",
        steel_blue,
    )


# -----------------------------
# Main Execution
# -----------------------------
def main_export():
    """
    Main script execution for importing data into Slicer.
    """
    args = parse_arguments()

    slicer.mrmlScene.Clear(0)
    results_folder = os.getcwd()

    if not os.path.isdir(results_folder):
        print("SLICERLOADER: Results folder not found")
        return

    ref_node = load_anat(results_folder, "ref")
    if ref_node is None:
        print("SLICERLOADER: Reference volume not found")
        return

    # Load base anatomical volumes
    base_volumes = [
        "ref_brain",
        "r-flair_brain",
        "r-flair",
        "r-mdc_brain",
        "r-mdc",
        "r-FA",
        "r-flair2d_tra_brain",
        "r-flair2d_cor_brain",
        "r-flair2d_sag_brain",
        "r-t2_cor_brain",
        "r-t2_cor",
        "r-binary_flair",
        "r-junction_z",
        "r-extension_z",
        "r-melodic_IC",
    ]
    for vol in base_volumes:
        load_anat(results_folder, vol)

    # Load colored volumes
    color_volumes = [
        ("r-asl_ai", "vtkMRMLColorTableNodeFileDivergingBlueRed.txt", False),
        ("r-pet_ai", "vtkMRMLColorTableNodeFileDivergingBlueRed.txt", False),
        ("r-pet", "vtkMRMLColorTableNodeFileColdToHotRainbow.txt", True),
        ("r-pet_zscore", "vtkMRMLColorTableNodeFileColdToHotRainbow.txt", False),
        ("r-asl", "vtkMRMLColorTableNodeFileColdToHotRainbow.txt", True),
        ("r-asl_zscore", "vtkMRMLColorTableNodeFileColdToHotRainbow.txt", False),
    ]
    for vol_name, color_node, hide_zero in color_volumes:
        load_anat(results_folder, vol_name, color_node_id=color_node, hide_zero=hide_zero)

    # Example: load lesions, fMRI, veins, FreeSurfer
    # lesion_segment(results_folder)
    load_fmri_task(results_folder)
    load_fmri_resting_state(results_folder)
    load_vein(
        results_folder,
        vein_threshold_mr=args.vein_threshold_mr,
        vein_threshold_ct=args.vein_threshold_ct,
    )
    load_freesurfer(results_folder, ref_node)
    dtiDir = os.path.join(results_folder, "dti")
    if os.path.isdir(dtiDir):
        main_tract(dtiDir, results_folder)
    load_seeg(results_folder)
    show_node(ref_node)

    print("SLICERLOADER: Saving Slicer scene")
    slicer.util.saveScene(os.path.join(results_folder, "scene.mrb"))

main_export()
qt.QTimer.singleShot(0, slicer.app.quit)
