import slicer
import sys
import vtk
import vtkITK
import argparse
import qt
import os
os.environ["QT_LOGGING_RULES"] = "*.warning=false"


# ------------------------------------------------------------
# Utility: export single segment to NIfTI
# ------------------------------------------------------------
def export_segment_as_nifti(segmentationNode, segmentId, referenceVolumeNode, out_file):

    labelmapNode = slicer.mrmlScene.AddNewNodeByClass(
        "vtkMRMLLabelMapVolumeNode",
        "TempLabelmapNode"
    )

    slicer.modules.segmentations.logic().ExportSegmentsToLabelmapNode(
        segmentationNode,
        [segmentId],
        labelmapNode,
        referenceVolumeNode
    )

    slicer.util.saveNode(labelmapNode, out_file)
    slicer.mrmlScene.RemoveNode(labelmapNode)


# ------------------------------------------------------------
# Headless morphological closing smoothing
# ------------------------------------------------------------
def smooth_segment_morphological_closing(
    segmentationNode,
    segmentId,
    referenceVolumeNode,
    kernelSizeMm
):

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
    spacing = imageData.GetSpacing()

    kernelSizeVoxel = [
        int(round((kernelSizeMm / spacing[i] + 1) / 2) * 2 - 1)
        for i in range(3)
    ]
    kernelSizeVoxel = [k if k % 2 == 1 else k + 1 for k in kernelSizeVoxel]

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

    slicer.modules.segmentations.logic().ImportLabelmapToSegmentationNode(
        labelmapNode,
        segmentationNode
    )

    slicer.mrmlScene.RemoveNode(labelmapNode)


# ------------------------------------------------------------
# Argument parsing (named arguments)
# ------------------------------------------------------------
parser = argparse.ArgumentParser(description="Endocranium segmentation with Wrap Solidify (headless)")

parser.add_argument("--input", required=True, help="Input CT volume (NIfTI)")
parser.add_argument("--output", required=True, help="Output endocranium mask (NIfTI)")
parser.add_argument("--kernel-mm", type=float, default=3.0, help="Smoothing kernel size in mm")
parser.add_argument("--oversampling", type=float, default=1.0, help="Wrap Solidify remesh oversampling")
parser.add_argument("--iterations", type=int, default=2, help="Shrinkwrap iterations")
parser.add_argument("--split-diameter", type=float, default=30.0, help="Split cavities diameter (mm)")

args = parser.parse_args(sys.argv[1:])

in_file = args.input
out_endocranium = args.output
smoothingKernelSize = args.kernel_mm
oversampling = args.oversampling
shrinkwrapIterations = args.iterations
splitCavitiesDiameter = args.split_diameter


# ------------------------------------------------------------
# Load input volume
# ------------------------------------------------------------
inputVolume = slicer.util.loadVolume(in_file)
if not inputVolume:
    raise RuntimeError(f"Cannot load volume: {in_file}")


# ------------------------------------------------------------
# Create segmentation
# ------------------------------------------------------------
segmentationNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode")
segmentationNode.CreateDefaultDisplayNodes()
segmentationNode.SetReferenceImageGeometryParameterFromVolumeNode(inputVolume)

seg = segmentationNode.GetSegmentation()


# ------------------------------------------------------------
# Automatic bone threshold
# ------------------------------------------------------------
thresholdCalculator = vtkITK.vtkITKImageThresholdCalculator()
thresholdCalculator.SetInputData(inputVolume.GetImageData())
thresholdCalculator.SetMethodToMaximumEntropy()
thresholdCalculator.Update()

boneThresholdValue = thresholdCalculator.GetThreshold()
volumeScalarRange = inputVolume.GetImageData().GetScalarRange()

print(f"[INFO] Bone threshold = {boneThresholdValue}")


# ------------------------------------------------------------
# Segment Editor setup (headless)
# ------------------------------------------------------------
segmentEditorWidget = slicer.qMRMLSegmentEditorWidget()
segmentEditorWidget.setMRMLScene(slicer.mrmlScene)

segmentEditorNode = slicer.vtkMRMLSegmentEditorNode()
slicer.mrmlScene.AddNode(segmentEditorNode)

segmentEditorWidget.setMRMLSegmentEditorNode(segmentEditorNode)
segmentEditorWidget.setSegmentationNode(segmentationNode)
segmentEditorWidget.setSourceVolumeNode(inputVolume)


# ------------------------------------------------------------
# 1. bone_raw (threshold)
# ------------------------------------------------------------
boneRawID = seg.AddEmptySegment("bone_raw")
segmentEditorNode.SetSelectedSegmentID(boneRawID)

segmentEditorWidget.setActiveEffectByName("Threshold")
effect = segmentEditorWidget.activeEffect()
effect.setParameter("MinimumThreshold", str(boneThresholdValue))
# TODO: for now we set 220 as fixed value, maybe we can implement a better way
effect.setParameter("MinimumThreshold", "220")
effect.setParameter("MaximumThreshold", str(volumeScalarRange[1]))
effect.self().onApply()


# ------------------------------------------------------------
# 2. bone_smooth (copy + smoothing)
# ------------------------------------------------------------
boneSmoothID = seg.AddEmptySegment("bone_smooth")

seg.GetSegment(boneSmoothID).DeepCopy(
    seg.GetSegment(boneRawID)
)

smooth_segment_morphological_closing(
    segmentationNode=segmentationNode,
    segmentId=boneSmoothID,
    referenceVolumeNode=inputVolume,
    kernelSizeMm=smoothingKernelSize
)

segmentationNode.Modified()
slicer.mrmlScene.Modified()


# ------------------------------------------------------------
# 3. Wrap Solidify (ONLY on bone_smooth)
# ------------------------------------------------------------
segmentEditorNode.SetSelectedSegmentID(boneSmoothID)

segmentEditorWidget.setActiveEffectByName("Wrap Solidify")
effect = segmentEditorWidget.activeEffect()
wrapEffect = effect.self()
logic = wrapEffect.logic

wrapEffect.segmentationNode = segmentationNode
logic.segmentationNode = segmentationNode
wrapEffect.segmentId = boneSmoothID
logic.segmentId = boneSmoothID

logic.region = "largestCavity"
logic.regionSegmentId = ""
logic.splitCavities = True
logic.splitCavitiesDiameter = splitCavitiesDiameter

logic.outputType = "segment"
logic.remeshOversampling = oversampling
logic.smoothingFactor = 0.1
logic.shrinkwrapIterations = shrinkwrapIterations

logic.carveHolesInOuterSurface = False
logic.createShell = False
logic.shellPreserveCracks = False
logic.shellThickness = 1.5

logic.saveIntermediateResults = False
logic.outputModelNode = None

logic.applyWrapSolidify()


# ------------------------------------------------------------
# Export output
# ------------------------------------------------------------
export_segment_as_nifti(
    segmentationNode,
    boneSmoothID,
    inputVolume,
    out_endocranium
)

print("[OK] Endocranium mask exported:", out_endocranium)


# ------------------------------------------------------------
# Exit Slicer
# ------------------------------------------------------------
segmentEditorWidget = None
segmentEditorNode = None
qt.QTimer.singleShot(0, slicer.app.quit)
