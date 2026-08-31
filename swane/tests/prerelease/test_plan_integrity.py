"""Guards for the sweep plan itself — fast, no workflow is executed.

The pre-release sweep takes hours, so its plan must be known-good *before*
anyone starts it. These tests run in the ordinary light suite and fail the
moment the plan stops being coherent: a pass referring to an axis that no
longer exists, a value that is not one of the axis's own, or — the important
one — an axis value that no pass exercises, which would silently shrink
coverage the next time someone adds a setting to SWANe.
"""

import pytest

from swane.tests.prerelease.capabilities import Capabilities
from swane.tests.prerelease.plan import (
    AXES,
    AXES_BY_NAME,
    PASSES,
    SHAPE,
    _PASS_REQUIREMENTS,
    build_plan,
    coverage,
    plan_holes,
)


@pytest.fixture
def all_capable():
    """A host where everything is available, to judge the plan on its own merits."""
    caps = Capabilities(cores=8, ram_gb=64.0)
    needed = {gate for axis in AXES for gate in axis.gates.values()}
    needed.update(
        {"fsl", "dcm2niix", "freesurfer", "fsaverage", "slicer", "ram_budget"}
    )
    # Capabilities that gate whole passes (not tied to an axis value), e.g.
    # reconall_expert, so a fully capable host really skips nothing.
    needed.update(
        cap for caps_tuple in _PASS_REQUIREMENTS.values() for cap in caps_tuple
    )
    for name in needed:
        caps.add(name, True, "assumed available in this test")
    return caps


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
    plan = build_plan(all_capable, with_reconall=True)
    skipped = {p.name: p.skip_reason for p in plan if p.skipped}
    assert not skipped, "passes skipped on a fully capable host: %s" % skipped


def test_missing_capability_downgrades_instead_of_failing():
    """An unavailable option must be reported, never silently claimed."""
    caps = Capabilities(cores=4, ram_gb=8.0)
    needed = {gate for axis in AXES for gate in axis.gates.values()}
    for name in needed:
        caps.add(name, True, "available")
    caps.add("synth_morph", False, "needs 14.0 GB, only 8.0 GB allocated")
    for name in ("fsl", "dcm2niix", "fsaverage", "ram_budget", "slicer"):
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
    # FSL is always available; SYNTH and ANTS are gated on their dependencies.
    assert axis.gate_for("FSL") == ""
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
