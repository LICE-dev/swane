"""Deterministic, human-readable snapshots of a built Nipype workflow graph.

The settings-matrix tests assemble each ``*_workflow`` builder under many
configuration combinations and render the resulting graph to a stable text
block. That text is stored as a *golden* file under ``matrix/snapshots/`` so a
reviewer can open it and check by hand what SWANe builds for every setting
(which nodes exist, which command each runs, GPU/CUDA flags, resource hints and
how nodes are wired), while pytest uses the same text as a regression guard.

Determinism is the whole point, so the renderer:

* sorts nodes, input traits and connections by name;
* rewrites machine-specific absolute paths (the test ``tmp_path``, the home
  folder, ``swane_supplement`` resources, ``$FSLDIR``, the interpreter's
  ``site-packages`` and the current working directory) to stable ``<TOKEN>``s;
* normalises Windows back-slashes to ``/`` so a snapshot generated on Windows
  matches one generated on Linux/macOS.

Only construction state is read; nothing is executed.
"""

from __future__ import annotations

import ast
import os
import site
import sysconfig
import tempfile
from typing import Any

from nipype.interfaces.base import isdefined

from swane.config.preference_list import XTRACT_DATA_DIR


def _abs(path: Any) -> str:
    return os.path.abspath(str(path)).replace("\\", "/").rstrip("/")


def build_replacements(tmp_root: str) -> list[tuple[str, str]]:
    """Return ``(absolute_prefix, token)`` pairs, longest prefix first.

    Longest-first ordering guarantees that a nested root (e.g. the home folder
    inside ``tmp_path``) is rewritten before its parent.
    """
    roots: list[tuple[str, str]] = []

    def add(path: Any, token: str) -> None:
        if path:
            roots.append((_abs(path), token))

    add(tmp_root, "<TMP>")
    try:
        import swane_supplement

        add(swane_supplement.__path__[0], "<SUPPLEMENT>")
    except Exception:
        pass
    # XTRACT_DATA_DIR resolves under $FSLDIR to "Human" (FSL < 6.0.7) or
    # "HUMAN" (FSL >= 6.0.7) depending on the installed FSL version, so the
    # committed goldens must not encode either case — collapse both to one
    # token so the snapshot is identical across FSL versions/boxes. Registered
    # before <FSLDIR> so the longest-prefix-first sort picks the nested,
    # more specific root first.
    add(XTRACT_DATA_DIR, "<XTRACT_DATA>")
    add(os.environ.get("FSLDIR"), "<FSLDIR>")
    # nipype stamps SUBJECTS_DIR onto every FreeSurfer node; its value is
    # machine-specific (and, in the test session, a throwaway directory).
    add(os.environ.get("SUBJECTS_DIR"), "<SUBJECTS_DIR>")
    add(os.environ.get("HOME"), "<HOME>")
    add(os.environ.get("USERPROFILE"), "<HOME>")
    # Every package-install root -> <SITE>, so a path into an installed
    # package's data files (e.g. ica_aroma_py resources) collapses to a stable
    # token regardless of WHERE/HOW the package was installed: system
    # site-packages, a virtualenv, or a `pip install --user` user-site
    # (~/.local/lib/pythonX.Y/site-packages). Covering only sysconfig 'purelib'
    # missed the user-site, leaking e.g.
    # /home/<user>/.local/lib/python3.12/site-packages/ica_aroma_py/... into the
    # golden and tying it to one developer's machine and Python version. All
    # roots share the <SITE> token so the result is identical across install
    # layouts; longest-prefix-first ordering keeps nested roots (e.g.
    # <SUPPLEMENT>) winning over the enclosing site-packages dir.
    site_roots: list[Any] = [
        sysconfig.get_paths().get("purelib"),
        sysconfig.get_paths().get("platlib"),
    ]
    try:
        site_roots.extend(site.getsitepackages())
    except Exception:
        pass
    try:
        site_roots.append(site.getusersitepackages())
    except Exception:
        pass
    for site_root in site_roots:
        add(site_root, "<SITE>")
    add(os.getcwd(), "<CWD>")
    # test_run's recon-all -expert file lives at a fixed path in the system
    # temp dir (see freesurfer_workflow._reconall_test_expert_file), which
    # differs by OS (/tmp vs Windows' AppData\Local\Temp).
    add(tempfile.gettempdir(), "<SYSTEMP>")

    # De-duplicate while preserving the longest-first order.
    seen: set[str] = set()
    unique: list[tuple[str, str]] = []
    for prefix, token in sorted(roots, key=lambda r: len(r[0]), reverse=True):
        if prefix and prefix not in seen:
            seen.add(prefix)
            unique.append((prefix, token))
    return unique


def _normalise(value: Any, repl: list[tuple[str, str]]) -> Any:
    """Recursively rewrite volatile paths inside ``value`` for stable output."""
    if isinstance(value, str):
        text = value.replace("\\", "/")
        for prefix, token in repl:
            if prefix in text:
                text = text.replace(prefix, token)
        return text
    if isinstance(value, dict):
        return {k: _normalise(v, repl) for k, v in value.items()}
    if isinstance(value, tuple):
        return tuple(_normalise(v, repl) for v in value)
    if isinstance(value, list):
        # Includes traits' ``TraitListObject``; collapse to a plain list so the
        # result is reconstructable and renders deterministically.
        return [_normalise(v, repl) for v in value]
    return value


def _normalise_function_source(src: str) -> str:
    """Canonicalise a ``Function`` node's captured source, dropping comments.

    ``nipype.interfaces.utility.Function`` stores the wrapped callable's full
    source text (captured via ``inspect.getsource``) in its ``function_str``
    input. Comments and incidental whitespace inside that source are not part of
    the function's behavior, yet a bare diff of the raw text would flag them —
    so editing a comment inside a ``Function`` body would spuriously fail the
    snapshot regression.

    Parsing to an AST and unparsing back collapses comments and reformats the
    body to a canonical form (comments never survive the AST round-trip), while
    still changing whenever the actual logic changes. ``ast.unparse`` is
    preferred over ``ast.dump`` so the snapshot stays human-readable — reviewing
    what each node does by hand is the whole point of these golden files.
    """
    try:
        return ast.unparse(ast.parse(src))
    except (SyntaxError, ValueError):
        # Defensive fallback: keep behavior sane if ever handed something that
        # is not parseable Python (should not happen for a Function's source).
        return src


def _normalise_conn_field(field: Any, repl: list[tuple[str, str]]) -> Any:
    """Canonicalise a connection endpoint for stable rendering.

    nipype allows an inline transform on a connection — expressed as
    ``(field_name, function_source, args)`` — and the wrapped function's source
    text (comments included) would otherwise be diffed verbatim, exactly the
    fragility :func:`_normalise_function_source` removes for a node's
    ``function_str`` trait. Apply the same normalisation to any string the tuple
    carries (a plain field name is unaffected by the AST round-trip), so a
    comment/formatting edit inside a connection transform is not a false diff.
    """
    if isinstance(field, tuple):
        return tuple(
            (
                _normalise(_normalise_function_source(elem), repl)
                if isinstance(elem, str)
                else elem
            )
            for elem in field
        )
    return field


def _format_value(value: Any) -> str:
    """Render a (normalised) trait value deterministically."""
    if isinstance(value, dict):
        items = ", ".join("%s=%r" % (k, value[k]) for k in sorted(value))
        return "{%s}" % items
    return repr(value)


def _render_cmd(cmd: str, repl: list[tuple[str, str]]) -> str:
    """Render an interface command stably across machines and OSes.

    Bare commands (``flirt``, ``bet``, ``eddy`` ...) are kept verbatim. A command
    resolved to an absolute path — e.g. the ``dcm2niix`` binary bundled in
    ``site-packages`` — is reduced to its stem so the value neither leaks the
    install location nor differs by the Windows ``.exe`` suffix.

    ``Eddy`` resolves its GPU variant to ``eddy_cuda`` when that binary
    is on ``PATH``, falling back to the bare ``eddy`` otherwise — a machine
    difference (whether the box has the ``eddy_cuda`` symlink) unrelated to
    the workflow's own settings, which are already captured by the node's
    ``use_cuda`` input and the "cuda = true" config header. Canonicalise both
    variants to ``eddy`` so the golden is identical on GPU and non-GPU boxes;
    this is narrowly scoped to the one known GPU-variant command name.
    """
    text = _normalise(cmd, repl)
    if text == "eddy_cuda":
        return "eddy"
    if "/" in text:
        base = text.rsplit("/", 1)[-1]
        if base.endswith(".exe"):
            base = base[: -len(".exe")]
        return base
    return text


def _is_workflow(node: Any) -> bool:
    return hasattr(node, "_graph") and not hasattr(node, "interface")


def _node_block(node: Any, repl: list[tuple[str, str]], indent: str) -> list[str]:
    """Render a single leaf node (Node / MapNode) to snapshot lines."""
    interface = node.interface
    header = "%s- %s [%s]" % (indent, node.name, type(interface).__name__)

    cmd = getattr(interface, "_cmd", None)
    if cmd:
        header += " cmd=%s" % _render_cmd(cmd, repl)

    iterfield = getattr(node, "iterfield", None)
    if iterfield:
        header += " mapnode(iterfield=%s)" % ",".join(iterfield)

    try:
        mem = node.mem_gb
        if mem is not None:
            header += " mem_gb=%s" % mem
    except Exception:
        pass
    try:
        n_procs = node.n_procs
        if n_procs is not None:
            header += " n_procs=%s" % n_procs
    except Exception:
        pass

    lines = [header]
    inputs = node.inputs
    for trait_name in sorted(inputs.editable_traits()):
        raw = getattr(inputs, trait_name)
        if not isdefined(raw):
            continue
        if trait_name == "function_str" and isinstance(raw, str):
            # Function nodes capture their source verbatim (comments included);
            # canonicalise it so a comment/formatting edit is not a false diff.
            value = _normalise(_normalise_function_source(raw), repl)
        else:
            value = _normalise(raw, repl)
        lines.append("%s    %s = %s" % (indent, trait_name, _format_value(value)))
    return lines


def _graph_lines(workflow: Any, repl: list[tuple[str, str]], indent: str) -> list[str]:
    graph = workflow._graph
    nodes = sorted(graph.nodes(), key=lambda n: n.name)

    lines: list[str] = []
    for node in nodes:
        if _is_workflow(node):
            lines.append("%s+ %s (sub-workflow)" % (indent, node.name))
            lines.extend(_graph_lines(node, repl, indent + "    "))
        else:
            lines.extend(_node_block(node, repl, indent))

    # Connections between direct children of this workflow.
    conn_lines: list[str] = []
    for src, dst, data in graph.edges(data=True):
        for src_field, dst_field in data.get("connect", []):
            conn_lines.append(
                "%s%s.%s -> %s.%s"
                % (
                    indent,
                    src.name,
                    _normalise_conn_field(src_field, repl),
                    dst.name,
                    dst_field,
                )
            )
    if conn_lines:
        lines.append("%s# connections" % indent)
        lines.extend(sorted(conn_lines))
    return lines


def render_snapshot(workflow: Any, tmp_root: str, *, title: str, config: dict) -> str:
    """Render ``workflow`` (built under ``config``) to deterministic text.

    Parameters
    ----------
    workflow
        The built :class:`CustomWorkflow` (or ``None`` when a builder guards out).
    tmp_root
        The test's ``tmp_path``; every path beneath it is tokenised to ``<TMP>``.
    title
        Human label for the snapshot header (usually the builder + combo id).
    config
        The setting combination that produced this graph, echoed in the header
        so the golden file is self-describing.
    """
    repl = build_replacements(tmp_root)

    header = ["# workflow snapshot: %s" % title, "#"]
    for key in sorted(config):
        header.append("#   %s = %s" % (key, config[key]))

    if workflow is None:
        header.append("#")
        header.append("(builder returned None — no graph constructed)")
        return "\n".join(header) + "\n"

    graph = workflow._graph
    header.append("#")
    header.append(
        "# nodes=%d edges=%d" % (graph.number_of_nodes(), graph.number_of_edges())
    )
    body = _graph_lines(workflow, repl, "")
    return "\n".join(header + [""] + body) + "\n"
