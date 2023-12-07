# slicerpython script for module checking
# Warning: slicer library is not required beacuse the script is executed in Slicer environment
import sys

extensionName = 'SlicerFreeSurfer'
em = slicer.app.extensionsManagerModel()
em.interactive = False  # prevent display of popups
restart = False
if not em.installExtensionFromServer(extensionName, restart):
  raise ValueError(f"Failed to install {extensionName} extension")
sys.exit(0)
