def hash_eddy_with_args(eddy, args, queue):
    """Hash a pickled/forked Eddy interface inside a child process."""
    eddy.inputs.args = args
    hashed_inputs, hash_value = eddy.inputs.get_hashval()
    queue.put(
        {
            "args_in_hash": "args" in dict(hashed_inputs),
            "hash_value": hash_value,
        }
    )
