"""Parsing of the converted file names that dcm2niix prints.

Nipype finds each name with ``re.search(r"\\S+/\\S+", line)`` on the
``Convert <n> DICOM as <path> (<dims>)`` lines. On Windows dcm2niix writes
``.\\name`` (and the path may contain blank spaces), which that pattern does
not match, so SWANe parses those lines with a separator- and space-tolerant
pattern there. Linux/macOS keep Nipype's parser unchanged.
"""

import os

import pytest
from nipype.interfaces.dcm2nii import Dcm2niix

from swane.nipype_pipeline.interfaces.dcm2nii.CustomDcm2niix import CustomDcm2niix
from swane.patches import windows_compat

HEADER = (
    "Chris Rorden's dcm2niiX version v1.0.20260724 (64-bit Windows)\n"
    "Found 131 DICOM file(s)\n"
    "Warning: Unable to determine manufacturer (0008,0070)\n"
)
FOOTER = "Conversion required 0.193972 seconds (0.071007 for core code).\n"


def _stdout(*names, dims="(124x151x131x1)", newline="\n"):
    lines = HEADER + "".join(
        "Convert 131 DICOM as %s %s\n" % (name, dims) for name in names
    )
    return (lines + FOOTER).replace("\n", newline)


@pytest.mark.parametrize(
    "name",
    [
        "./converted",
        ".\\converted",
        "C:\\Users\\Name Surname\\subj 01\\work dir\\converted",
        "/tmp/work dir/converted",
        ".\\converted_e2",
    ],
)
@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_windows_parses_backslash_and_spaced_paths(monkeypatch, name, newline):
    monkeypatch.setattr(windows_compat, "is_windows", lambda: True)
    parsed = CustomDcm2niix()._parse_stdout(_stdout(name, newline=newline))
    assert parsed == [os.path.abspath(name)]


def test_windows_keeps_every_converted_file_in_order(monkeypatch):
    monkeypatch.setattr(windows_compat, "is_windows", lambda: True)
    names = [".\\converted", ".\\converted_e2", ".\\converted_ph"]
    stdout = _stdout(*names[:2]) + _stdout(names[2], dims="(64x64x30x2x3)")
    parsed = CustomDcm2niix()._parse_stdout(stdout)
    assert parsed == [os.path.abspath(n) for n in names]


def test_windows_no_conversion_gives_no_files(monkeypatch):
    monkeypatch.setattr(windows_compat, "is_windows", lambda: True)
    assert CustomDcm2niix()._parse_stdout(HEADER + FOOTER) == []


def test_posix_uses_nipype_parser(monkeypatch):
    monkeypatch.setattr(windows_compat, "is_windows", lambda: False)
    stdout = _stdout("./converted", "./converted_e2")
    assert CustomDcm2niix()._parse_stdout(stdout) == Dcm2niix()._parse_stdout(stdout)
    assert CustomDcm2niix()._parse_stdout(stdout) == [
        os.path.abspath("./converted"),
        os.path.abspath("./converted_e2"),
    ]
