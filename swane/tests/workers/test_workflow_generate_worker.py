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
