"""Launch 3D Slicer isolated from the user's own Slicer customizations.

SWANe's batch Slicer runs (pipeline nodes, scene export) must not depend on
the user's ``~/.slicerrc.py`` or on the extra modules the user added to
Slicer: those run at every Slicer start and can fail, hang or change Slicer's
behavior. ``--disable-settings`` drops the user's settings, but Slicer keeps
the extensions' module folders in the same settings key as the user's extra
modules, so the folders of the extensions SWANe needs are passed back
explicitly. Their paths are not built by SWANe: the full Slicer check asks
Slicer itself (``extensionModulePaths``) and records them in the
``slicer_extensions_state`` preference.

Qt-free on purpose: the Nipype workflow imports it.
"""

import json
import os

ISOLATION_FLAGS = ("--disable-settings", "--ignore-slicerrc")


def extension_module_dirs(raw_state, extensions) -> list | None:
    """
    Module folders recorded by the last full Slicer check for ``extensions``.

    Parameters
    ----------
    raw_state : str
        The ``slicer_extensions_state`` preference (JSON).
    extensions : list
        Names of the required extensions.

    Returns
    -------
    list or None
        The folders, in extension order, or None if the state is empty,
        malformed, misses an extension or lists a folder that no longer
        exists (the full Slicer check must run again).
    """
    try:
        module_paths = json.loads(raw_state)["module_paths"]
    except (TypeError, ValueError, KeyError):
        return None
    if not isinstance(module_paths, dict):
        return None
    dirs = []
    for extension in extensions:
        paths = module_paths.get(extension)
        if not isinstance(paths, list) or not paths:
            return None
        for path in paths:
            if not isinstance(path, str) or not os.path.isdir(path):
                return None
            dirs.append(path)
    return dirs


def isolation_args(module_dirs) -> list:
    """
    Slicer command-line arguments for an isolated batch run.

    Parameters
    ----------
    module_dirs : list
        Extension module folders to load (see ``extension_module_dirs``).

    Returns
    -------
    list
        Arguments to put before ``--python-script``.
    """
    args = list(ISOLATION_FLAGS)
    if module_dirs:
        args.append("--additional-module-paths")
        args.extend(module_dirs)
    return args
