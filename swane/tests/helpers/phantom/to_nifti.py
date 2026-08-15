"""Convert a generated phantom subject to NIfTI, for visual inspection.

Runs the same ``dcm2niix`` binary SWANe uses, over every series folder of a
phantom subject, so the result is exactly what the workflows will see.  Handy
both as a developer aid (open the volumes in FSLeyes/freeview/Slicer) and as a
smoke test that every series converts cleanly.

Usage::

    python -m swane.tests.helpers.phantom.to_nifti <subject_dir> [out_dir]
"""

from __future__ import annotations

import os
import subprocess
import sys


def convert_series(series_dir: str, out_dir: str, name: str) -> dict:
    """Convert one series folder; returns a small report dict."""
    import dcm2niix

    os.makedirs(out_dir, exist_ok=True)
    result = subprocess.run(
        [dcm2niix.bin, "-b", "y", "-z", "y", "-f", name, "-o", out_dir, series_dir],
        capture_output=True,
        text=True,
    )
    produced = sorted(
        f
        for f in os.listdir(out_dir)
        if f.startswith(name + ".") or f == name + ".nii.gz"
    )
    warnings = [
        line.strip()
        for line in result.stdout.splitlines()
        if "Warning" in line or "Error" in line
    ]
    return {
        "name": name,
        "returncode": result.returncode,
        "files": produced,
        # the manufacturer notice is expected: dcm2niix only knows real vendors
        "warnings": sorted({w for w in warnings if "manufacturer" not in w}),
    }


def convert_subject(subject_dir: str, out_dir: str) -> list:
    """Convert every series of a phantom subject into ``out_dir``."""
    dicom_root = os.path.join(subject_dir, "dicom")
    reports = []
    for name in sorted(os.listdir(dicom_root)):
        series_dir = os.path.join(dicom_root, name)
        if not os.path.isdir(series_dir):
            continue
        report = convert_series(series_dir, out_dir, name)
        reports.append(report)
        status = "ok " if report["returncode"] == 0 and report["files"] else "FAIL"
        print("%s %-22s -> %s" % (status, name, ", ".join(report["files"])), flush=True)
        for warning in report["warnings"]:
            print("        %s" % warning, flush=True)
    return reports


if __name__ == "__main__":  # pragma: no cover - developer aid
    subject = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(subject, "nifti")
    reports = convert_subject(subject, out)
    failed = [r["name"] for r in reports if r["returncode"] != 0 or not r["files"]]
    print(
        "\n%d/%d series converted; output in %s"
        % (len(reports) - len(failed), len(reports), out)
    )
    if failed:
        print("failed: %s" % ", ".join(failed))
        sys.exit(1)
