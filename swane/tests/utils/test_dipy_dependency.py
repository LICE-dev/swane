import os

from swane.utils.DependencyManager import DependencyManager, DependenceStatus
from swane.utils import LicenseReference as LR
from swane.utils import license_consent as lc


def test_check_dipy_detects_installed_package():
    # dipy is a real pinned dependency of the dev environment, so this exercises
    # the real find_spec/metadata probe, not a mock.
    dep = DependencyManager.check_dipy()
    assert dep.state == DependenceStatus.DETECTED
    assert DependencyManager.is_dipy() is True


def test_is_dipy_true_when_present(monkeypatch):
    monkeypatch.setattr(
        "swane.utils.DependencyManager.importlib.util.find_spec",
        lambda name: object() if name == "dipy" else None,
    )
    monkeypatch.setattr(
        "swane.utils.DependencyManager.importlib.metadata.version",
        lambda name: DependencyManager.MIN_DIPY_VERSION,
    )
    assert DependencyManager.is_dipy() is True
    assert DependencyManager.check_dipy().state == DependenceStatus.DETECTED


def test_is_dipy_false_when_absent(monkeypatch):
    monkeypatch.setattr(
        "swane.utils.DependencyManager.importlib.util.find_spec",
        lambda name: None,
    )
    assert DependencyManager.is_dipy() is False
    assert DependencyManager.check_dipy().state == DependenceStatus.MISSING


def test_check_dipy_wrong_version_warns(monkeypatch):
    monkeypatch.setattr(
        "swane.utils.DependencyManager.importlib.util.find_spec",
        lambda name: object() if name == "dipy" else None,
    )
    monkeypatch.setattr(
        "swane.utils.DependencyManager.importlib.metadata.version",
        lambda name: "1.0.0",
    )
    dep = DependencyManager.check_dipy()
    assert dep.state == DependenceStatus.WARNING


def test_check_dipy_label_includes_license_link(monkeypatch):
    monkeypatch.setattr(
        "swane.utils.DependencyManager.importlib.util.find_spec",
        lambda name: object() if name == "dipy" else None,
    )
    monkeypatch.setattr(
        "swane.utils.DependencyManager.importlib.metadata.version",
        lambda name: DependencyManager.MIN_DIPY_VERSION,
    )
    dep = DependencyManager.check_dipy()
    assert "href=" in dep.label


def test_dependency_manager_init_sets_dipy_attr():
    manager = DependencyManager()
    assert manager.dipy.state in (
        DependenceStatus.DETECTED,
        DependenceStatus.WARNING,
        DependenceStatus.MISSING,
    )


def test_dipy_license_registered():
    assert LR.DIPY == "dipy"
    assert LR.DIPY in LR.TOOL_IDS
    assert LR.DIPY in LR.LICENSES
    info = LR.LICENSES[LR.DIPY]
    assert info.display_name
    assert os.path.exists(LR.bundled_license_path(info))


def test_dipy_candidates_from_pip_dist_info(monkeypatch):
    import importlib.metadata as im

    class _FakeEntry:
        def __init__(self, parts, name):
            self.parts = parts
            self.name = name

    class _FakeDist:
        def __init__(self, files):
            self.files = files

        def locate_file(self, entry):
            return "/abs/" + "/".join(entry.parts)

    license_entry = _FakeEntry(("dipy-1.12.0.dist-info", "LICENSE"), "LICENSE")
    code_entry = _FakeEntry(("dipy", "__init__.py"), "__init__.py")
    monkeypatch.setattr(
        im, "distribution", lambda name: _FakeDist([code_entry, license_entry])
    )

    candidates = LR.LICENSES[LR.DIPY].installed_path_candidates({})
    assert candidates == ["/abs/dipy-1.12.0.dist-info/LICENSE"]


def test_dipy_candidates_missing_package(monkeypatch):
    import importlib.metadata as im

    def _raise(name):
        raise im.PackageNotFoundError(name)

    monkeypatch.setattr(im, "distribution", _raise)
    assert LR.LICENSES[LR.DIPY].installed_path_candidates({}) == []


def test_dipy_offered_for_consent_like_other_tools(monkeypatch):
    class _FakeDM:
        def is_fsl(self):
            return False

        def is_freesurfer(self):
            return False

        def is_dcm2niix(self):
            return False

        def is_antspyx(self):
            return False

        def is_antspynet(self):
            return False

        def is_dipy(self):
            return True

    class _FakeConfig:
        def get_accepted_license_version(self, tool_id):
            return ""

        def get_slicer_path(self):
            return ""

        def get_slicer_version(self):
            return ""

    monkeypatch.setattr(lc, "_is_slicer_detected", lambda config: False)
    monkeypatch.setattr(lc, "_dipy_version", lambda: "1.12.0")

    dm, cfg = _FakeDM(), _FakeConfig()
    detected = lc.detected_tool_versions(dm, cfg)
    assert detected == {"dipy": "1.12.0"}
    assert "dipy" in lc.tools_needing_consent(dm, cfg, detected)
