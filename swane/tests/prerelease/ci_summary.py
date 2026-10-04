"""Merge the per-pass results of a CI prerelease sweep into one summary.

Stdlib only, so the CI summary job needs no SWANe install. Each matrix job
uploads an artifact holding ``<pass>/pass_result.json`` (see
:class:`swane.tests.prerelease.runner.PassResult`); the plan job uploads
``dry-run.txt``. After ``actions/download-artifact`` the files sit in one folder
per artifact, so this script just walks the tree.

Usage::

    python swane/tests/prerelease/ci_summary.py ARTIFACTS_DIR \
        [--expected '["pass_a", "pass_b"]'] [--output summary.md]

Exit status is non-zero when any pass failed, or any expected pass left no
result at all.
"""

import argparse
import json
import os
import sys

PASS_RESULT_FILE = "pass_result.json"
DRY_RUN_FILE = "dry-run.txt"
_ERROR = "error"


def find_files(root: str, filename: str) -> list:
    found = []
    for dirpath, _dirs, files in os.walk(root):
        if filename in files:
            found.append(os.path.join(dirpath, filename))
    return sorted(found)


def load_results(root: str) -> list:
    results = []
    for path in find_files(root, PASS_RESULT_FILE):
        try:
            with open(path, encoding="utf-8") as handle:
                results.append(json.load(handle))
        except (OSError, ValueError):
            results.append(
                {
                    "name": os.path.basename(os.path.dirname(path)),
                    "status": "error",
                    "reason": "unreadable %s" % PASS_RESULT_FILE,
                }
            )
    return results


def failed_checks(result: dict) -> list:
    return [
        c
        for c in result.get("checks", [])
        if not c.get("passed", True) and c.get("severity", _ERROR) == _ERROR
    ]


def outcome(result: dict) -> str:
    """'ok', 'skipped' or 'FAILED' for one pass result."""
    status = result.get("status")
    if status == "skipped":
        return "skipped"
    if status != "completed" or result.get("node_errors") or failed_checks(result):
        return "FAILED"
    return "ok"


def coverage_section(dry_run_text: str) -> str:
    """Lines of the dry-run report after the pass list (unreachable values, coverage)."""
    lines = dry_run_text.splitlines()
    start = next(
        (i for i, line in enumerate(lines) if line.startswith("Planned passes")), None
    )
    if start is None:
        return ""
    i = start + 1
    while i < len(lines) and (lines[i].startswith(" ") or not lines[i].strip()):
        i += 1
    section = []
    for line in lines[i:]:
        if line.startswith("Dry run"):
            break
        section.append(line)
    return "\n".join(section).strip()


def build_summary(root: str, expected=None) -> tuple:
    """Return ``(markdown, ok)``."""
    results = load_results(root)
    by_name = {r.get("name", "?"): r for r in results}
    missing = sorted(set(expected or []) - set(by_name))

    rows = ["| Pass | Outcome | Detail |", "| --- | --- | --- |"]
    ok = not missing
    for name in sorted(by_name):
        result = by_name[name]
        verdict = outcome(result)
        if verdict == "FAILED":
            ok = False
        detail = result.get("reason", "")
        if result.get("node_errors"):
            detail = (detail + " %d node error(s)" % len(result["node_errors"])).strip()
        bad = failed_checks(result)
        if bad:
            detail = (
                detail + " failed checks: " + ", ".join(c.get("name", "?") for c in bad)
            ).strip()
        rows.append("| %s | %s | %s |" % (name, verdict, detail.replace("|", "/")))
    for name in missing:
        rows.append("| %s | FAILED | no %s uploaded |" % (name, PASS_RESULT_FILE))

    parts = ["## Prerelease sweep", ""]
    parts.append("Overall: **%s**" % ("success" if ok else "FAILURE"))
    parts.append("")
    parts.extend(rows)
    for path in find_files(root, DRY_RUN_FILE):
        with open(path, encoding="utf-8", errors="replace") as handle:
            section = coverage_section(handle.read())
        if section:
            parts.extend(["", "### Coverage", "", "```", section, "```"])
        break
    return "\n".join(parts) + "\n", ok


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("artifacts_dir")
    parser.add_argument("--expected", help="JSON list of pass names that must report")
    parser.add_argument("--output", help="also write the summary to this file")
    args = parser.parse_args(argv)

    expected = json.loads(args.expected) if args.expected else None
    markdown, ok = build_summary(args.artifacts_dir, expected)
    print(markdown)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(markdown)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
