import multiprocessing as mp

import pytest

from swane.nipype_pipeline.nodes.CustomEddy import CustomEddy
from swane.tests.nipype_pipeline.nodes.custom_eddy_multiprocessing import (
    hash_eddy_with_args,
)


def test_thread_argument_does_not_change_hash():
    eddy = CustomEddy()
    eddy.inputs.args = "--nthr=2"
    hashed_inputs, two_thread_hash = eddy.inputs.get_hashval()

    assert eddy.inputs.has_metadata("args", "nohash", True)
    assert "args" not in dict(hashed_inputs)

    eddy.inputs.args = "--nthr=8"
    _, eight_thread_hash = eddy.inputs.get_hashval()

    assert eight_thread_hash == two_thread_hash


@pytest.mark.parametrize(
    "start_method",
    [
        method
        for method in ("fork", "spawn")
        if method in mp.get_all_start_methods()
    ],
)
def test_thread_argument_stays_nohash_in_child_process(start_method):
    eddy = CustomEddy()
    eddy.inputs.args = "--nthr=2"
    _, parent_hash = eddy.inputs.get_hashval()

    context = mp.get_context(start_method)
    queue = context.Queue()
    process = context.Process(
        target=hash_eddy_with_args,
        args=(eddy, "--nthr=8", queue),
    )
    try:
        process.start()
        process.join(30)

        assert process.exitcode == 0
        child_result = queue.get(timeout=5)
        assert not child_result["args_in_hash"]
        assert child_result["hash_value"] == parent_hash
    finally:
        if process.is_alive():
            process.terminate()
            process.join(5)
        queue.close()
        queue.join_thread()
