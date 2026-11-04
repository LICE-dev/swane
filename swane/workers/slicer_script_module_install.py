# slicerpython script for module checking
# Warning: slicer library is not required beacuse the script is executed in Slicer environment
import json
import os
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
            if not hasattr(
                em, "installExtensionFromServer"
            ) or not em.installExtensionFromServer(extensionName, restart):
                errors.append(extensionName)

    # Report where Slicer keeps each extension, so SWANe can later verify the
    # install with a plain filesystem check instead of launching Slicer.
    print("SLICER REVISION:" + str(slicer.app.revision))
    for extensionName in extension_list:
        if extensionName in errors:
            continue
        try:
            ext_path = em.extensionInstallPath(extensionName)
        except Exception:
            continue
        if ext_path and os.path.isdir(ext_path):
            print("MODULE PATH:" + extensionName + "=" + ext_path)
        # The extension's module folders, as Slicer itself lists them: SWANe
        # passes them to its isolated batch runs (swane.utils.slicer_isolation)
        # instead of rebuilding them from the install layout, which differs
        # between Slicer versions and platforms.
        try:
            module_dirs = [str(path) for path in em.extensionModulePaths(extensionName)]
        except Exception:
            continue
        if module_dirs:
            print("MODULE DIRS:" + extensionName + "=" + json.dumps(module_dirs))

    if len(errors) == 0:
        print("MODULE FOUND")
        return 0
    else:
        print("MODULE MISSING:" + ", ".join(errors))
        return 1


if __name__ == "__main__":
    # preserve original CLI behaviour
    sys.exit(install_extensions_from_args(sys.argv))
