# slicerpython script for module checking
# Warning: slicer library is not required beacuse the script is executed in Slicer environment
import sys

em = slicer.app.extensionsManagerModel()
em.interactive = False  # prevent display of popups
restart = False

extension_list = sys.argv[1].split(',')
errors = []

for extensionName in extension_list:
    if not hasattr(
        slicer.moduleNames, extensionName
    ) and not em.installExtensionFromServer(extensionName, restart):
        errors.append(extensionName)

if len(errors) == 0:
    print("MODULE FOUND")
else:
    print("MODULE MISSING:" + ", ".join(errors))

sys.exit(0)
