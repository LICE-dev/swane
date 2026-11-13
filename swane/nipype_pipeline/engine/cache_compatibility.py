"""Check whether a previous workflow execution can be resumed.

Nipype pickles the classes of a node result (its interface, traits, outputs)
by module path. When a SWANe release moves or renames one of those classes
(e.g. 0.3 moved ``swane.nipype_pipeline.nodes.*`` to ``interfaces/<tool>/``),
the results of an older workflow directory can no longer be loaded and a
resumed run aborts as soon as a cached node feeds a node to run.
"""

import _compat_pickle
import gzip
import importlib
import os
import pickletools

RESULT_PREFIX = "result_"
RESULT_SUFFIX = ".pklz"

# Opcodes that push a string on the unpickling stack
_STRING_OPCODES = {
    "STRING",
    "BINSTRING",
    "SHORT_BINSTRING",
    "UNICODE",
    "BINUNICODE",
    "SHORT_BINUNICODE",
    "BINUNICODE8",
}
# Opcodes that read back a memoized object
_GET_OPCODES = {"GET", "BINGET", "LONG_BINGET"}
# Opcodes that store the stack top in the memo
_PUT_OPCODES = {"PUT", "BINPUT", "LONG_BINPUT"}
# Opcodes that leave the stack unchanged
_NEUTRAL_OPCODES = {"PROTO", "FRAME", "MEMOIZE"} | _PUT_OPCODES


def _fix_python2_name(protocol: int, module: str, name: str) -> tuple[str, str]:
    """
    Map a Python 2 name as the unpickler does for protocols older than 3
    """
    if protocol < 3:
        if (module, name) in _compat_pickle.NAME_MAPPING:
            return _compat_pickle.NAME_MAPPING[(module, name)]
        if module in _compat_pickle.IMPORT_MAPPING:
            return _compat_pickle.IMPORT_MAPPING[module], name
    return module, name


def _pickled_globals(content: bytes) -> set[tuple[str, str]]:
    """
    List the (module, qualified name) pairs a pickle references, without
    unpickling it.

    Parameters
    ----------
    content: bytes
        The pickle content

    Returns
    -------
    The set of referenced (module, qualified name) pairs

    Raises
    ------
    ValueError
        If the content is not a well-formed pickle
    """
    references = set()
    protocol = 0
    memo = {}
    # The values pushed so far, None for anything but a string: STACK_GLOBAL
    # takes the module and the name from the last two pushes.
    pushed = []
    for opcode, arg, _ in pickletools.genops(content):
        name = opcode.name
        if name == "PROTO":
            protocol = arg
        elif name in _STRING_OPCODES:
            pushed.append(arg)
        elif name in _GET_OPCODES:
            pushed.append(memo.get(arg))
        elif name == "MEMOIZE":
            memo[len(memo)] = pushed[-1] if pushed else None
        elif name in _PUT_OPCODES:
            memo[arg] = pushed[-1] if pushed else None
        elif name == "GLOBAL":
            module, qualname = arg.split(" ", 1)
            references.add(_fix_python2_name(protocol, module, qualname))
            pushed.append(None)
        elif name == "STACK_GLOBAL":
            if len(pushed) < 2 or not all(
                isinstance(value, str) for value in pushed[-2:]
            ):
                raise ValueError("STACK_GLOBAL without module and name")
            references.add(_fix_python2_name(protocol, pushed[-2], pushed[-1]))
            pushed.append(None)
        elif name not in _NEUTRAL_OPCODES:
            pushed.append(None)
    return references


def _is_resolvable(module: str, qualname: str) -> bool:
    """
    Returns
    -------
    True if the class or function can be imported as the unpickler would
    """
    try:
        target = importlib.import_module(module)
        for part in qualname.split("."):
            target = getattr(target, part)
    except Exception:
        return False
    return True


def _read_pickle(path: str) -> bytes:
    with gzip.open(path, "rb") as f:
        content = f.read()
    # Nipype may write a line of JSON metadata before the pickle
    if content.startswith(b"{"):
        newline = content.find(b"\n")
        if newline >= 0:
            content = content[newline + 1 :]
    return content


def find_unloadable_result(workflow_dir: str) -> str | None:
    """
    Look for a node result of a previous execution that this SWANe version
    cannot load. Nothing is unpickled: only the referenced classes are
    resolved.

    Parameters
    ----------
    workflow_dir: str
        The workflow directory of the previous execution

    Returns
    -------
    The path of the first unloadable result file, None if every result file
    can be loaded or the directory has none
    """
    resolved = {}
    for folder, _, files in os.walk(workflow_dir):
        for file_name in sorted(files):
            if not (
                file_name.startswith(RESULT_PREFIX)
                and file_name.endswith(RESULT_SUFFIX)
            ):
                continue
            path = os.path.join(folder, file_name)
            try:
                references = _pickled_globals(_read_pickle(path))
            except Exception:
                return path
            for reference in references:
                if reference not in resolved:
                    resolved[reference] = _is_resolvable(*reference)
                if not resolved[reference]:
                    return path
    return None
