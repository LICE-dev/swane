"""Pre-fetch the antspynet brain-extraction weights the sweep will need.

``antspynet.brain_extraction`` downloads its pretrained network (and the
reorientation template they share) on first use, into ``~/.keras/ANTsXNet``.
Left to the workflows, that download happens inside a nipype worker: several
passes -- or several nodes of one pass -- can race for the same file, and a
node that is really waiting on a network transfer looks like a node that hangs.

Fetching them once, up front, in the parent process removes both problems.
``get_pretrained_network``/``get_antsxnet_data`` return immediately when the
file is already cached, so this is a no-op on a warm host and safe to call on
every run. It is *not* inference: no model is built or run here.

The fetch happens in a **short-lived child process**. Importing antspynet pulls
in TensorFlow, which stays resident for the life of the importing process
(~700 MB measured); the caller here is the sweep master, which then lives for
hours and forks a process per pass, so every pass would inherit that footprint.
On a memory-tight host that is enough to push antspyx/ITK nodes into swap or a
crash. The child exits as soon as the files are on disk, leaving the master at
its original size.
"""

from __future__ import annotations

import subprocess
import sys

from swane.config.config_enums import DeskullModality

#: antspynet modality key -> the pretrained network ``brain_extraction`` loads
#: for it (see ``antspynet/utilities/brain_extraction.py``). Only the keys
#: SWANe actually asks for are listed, so a modality the application stops
#: using also stops being downloaded.
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


def antspynet_weights(modalities=None) -> list:
    """Return the weight names needed for ``modalities`` (default: all of them).

    Parameters
    ----------
    modalities : iterable of DeskullModality, optional
        Defaults to every member of :class:`DeskullModality`. Members sharing a
        network (``BOLD`` and ``NODIF`` both map to ``bold``) are fetched once.
    """
    if modalities is None:
        modalities = list(DeskullModality)
    names = []
    for modality in modalities:
        weight = WEIGHTS_BY_MODALITY[modality.value]
        if weight not in names:
            names.append(weight)
    return names


def fetch_weights(names) -> None:
    """Fetch ``names`` plus the shared template. Runs in the child process."""
    from antspynet.utilities import get_antsxnet_data, get_pretrained_network

    for weight in names:
        get_pretrained_network(weight)
    get_antsxnet_data(TEMPLATE_NAME)


#: What the child runs. Kept as a one-liner so the child imports antspynet (and
#: therefore TensorFlow) and nothing else of SWANe's runtime.
_CHILD = (
    "from swane.tests.prerelease.antspynet_cache import fetch_weights;"
    "import sys; fetch_weights(sys.argv[1:])"
)


def preload_antspynet_models(modalities=None, verbose: bool = True) -> list:
    """Download the weights (and shared template) for ``modalities``.

    Returns the list of weight names requested. Raises
    :class:`subprocess.CalledProcessError` if the child cannot get them: a sweep
    that cannot fetch its weights must say so here rather than hours later
    inside a node.
    """
    names = antspynet_weights(modalities)
    if verbose:
        print(
            "Pre-caching %d antspynet network(s) + %s" % (len(names), TEMPLATE_NAME),
            flush=True,
        )
    subprocess.run([sys.executable, "-c", _CHILD, *names], check=True)
    return names
