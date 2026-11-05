"""Unit tests for :mod:`swane.utils.print_error`."""

import swane.utils.print_error as pe


def test_print_error_appends_exception_to_log(tmp_path, monkeypatch):
    log_file = tmp_path / "err.log"
    monkeypatch.setattr(pe, "ERROR_FILE", str(log_file))

    try:
        raise ValueError("boom")
    except ValueError:
        pe.print_error()

    content = log_file.read_text()
    assert "ValueError" in content
    assert "test_print_error_appends_exception_to_log" in content
