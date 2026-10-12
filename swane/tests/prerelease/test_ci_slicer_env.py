"""ci_slicer_env resolves a pinned Slicer package from synthetic server replies."""

import pytest

from swane.tests.prerelease import ci_slicer_env


def _package(item_id, os_name, release="5.12.4", arch="amd64", pre_release=False):
    return {
        "_id": item_id,
        "meta": {
            "os": os_name,
            "arch": arch,
            "release": release,
            "pre_release": pre_release,
        },
    }


def _fake_server(packages, files):
    """A ``fetch`` answering the package query and each item's file listing."""
    seen = []

    def fetch(url):
        seen.append(url)
        if "/package?" in url:
            return packages
        item_id = url.split("/item/")[1].split("/")[0]
        return files[item_id]

    fetch.seen = seen
    return fetch


def test_resolves_url_filename_and_file_checksum():
    fetch = _fake_server(
        [_package("mac1", "macosx")],
        {
            "mac1": [
                {"name": "Slicer-5.12.4-macosx-amd64.dmg", "sha512": "abc"},
            ]
        },
    )
    info = ci_slicer_env.resolve("5.12.4", "macosx", fetch=fetch)
    assert info == {
        "release": "5.12.4",
        "os": "macosx",
        "url": "%s/item/mac1/download" % ci_slicer_env.SERVER,
        "filename": "Slicer-5.12.4-macosx-amd64.dmg",
        "sha512": "abc",
    }
    # The query pins release, OS and arch on the server side too.
    query = fetch.seen[0]
    assert "release_id_or_name=5.12.4" in query
    assert "os=macosx" in query and "arch=amd64" in query


def test_never_picks_a_preview_or_another_platform():
    # A loose server-side filter must not install a preview build, another OS
    # or another release.
    fetch = _fake_server(
        [
            _package("prev", "win", pre_release=True),
            _package("lin", "linux"),
            _package("old", "win", release="5.12.3"),
            _package("good", "win"),
        ],
        {"good": [{"name": "Slicer-5.12.4-win-amd64.exe", "sha512": "x"}]},
    )
    info = ci_slicer_env.resolve("5.12.4", "win", fetch=fetch)
    assert info["url"].endswith("/item/good/download")


def test_missing_release_fails_clearly():
    fetch = _fake_server([_package("old", "win", release="5.12.3")], {})
    with pytest.raises(SystemExit, match="no stable Slicer 5.12.4"):
        ci_slicer_env.resolve("5.12.4", "win", fetch=fetch)


def test_package_without_installer_fails_clearly():
    fetch = _fake_server(
        [_package("mac1", "macosx")], {"mac1": [{"name": "README.txt", "sha512": ""}]}
    )
    with pytest.raises(SystemExit, match=r"no \.dmg file"):
        ci_slicer_env.resolve("5.12.4", "macosx", fetch=fetch)


def test_rejects_a_malformed_release():
    with pytest.raises(SystemExit, match="not a Slicer release"):
        ci_slicer_env.resolve("latest", "win", fetch=lambda url: [])


def test_default_release_meets_the_swane_minimum():
    # CI must not pin a Slicer that SWANe itself would reject.
    from swane.utils.DependencyManager import DependencyManager

    assert DependencyManager.check_slicer_version(ci_slicer_env.DEFAULT_RELEASE)
