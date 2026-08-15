"""Render PNG contact sheets of a generated phantom, for visual inspection.

Purely a developer aid: the automated tests never call this.  It converts each
DICOM series back to a volume and lays out orthogonal slices, so a human can
confirm at a glance that contrast, coverage, bias field and the CST/activation
overlays look right.

Usage::

    python -m swane.tests.helpers.phantom.preview <subject_dir> <out_dir>
"""

from __future__ import annotations

import os
import sys

import numpy as np


def _read_series(series_dir: str):
    """Load a DICOM series folder into ``(volume, spacing)``.

    Slices are ordered by ``InstanceNumber``; for 4D series only the first
    volume is previewed.
    """
    import pydicom

    files = sorted(
        os.path.join(series_dir, f)
        for f in os.listdir(series_dir)
        if f.endswith(".dcm")
    )
    if not files:
        raise RuntimeError("no DICOM in %s" % series_dir)

    datasets = [pydicom.dcmread(f) for f in files]
    datasets.sort(key=lambda d: int(getattr(d, "InstanceNumber", 0)))

    n_temporal = int(getattr(datasets[0], "NumberOfTemporalPositions", 1) or 1)
    n_slices = len(datasets) // max(n_temporal, 1)
    datasets = datasets[:n_slices]  # first volume only

    slope = float(getattr(datasets[0], "RescaleSlope", 1.0))
    intercept = float(getattr(datasets[0], "RescaleIntercept", 0.0))
    vol = np.stack([d.pixel_array.astype(np.float32) for d in datasets], axis=-1)
    vol = vol * slope + intercept

    row_sp, col_sp = [float(v) for v in datasets[0].PixelSpacing]
    thickness = float(getattr(datasets[0], "SliceThickness", 1.0))
    return vol, (row_sp, col_sp, thickness)


def _normalise(img: np.ndarray) -> np.ndarray:
    lo, hi = np.percentile(img, [1.0, 99.0])
    if hi <= lo:
        lo, hi = float(img.min()), float(img.max()) or 1.0
    return np.clip((img - lo) / (hi - lo), 0.0, 1.0)


def contact_sheet(series_dir: str, out_png: str, title: str = ""):
    """Write a 3-plane contact sheet for one series."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    vol, spacing = _read_series(series_dir)
    # vol is (rows, cols, slices)
    n_rows, n_cols, n_sl = vol.shape

    planes = [
        ("through-plane", vol[:, :, n_sl // 2]),
        ("rows", vol[n_rows // 2, :, :].T),
        ("cols", vol[:, n_cols // 2, :].T),
    ]

    fig, axes = plt.subplots(1, 3, figsize=(12, 4.5))
    for ax, (name, img) in zip(axes, planes):
        ax.imshow(_normalise(img), cmap="gray", origin="lower", aspect="auto")
        ax.set_title(name, fontsize=9)
        ax.axis("off")
    fig.suptitle(
        "%s   %s  vox=%.2fx%.2fx%.2f mm" % (title, vol.shape, *spacing), fontsize=11
    )
    fig.tight_layout()
    os.makedirs(os.path.dirname(os.path.abspath(out_png)), exist_ok=True)
    fig.savefig(out_png, dpi=90, facecolor="white")
    plt.close(fig)
    return out_png


def preview_subject(subject_dir: str, out_dir: str):
    """Write one contact sheet per series plus an index of what was found."""
    dicom_root = os.path.join(subject_dir, "dicom")
    written = []
    for name in sorted(os.listdir(dicom_root)):
        series_dir = os.path.join(dicom_root, name)
        if not os.path.isdir(series_dir):
            continue
        out_png = os.path.join(out_dir, "%s.png" % name)
        try:
            contact_sheet(series_dir, out_png, title=name)
            written.append(out_png)
            print("ok   %s" % name, flush=True)
        except Exception as exc:  # pragma: no cover - developer aid
            print("FAIL %s: %s" % (name, exc), flush=True)
    return written


if __name__ == "__main__":  # pragma: no cover
    subject = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(subject, "preview")
    preview_subject(subject, out)
    print("preview written to %s" % out)
