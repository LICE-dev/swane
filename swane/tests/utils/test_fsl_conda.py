"""fsl_conda resolves a pinned FSL install from a synthetic release manifest."""

import json
import os

import pytest

from swane.utils import fsl_conda


def _environment(versions: dict) -> str:
    lines = ["name: FSL", "channels:", " - conda-forge", "dependencies:"]
    lines += [" - %s %s" % item for item in versions.items()]
    return "\n".join(lines) + "\n"


def _full(tag: str) -> dict:
    """Every pinned package, at a version derived from ``tag``."""
    names = fsl_conda.FSL_PACKAGES + fsl_conda.EXTRA_PACKAGES
    return {name: "%s.%d" % (tag, i) for i, name in enumerate(names)}


@pytest.fixture
def manifest(tmp_path):
    """6.0.5 (too old), 6.0.6 (x86 only), 6.0.6.3 and 6.0.7 (also M1)."""
    envs = {}
    for release in ("6.0.5", "6.0.6", "6.0.6.3", "6.0.7"):
        path = tmp_path / ("fsl-%s.yml" % release)
        path.write_text(_environment(_full(release)))
        envs[release] = str(path)
    versions = {
        release: [{"platform": "linux-64", "environment": envs[release]}]
        for release in envs
    }
    for release in ("6.0.6.3", "6.0.7"):
        versions[release].append({"platform": "macos-M1", "environment": envs[release]})
    versions["latest"] = "6.0.7"
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"versions": versions}))
    return path


def test_picks_the_minimum_release_when_the_platform_has_it(manifest):
    data = json.loads(manifest.read_text())
    release, _env = fsl_conda.select_release(data, "linux-64", "6.0.6")
    assert release == "6.0.6"


def test_skips_releases_without_a_build_for_the_platform(manifest):
    # 6.0.6 has no Apple Silicon build: the oldest supported one is 6.0.6.3,
    # which still satisfies the minimum (and is what fslversion will say).
    data = json.loads(manifest.read_text())
    release, _env = fsl_conda.select_release(data, "macos-M1", "6.0.6")
    assert release == "6.0.6.3"


def test_explicit_release_overrides_the_minimum(manifest):
    data = json.loads(manifest.read_text())
    release, _env = fsl_conda.select_release(data, "macos-M1", "6.0.6", "6.0.7")
    assert release == "6.0.7"


def test_missing_platform_or_release_fails(manifest):
    data = json.loads(manifest.read_text())
    with pytest.raises(SystemExit):
        fsl_conda.select_release(data, "windows-64", "6.0.6")
    with pytest.raises(SystemExit):
        fsl_conda.select_release(data, "macos-M1", "6.0.6", "6.0.6")


def test_pinned_specs_takes_the_release_versions():
    specs = fsl_conda.pinned_specs(_environment({**_full("1"), "fsl-other": "9"}))
    expected = _full("1")
    assert specs == ["%s=%s" % item for item in expected.items()]
    assert not any(spec.startswith("fsl-other") for spec in specs)
    assert not any("cuda" in spec for spec in specs)


def test_pinned_specs_fails_on_a_missing_package():
    versions = _full("1")
    del versions["fsl-eddy"]
    with pytest.raises(SystemExit, match="fsl-eddy"):
        fsl_conda.pinned_specs(_environment(versions))


def test_min_fsl_version_matches_dependency_manager():
    from swane.utils.DependencyManager import DependencyManager

    assert fsl_conda.min_fsl_version() == DependencyManager.MIN_FSL_VERSION


def test_main_github_output(manifest, capsys, monkeypatch):
    monkeypatch.setattr(fsl_conda, "min_fsl_version", lambda: "6.0.6")
    fsl_conda.main(
        ["--manifest", str(manifest), "--platform", "macos-M1", "--format", "github"]
    )
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "release=6.0.6.3"
    assert lines[1] == "platform=macos-M1"
    assert lines[2].startswith("specs=fsl-bet2=6.0.6.3.0 ")


def test_dependency_manager_path_points_at_live_source():
    from swane.utils.DependencyManager import DependencyManager

    assert os.path.isfile(fsl_conda.DEPENDENCY_MANAGER)
    assert fsl_conda.min_fsl_version() == DependencyManager.MIN_FSL_VERSION


def test_fsl_channel_is_fsl_public_conda_channel():
    assert fsl_conda.FSL_CHANNEL == (
        "https://fsl.fmrib.ox.ac.uk/fsldownloads/fslconda/public/"
    )
