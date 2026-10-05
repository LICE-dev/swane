"""The high-pass ``op_string`` embeds the mean image path in a niimath command.

Nipype only quotes path *inputs*; a path written inside a string input reaches
the shell as is. On Windows, where SWANe allows blank spaces in the subject
path, the workflows therefore wire a variant that quotes that path for cmd.exe.
Linux/macOS keep the original builder, so their graphs (and the matrix
snapshots, which record the function source) are unchanged.
"""

from inspect import getsource

from nipype.pipeline.engine.utils import evaluate_connect_function

from swane.nipype_pipeline.workflows import fMRI_preproc_workflow as preproc
from swane.patches import windows_compat

MEAN = r"C:\Users\Name Surname\subj 01\fMRI\mean_func.nii.gz"


def _evaluate(function, merged, cutoff):
    # Exactly how Nipype runs a connection function: from its source text.
    return evaluate_connect_function(getsource(function), (cutoff,), merged)


def test_posix_uses_the_original_builder(monkeypatch):
    monkeypatch.setattr(windows_compat, "is_windows", lambda: False)
    assert preproc.highpass_op_string_function() is preproc.highpass_op_string
    assert (
        _evaluate(preproc.highpass_op_string, [2.0, "/data/mean.nii.gz"], 60)
        == "-bptf 15.000000 -1 -add /data/mean.nii.gz"
    )


def test_windows_quotes_the_mean_image_path(monkeypatch):
    monkeypatch.setattr(windows_compat, "is_windows", lambda: True)
    function = preproc.highpass_op_string_function()
    assert function is preproc.windows_highpass_op_string

    op_string = _evaluate(function, [2.0, MEAN], 60)
    assert op_string == '-bptf 15.000000 -1 -add "%s"' % MEAN
    assert windows_compat.windows_split(op_string) == [
        "-bptf",
        "15.000000",
        "-1",
        "-add",
        MEAN,
    ]
