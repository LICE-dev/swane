# slicerpython script for module checking
# Warning: slicer library is not required beacuse the script is executed in Slicer environment
import sys

em = slicer.app.extensionsManagerModel()
em.interactive = False  # prevent display of popups
restart = False

extension_list = ["SlicerFreeSurfer", "SurfaceWrapSolidify"]
for extensionName in extension_list:
    if not hasattr(slicer.moduleNames, extensionName) and not em.installExtensionFromServer(extensionName, restart):
        raise ValueError(f"Failed to install {extensionName} extension")
print("MODULE FOUND")
sys.exit(0)
