import os
from swane.utils import LicenseReference as LR


def test_registry_has_all_tools():
    assert set(LR.LICENSES) == set(LR.TOOL_IDS)
    assert set(LR.TOOL_IDS) == {
        "fsl",
        "freesurfer",
        "slicer",
        "dcm2niix",
        "antspyx",
        "antspynet",
    }


def test_each_tool_has_url_and_bundled_file():
    for tool_id, info in LR.LICENSES.items():
        assert info.official_url.startswith("http")
        path = LR.bundled_license_path(info)
        assert os.path.isfile(path), f"missing bundled license for {tool_id}: {path}"
        with open(path, encoding="utf-8", errors="replace") as fh:
            assert fh.read().strip(), f"empty bundled license for {tool_id}"


def test_freesurfer_candidates_exclude_user_key_file(monkeypatch):
    monkeypatch.setenv("FREESURFER_HOME", "/opt/freesurfer")
    candidates = LR.LICENSES["freesurfer"].installed_path_candidates({})
    # The legal license, never the per-user registration key files
    assert any(c.endswith("LICENSE.txt") for c in candidates)
    assert all(not c.endswith(".license") for c in candidates)
    assert all(os.path.basename(c) != "license.txt" for c in candidates)
    # FreeSurfer ships the per-user key as "_license.txt"; never display it
    assert all(os.path.basename(c) != "_license.txt" for c in candidates)


def test_freesurfer_candidates_include_sla_agreement(monkeypatch):
    monkeypatch.setenv("FREESURFER_HOME", "/opt/freesurfer")
    candidates = LR.LICENSES["freesurfer"].installed_path_candidates({})
    # The real legal agreement filename shipped by FreeSurfer
    assert (
        os.path.join("/opt/freesurfer", "docs", "license.freesurfer_SLA.txt")
        in candidates
    )
    # ...and it must be preferred over the generic guesses
    assert candidates[0].endswith(os.path.join("docs", "license.freesurfer_SLA.txt"))


def test_fsl_candidates_include_real_licence_filename(monkeypatch):
    monkeypatch.setenv("FSLDIR", "/opt/fsl")
    candidates = LR.LICENSES["fsl"].installed_path_candidates({})
    # FSL ships its licence as "LICENCE.FSL" (British spelling, .FSL extension)
    assert os.path.join("/opt/fsl", "LICENCE.FSL") in candidates


class _FakeEntry:
    def __init__(self, parts, name):
        self.parts = parts
        self.name = name


class _FakeDist:
    def __init__(self, files):
        self.files = files

    def locate_file(self, entry):
        return "/abs/" + "/".join(entry.parts)


def test_dcm2niix_candidates_from_pip_dist_info(monkeypatch):
    import importlib.metadata as im

    license_entry = _FakeEntry(
        ("dcm2niix-1.0.dist-info", "licenses", "license.txt"), "license.txt"
    )
    code_entry = _FakeEntry(("dcm2niix", "__init__.py"), "__init__.py")
    monkeypatch.setattr(
        im, "distribution", lambda name: _FakeDist([code_entry, license_entry])
    )

    candidates = LR.LICENSES["dcm2niix"].installed_path_candidates({})
    assert candidates == ["/abs/dcm2niix-1.0.dist-info/licenses/license.txt"]


def test_dcm2niix_candidates_missing_package(monkeypatch):
    import importlib.metadata as im

    def _raise(name):
        raise im.PackageNotFoundError(name)

    monkeypatch.setattr(im, "distribution", _raise)
    assert LR.LICENSES["dcm2niix"].installed_path_candidates({}) == []


def test_antspyx_candidates_from_pip_dist_info(monkeypatch):
    import importlib.metadata as im

    license_entry = _FakeEntry(
        ("antspyx-0.6.3.dist-info", "licenses", "LICENSE"), "LICENSE"
    )
    code_entry = _FakeEntry(("ants", "__init__.py"), "__init__.py")
    monkeypatch.setattr(
        im, "distribution", lambda name: _FakeDist([code_entry, license_entry])
    )

    candidates = LR.LICENSES["antspyx"].installed_path_candidates({})
    assert candidates == ["/abs/antspyx-0.6.3.dist-info/licenses/LICENSE"]


def test_antspyx_candidates_missing_package(monkeypatch):
    import importlib.metadata as im

    def _raise(name):
        raise im.PackageNotFoundError(name)

    monkeypatch.setattr(im, "distribution", _raise)
    assert LR.LICENSES["antspyx"].installed_path_candidates({}) == []


def test_antspynet_in_tool_ids_and_has_bundled_license():
    assert LR.ANTSPYNET == "antspynet"
    assert LR.ANTSPYNET in LR.TOOL_IDS
    info = LR.LICENSES[LR.ANTSPYNET]
    assert os.path.exists(LR.bundled_license_path(info))
