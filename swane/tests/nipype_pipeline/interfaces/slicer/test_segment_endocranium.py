"""Unit tests for
:class:`swane.nipype_pipeline.interfaces.slicer.SegmentEndocranium.SegmentEndocranium`.

The real command drives 3D Slicer; only the FSL/Slicer-free output-name helper
is tested here (``out_file`` is a ``genfile`` with a fixed name).
"""

import os

from swane.nipype_pipeline.interfaces.slicer.SegmentEndocranium import (
    SegmentEndocranium,
)


class TestSegmentEndocraniumOutputName:
    def test_genfile_returns_fixed_mask_name(self):
        """The generated ``out_file`` name is the fixed inskull-mask filename."""
        node = SegmentEndocranium()
        out = node._gen_filename("out_file")
        assert os.path.basename(out) == "inskull_mask.nii.gz"
        assert os.path.isabs(out)

    def test_genfile_unknown_name_returns_none(self):
        """Only ``out_file`` is generated; other names return ``None``."""
        node = SegmentEndocranium()
        assert node._gen_filename("something_else") is None

    def test_list_outputs_uses_generated_name(self):
        """``_list_outputs`` reports the generated (genfile) mask path."""
        node = SegmentEndocranium()
        outputs = node._list_outputs()
        assert os.path.basename(outputs["out_file"]) == "inskull_mask.nii.gz"


class TestSegmentEndocraniumPathWithSpaces:
    def test_cmdline_quotes_slicer_and_worker_paths(self, tmp_path):
        """nipype runs ``_cmd`` through a shell: a Slicer path with a space (always
        the case on Windows) must stay one token."""
        import shlex

        slicer_dir = tmp_path / "Slicer 5.8.1"
        slicer_dir.mkdir()
        slicer = slicer_dir / "Slicer"
        slicer.write_text("#!/bin/sh\n")
        slicer.chmod(0o755)
        ct = tmp_path / "ct.nii.gz"
        ct.write_text("x")

        node = SegmentEndocranium(slicer_cmd=str(slicer), in_file=str(ct))
        if os.name == "nt":
            return  # POSIX quoting asserted below; Windows in the class below
        tokens = shlex.split(node.cmdline)
        assert tokens[0] == str(slicer)
        idx = tokens.index("--python-script")
        assert tokens[idx + 1].endswith("slicer_seg_endocranium.py")
        assert tokens[idx - 2 : idx] == ["--no-splash", "--no-main-window"]


def _fake_slicer(tmp_path):
    slicer_dir = tmp_path / "Slicer 5.8.1"
    slicer_dir.mkdir()
    slicer = slicer_dir / "Slicer"
    slicer.write_text("#!/bin/sh\n")
    slicer.chmod(0o755)
    ct = tmp_path / "ct.nii.gz"
    ct.write_text("x")
    return str(slicer), str(ct)


class TestSegmentEndocraniumQuotingPerPlatform:
    def test_posix_cmd_is_shlex_quoted(self, tmp_path, monkeypatch):
        """On Linux/macOS the command is unchanged: both paths ``shlex.quote``d."""
        import shlex

        from swane.patches import windows_compat

        monkeypatch.setattr(windows_compat, "is_windows", lambda: False)
        slicer, ct = _fake_slicer(tmp_path)
        node = SegmentEndocranium(slicer_cmd=slicer, in_file=ct)
        worker = node._cmd.rsplit(" ", 1)[1]
        assert node._cmd == (
            f"{shlex.quote(slicer)} --no-splash --no-main-window "
            f"--python-script {worker}"
        )
        assert shlex.split(worker)[0].endswith("slicer_seg_endocranium.py")

    def test_windows_cmdline_uses_double_quotes(self, tmp_path, monkeypatch):
        """On Windows every path is double-quoted (MSVCRT rules) with its
        backslashes kept, and the split nipype runs before ``which`` recovers
        the Slicer executable."""
        from nipype.interfaces.base import core as nipype_core

        import swane.patches.nipype_patches as npx
        from swane.patches import windows_compat

        monkeypatch.setattr(windows_compat, "is_windows", lambda: True)
        monkeypatch.setattr(nipype_core, "shlex", nipype_core.shlex)
        npx.install_windows_cmdline_quoting()
        slicer, ct = _fake_slicer(tmp_path)

        node = SegmentEndocranium(slicer_cmd=slicer, in_file=ct)
        cmdline = node.cmdline
        assert "'" not in cmdline
        assert cmdline.startswith(f'"{slicer}" --no-splash --no-main-window ')
        tokens = windows_compat.windows_split(cmdline)
        assert tokens[0] == slicer
        assert nipype_core.shlex.split(cmdline)[0] == slicer
        idx = tokens.index("--python-script")
        assert tokens[idx + 1].endswith("slicer_seg_endocranium.py")
        assert tokens[tokens.index("--input") + 1] == ct
