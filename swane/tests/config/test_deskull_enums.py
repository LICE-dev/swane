from swane.config.config_enums import DeskullEngine, DeskullModality


def test_deskull_engine_members_and_labels():
    assert {e.name for e in DeskullEngine} == {"ANTSPYNET", "SYNTHSTRIP", "BET"}
    assert DeskullEngine.ANTSPYNET.value == "ANTs (antspynet)"
    assert DeskullEngine.SYNTHSTRIP.value == "FreeSurfer SynthStrip"
    assert DeskullEngine.BET.value == "FSL BET"


def test_deskull_modality_fixed_keys_are_antspynet_literals():
    assert DeskullModality.T1.value == "t1"
    assert DeskullModality.FLAIR.value == "flair"
    assert DeskullModality.T2.value == "t2"
    assert DeskullModality.BOLD.value == "bold"


def test_oracle_decided_modalities():
    assert DeskullModality.NODIF.value == "bold"
    assert DeskullModality.VENOUS.value == "flair.v0"
