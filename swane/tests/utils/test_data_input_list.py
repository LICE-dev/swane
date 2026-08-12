from swane.utils.DataInputList import DataInputList, DataInput
from swane.config.config_enums import ImageModality


def test_is_image_modality():
    di = DataInput(name='test', image_modality=[ImageModality.RM])
    assert di.is_image_modality(ImageModality.RM) is True
    assert di.is_image_modality('RM') is True
    assert di.get_modality_str() != ''


def test_enum_str():
    # ensure __str__ returns DataInput name
    for di in list(DataInputList)[:3]:
        assert str(di) == di.value.name
