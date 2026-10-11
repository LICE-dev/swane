import pytest
from unittest.mock import MagicMock
from swane.workers.WorkflowGenerateWorker import WorkflowGenerateWorker
from swane.config.config_enums import GlobalPrefCategoryList, DeskullEngine


def test_preload_models_only_when_antspynet(monkeypatch):
    subject = MagicMock()
    synth_config = MagicMock()
    subject.global_config = {GlobalPrefCategoryList.SYNTH: synth_config}

    worker = WorkflowGenerateWorker(subject)

    # Mock dependencies
    strings_mock = MagicMock()
    strings_mock.subj_tab_wf_gen_models = "Downloading models..."

    mock_resolve = MagicMock()
    monkeypatch.setattr(
        "swane.nipype_pipeline.interfaces.utils.resolve_deskull_engine",
        mock_resolve,
        raising=False,
    )

    mock_weights_are_fetched = MagicMock(return_value=False)
    monkeypatch.setattr(
        "swane.utils.antspynet_weights.weights_are_fetched",
        mock_weights_are_fetched,
        raising=False,
    )

    mock_preload_weights = MagicMock()
    monkeypatch.setattr(
        "swane.utils.antspynet_weights.preload_weights",
        mock_preload_weights,
        raising=False,
    )

    # Case 1: NOT ANTSPYNET
    mock_resolve.return_value = DeskullEngine.BET
    worker._preload_models(strings_mock)
    mock_preload_weights.assert_not_called()

    # Case 2: ANTSPYNET
    mock_resolve.return_value = DeskullEngine.ANTSPYNET
    worker._preload_models(strings_mock)
    mock_preload_weights.assert_called_once()


def _dipy_subject(engine, dti_loaded, tractography):
    from swane.utils.DataInputList import DataInputList as DIL

    subject = MagicMock()
    subject.global_config.getenum_safe.return_value = engine
    subject.input_state_list = {DIL.DTI: MagicMock(loaded=dti_loaded)}
    subject.config.getboolean_safe.return_value = tractography
    return subject


@pytest.fixture
def mock_atlas(monkeypatch, tmp_path):
    """Point the atlas at an empty tmp dir and mock the fetch."""
    import swane.nipype_pipeline.interfaces.dipy.DipyAtlasSLR as slr

    mock_ensure = MagicMock()
    monkeypatch.setattr(slr, "DEFAULT_ATLAS_DIR", str(tmp_path))
    monkeypatch.setattr(slr, "ensure_atlas", mock_ensure)
    return mock_ensure, tmp_path


@pytest.mark.parametrize(
    "engine, dti_loaded, tractography",
    [
        ("FSL_XTRACT", True, True),
        ("DIPY_RECOBUNDLES", False, True),
        ("DIPY_RECOBUNDLES", True, False),
    ],
)
def test_preload_dipy_atlas_skipped_without_dipy_tractography(
    mock_atlas, engine, dti_loaded, tractography
):
    from swane.config.config_enums import TractographyEngine

    mock_ensure, _ = mock_atlas
    subject = _dipy_subject(TractographyEngine[engine], dti_loaded, tractography)
    worker = WorkflowGenerateWorker(subject)

    worker._preload_dipy_atlas(MagicMock())

    mock_ensure.assert_not_called()


def test_preload_dipy_atlas_fetches_when_dipy_tractography(mock_atlas):
    from swane.config.config_enums import TractographyEngine

    mock_ensure, atlas_dir = mock_atlas
    subject = _dipy_subject(TractographyEngine.DIPY_RECOBUNDLES, True, True)
    worker = WorkflowGenerateWorker(subject)

    worker._preload_dipy_atlas(MagicMock())

    mock_ensure.assert_called_once_with(str(atlas_dir))


def test_preload_dipy_atlas_skipped_when_already_fetched(mock_atlas):
    from swane.config.config_enums import TractographyEngine
    from swane.nipype_pipeline.interfaces.dipy.DipyAtlasSLR import (
        atlas_wholebrain_path,
    )

    mock_ensure, atlas_dir = mock_atlas
    wholebrain = atlas_wholebrain_path(atlas_dir)
    wholebrain.parent.mkdir(parents=True)
    wholebrain.touch()
    subject = _dipy_subject(TractographyEngine.DIPY_RECOBUNDLES, True, True)
    worker = WorkflowGenerateWorker(subject)

    worker._preload_dipy_atlas(MagicMock())

    mock_ensure.assert_not_called()


def test_failed_preload_does_not_skip_the_others(monkeypatch):
    subject = MagicMock()
    worker = WorkflowGenerateWorker(subject)
    calls = []

    def _failing(_strings):
        calls.append("templates")
        raise RuntimeError("offline")

    monkeypatch.setattr(worker, "_preload_templates", _failing)
    monkeypatch.setattr(worker, "_preload_models", lambda _s: calls.append("models"))
    monkeypatch.setattr(
        worker, "_preload_dipy_atlas", lambda _s: calls.append("dipy_atlas")
    )

    worker.run()

    assert calls == ["templates", "models", "dipy_atlas"]
    subject.generate_workflow.assert_called_once()
