"""Build browsable reports from the committed workflow snapshots.

Both reports group scenarios by workflow and show, per setting combination, the
extracted "decision" highlights (commands used, CUDA/GPU flags, node count):

* ``matrix_report.html`` — a rich, self-contained local view that also embeds
  the full snapshot text in collapsible blocks (git-ignored; regenerate on
  demand).
* ``MATRIX.md`` — a deterministic, versioned Markdown summary that GitHub
  renders as living documentation, linking each scenario to its golden ``.txt``.

This is a plain script, not a pytest test (the file name does not start with
``test_``). Run it with::

    python swane/tests/nipype_pipeline/matrix/generate_report.py [html_output]

It reads ``snapshots/`` next to this file, writes the HTML (to the given path or
``matrix_report.html``) and always refreshes ``MATRIX.md``. It never touches the
golden files.
"""

from __future__ import annotations

import html
import os
import re
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
SNAPSHOTS_DIR = os.path.join(HERE, "snapshots")

_CMD_RE = re.compile(r"cmd=(\S+)")
_GPU_RE = re.compile(r"(use_cuda|use_gpu)\s*=\s*(True|False)")


def _parse(text: str) -> dict:
    """Extract config header, node count and decision highlights from a snapshot."""
    config: dict[str, str] = {}
    for line in text.splitlines():
        # Config header lines use ``#   key = value`` (spaces around ``=``); the
        # ``# nodes=.. edges=..`` summary line has no spaces and is skipped.
        m = re.match(r"#\s+([A-Za-z0-9_]+)\s+=\s+(.*)$", line)
        if m:
            config[m.group(1)] = m.group(2)
    nodes_m = re.search(r"# nodes=(\d+) edges=(\d+)", text)
    commands = sorted(set(_CMD_RE.findall(text)))
    gpu = sorted({"%s=%s" % (k, v) for k, v in _GPU_RE.findall(text)})
    is_none = "builder returned None" in text
    return {
        "config": config,
        "nodes": nodes_m.group(1) if nodes_m else ("0" if is_none else "?"),
        "edges": nodes_m.group(2) if nodes_m else ("0" if is_none else "?"),
        "commands": commands,
        "gpu": gpu,
        "is_none": is_none,
    }


def _collect() -> dict:
    families: dict[str, list] = {}
    for workflow in sorted(os.listdir(SNAPSHOTS_DIR)):
        folder = os.path.join(SNAPSHOTS_DIR, workflow)
        if not os.path.isdir(folder):
            continue
        scenarios = []
        for fname in sorted(os.listdir(folder)):
            if not fname.endswith(".txt"):
                continue
            with open(os.path.join(folder, fname), encoding="utf-8") as fh:
                text = fh.read()
            scenarios.append((fname[:-4], text, _parse(text)))
        if scenarios:
            families[workflow] = scenarios
    return families


def _chips(values: list[str], kind: str) -> str:
    if not values:
        return '<span class="muted">—</span>'
    return "".join(
        '<span class="chip %s">%s</span>' % (kind, html.escape(v)) for v in values
    )


def _render(families: dict) -> str:
    total = sum(len(s) for s in families.values())
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    parts: list[str] = []
    parts.append(
        "<title>SWANe Workflow Matrix</title>"
        '<p class="lead">Construction snapshots for %d scenarios across %d workflow '
        "families. Each row is one setting combination; expand it to read the full "
        "graph (nodes, commands, flags, wiring). Generated %s.</p>"
        % (total, len(families), html.escape(generated))
    )

    # Table of contents
    parts.append('<nav class="toc">')
    for workflow, scenarios in families.items():
        parts.append(
            '<a href="#%s">%s <span class="count">%d</span></a>'
            % (html.escape(workflow), html.escape(workflow), len(scenarios))
        )
    parts.append("</nav>")

    for workflow, scenarios in families.items():
        parts.append('<section id="%s">' % html.escape(workflow))
        parts.append("<h2>%s</h2>" % html.escape(workflow))
        parts.append(
            "<table><thead><tr><th>scenario</th><th>settings</th>"
            "<th>nodes</th><th>commands</th><th>GPU</th></tr></thead><tbody>"
        )
        for name, text, info in scenarios:
            settings = " · ".join(
                "%s=%s" % (html.escape(k), html.escape(v))
                for k, v in info["config"].items()
            )
            node_label = (
                "None"
                if info["is_none"]
                else "%s / %se" % (info["nodes"], info["edges"])
            )
            parts.append("<tr>")
            parts.append('<td class="name">%s</td>' % html.escape(name))
            parts.append('<td class="settings">%s</td>' % settings)
            parts.append('<td class="num">%s</td>' % node_label)
            parts.append("<td>%s</td>" % _chips(info["commands"], "cmd"))
            parts.append("<td>%s</td>" % _chips(info["gpu"], "gpu"))
            parts.append("</tr>")
            parts.append(
                '<tr class="detail"><td colspan="5"><details>'
                "<summary>full snapshot</summary>"
                "<pre>%s</pre></details></td></tr>" % html.escape(text)
            )
        parts.append("</tbody></table></section>")

    return "<style>%s</style>%s" % (_CSS, "".join(parts))


_CSS = """
:root{--bg:#ffffff;--fg:#1b1f24;--muted:#6b7280;--line:#e5e7eb;--card:#f8fafc;
--accent:#2563eb;--cmd-bg:#eef2ff;--cmd-fg:#3730a3;--gpu-bg:#ecfdf5;--gpu-fg:#065f46;}
:root:not([data-theme="light"]){}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
--bg:#0d1117;--fg:#e6edf3;--muted:#9198a1;--line:#232b36;--card:#161b22;
--accent:#4f8cff;--cmd-bg:#1e2438;--cmd-fg:#c3cbff;--gpu-bg:#132a22;--gpu-fg:#8ff0c8;}}
:root[data-theme="dark"]{--bg:#0d1117;--fg:#e6edf3;--muted:#9198a1;--line:#232b36;
--card:#161b22;--accent:#4f8cff;--cmd-bg:#1e2438;--cmd-fg:#c3cbff;--gpu-bg:#132a22;--gpu-fg:#8ff0c8;}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--fg);margin:0;padding:24px;
font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;}
.lead{color:var(--muted);max-width:70ch}
h2{margin-top:2.2rem;border-bottom:2px solid var(--line);padding-bottom:.3rem}
.toc{display:flex;flex-wrap:wrap;gap:.5rem;margin:1rem 0}
.toc a{background:var(--card);border:1px solid var(--line);border-radius:999px;
padding:.25rem .7rem;text-decoration:none;color:var(--fg);font-size:13px}
.toc .count{color:var(--muted)}
table{width:100%;border-collapse:collapse;margin:.5rem 0 1rem}
th,td{text-align:left;padding:.5rem .6rem;border-bottom:1px solid var(--line);
vertical-align:top;font-size:14px}
th{color:var(--muted);font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.03em}
td.name{font-weight:600;white-space:nowrap}
td.settings{color:var(--muted);font-size:13px;max-width:38ch}
td.num{white-space:nowrap;font-variant-numeric:tabular-nums}
.chip{display:inline-block;border-radius:6px;padding:.1rem .45rem;margin:.1rem;
font:12px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace}
.chip.cmd{background:var(--cmd-bg);color:var(--cmd-fg)}
.chip.gpu{background:var(--gpu-bg);color:var(--gpu-fg)}
.muted{color:var(--muted)}
tr.detail td{padding-top:0;border-bottom:1px solid var(--line)}
details summary{cursor:pointer;color:var(--accent);font-size:13px;margin:.2rem 0}
pre{background:var(--card);border:1px solid var(--line);border-radius:8px;
padding:12px;overflow-x:auto;font:12px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace}
"""


def _md_cell(text: str) -> str:
    """Escape a value for a Markdown table cell."""
    return text.replace("|", "\\|").replace("\n", " ")


def _render_markdown(families: dict) -> str:
    """Render a deterministic Markdown summary (no timestamp) for versioning.

    GitHub renders this natively as living documentation. It links each scenario
    to its committed golden ``.txt`` snapshot rather than embedding the full
    graph, so it stays a compact overview and never duplicates the source text.
    """
    total = sum(len(s) for s in families.values())

    lines: list[str] = []
    lines.append("# SWANe workflow settings matrix")
    lines.append("")
    lines.append(
        "Overview of %d construction scenarios across %d workflow families. Each "
        "row is one setting combination; follow the *snapshot* link for the full "
        "graph (nodes, commands, flags, wiring)." % (total, len(families))
    )
    lines.append("")
    lines.append(
        "> Generated from the golden snapshots by "
        "`python swane/tests/nipype_pipeline/matrix/generate_report.py` — "
        "do not edit by hand. Regenerate after refreshing the snapshots "
        "(`SWANE_SNAPSHOT_UPDATE=1 pytest .../matrix`)."
    )
    lines.append("")

    # Table of contents.
    lines.append(
        " · ".join("[%s](#%s)" % (wf, wf.replace("_", "-")) for wf in families)
    )
    lines.append("")

    for workflow, scenarios in families.items():
        lines.append("## %s" % workflow)
        lines.append("")
        lines.append("| scenario | settings | nodes/edges | commands | GPU |")
        lines.append("|----------|----------|-------------|----------|-----|")
        for name, _text, info in scenarios:
            settings = "; ".join("%s=%s" % (k, v) for k, v in info["config"].items())
            node_label = (
                "None"
                if info["is_none"]
                else "%s / %s" % (info["nodes"], info["edges"])
            )
            commands = ", ".join("`%s`" % c for c in info["commands"]) or "—"
            gpu = ", ".join("`%s`" % g for g in info["gpu"]) or "—"
            link = "[%s](snapshots/%s/%s.txt)" % (name, workflow, name)
            lines.append(
                "| %s | %s | %s | %s | %s |"
                % (
                    link,
                    _md_cell(settings),
                    node_label,
                    _md_cell(commands),
                    _md_cell(gpu),
                )
            )
        lines.append("")

    return "\n".join(lines) + "\n"


def main() -> None:
    families = _collect()
    if not families:
        raise SystemExit("No snapshots found in %s" % SNAPSHOTS_DIR)
    total = sum(len(s) for s in families.values())

    # HTML: rich local view (git-ignored). Optional explicit path as argv[1].
    html_out = (
        sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "matrix_report.html")
    )
    with open(html_out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(_render(families))
    print("Wrote %s (%d scenarios, %d workflows)" % (html_out, total, len(families)))

    # Markdown: deterministic, versioned documentation rendered by GitHub.
    md_out = os.path.join(HERE, "MATRIX.md")
    with open(md_out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(_render_markdown(families))
    print("Wrote %s" % md_out)


if __name__ == "__main__":
    main()
