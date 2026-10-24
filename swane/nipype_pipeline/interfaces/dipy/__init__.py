# -*- coding: utf-8 -*-
import os
from contextlib import contextmanager

TRX_TMPDIR_VAR = "TRX_TMPDIR"
# trx-python's value for "the current working directory" (trx.io.get_trx_tmp_dir).
TRX_USE_WORKING_DIR = "use_working_dir"


@contextmanager
def trx_tmpdir_in_working_dir():
    """Make trx-python create its temporary memmaps in the current directory.

    trx puts the memmaps of every streamed, resized, copied or converted
    tractogram in ``$TRX_TMPDIR``, or ``tempfile.gettempdir()`` when unset. On a
    host whose ``/tmp`` is a tmpfs that holds a whole tractogram in RAM outside
    the node reservations (and a killed node leaves it there). Inside a nipype
    node the current directory is the node's own directory, so the memmaps sit
    on the subject disk next to the output and a re-run of the node clears what
    a killed run left. The variable is forced, whatever the caller set, and its
    previous value (or absence) is restored on exit.
    """
    previous = os.environ.get(TRX_TMPDIR_VAR)
    os.environ[TRX_TMPDIR_VAR] = TRX_USE_WORKING_DIR
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(TRX_TMPDIR_VAR, None)
        else:
            os.environ[TRX_TMPDIR_VAR] = previous


class TrxWorkingDirMixin:
    """Run the interface with :func:`trx_tmpdir_in_working_dir`.

    For every interface that reads or writes ``.trx``. List it before
    ``BaseInterface`` in the bases: it wraps ``run``, which nipype calls with the
    node directory as ``cwd`` and which changes into it before
    ``_run_interface``, the point where trx resolves the working directory.
    """

    def run(self, *args, **kwargs):
        with trx_tmpdir_in_working_dir():
            return super().run(*args, **kwargs)
