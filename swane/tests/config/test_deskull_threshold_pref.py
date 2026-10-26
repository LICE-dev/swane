from swane.config.config_enums import DeskullEngine, GlobalPrefCategoryList
from swane.config.preference_list import WF_PREFERENCES
from swane.utils.DataInputList import DataInputList

BET_THR_CATS = [
    DataInputList.T13D,
    DataInputList.FLAIR3D,
    DataInputList.MDC,
    DataInputList.VENOUS_MR,
]


def test_antspynet_thr_added_to_each_bet_thr_category():
    for cat in BET_THR_CATS:
        entry = WF_PREFERENCES[cat]["antspynet_thr"]
        assert entry.default == 0.5
        assert entry.range == [0, 1]
        req = entry.pref_requirement[GlobalPrefCategoryList.SYNTH]
        assert ("deskull_engine", DeskullEngine.ANTSPYNET) in req


def test_bet_thr_gated_by_bet_engine():
    for cat in BET_THR_CATS:
        req = WF_PREFERENCES[cat]["bet_thr"].pref_requirement[
            GlobalPrefCategoryList.SYNTH
        ]
        assert ("deskull_engine", DeskullEngine.BET) in req


def test_bet_bias_correction_gated_by_bet_engine():
    for cat in (DataInputList.T13D, DataInputList.FLAIR3D, DataInputList.MDC):
        req = WF_PREFERENCES[cat]["bet_bias_correction"].pref_requirement[
            GlobalPrefCategoryList.SYNTH
        ]
        assert ("deskull_engine", DeskullEngine.BET) in req
