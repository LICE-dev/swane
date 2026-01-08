# slicerpython script for module checking
# Warning: slicer library is not required beacuse the script is executed in Slicer environment
import sys

em = slicer.app.extensionsManagerModel()
em.interactive = False  # prevent display of popups
restart = False

extension_list = ["SlicerFreeSurfer", "SurfaceWrapSolidify"]
errors = False

for extensionName in extension_list:
    if not hasattr(slicer.moduleNames, extensionName) and not em.installExtensionFromServer(extensionName, restart):
        errors = True

if not errors:
    print("MODULE FOUND")

sys.exit(0)
