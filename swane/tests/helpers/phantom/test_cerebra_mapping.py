"""CerebrA label names -> phantom tissue classes, on tiny synthetic volumes."""

import numpy as np
import pytest

from swane.tests.helpers.phantom import tissue as T
from swane.tests.helpers.phantom.tissue import TissueClass as TC

P = T._PAD_VOXELS


def _vols(shape=(4, 4, 4)):
    z = np.zeros(shape, dtype=np.float32)
    return z.copy(), z.copy(), z.copy(), np.ones(shape, dtype=bool)


def _map(cerebra, names, gm, wm, csf, mask, affine=None):
    affine = np.eye(4) if affine is None else affine
    labels, precentral, aff = T._cerebra_class_map(
        cerebra, names, gm, wm, csf, mask, affine
    )
    core = tuple(slice(P, -P) for _ in range(3))
    return labels[core], precentral[core], aff, labels, precentral


def test_every_table_entry_maps_to_its_class():
    names = {i + 1: n for i, n in enumerate(sorted(T._CEREBRA_CLASSES))}
    cerebra = np.zeros((len(names), 1, 1), dtype=np.int32)
    cerebra[:, 0, 0] = list(names)
    gm, wm, csf, mask = _vols(cerebra.shape)
    gm[:] = 1.0  # GM-dominant: no cortex voxel turns into WM
    core, _pc, _aff, _l, _p = _map(cerebra, names, gm, wm, csf, mask)
    for i, label in enumerate(names):
        expected = T._CEREBRA_CLASSES[names[label]]
        want = TC.AIR if expected is None else expected
        assert core[i, 0, 0] == want, names[label]


def test_unknown_name_raises():
    cerebra = np.ones((2, 2, 2), dtype=np.int32)
    gm, wm, csf, mask = _vols((2, 2, 2))
    with pytest.raises(ValueError, match="Hyperthalamus"):
        T._cerebra_class_map(
            cerebra, {1: "Hyperthalamus"}, gm, wm, csf, mask, np.eye(4)
        )


def test_cortex_where_wm_beats_gm_becomes_wm_and_leaves_precentral():
    cerebra = np.full((2, 1, 1), 7, dtype=np.int32)
    gm, wm, csf, mask = _vols((2, 1, 1))
    gm[0], wm[0] = 0.6, 0.4  # stays cortex
    gm[1], wm[1] = 0.3, 0.7  # becomes WM
    core, pc, _aff, _l, _p = _map(cerebra, {7: "Precentral"}, gm, wm, csf, mask)
    assert core[0, 0, 0] == TC.CORTICAL_GM and pc[0, 0, 0]
    assert core[1, 0, 0] == TC.WM and not pc[1, 0, 0]


def test_unlabelled_brain_takes_the_dominant_probseg_class():
    cerebra = np.zeros((4, 1, 1), dtype=np.int32)
    gm, wm, csf, mask = _vols((4, 1, 1))
    gm[0] = 0.9
    wm[1] = 0.9
    csf[2] = 0.9
    gm[3], wm[3], csf[3] = 0.1, 0.1, 0.1  # total <= 0.5: not brain
    core, _pc, _aff, _l, _p = _map(cerebra, {}, gm, wm, csf, mask)
    assert [int(v) for v in core[:, 0, 0]] == [
        TC.CORTICAL_GM,
        TC.WM,
        TC.CSF_EXTRA,
        TC.AIR,
    ]


def test_outside_the_brain_mask_stays_air():
    cerebra = np.zeros((1, 1, 1), dtype=np.int32)
    gm, wm, csf, mask = _vols((1, 1, 1))
    wm[:] = 1.0
    mask[:] = False
    core, _pc, _aff, _l, _p = _map(cerebra, {}, gm, wm, csf, mask)
    assert core[0, 0, 0] == TC.AIR


def test_padding_preserves_world_coordinates():
    affine = np.array(
        [[1.0, 0, 0, -96.0], [0, 1.0, 0, -132.0], [0, 0, 1.0, -78.0], [0, 0, 0, 1]]
    )
    cerebra = np.zeros((3, 3, 3), dtype=np.int32)
    cerebra[1, 2, 0] = 5
    gm, wm, csf, mask = _vols((3, 3, 3))
    gm[:] = 1.0
    _core, _pc, aff, labels, _p = _map(
        cerebra, {5: "Thalamus"}, gm, wm, csf, mask, affine
    )
    assert labels.shape == (3 + 2 * P,) * 3
    world_before = affine @ np.array([1, 2, 0, 1.0])
    world_after = aff @ np.array([1 + P, 2 + P, 0 + P, 1.0])
    assert np.allclose(world_before, world_after)
    assert labels[1 + P, 2 + P, 0 + P] == TC.DEEP_GM
    assert labels[0, 0, 0] == TC.AIR


def test_read_cerebra_names(tmp_path):
    tsv = tmp_path / "t.tsv"
    tsv.write_text(
        "label\tname\themi\tmindboggle mapping\n80\tThird Ventricle\tL\t14\n"
        "29\tThird Ventricle\tR\t14\n"
    )
    assert T._read_cerebra_names(str(tsv)) == {
        80: "Third Ventricle",
        29: "Third Ventricle",
    }


def test_every_real_tsv_name_is_mapped():
    from swane.tests.helpers.phantom.anatomy_source import (
        anatomy_available,
        resolve_anatomy_files,
    )

    if not anatomy_available():
        pytest.skip("CerebrA/ICBM 2009c Sym not in the TemplateFlow cache")
    names = T._read_cerebra_names(resolve_anatomy_files(allow_download=False)["tsv"])
    assert len(names) == 102
    assert set(names.values()) <= set(T._CEREBRA_CLASSES)
    assert T._PRECENTRAL_NAME in names.values()
