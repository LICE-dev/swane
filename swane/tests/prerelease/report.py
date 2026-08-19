"""Write the sweep outcome in a form a human can audit.

Two artefacts, both in the work directory:

* ``prerelease_report.json`` - the machine-readable record (every pass, every
  check, every skip reason), suitable for diffing between releases;
* ``prerelease_report.html`` - a single self-contained page for reading, with
  each pass's configuration, checks and the path to its results so anything
  suspicious can be opened directly.

Both deliberately record *why* something did not run. A pass skipped for a
missing Slicer and a pass that passed its checks must never look alike.
"""

from __future__ import annotations

import html
import json
import os
import platform
from datetime import datetime

from swane.tests.prerelease.checks import ERROR, WARNING, summarise

JSON_REPORT = "prerelease_report.json"
HTML_REPORT = "prerelease_report.html"


def build_report(results, caps, cover, work_dir: str, options: dict) -> dict:
    """Assemble the full machine-readable record of a sweep."""
    passes = []
    for result in results:
        passed, errors, warnings = summarise(result.checks)
        passes.append(
            {
                "name": result.name,
                "status": result.status,
                "reason": result.reason,
                "seconds": round(result.seconds, 1),
                "subject_dir": result.subject_dir,
                "inputs": result.inputs,
                "values": result.values,
                "downgrades": result.downgrades,
                "nodes_started": result.nodes_started,
                "nodes_completed": result.nodes_completed,
                "node_errors": result.node_errors,
                "checks": [_check_json(c) for c in result.checks],
                "checks_passed": passed,
                "checks_failed": errors,
                "checks_warned": warnings,
            }
        )

    executed = [p for p in passes if p["status"] not in ("skipped",)]
    return {
        "generated": datetime.now().isoformat(timespec="seconds"),
        # A restricted run cannot be judged on coverage.
        "partial_run": bool(options.get("only")),
        "host": {
            "platform": platform.platform(),
            "python": platform.python_version(),
        },
        "options": options,
        "capabilities": {
            name: {"available": cap.available, "reason": cap.reason}
            for name, cap in caps.items.items()
        },
        "coverage": {
            name: {
                "covered": {v: names for v, names in c.covered.items()},
                "unreachable": c.unreachable,
                "deferred": c.deferred,
                "missing": c.missing,
            }
            for name, c in cover.items()
        },
        "passes": passes,
        "summary": {
            "total": len(passes),
            "executed": len(executed),
            "skipped": sum(1 for p in passes if p["status"] == "skipped"),
            "completed": sum(1 for p in passes if p["status"] == "completed"),
            "failed": sum(1 for p in passes if p["status"] in ("failed", "error")),
            "checks_failed": sum(p["checks_failed"] for p in passes),
            "checks_warned": sum(p["checks_warned"] for p in passes),
            "seconds": round(sum(p["seconds"] for p in passes), 1),
        },
    }


def _check_json(check) -> dict:
    if isinstance(check, dict):
        return check
    return check.to_json()


def write_json(report: dict, work_dir: str) -> str:
    path = os.path.join(work_dir, JSON_REPORT)
    with open(path, "w") as handle:
        json.dump(report, handle, indent=2)
    return path


def overall_success(report: dict) -> bool:
    """A sweep succeeds when nothing failed to run and no error check failed.

    Coverage holes count only in a full sweep. When the run was deliberately
    restricted with ``--only``, the uncovered axes are the direct consequence
    of that choice, not a defect in the plan.
    """
    summary = report["summary"]
    holes = any(c["missing"] for c in report["coverage"].values())
    if report.get("partial_run"):
        holes = False
    return summary["failed"] == 0 and summary["checks_failed"] == 0 and not holes


# --------------------------------------------------------------------------- #
# HTML
# --------------------------------------------------------------------------- #
_CSS = """
:root { --bg:#ffffff; --fg:#1a1a1a; --muted:#666; --line:#e3e3e3;
        --ok:#137333; --bad:#c5221f; --warn:#b06000; --skip:#5f6368;
        --card:#fafafa; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#16181c; --fg:#e8eaed; --muted:#9aa0a6; --line:#31343a;
          --ok:#7ee2a8; --bad:#ff8b82; --warn:#f5bd6b; --skip:#9aa0a6;
          --card:#1e2126; }
}
* { box-sizing:border-box; }
body { margin:0; padding:2rem 1.25rem; background:var(--bg); color:var(--fg);
       font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
main { max-width:1100px; margin:0 auto; }
h1 { font-size:1.6rem; margin:0 0 .25rem; }
h2 { font-size:1.15rem; margin:2rem 0 .6rem; padding-bottom:.3rem;
     border-bottom:1px solid var(--line); }
.sub { color:var(--muted); margin:0 0 1.5rem; }
.tiles { display:flex; flex-wrap:wrap; gap:.75rem; margin:1rem 0 1.5rem; }
.tile { background:var(--card); border:1px solid var(--line); border-radius:8px;
        padding:.7rem 1rem; min-width:110px; }
.tile b { display:block; font-size:1.5rem; line-height:1.2; }
.tile span { color:var(--muted); font-size:.8rem; text-transform:uppercase;
             letter-spacing:.04em; }
.ok{color:var(--ok)} .bad{color:var(--bad)} .warn{color:var(--warn)}
.skip{color:var(--skip)}
table { width:100%; border-collapse:collapse; margin:.5rem 0 1rem; font-size:.9rem; }
th,td { text-align:left; padding:.4rem .6rem; border-bottom:1px solid var(--line);
        vertical-align:top; }
th { font-weight:600; color:var(--muted); font-size:.78rem;
     text-transform:uppercase; letter-spacing:.04em; }
.wrap { overflow-x:auto; }
details { background:var(--card); border:1px solid var(--line); border-radius:8px;
          padding:.6rem .9rem; margin:.55rem 0; }
summary { cursor:pointer; font-weight:600; }
summary .meta { font-weight:400; color:var(--muted); margin-left:.5rem;
                font-size:.85rem; }
code { background:rgba(127,127,127,.14); padding:.1rem .3rem; border-radius:4px;
       font-size:.85em; }
.kv { color:var(--muted); font-size:.85rem; margin:.4rem 0; }
.viewbtn { display:inline-flex; align-items:center; gap:.35rem; margin:.2rem 0 .4rem;
           padding:.25rem .6rem; border:1px solid var(--line); border-radius:6px;
           background:transparent; color:var(--fg); font:inherit; font-size:.8rem;
           cursor:pointer; }
.viewbtn:hover { background:rgba(127,127,127,.12); }
"""

#: A static HTML file has no server behind it, so a link cannot launch a local
#: process directly -- the browser sandbox forbids it. This copies the exact
#: `--view` command to the clipboard instead: one click, then paste into a
#: terminal. document.execCommand('copy') (not the async Clipboard API) is
#: used deliberately: it works from a plain file:// page in every browser,
#: whereas navigator.clipboard often refuses outside a secure context/server.
_COPY_JS = """
function swaneCopyView(btn, cmd) {
  var ta = document.createElement('textarea');
  ta.value = cmd;
  ta.style.position = 'fixed';
  ta.style.opacity = '0';
  document.body.appendChild(ta);
  ta.select();
  try { document.execCommand('copy'); } catch (e) {}
  document.body.removeChild(ta);
  var original = btn.textContent;
  btn.textContent = 'copied!';
  setTimeout(function () { btn.textContent = original; }, 1500);
}
"""


def _badge(status: str) -> str:
    cls = {
        "completed": "ok",
        "failed": "bad",
        "error": "bad",
        "skipped": "skip",
    }.get(status, "")
    return '<span class="%s">%s</span>' % (cls, html.escape(status))


def _pass_section(item: dict, work_dir: str) -> str:
    checks = item["checks"]
    failed = [c for c in checks if not c["passed"] and c["severity"] == ERROR]
    warned = [c for c in checks if not c["passed"] and c["severity"] == WARNING]

    meta = "%s &middot; %s" % (_badge(item["status"]), _fmt_time(item["seconds"]))
    if item["status"] != "skipped":
        meta += " &middot; %d/%d nodes &middot; %d checks, %d failed, %d warnings" % (
            item["nodes_completed"],
            item["nodes_started"],
            len(checks),
            len(failed),
            len(warned),
        )

    rows = []
    if item["reason"]:
        rows.append('<p class="kv">%s</p>' % html.escape(item["reason"][:2000]))
    if item["inputs"]:
        rows.append(
            '<p class="kv">Inputs: %s</p>'
            % ", ".join("<code>%s</code>" % html.escape(i) for i in item["inputs"])
        )
    if item["values"]:
        rows.append(
            '<p class="kv">Settings: %s</p>'
            % ", ".join(
                "<code>%s=%s</code>" % (html.escape(k), html.escape(str(v)))
                for k, v in sorted(item["values"].items())
            )
        )
    for axis, wanted, used, reason in item["downgrades"]:
        rows.append(
            '<p class="kv warn">downgraded %s: %s &rarr; %s (%s)</p>'
            % tuple(html.escape(str(x)) for x in (axis, wanted, used, reason))
        )
    if item["subject_dir"]:
        rows.append(
            '<p class="kv">Results: <code>%s</code></p>'
            % html.escape(os.path.join(item["subject_dir"], "results"))
        )
        if os.path.isdir(os.path.join(item["subject_dir"], "results")):
            view_cmd = "python -m swane.tests.prerelease --view %s --work-dir %s" % (
                item["name"],
                work_dir,
            )
            onclick = "swaneCopyView(this,%s)" % json.dumps(view_cmd)
            rows.append(
                '<button type="button" class="viewbtn" onclick="%s">'
                "&#128203; copy view-scene command</button>" % html.escape(onclick)
            )
    if item["node_errors"]:
        rows.append("<table><tr><th>failed node</th><th>crash file</th></tr>")
        for err in item["node_errors"]:
            rows.append(
                "<tr><td>%s</td><td><code>%s</code></td></tr>"
                % (
                    html.escape(str(err.get("node"))),
                    html.escape(str(err.get("crash_file") or "-")),
                )
            )
        rows.append("</table>")
    if checks:
        rows.append(
            '<div class="wrap"><table><tr><th>check</th><th>result</th>'
            "<th>detail</th></tr>"
        )
        for check in checks:
            cls = (
                "ok"
                if check["passed"]
                else ("bad" if check["severity"] == ERROR else "warn")
            )
            label = "pass" if check["passed"] else check["severity"]
            rows.append(
                '<tr><td>%s</td><td class="%s">%s</td><td>%s</td></tr>'
                % (
                    html.escape(check["name"]),
                    cls,
                    label,
                    html.escape(check["detail"]),
                )
            )
        rows.append("</table></div>")

    open_attr = " open" if failed or item["status"] in ("failed", "error") else ""
    return (
        '<details%s><summary>%s<span class="meta">%s</span></summary>%s</details>'
        % (open_attr, html.escape(item["name"]), meta, "".join(rows))
    )


def _fmt_time(seconds: float) -> str:
    seconds = int(seconds or 0)
    if seconds < 60:
        return "%ds" % seconds
    if seconds < 3600:
        return "%dm%02ds" % (seconds // 60, seconds % 60)
    return "%dh%02dm" % (seconds // 3600, (seconds % 3600) // 60)


def write_html(report: dict, work_dir: str) -> str:
    summary = report["summary"]
    ok = overall_success(report)

    tiles = [
        ("passes run", summary["executed"], ""),
        ("completed", summary["completed"], "ok"),
        ("failed", summary["failed"], "bad" if summary["failed"] else ""),
        ("skipped", summary["skipped"], "skip"),
        (
            "checks failed",
            summary["checks_failed"],
            "bad" if summary["checks_failed"] else "",
        ),
        (
            "warnings",
            summary["checks_warned"],
            "warn" if summary["checks_warned"] else "",
        ),
        ("total time", _fmt_time(summary["seconds"]), ""),
    ]
    tile_html = "".join(
        '<div class="tile"><b class="%s">%s</b><span>%s</span></div>'
        % (cls, value, label)
        for label, value, cls in tiles
    )

    caps_rows = "".join(
        '<tr><td>%s</td><td class="%s">%s</td><td>%s</td></tr>'
        % (
            html.escape(name),
            "ok" if cap["available"] else "skip",
            "yes" if cap["available"] else "no",
            html.escape(cap["reason"]),
        )
        for name, cap in sorted(report["capabilities"].items())
    )

    cover_rows = []
    for name, entry in sorted(report["coverage"].items()):
        parts = []
        for value, passes in sorted(entry["covered"].items()):
            parts.append(
                '<span class="ok">%s</span> <span class="kv">(%s)</span>'
                % (html.escape(str(value)), html.escape(", ".join(passes)))
            )
        for value, reason in sorted(entry["unreachable"].items()):
            parts.append(
                '<span class="skip">%s &mdash; unreachable: %s</span>'
                % (html.escape(str(value)), html.escape(reason))
            )
        for value, reason in sorted(entry["deferred"].items()):
            parts.append(
                '<span class="warn">%s &mdash; deferred: %s</span>'
                % (html.escape(str(value)), html.escape(reason))
            )
        for value in entry["missing"]:
            parts.append(
                '<span class="bad">%s &mdash; NOT COVERED</span>'
                % html.escape(str(value))
            )
        cover_rows.append(
            "<tr><td>%s</td><td>%s</td></tr>"
            % (html.escape(name), "<br>".join(parts) or "-")
        )

    body = """<main>
<h1>SWANe pre-release sweep &mdash; <span class="%s">%s</span></h1>
<p class="sub">%s &middot; %s &middot; Python %s</p>
<div class="tiles">%s</div>
<h2>Passes</h2>
%s
<h2>Host capabilities</h2>
<div class="wrap"><table><tr><th>capability</th><th>available</th><th>detail</th></tr>%s</table></div>
<h2>Axis coverage</h2>
<div class="wrap"><table><tr><th>axis</th><th>values</th></tr>%s</table></div>
</main>""" % (
        "ok" if ok else "bad",
        "PASSED" if ok else "ATTENTION NEEDED",
        html.escape(report["generated"]),
        html.escape(report["host"]["platform"]),
        html.escape(report["host"]["python"]),
        tile_html,
        "".join(_pass_section(p, work_dir) for p in report["passes"]),
        caps_rows,
        "".join(cover_rows),
    )

    page = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>SWANe pre-release sweep</title><style>%s</style>"
        "<script>%s</script></head>"
        "<body>%s</body></html>" % (_CSS, _COPY_JS, body)
    )
    path = os.path.join(work_dir, HTML_REPORT)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(page)
    return path


def print_summary(report: dict) -> None:
    summary = report["summary"]
    print("")
    print("=" * 66)
    print(
        "Pre-release sweep: %s"
        % ("PASSED" if overall_success(report) else "ATTENTION NEEDED")
    )
    print("-" * 66)
    print(
        "  passes: %d run, %d completed, %d failed, %d skipped"
        % (
            summary["executed"],
            summary["completed"],
            summary["failed"],
            summary["skipped"],
        )
    )
    print(
        "  checks: %d failed, %d warnings"
        % (summary["checks_failed"], summary["checks_warned"])
    )
    print("  time:   %s" % _fmt_time(summary["seconds"]))

    holes = {n: c["missing"] for n, c in report["coverage"].items() if c["missing"]}
    if holes and report.get("partial_run"):
        print(
            "  (%d axis value(s) not covered: the run was restricted with --only)"
            % sum(len(v) for v in holes.values())
        )
    elif holes:
        print("  PLAN HOLES (no pass covers these):")
        for name, values in sorted(holes.items()):
            print("    - %s: %s" % (name, ", ".join(map(str, values))))
    print("=" * 66)
