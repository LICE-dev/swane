"""Windows compatibility shims installed before Nipype is imported.

Nipype's ``nipype/pipeline/plugins/__init__.py`` imports every execution
plugin, including ``sge.py``, which does ``import pwd`` at module level. ``pwd``
exists only on Unix, so on Windows the whole plugin package -- and with it the
MultiProc plugin SWANe runs every workflow with -- fails to import. ``sge.py``
only queries ``pwd`` while submitting SGE cluster jobs, which SWANe never does,
so a stub whose lookups fail like an unknown user is enough.
"""

import os
import sys
import types


def install_pwd_stub() -> bool:
    """Register a minimal ``pwd`` module on Windows when the real one is missing.

    Returns
    -------
    bool
        True when the stub was installed, False when nothing was needed.
    """
    if os.name != "nt" or sys.modules.get("pwd") is not None:
        return False
    try:
        import pwd  # noqa: F401
    except ImportError:
        pass
    else:
        return False

    stub = types.ModuleType("pwd")

    def _unknown_user(*args, **kwargs):
        raise KeyError("the pwd database is not available on Windows")

    stub.getpwuid = _unknown_user
    stub.getpwnam = _unknown_user
    stub.getpwall = lambda: []
    stub.__swane_stub__ = True
    sys.modules["pwd"] = stub
    return True
