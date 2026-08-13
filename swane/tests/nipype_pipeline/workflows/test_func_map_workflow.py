"""Construction tests for
:func:`swane.nipype_pipeline.workflows.func_map_workflow.func_map_workflow`.

This is the ASL/PET functional-map builder. Optional stages are gated by the
FreeSurfer step (surface projection, cortical z-score) and by the ``ai``
preference (asymmetry-index chain). The graph is assembled with no FSL/
FreeSurfer execution and no DICOM data (the input directory is an empty folder).
"""

import pytest

from swane.config.config_enums import GlobalPrefCategoryList, FreesurferStep
from swane.utils.DataInputList import DataInputList
from swane.nipype_pipeline.workflows.func_map_workflow import func_map_workflow

WF_NAME = "asl"


def _node_names(workflow):
    """Return the set of node names in a (non-nested) workflow graph."""
    return {node.name for node in workflow._graph.nodes()}


def _build(subject_config, global_config, dicom_dir, freesurfer_step, ai):
    """Assemble the func-map workflow for the given FreeSurfer step / AI flag."""
    subject_config[DataInputList.ASL]["ai"] = "true" if ai else "false"
    return func_map_workflow(
        WF_NAME,
        dicom_dir=dicom_dir,
        freesurfer_step=freesurfer_step,
        config=subject_config[DataInputList.ASL],
        synth_config=global_config[GlobalPrefCategoryList.SYNTH],
    )


class TestBasePipeline:
    def test_core_nodes_always_present(
        self, subject_config, global_config, make_input_dir
    ):
        """Conversion, smoothing, registration and masking always exist."""
        wf = _build(
            subject_config,
            global_config,
            make_input_dir(),
            FreesurferStep.DISABLED,
            ai=False,
        )
        names = _node_names(wf)
        for expected in (
            "inputnode",
            "outputnode",
            "asl_conv",
            "asl_reOrient",
            "asl_smooth",
            "asl_2_ref_flirt",
            "asl_smooth_2_ref_flirt_apply_xfm",
            "asl_mask",
        ):
            assert expected in names

    def test_no_optional_nodes_when_freesurfer_disabled_and_ai_off(
        self, subject_config, global_config, make_input_dir
    ):
        """With FreeSurfer disabled and AI off, no surface/z-score/AI nodes appear."""
        wf = _build(
            subject_config,
            global_config,
            make_input_dir(),
            FreesurferStep.DISABLED,
            ai=False,
        )
        names = _node_names(wf)
        for absent in (
            "asl_surf_lh",
            "asl_zscore",
            "asl_zscore_surf_lh",
            "asl_ai",
        ):
            assert absent not in names


class TestFreesurferGating:
    def test_parcellation_only_adds_zscore_but_no_surface(
        self, subject_config, global_config, make_input_dir
    ):
        """SYNTHSEG has parcellation but no surface: z-score yes, projections no."""
        wf = _build(
            subject_config,
            global_config,
            make_input_dir(),
            FreesurferStep.SYNTHSEG,
            ai=False,
        )
        names = _node_names(wf)
        assert "asl_zscore" in names
        assert "asl_surf_lh" not in names
        assert "asl_zscore_surf_lh" not in names

    def test_full_reconall_adds_surface_projections(
        self, subject_config, global_config, make_input_dir
    ):
        """RECONALL provides surfaces: map and z-score are projected per hemisphere."""
        wf = _build(
            subject_config,
            global_config,
            make_input_dir(),
            FreesurferStep.RECONALL,
            ai=False,
        )
        names = _node_names(wf)
        for expected in (
            "asl_surf_lh",
            "asl_surf_rh",
            "asl_zscore",
            "asl_zscore_surf_lh",
            "asl_zscore_surf_rh",
        ):
            assert expected in names


class TestAsymmetryIndex:
    def test_ai_chain_added_when_enabled(
        self, subject_config, global_config, make_input_dir
    ):
        """Enabling AI adds the symmetric-atlas warp, swap and AI map nodes."""
        wf = _build(
            subject_config,
            global_config,
            make_input_dir(),
            FreesurferStep.DISABLED,
            ai=True,
        )
        names = _node_names(wf)
        for expected in (
            "asl_2_sym_warp_apply_warp",
            "asl_sym_swap",
            "asl_ai",
            "asl_ai_threshold",
            "asl_ai_2_ref_apply_warp",
            "asl_ai_mask",
        ):
            assert expected in names

    def test_ai_surface_projection_requires_surface(
        self, subject_config, global_config, make_input_dir
    ):
        """AI surface projection appears only when FreeSurfer provides surfaces."""
        without_surface = _build(
            subject_config,
            global_config,
            make_input_dir("d1"),
            FreesurferStep.DISABLED,
            ai=True,
        )
        assert "asl_ai_surf_lh" not in _node_names(without_surface)

        with_surface = _build(
            subject_config,
            global_config,
            make_input_dir("d2"),
            FreesurferStep.RECONALL,
            ai=True,
        )
        assert "asl_ai_surf_lh" in _node_names(with_surface)

    def test_ai_chain_absent_when_disabled(
        self, subject_config, global_config, make_input_dir
    ):
        """With AI off the asymmetry-index nodes are not created."""
        wf = _build(
            subject_config,
            global_config,
            make_input_dir(),
            FreesurferStep.RECONALL,
            ai=False,
        )
        assert "asl_ai" not in _node_names(wf)
