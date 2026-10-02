"""Pre-fetch the antspynet brain-extraction weights a workflow will need.

``antspynet.brain_extraction`` downloads its pretrained network (and the
reorientation template they share) on first use, into ``~/.keras/ANTsXNet``.
Left to the workflow, that download happens inside a Nipype worker, where:

* concurrent nodes can race for the same file;
* a node waiting on a network transfer looks like a node that hangs;
* on macOS, a ``fork``-ed worker can segfault in urllib's system proxy lookup
  (``_scproxy``), because Apple's frameworks are not fork-safe (see
  :mod:`swane.utils.mp_start_method`).

Fetching them once, before the workflow starts, removes all three.
``get_pretrained_network``/``get_antsxnet_data`` return immediately when the
file is already cached, so this is a no-op on a warm host and safe to call on
every run. It is *not* inference: no model is built or run here.

The fetch happens in a **short-lived child process** started with ``exec``.
Importing antspynet pulls in TensorFlow, which would stay resident (~700 MB
measured) in the long-lived caller, and every worker forked from it would
inherit that footprint. The child exits as soon as the files are on disk.
"""

import subprocess
import sys

#: antspynet modality key -> the pretrained network ``brain_extraction`` loads
#: for it (see ``antspynet/utilities/brain_extraction.py``). Only the keys
#: SWANe actually asks for (``DeskullModality`` values) are listed.
WEIGHTS_BY_MODALITY = {
    "t1": "brainExtractionRobustT1",
    "flair": "brainExtractionRobustFLAIR",
    "t2": "brainExtractionRobustT2",
    "bold": "brainExtractionRobustBOLD",
    # DeskullModality.VENOUS: a previous-version network, hence the plain name.
    "flair.v0": "brainExtractionFLAIR",
}

#: The reorientation template every one of those networks reads.
TEMPLATE_NAME = "S_template3"

#: What the child runs. Kept as a one-liner so the child imports antspynet (and
#: therefore TensorFlow) and nothing else of SWANe's runtime.
_CHILD = (
    "from swane.utils.antspynet_weights import fetch_weights;"
    "import sys; fetch_weights(sys.argv[1:])"
)


def weight_names(modality_keys) -> list:
    """Return the weight names needed for ``modality_keys``, without duplicates.

    Parameters
    ----------
    modality_keys : iterable of str
        antspynet modality keys (``DeskullModality`` values). Keys sharing a
        network are fetched once; keys not in :data:`WEIGHTS_BY_MODALITY` are
        ignored, so their node downloads its own weights as before.
    """
    names = []
    for key in modality_keys:
        weight = WEIGHTS_BY_MODALITY.get(key)
        if weight is not None and weight not in names:
            names.append(weight)
    return names


def weights_are_fetched(names) -> bool:
    """Return True if all weights (and the shared template) are already cached.

    This performs a fast filesystem check without importing ``antspynet`` or
    TensorFlow, making it safe and cheap to call from the main UI thread.
    """
    import os

    candidates = [
        os.path.expanduser(os.environ.get("KERAS_HOME") or "~/.keras"),
        "/tmp/.keras",
    ]
    cache_dirs = [os.path.join(c, "ANTsXNet") for c in candidates]
    existing_dirs = [d for d in cache_dirs if os.path.isdir(d)]

    if not existing_dirs:
        return False

    for weight in names:
        if not any(
            os.path.exists(os.path.join(d, weight + ".h5")) for d in existing_dirs
        ):
            return False

    if not any(
        os.path.exists(os.path.join(d, TEMPLATE_NAME + ".nii.gz"))
        for d in existing_dirs
    ):
        return False

    return True


def workflow_modalities(workflow) -> list:
    """Return the sorted antspynet modality keys used by ``workflow``'s nodes.

    Parameters
    ----------
    workflow : nipype.pipeline.engine.Workflow
        The workflow to inspect, nested sub-workflows included.
    """
    from nipype.interfaces.base import isdefined
    from swane.nipype_pipeline.interfaces.ants.AntsPyNetBrainExtraction import (
        AntsPyNetBrainExtraction,
    )

    keys = set()
    for node in workflow._get_all_nodes():
        if isinstance(node.interface, AntsPyNetBrainExtraction):
            modality = node.inputs.modality
            if isdefined(modality):
                keys.add(modality)
    return sorted(keys)


def fetch_weights(names) -> None:
    """Fetch ``names`` plus the shared template. Runs in the child process."""
    from antspynet.utilities import get_antsxnet_data, get_pretrained_network

    for weight in names:
        get_pretrained_network(weight)
    get_antsxnet_data(TEMPLATE_NAME)


def preload_weights(names) -> None:
    """Download ``names`` (and the shared template) in a child process.

    Raises
    ------
    subprocess.CalledProcessError
        If the child cannot get them. Its captured output is on the exception.
    """
    if weights_are_fetched(names):
        return

    import os

    env = os.environ.copy()
    if "PYTHONPATH" not in env:
        # If running from source, swane might be in the current working directory's parent
        # We append the current directory and its parent to ensure swane is found
        env["PYTHONPATH"] = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )

    subprocess.run(
        [sys.executable, "-c", _CHILD, *names],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
