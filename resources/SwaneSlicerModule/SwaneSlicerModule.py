import slicer
import qt
import vtk
import numpy as np

class SwaneSlicerModule:
    """
    Minimal Slicer module to hide zeros in loaded scalar volumes.

    Features
    --------
    - Automatically observes newly added scalar volumes in the scene.
    - Can mark individual volumes to hide zeros using an attribute.
    - Applies display thresholding without modifying the original volume data.

    Usage
    -----
    # In your script or module __init__.py
    from SwaneSlicerModule import SwaneSlicerModule

    myHideZero = SwaneSlicerModule()  # Automatically observes new nodes

    # Later, mark a node manually to hide zeros
    SwaneSlicerModule.mark_node_hide_zero(node)
    """

    def __init__(self, parent=None):
        self.parent = parent
        self._hideZeroObserver = None
        if not parent:
            self.setup()

    def setup(self):
        """Set up a scene observer to catch newly added scalar volumes."""
        if not self._hideZeroObserver:
            self._hideZeroObserver = slicer.mrmlScene.AddObserver(
                slicer.mrmlScene.NodeAddedEvent,
                self.onNodeAdded
            )

    def onNodeAdded(self, caller, event, callData=None):
        """
        Callback triggered when a new node is added to the scene.
        If the node is a scalar volume and has the 'HideZero' attribute, apply thresholding.
        """
        node = callData
        if node and node.IsA("vtkMRMLScalarVolumeNode"):
            if node.GetAttribute("HideZero") == "True":
                self.apply_hide_zero(node)

    @staticmethod
    def mark_node_hide_zero(node):
        """
        Set the 'HideZero' attribute on a node.

        Once marked, `apply_hide_zero` will hide voxel values equal to 0 in display.

        Parameters
        ----------
        node : vtkMRMLScalarVolumeNode
            The volume node to mark.
        """
        if not node or not node.IsA("vtkMRMLScalarVolumeNode"):
            return
        node.SetAttribute("HideZero", "True")
        SwaneSlicerModule.apply_hide_zero(node)

    @staticmethod
    def apply_hide_zero(node):
        """
        Apply display thresholding to hide zeros in a volume node.

        Only nodes with the attribute 'HideZero' set to 'True' will be affected.
        This does NOT modify the original voxel data.

        Parameters
        ----------
        node : vtkMRMLScalarVolumeNode
            The volume node to modify.
        """
        if not node or not node.IsA("vtkMRMLScalarVolumeNode"):
            return

        if node.GetAttribute("HideZero") != "True":
            return

        dn = node.GetDisplayNode()
        if not dn:
            return

        dn.SetApplyThreshold(True)
        dn.SetLowerThreshold(1e-6)  # Excludes zeros
        dn.SetUpperThreshold(float("inf"))
        dn.SetAutoWindowLevel(False)
