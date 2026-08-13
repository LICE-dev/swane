# slicerpython script for module checking
# Warning: slicer library is not required beacuse the script is executed in Slicer environment
import sys

def install_extensions_from_args(argv):
    """Install extensions given an argv-like list (argv[0] is script name).

    This function is safe to import in a non-Slicer environment if a mock
    `slicer` module is provided in tests.
    """
    # Emulate the original behaviour but keep it callable
    em = slicer.app.extensionsManagerModel()
    em.interactive = False  # prevent display of popups
    restart = False

    extension_list = argv[1].split(",") if len(argv) > 1 else []
    errors = []

    for extensionName in extension_list:
        if not hasattr(slicer.moduleNames, extensionName):
            if not hasattr(em, "installExtensionFromServer") or not em.installExtensionFromServer(extensionName, restart):
                errors.append(extensionName)

    if len(errors) == 0:
        print("MODULE FOUND")
        return 0
    else:
        print("MODULE MISSING:" + ", ".join(errors))
        return 1


if __name__ == "__main__":
    # preserve original CLI behaviour
    sys.exit(install_extensions_from_args(sys.argv))
