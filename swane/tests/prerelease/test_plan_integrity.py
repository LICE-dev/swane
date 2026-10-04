"""Guards for the sweep plan itself — fast, no workflow is executed.

The pre-release sweep takes hours, so its plan must be known-good *before*
anyone starts it. These tests run in the ordinary light suite and fail the
moment the plan stops being coherent: a pass referring to an axis that no
longer exists, a value that is not one of the axis's own, or — the important
one — an axis value that no pass exercises, which would silently shrink
coverage the next time someone adds a setting to SWANe.
"""

import pytest

from swane.tests.prerelease.capabilities import BLOCKING, Capabilities
from swane.tests.prerelease.plan import (
    AXES,
    AXES_BY_NAME,
    PASSES,
    SHAPE,
    _PASS_REQUIREMENTS,
    build_plan,
    coverage,
    gate_capabilities,
    plan_holes,
)


def _all_capable_caps() -> Capabilities:
    """A host where everything is available, to judge the plan on its own merits."""
    caps = Capabilities(cores=8, ram_gb=64.0)
    needed = gate_capabilities()
    needed.update({"fsl", "freesurfer", "slicer", "tractography"} | set(BLOCKING))
    # Capabilities that gate whole passes (not tied to an axis value), e.g.
    # reconall_expert, so a fully capable host really skips nothing.
    needed.update(
        cap for caps_tuple in _PASS_REQUIREMENTS.values() for cap in caps_tuple
    )
    for name in needed:
        caps.add(name, True, "assumed available in this test")
    return caps


@pytest.fixture
def all_capable():
    return _all_capable_caps()


def test_pass_names_are_unique():
    names = [spec.name for spec in PASSES]
    assert len(names) == len(set(names)), "duplicate pass name in PASSES"


def test_passes_reference_known_axes():
    for spec in PASSES:
        for axis_name in spec.values:
            assert axis_name in AXES_BY_NAME, "%s sets unknown axis %r" % (
                spec.name,
                axis_name,
            )


def test_pass_values_belong_to_their_axis():
    for spec in PASSES:
        for axis_name, value in spec.values.items():
            axis = AXES_BY_NAME[axis_name]
            assert value in axis.values, "%s sets %s=%r, not one of %s" % (
                spec.name,
                axis_name,
                value,
                axis.values,
            )


def test_every_pass_loads_the_reference():
    """T13D is the reference every other workflow registers to."""
    from swane.utils.DataInputList import DataInputList

    for spec in PASSES:
        assert DataInputList.T13D in spec.inputs, (
            "%s does not load the T13D reference" % spec.name
        )


def test_axes_that_need_an_input_declare_it():
    """A preference axis is only meaningful if its input is loaded."""
    for axis in AXES:
        if axis.scope == SHAPE:
            continue
        if axis.section is None:
            continue
        # Global preferences legitimately have no input; per-input ones should
        # say which input they belong to so coverage is not over-claimed.
        from swane.utils.DataInputList import DataInputList

        if isinstance(axis.section, DataInputList) and axis.needs_input is None:
            # T13D-scoped axes affect the whole run, so they are exempt.
            assert (
                axis.section is DataInputList.T13D
            ), "axis %s is scoped to %s but declares no needs_input" % (
                axis.name,
                axis.section,
            )


def test_plan_covers_every_axis_value(all_capable):
    """The whole point: no axis value may go unexercised on a capable host."""
    plan = build_plan(all_capable, with_reconall=True)
    holes = plan_holes(coverage(plan, all_capable))
    assert not holes, (
        "no pass exercises these axis values: %s\n"
        "Add them to an existing pass in plan.py, or add a new pass." % holes
    )


def test_nothing_is_skipped_on_a_capable_host(all_capable):
    """Only the FSL-free stand-ins are skipped, each because its FSL original
    runs: on a capable host the sweep is the FSL plan, plus nothing."""
    plan = build_plan(all_capable, with_reconall=True)
    running = {p.name for p in plan if not p.skipped}
    skipped = {p.name: p.skip_reason for p in plan if p.skipped}
    stand_ins = {spec.name: spec.stands_in_for for spec in PASSES if spec.stands_in_for}
    assert stand_ins, "expected FSL-free stand-in passes in the plan"
    assert set(skipped) == set(stand_ins), (
        "passes skipped on a fully capable host: %s" % skipped
    )
    for name, original in stand_ins.items():
        assert original in running, (name, original)


def test_missing_capability_downgrades_instead_of_failing():
    """An unavailable option must be reported, never silently claimed."""
    caps = Capabilities(cores=4, ram_gb=8.0)
    needed = gate_capabilities()
    for name in needed:
        caps.add(name, True, "available")
    caps.add("synth_morph", False, "needs 14.0 GB, only 8.0 GB allocated")
    # FSL stays available here: this test is about losing SynthMorph alone.
    for name in BLOCKING + ("fsl", "slicer"):
        caps.add(name, True, "available")

    plan = build_plan(caps, with_reconall=True)
    cover = coverage(plan, caps)

    assert (
        "SYNTH" in cover["registration_engine"].unreachable
    ), "an unavailable SynthMorph engine must be reported as unreachable"
    assert (
        "SYNTH" not in cover["registration_engine"].covered
    ), "an unavailable option must never be counted as covered"
    # Everything that does not depend on SynthMorph must still be covered
    # (FSL and ANTS engine values included).
    assert not plan_holes(cover), (
        "losing one capability must not take unrelated axes down with it: %s"
        % plan_holes(cover)
    )


def test_registration_engine_axis_has_the_three_backends():
    """Group A replaced the dead ``morph`` key with the engine ENUM; the sweep
    must drive that ENUM, with one value per registration backend."""
    axis = AXES_BY_NAME["registration_engine"]
    assert axis.option == "engine"
    assert set(axis.values) == {"FSL", "SYNTH", "ANTS"}
    # Each backend is gated on its own dependency (FSL is optional, see
    # test_fsl_free_plan.py).
    assert axis.gate_for("FSL") == "fsl"
    assert axis.gate_for("SYNTH") == "synth_morph"
    assert axis.gate_for("ANTS") == "antspyx"


def test_every_registration_backend_is_covered_by_a_named_pass(all_capable):
    """FSL, SYNTH and ANTS must each be forced by at least one named pass, so
    no backend rides only on the (implicit) default."""
    plan = build_plan(all_capable, with_reconall=True)
    cover = coverage(plan, all_capable)
    covered = cover["registration_engine"].covered
    for backend in ("FSL", "SYNTH", "ANTS"):
        assert covered.get(
            backend
        ), "no named pass forces registration_engine=%s: %s" % (backend, covered)


def test_structural_ants_pass_forces_the_ants_backend():
    """A named ANTS pass makes the default backend explicit and reviewable."""
    by_name = {spec.name: spec for spec in PASSES}
    assert "structural_ants" in by_name, "missing the named ANTS structural pass"
    assert by_name["structural_ants"].values["registration_engine"] == "ANTS"


# --------------------------------------------------------------------------- #
# No two running passes may be the same execution
# --------------------------------------------------------------------------- #
def _duplicate_passes(plan) -> list:
    """Pairs of non-skipped passes that resolve to the same (inputs, values)."""
    seen = {}
    duplicates = []
    for item in plan:
        if item.skipped:
            continue
        key = (tuple(item.inputs), tuple(sorted(item.values.items())))
        if key in seen:
            duplicates.append((seen[key], item.name))
        else:
            seen[key] = item.name
    return duplicates


def _fsl_without_xtract(caps):
    caps.add("xtract", False, "no XTRACT protocol data in this test")
    return caps


@pytest.mark.parametrize("host", ["all_capable", "no_fsl", "fsl_without_xtract"])
def test_no_two_running_passes_are_identical(host, all_capable):
    from swane.tests.prerelease.test_fsl_free_plan import _no_fsl_caps

    caps = {
        "all_capable": lambda: all_capable,
        "no_fsl": _no_fsl_caps,
        "fsl_without_xtract": lambda: _fsl_without_xtract(all_capable),
    }[host]()
    plan = build_plan(caps, with_reconall=True)
    duplicates = _duplicate_passes(plan)
    assert (
        not duplicates
    ), "passes resolving to the same inputs and values on %s: %s" % (host, duplicates)


def test_dti_classic_runs_the_fsl_diffusion_chain():
    """old_eddy_correct is read only by the FSL diffusion chain, so the pass
    that sets it to true must pin the FSL_XTRACT engine (the dipy default
    ignores it) and be skipped wherever that chain cannot run."""
    by_name = {spec.name: spec for spec in PASSES}
    assert by_name["dti_classic"].values["old_eddy_correct"] == "true"
    assert by_name["dti_classic"].values["tractography_engine"] == "FSL_XTRACT"
    assert set(_PASS_REQUIREMENTS["dti_classic"]) >= {"fsl", "xtract"}
    assert AXES_BY_NAME["old_eddy_correct"].gate_for("true") == "fsl"


def test_old_eddy_correct_is_not_claimed_without_xtract(all_capable):
    caps = _fsl_without_xtract(all_capable)
    plan = {item.name: item for item in build_plan(caps, with_reconall=True)}
    assert plan["dti_classic"].skipped
    cover = coverage(list(plan.values()), caps)
    assert "true" not in cover["old_eddy_correct"].covered
