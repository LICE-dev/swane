"""ci_summary merges synthetic per-pass results (no real sweep involved)."""

import json

from swane.tests.prerelease import capabilities as caps_mod
from swane.tests.prerelease import checks as checks_mod
from swane.tests.prerelease import ci_summary
from swane.tests.prerelease import report as report_mod
from swane.tests.prerelease import runner

DRY_RUN = """Capabilities
  [yes] dcm2niix

Planned passes: 2 to run, 1 skipped
  - a   t13d
  - b   t13d
Values this host cannot exercise:
  - x=Y (needs z)
Coverage: every reachable axis value is exercised.

Dry run: nothing was executed.
"""


def _write(root, artifact, name, checks=(), **fields):
    """Produce one matrix-job artifact with the real writers: pass_result.json
    (before the checks, as run_passes does) and prerelease_report.json (after)."""
    folder = root / artifact
    subject_dir = folder / name
    subject_dir.mkdir(parents=True)
    fields.setdefault("status", "completed")
    result = runner.PassResult(name=name, subject_dir=str(subject_dir), **fields)
    runner._write_pass_result(result)
    result.checks = [
        checks_mod.CheckResult(c["name"], c["passed"], severity=c["severity"])
        for c in checks
    ]
    report = report_mod.build_report(
        [result], caps_mod.Capabilities(cores=4, ram_gb=14.0), {}, str(folder), {}
    )
    report_mod.write_json(report, str(folder))


def test_all_passes_ok(tmp_path):
    _write(tmp_path, "prerelease-a", "a")
    _write(tmp_path, "prerelease-b", "b")
    (tmp_path / "prerelease-plan").mkdir()
    (tmp_path / "prerelease-plan" / "dry-run.txt").write_text(DRY_RUN)

    markdown, ok = ci_summary.build_summary(str(tmp_path), ["a", "b"])
    assert ok
    assert "| a | ok |" in markdown and "| b | ok |" in markdown
    assert "Values this host cannot exercise" in markdown
    assert "Coverage: every reachable axis value" in markdown
    assert "t13d" not in markdown  # the pass list itself is not repeated


def test_failures_are_reported_and_fail(tmp_path):
    _write(tmp_path, "prerelease-a", "a", status="failed", reason="boom")
    _write(tmp_path, "prerelease-b", "b", node_errors=[{"node": "n"}])
    _write(
        tmp_path,
        "prerelease-c",
        "c",
        checks=[
            {"name": "c.shape", "passed": False, "severity": "error"},
            {"name": "c.soft", "passed": False, "severity": "warning"},
        ],
    )
    _write(
        tmp_path,
        "prerelease-d",
        "d",
        checks=[{"name": "d.soft", "passed": False, "severity": "warning"}],
    )

    markdown, ok = ci_summary.build_summary(str(tmp_path))
    assert not ok
    assert "| a | FAILED | boom |" in markdown
    assert "| b | FAILED |" in markdown
    assert "c.shape" in markdown and "c.soft" not in markdown
    assert "| d | ok |" in markdown


def test_pass_result_file_has_no_checks_so_report_is_needed(tmp_path):
    """Guards the producer shape: pass_result.json never carries the checks."""
    _write(
        tmp_path,
        "prerelease-a",
        "a",
        checks=[{"name": "a.x", "passed": False, "severity": "error"}],
    )
    data = json.loads(
        (tmp_path / "prerelease-a" / "a" / "pass_result.json").read_text()
    )
    assert data["checks"] == []
    markdown, ok = ci_summary.build_summary(str(tmp_path), ["a"])
    assert not ok and "a.x" in markdown


def test_expected_pass_without_result_fails(tmp_path):
    _write(tmp_path, "prerelease-a", "a")
    markdown, ok = ci_summary.build_summary(str(tmp_path), ["a", "ghost"])
    assert not ok
    assert "| ghost | FAILED |" in markdown


def test_empty_plan_is_success(tmp_path):
    markdown, ok = ci_summary.build_summary(str(tmp_path), [])
    assert ok


def test_main_exit_code_and_output_file(tmp_path):
    _write(tmp_path, "prerelease-a", "a", status="error")
    out = tmp_path / "summary.md"
    assert ci_summary.main([str(tmp_path), "--output", str(out)]) == 1
    assert "FAILURE" in out.read_text()
