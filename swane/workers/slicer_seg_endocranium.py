import slicer
import sys
import os
import vtkITK
import vtk

import vtk
import slicer


def export_segment_as_nifti(segmentationNode, segmentId, referenceVolumeNode, out_file):
    """
    Esporta un singolo segmento come NIfTI, headless-safe.
    - segmentationNode: vtkMRMLSegmentationNode
    - segmentId: string
    - referenceVolumeNode: vtkMRMLScalarVolumeNode
    - out_file: path NIfTI (.nii o .nii.gz)
    """

    # Controlli tipi nodi
    if segmentationNode is None or segmentationNode.GetClassName() != "vtkMRMLSegmentationNode":
        raise ValueError("segmentationNode deve essere vtkMRMLSegmentationNode")
    if referenceVolumeNode is None or referenceVolumeNode.GetClassName() != "vtkMRMLScalarVolumeNode":
        raise ValueError("referenceVolumeNode deve essere vtkMRMLScalarVolumeNode")

    # Crea nodo temporaneo labelmap
    labelmapNode = slicer.mrmlScene.AddNewNodeByClass(
        "vtkMRMLLabelMapVolumeNode",
        "TempLabelmapNode"
    )

    # Export del segmento
    # Positional arguments obbligatori, senza keyword arguments
    slicer.modules.segmentations.logic().ExportSegmentsToLabelmapNode(
        segmentationNode,
        [segmentId],
        labelmapNode,
        referenceVolumeNode
    )

    # Salva NIfTI
    slicer.util.saveNode(labelmapNode, out_file)

    # Pulizia nodo temporaneo
    slicer.mrmlScene.RemoveNode(labelmapNode)


def smooth_segment_morphological_closing(
    segmentationNode,
    segmentId,
    referenceVolumeNode,
    kernelSizeMm
):
    """
    Headless replacement for SegmentEditorSmoothingEffect.smoothSelectedSegment
    (MORPHOLOGICAL_CLOSING only)
    """

    # 1. Export segment to labelmap
    labelmapNode = slicer.mrmlScene.AddNewNodeByClass(
        "vtkMRMLLabelMapVolumeNode"
    )

    slicer.modules.segmentations.logic().ExportSegmentsToLabelmapNode(
        segmentationNode,
        [segmentId],
        labelmapNode,
        referenceVolumeNode
    )

    imageData = labelmapNode.GetImageData()

    # 2. Compute kernel size in voxels
    spacing = imageData.GetSpacing()
    kernelSizeVoxel = [
        int(round((kernelSizeMm / spacing[i] + 1) / 2) * 2 - 1)
        for i in range(3)
    ]

    # Ensure odd kernel size
    kernelSizeVoxel = [
        k if k % 2 == 1 else k + 1
        for k in kernelSizeVoxel
    ]

    # 3. Morphological closing (dilation + erosion)
    closeFilter = vtk.vtkImageOpenClose3D()
    closeFilter.SetInputData(imageData)
    closeFilter.SetKernelSize(
        kernelSizeVoxel[0],
        kernelSizeVoxel[1],
        kernelSizeVoxel[2]
    )
    closeFilter.SetOpenValue(0)
    closeFilter.SetCloseValue(1)
    closeFilter.Update()

    smoothedImage = closeFilter.GetOutput()

    # 4. Import back into segmentation (overwrite)
    slicer.modules.segmentations.logic().ImportLabelmapToSegmentationNode(
        labelmapNode,
        segmentationNode
    )

    # Cleanup
    slicer.mrmlScene.RemoveNode(labelmapNode)


# ---- Arguments ----
in_file = sys.argv[1]
out_file = sys.argv[2]   # .nii o .nii.gz
skull_mask = sys.argv[3]   # .nii o .nii.gz
smoothingKernelSize = float(sys.argv[4])
splitCavitiesDiameter = 15

if not out_file.endswith((".nii", ".nii.gz")):
    raise ValueError("out_file deve essere .nii o .nii.gz")

# ---- Load volume ----
inputVolume = slicer.util.loadVolume(in_file)
if not inputVolume:
    raise RuntimeError(f"Errore caricamento volume: {in_file}")

# ---- Seg node ----
outputSegmentation = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode")
outputSegmentation.SetName("Endocranium")
outputSegmentation.CreateDefaultDisplayNodes()
outputSegmentation.SetReferenceImageGeometryParameterFromVolumeNode(inputVolume)


thresholdCalculator = vtkITK.vtkITKImageThresholdCalculator()
thresholdCalculator.SetInputData(inputVolume.GetImageData())
thresholdCalculator.SetMethodToMaximumEntropy()
thresholdCalculator.Update()
boneThresholdValue = thresholdCalculator.GetThreshold()
volumeScalarRange = inputVolume.GetImageData().GetScalarRange()
print(f"Volume minimum = {volumeScalarRange[0]}, maximum = {volumeScalarRange[1]}, bone threshold = {boneThresholdValue}")

# Set up segmentation
outputSegmentation.CreateDefaultDisplayNodes()
outputSegmentation.SetReferenceImageGeometryParameterFromVolumeNode(inputVolume)

# Create segment editor to get access to effects
segmentEditorWidget = slicer.qMRMLSegmentEditorWidget()
segmentEditorWidget.setMRMLScene(slicer.mrmlScene)
if not segmentEditorWidget.effectByName("Wrap Solidify"):
  raise NotImplementedError("SurfaceWrapSolidify extension is required")

segmentEditorNode = slicer.vtkMRMLSegmentEditorNode()
slicer.mrmlScene.AddNode(segmentEditorNode)
segmentEditorWidget.setMRMLSegmentEditorNode(segmentEditorNode)
segmentEditorWidget.setSegmentationNode(outputSegmentation)
segmentEditorWidget.setSourceVolumeNode(inputVolume)
# Create bone segment by thresholding
boneSegmentID = outputSegmentation.GetSegmentation().AddEmptySegment("bone")
segmentEditorNode.SetSelectedSegmentID(boneSegmentID)
segmentEditorWidget.setActiveEffectByName("Threshold")


effect = segmentEditorWidget.activeEffect()
effect.setParameter("MinimumThreshold", str(boneThresholdValue))
effect.setParameter("MaximumThreshold", str(volumeScalarRange[1]))
effect.setParameter("SmoothingMethod", "MORPHOLOGICAL_CLOSING")
effect.setParameter("KernelSizeMm", str(smoothingKernelSize))
effect.self().onApply()

smooth_segment_morphological_closing(
    segmentationNode=outputSegmentation,
    segmentId=boneSegmentID,
    referenceVolumeNode=inputVolume,
    kernelSizeMm=smoothingKernelSize
)

# Solidify bone
segmentEditorWidget.setActiveEffectByName("Wrap Solidify")
effect = segmentEditorWidget.activeEffect()
wrapEffect = effect.self()
logic = wrapEffect.logic

wrapEffect.segmentationNode = outputSegmentation
logic.segmentationNode = outputSegmentation
wrapEffect.segmentId = segmentEditorNode.GetSelectedSegmentID()
logic.segmentId = segmentEditorNode.GetSelectedSegmentID()
assert isinstance(logic.segmentId, str)

logic.region = "largestCavity"
logic.regionSegmentId = ""
logic.splitCavities = True
logic.splitCavitiesDiameter = float(splitCavitiesDiameter)
logic.outputType = "newSegment"
logic.remeshOversampling = 2.5
logic.smoothingFactor = 0.2
logic.shrinkwrapIterations = 6
logic.carveHolesInOuterSurface = False
logic.createShell = False
logic.shellPreserveCracks = False
logic.shellThickness = 1.5
logic.outputType = 'segment'
logic.saveIntermediateResults = False
logic.outputModelNode = None
logic.applyWrapSolidify()

# ---- Converto to LabelMap ----
labelmapNode = slicer.mrmlScene.AddNewNodeByClass(
    "vtkMRMLLabelMapVolumeNode",
    "EndocraniumLabel"
)

# Export last segment
skullSegmentID = outputSegmentation.GetSegmentation().GetNthSegmentID(1)
brainSegmentID = outputSegmentation.GetSegmentation().GetNthSegmentID(0)

export_segment_as_nifti(
    segmentationNode=outputSegmentation,
    segmentId=skullSegmentID,
    referenceVolumeNode=inputVolume,
    out_file=out_file
)

export_segment_as_nifti(
    segmentationNode=outputSegmentation,
    segmentId=brainSegmentID,
    referenceVolumeNode=inputVolume,
    out_file=skull_mask
)

slicer.app.exit()


print(f"[OK] Endocranium salvato in NIfTI: {out_file}")
