"""Unit tests for :class:`swane.nipype_pipeline.nodes.FMRIGenSpec.FMRIGenSpec`.

The interface turns fMRI timing parameters into FSL FEAT model specifications
(event ``Bunch`` + T contrasts). It is pure Python, so it runs with no FSL.
"""

from swane.config.config_enums import BlockDesign
from swane.nipype_pipeline.nodes.FMRIGenSpec import FMRIGenSpec


def _run(block_design, TR=2.0, nvols=10, task=4, rest=6, **names):
    """Run the interface with the given design/timing and return its outputs."""
    node = FMRIGenSpec()
    node.inputs.TR = TR
    node.inputs.nvols = nvols
    node.inputs.task_duration = task
    node.inputs.rest_duration = rest
    node.inputs.block_design = block_design
    for key, value in names.items():
        setattr(node.inputs, key, value)
    return node.run().outputs


class TestBlockDesignDefaults:
    def test_default_block_design_is_rara(self):
        """The ``block_design`` enum trait defaults to the first member, ``RARA``."""
        assert FMRIGenSpec().inputs.block_design == BlockDesign.RARA

    def test_default_task_names_are_filled_in(self):
        """Missing task names default to ``TaskA``/``TaskB`` during the run."""
        outputs = _run(BlockDesign.RARB)
        assert outputs.task_a_name == "TaskA"
        assert outputs.task_b_name == "TaskB"


class TestRARADesign:
    """A single-task (rest/A/rest/A...) block design."""

    def test_single_contrast_against_rest(self):
        """RARA yields one 'task-vs-rest' T contrast for task A."""
        outputs = _run(BlockDesign.RARA)
        assert outputs.contrasts == [["TaskA_versus_Rest", "T", ["TaskA"], [1]]]

    def test_onsets_start_after_rest_and_step_by_task_plus_rest(self):
        """Onsets are ``range(rest, TR*nvols, task+rest)``.

        With TR=2, nvols=10 (=> 20 s), task=4, rest=6 the block starts at 6 s
        and repeats every 10 s: [6, 16].
        """
        outputs = _run(BlockDesign.RARA)
        assert outputs.evs_run.conditions == ["TaskA"]
        assert outputs.evs_run.onsets == [[6, 16]]
        assert outputs.evs_run.durations == [[4]]


class TestRARBDesign:
    """A two-task (rest/A/rest/B...) block design."""

    def test_two_reciprocal_contrasts(self):
        """RARB yields the A-vs-B and B-vs-A reciprocal T contrasts."""
        outputs = _run(BlockDesign.RARB)
        assert outputs.contrasts == [
            ["TaskA_versus_TaskB", "T", ["TaskA", "TaskB"], [1, -1]],
            ["TaskB_versus_TaskA", "T", ["TaskA", "TaskB"], [-1, 1]],
        ]

    def test_interleaved_onsets_for_both_tasks(self):
        """Task A and B onsets are interleaved half a cycle apart.

        Cycle = 2*task + 2*rest = 20 s. Task A starts at ``rest`` (6 s); task B
        starts at ``2*rest + task`` (16 s). Over 20 s that is [[6], [16]].
        """
        outputs = _run(BlockDesign.RARB)
        assert outputs.evs_run.conditions == ["TaskA", "TaskB"]
        assert outputs.evs_run.onsets == [[6], [16]]
        assert outputs.evs_run.durations == [[4], [4]]


class TestCustomTaskNames:
    def test_custom_task_names_flow_into_contrasts_and_outputs(self):
        """Explicit task names replace the defaults in contrasts and outputs."""
        outputs = _run(BlockDesign.RARB, task_a_name="Fingers", task_b_name="Toes")
        assert outputs.task_a_name == "Fingers"
        assert outputs.task_b_name == "Toes"
        assert outputs.contrasts[0][0] == "Fingers_versus_Toes"
        assert outputs.evs_run.conditions == ["Fingers", "Toes"]
