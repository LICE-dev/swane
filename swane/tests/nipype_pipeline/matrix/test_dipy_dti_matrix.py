"""Settings matrix for
:func:`swane.nipype_pipeline.workflows.dipy_dti_preproc_workflow.dipy_dti_preproc_workflow`.

Sweeps the dipy/RecoBundles engine's own axes: whether the CSD + RecoBundles
tractography tail is built at all (``tractography`` on/off), and the per-node
**thread count** the parallel dipy nodes declare to nipype as ``n_procs``
(``max_cpu``) -- the factory's own HARD_CAP-only core budget (spec section
10). Unlike ``dti_preproc_workflow``, these new dipy nodes take no
``multicore_node_limit``/``CoreLimit`` parameter at all, so there is no
SOFT_CAP/HARD_CAP mode axis to sweep here -- only the raw thread count. One
golden graph snapshot is recorded per scenario under
``snapshots/dipy_dti_preproc/``.

This workflow is selected by the ``TractographyEngine.DIPY_RECOBUNDLES``
SYNTH preference (see ``MainWorkflow``); that setting is echoed into every
scenario's config header for documentation even though the factory itself
never reads it -- only ``MainWorkflow`` consults it to choose between the
FSL/XTRACT and dipy/RecoBundles builders.

The diffusion<->reference registration is always ANTs (never FSL) by design,
so no registration-engine axis is swept here -- see
``test_dipy_dti_wiring.py`` for the graph-shape assertions covering that
invariant and the full node wiring.
"""

import pytest

from swane.config.config_enums import (
    DeskullEngine,
    GlobalPrefCategoryList,
    TractographyEngine,
)
from swane.utils.DataInputList import DataInputList
from swane.tests.nipype_pipeline.matrix.conftest import import_workflow_or_skip

dipy_dti_preproc_workflow = import_workflow_or_skip(
    "swane.nipype_pipeline.workflows.dipy_dti_preproc_workflow",
    "dipy_dti_preproc_workflow",
)

SUBDIR = "dipy_dti_preproc"

# name -> (tractography, max_cpu)
SCENARIOS = {
    "no_tractography": (False, 4),
    "tractography": (True, 4),
    "tractography_single_thread": (True, 1),
}


def _bool(value):
    return "true" if value else "false"


@pytest.mark.parametrize("scenario", list(SCENARIOS), ids=list(SCENARIOS))
def test_dipy_dti_matrix(
    scenario, subject_config, global_config, make_input_dir, graph_snapshot
):
    tractography, max_cpu = SCENARIOS[scenario]
    section = subject_config[DataInputList.DTI]
    section["tractography"] = _bool(tractography)
    synth = global_config[GlobalPrefCategoryList.SYNTH]
    synth["tractography_engine"] = TractographyEngine.DIPY_RECOBUNDLES.name
    # The dipy pipeline never touches FSL; a non-FSL deskull engine keeps the
    # shared head FSL-free (registration is forced to ANTs by the factory
    # regardless of the SYNTH engine, so no engine axis is swept here).
    synth["deskull_engine"] = DeskullEngine.ANTSPYNET.name

    wf = dipy_dti_preproc_workflow(
        "dti",
        dti_dir=make_input_dir(),
        config=section,
        synth_config=synth,
        max_cpu=max_cpu,
    )

    config_echo = {
        "tractography": section["tractography"],
        "tractography_engine": synth["tractography_engine"],
        "max_cpu": max_cpu,
        "deskull_engine": synth["deskull_engine"],
    }
    graph_snapshot(
        wf,
        subdir=SUBDIR,
        name=scenario,
        config=config_echo,
        title="dipy_dti_preproc / %s" % scenario,
    )
