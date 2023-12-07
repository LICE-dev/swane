# slicerpython script for module checking
# Warning: slicer library is not required beacuse the script is executed in Slicer environment
import sys

manager = slicer.app.extensionsManagerModel()
manager.downloadAndInstallExtensionByName("SlicerFreeSurfer")
while len(manager.activeTasks) > 0:
    print(manager.activeTasks)

sys.exit(0)
