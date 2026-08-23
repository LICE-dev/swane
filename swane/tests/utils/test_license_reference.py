import os
from swane.utils import LicenseReference as LR


def test_registry_has_all_tools():
    assert set(LR.LICENSES) == set(LR.TOOL_IDS)
    assert set(LR.TOOL_IDS) == {"fsl", "freesurfer", "slicer", "dcm2niix"}


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
