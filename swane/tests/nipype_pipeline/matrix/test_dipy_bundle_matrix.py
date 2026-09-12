"""Settings matrix for
:func:`swane.nipype_pipeline.workflows.dipy_bundle_workflow.dipy_bundle_workflow`.

Sweeps the per-tract bundle recognition workflow's own axes: a plain bilateral
tract (``af``), the fornix special case (``fx``, which inserts the
:class:`DipyFornixSplit` before its two recognitions), and the dipy-only cingulum
(``cingulum`` -> ``C_L``/``C_R``). The recognise node is always a MapNode over the
shared builds/chunks (their runtime list length is chosen by the preproc chunker's
RAM estimator), so there is no construction-time chunk axis. One golden graph
snapshot is recorded per scenario under ``snapshots/dipy_bundle/``.

This workflow does **not** re-run the whole-brain SLR or the RecoBundles build
(both ran once, shared, in ``dipy_dti_preproc_workflow``); the snapshots are the
by-hand-reviewable proof that only recognise/union/to-ref nodes appear here.
"""

import pytest

from swane.tests.nipype_pipeline.matrix.conftest import import_workflow_or_skip

dipy_bundle_workflow = import_workflow_or_skip(
    "swane.nipype_pipeline.workflows.dipy_bundle_workflow",
    "dipy_bundle_workflow",
)

SUBDIR = "dipy_bundle"

# name -> (tract, num_threads)
SCENARIOS = {
    "af": ("af", 4),
    "fornix": ("fx", 4),
    "cingulum": ("cingulum", 4),
}


@pytest.mark.parametrize("scenario", list(SCENARIOS), ids=list(SCENARIOS))
def test_dipy_bundle_matrix(scenario, graph_snapshot):
    tract, num_threads = SCENARIOS[scenario]

    wf = dipy_bundle_workflow(
        tract,
        num_threads=num_threads,
    )

    config_echo = {
        "tract": tract,
        "num_threads": num_threads,
    }
    graph_snapshot(
        wf,
        subdir=SUBDIR,
        name=scenario,
        config=config_echo,
        title="dipy_bundle / %s" % scenario,
    )
