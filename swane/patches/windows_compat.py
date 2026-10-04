"""Windows compatibility shims installed before Nipype is imported.

Nipype's ``nipype/pipeline/plugins/__init__.py`` imports every execution
plugin, including ``sge.py``, which does ``import pwd`` at module level. ``pwd``
exists only on Unix, so on Windows the whole plugin package -- and with it the
MultiProc plugin SWANe runs every workflow with -- fails to import. ``sge.py``
only queries ``pwd`` while submitting SGE cluster jobs, which SWANe never does,
so a stub whose lookups fail like an unknown user is enough.

Command-line quoting
--------------------
Nipype quotes path arguments with ``shlex.quote`` (POSIX single quotes) and
runs every command line with ``subprocess.Popen(..., shell=True)``, i.e.
through ``cmd.exe`` on Windows, where single quotes are ordinary characters and
backslashes are path separators, not escapes. The helpers below quote with
double quotes following the MSVCRT argv rules (the ones
``subprocess.list2cmdline`` targets) and split with the same rules, so a quoted
argument always round-trips. :data:`WINDOWS_SHLEX` bundles them as a drop-in
for the ``shlex`` module; ``swane.patches.nipype_patches`` installs it in
Nipype's CommandLine core on Windows only. Nothing here imports Nipype.
"""

import os
import re
import shlex
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


def is_windows() -> bool:
    """Return True on Windows (single switch, patched by the tests)."""
    return os.name == "nt"


# Same "safe" set as ``shlex.quote``: such strings need no quoting anywhere.
_SAFE = re.compile(r"[\w@%+=:,./-]+", re.ASCII)


def windows_quote(value: str) -> str:
    """Quote ``value`` as one argument for ``cmd.exe`` + the MSVCRT argv parser.

    Strings ``shlex.quote`` would leave bare are returned unchanged; every other
    string (in practice every Windows path, which contains ``\\``) is wrapped
    in double quotes. Backslashes stay literal, except that a run of
    backslashes preceding a double quote (an embedded one or the closing one)
    is doubled, and embedded double quotes are escaped as ``\\"``.
    """
    if value and _SAFE.fullmatch(value):
        return value
    out = ['"']
    backslashes = 0
    for char in value:
        if char == "\\":
            backslashes += 1
            continue
        if char == '"':
            out.append("\\" * (2 * backslashes + 1))
        else:
            out.append("\\" * backslashes)
        out.append(char)
        backslashes = 0
    out.append("\\" * (2 * backslashes))
    out.append('"')
    return "".join(out)


def windows_split(line: str) -> list:
    """Split a command line with the MSVCRT argv rules (inverse of
    :func:`windows_quote`).

    Unlike POSIX ``shlex.split`` it keeps backslashes literal, so bare drive
    paths (``C:\\env\\tool.exe``) and UNC paths survive.
    """
    args = []
    current = []
    in_token = False
    in_quotes = False
    backslashes = 0
    i = 0
    while i < len(line):
        char = line[i]
        if char == "\\":
            backslashes += 1
            in_token = True
        elif char == '"':
            current.append("\\" * (backslashes // 2))
            if backslashes % 2:
                current.append('"')
            elif in_quotes and line[i + 1 : i + 2] == '"':
                current.append('"')  # "" inside quotes: a literal quote
                i += 1
            else:
                in_quotes = not in_quotes
            backslashes = 0
            in_token = True
        else:
            current.append("\\" * backslashes)
            backslashes = 0
            if char in " \t" and not in_quotes:
                if in_token:
                    args.append("".join(current))
                current = []
                in_token = False
            else:
                current.append(char)
                in_token = True
        i += 1
    current.append("\\" * backslashes)
    if in_token:
        args.append("".join(current))
    return args


class _WindowsShlex(types.ModuleType):
    """``shlex`` stand-in with Windows ``quote``/``split``; everything else
    (``join``, ``shlex``, ...) is the real module's."""

    quote = staticmethod(windows_quote)
    split = staticmethod(windows_split)

    def __getattr__(self, attr):
        return getattr(shlex, attr)


WINDOWS_SHLEX = _WindowsShlex("swane_windows_shlex")


def cmdline_quote(value: str) -> str:
    """Quote one argument for a shell command line built for Nipype:
    :func:`windows_quote` on Windows, ``shlex.quote`` elsewhere."""
    return windows_quote(value) if is_windows() else shlex.quote(value)


def shell_executable(path: str) -> str:
    """Return an absolute executable path ready to be a Nipype ``_cmd``.

    On Windows the path is :func:`windows_quote`-d (it may contain spaces, e.g.
    under the user profile). Elsewhere it is returned unchanged, as SWANe has
    always used it.
    """
    return windows_quote(path) if is_windows() else path
