"""Pre-fetch the antspynet brain-extraction weights the sweep will need.

The application already pre-fetches, per workflow, the weights its nodes use
(:mod:`swane.utils.antspynet_weights`, called by ``WorkflowProcess``). The
sweep additionally fetches *every* network once, up front, so that a missing
network connection fails the sweep here rather than hours later inside a pass,
and so that no pass pays for a download.

The fetch runs in a short-lived child process: importing antspynet in the sweep
master would leave TensorFlow resident (~700 MB measured) for the whole sweep.
"""

from __future__ import annotations

from swane.config.config_enums import DeskullModality
from swane.utils.antspynet_weights import (  # noqa: F401 - re-exported
    TEMPLATE_NAME,
    WEIGHTS_BY_MODALITY,
    fetch_weights,
    preload_weights,
    weight_names,
)


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
    return weight_names(modality.value for modality in modalities)


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
    preload_weights(names)
    return names
