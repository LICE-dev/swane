import os

import nibabel as nib
import numpy as np
import pytest

from swane.nipype_pipeline.interfaces.fmri.GgmThreshold import GgmThreshold
from swane.nipype_pipeline.interfaces.fmri.SpatialZThreshold import (
    SpatialZThreshold,
    spatial_z_threshold,
)

SHAPE = (30, 30, 30)


@pytest.fixture(autouse=True)
def _run_in_tmp_path(tmp_path, monkeypatch):
    # The interfaces write their outputs in the current directory.
    monkeypatch.chdir(tmp_path)


def _save(tmp_path, name, data):
    path = tmp_path / name
    nib.save(nib.Nifti1Image(data, np.diag([3.0, 3.0, 3.0, 1.0])), path)
    return str(path)


def _planted_map(seed=0):
    """One component: small background noise, +-10 blocks of 200 voxels,
    +-10 clusters of 3 voxels, and a 15-voxel positive line touching a
    15-voxel negative line (30 voxels if signs were merged)."""
    z = 0.1 * np.random.default_rng(seed).standard_normal(SHAPE)
    blocks = {
        "pos_big": (slice(2, 10), slice(2, 7), slice(2, 7)),  # 8*5*5 = 200
        "neg_big": (slice(18, 26), slice(2, 7), slice(2, 7)),
        "pos_small": (slice(2, 5), slice(20, 21), slice(20, 21)),
        "neg_small": (slice(10, 13), slice(20, 21), slice(20, 21)),
        "pos_line": (slice(5, 20), slice(26, 27), slice(15, 16)),
        "neg_line": (slice(5, 20), slice(27, 28), slice(15, 16)),
    }
    for name, sl in blocks.items():
        z[sl] = 10.0 if name.startswith("pos") else -10.0
    return z, blocks


def _run(tmp_path, z4d, min_cluster_voxels, mask=None, **inputs):
    if mask is None:
        mask = np.ones(SHAPE, np.uint8)
    node = SpatialZThreshold()
    node.inputs.zstat_file = _save(tmp_path, "zstat.nii.gz", z4d)
    node.inputs.mask_file = _save(tmp_path, "mask.nii.gz", mask.astype(np.uint8))
    node.inputs.min_cluster_voxels = min_cluster_voxels
    for name, value in inputs.items():
        setattr(node.inputs, name, value)
    return node.run().outputs


def test_small_clusters_removed_large_kept_per_sign(tmp_path):
    z, blocks = _planted_map()
    out = _run(tmp_path, z[..., None], 20)
    thr = nib.load(out.thresh_zstat_files[0]).get_fdata()

    for name in ("pos_big", "neg_big"):
        # Survivors keep the original z values, not the spatial z.
        np.testing.assert_allclose(thr[blocks[name]], z[blocks[name]])
    for name in ("pos_small", "neg_small", "pos_line", "neg_line"):
        assert np.all(thr[blocks[name]] == 0), name
    kept = np.zeros(SHAPE, bool)
    kept[blocks["pos_big"]] = kept[blocks["neg_big"]] = True
    assert np.all(thr[~kept] == 0)


def test_survivor_masks_are_uint8_and_split_by_sign(tmp_path):
    z, blocks = _planted_map()
    z4d = np.stack([z, -z], axis=-1)
    out = _run(tmp_path, z4d, 20)
    assert len(out.survivor_pos_files) == len(out.survivor_neg_files) == 2
    for k in range(2):
        thr = nib.load(out.thresh_zstat_files[k]).get_fdata()
        pos = nib.load(out.survivor_pos_files[k])
        neg = nib.load(out.survivor_neg_files[k])
        assert pos.get_data_dtype() == np.uint8
        assert neg.get_data_dtype() == np.uint8
        np.testing.assert_array_equal(pos.get_fdata() == 1, thr > 0)
        np.testing.assert_array_equal(neg.get_fdata() == 1, thr < 0)
        assert set(np.unique(pos.get_fdata())) <= {0, 1}
    pos0 = nib.load(out.survivor_pos_files[0]).get_fdata() > 0
    neg1 = nib.load(out.survivor_neg_files[1]).get_fdata() > 0
    np.testing.assert_array_equal(pos0, neg1)
    assert pos0[blocks["pos_big"]].all()


def test_connectivity_controls_cluster_merging(tmp_path):
    # Two 12-voxel lines touching only along an edge: separate clusters with
    # 6-connectivity (removed at k = 20), one 24-voxel cluster with
    # 18-connectivity (kept).
    z = np.zeros(SHAPE)
    z[2:14, 5, 5] = 10.0
    z[2:14, 6, 6] = 10.0
    z[20:28, 20:25, 20:25] = -10.0
    six = nib.load(_run(tmp_path, z[..., None], 20).thresh_zstat_files[0]).get_fdata()
    assert np.all(six[2:14, 5, 5] == 0)
    eighteen = nib.load(
        _run(tmp_path, z[..., None], 20, connectivity=2).thresh_zstat_files[0]
    ).get_fdata()
    assert np.all(eighteen[2:14, 5, 5] == 10.0)
    assert np.all(eighteen[2:14, 6, 6] == 10.0)


def test_threshold_applies_to_spatial_z_within_the_mask(tmp_path):
    # Values are shifted and scaled: the decision uses (z - mean) / SD over
    # the mask, so the survivors do not change. The offset is small enough
    # to keep every planted cluster's sign (clusters are split by the sign
    # of the stored z value).
    z, blocks = _planted_map(seed=3)
    mask = np.zeros(SHAPE, bool)
    mask[:, :, :29] = True
    shifted = 0.5 + 4.0 * z
    shifted[~mask] = 0
    ref = spatial_z_threshold(z[mask], mask, 1.95, 20)
    got = spatial_z_threshold(shifted[mask], mask, 1.95, 20)
    np.testing.assert_array_equal(ref != 0, got != 0)
    np.testing.assert_allclose(got[got != 0], shifted[mask][got != 0])


def test_spatial_z_is_not_capped(tmp_path):
    # A 20-voxel block far above a small background has a spatial z of
    # about 37: it must pass any threshold below that value.
    z = 0.1 * np.random.default_rng(1).standard_normal(SHAPE)
    block = (slice(2, 7), slice(2, 6), slice(2, 3))
    z[block] = 100.0
    mask = np.ones(SHAPE, bool)
    out = spatial_z_threshold(z[mask], mask, z_thr=9.0, min_vox=1)
    kept = np.zeros(SHAPE, bool)
    kept[mask] = out != 0
    assert np.array_equal(kept, z == 100.0)


def test_all_zero_and_near_constant_maps_give_all_zero_outputs(tmp_path):
    zero = np.zeros(SHAPE)
    near_constant = 5.0 + 1e-9 * np.random.default_rng(1).standard_normal(SHAPE)
    out = _run(tmp_path, np.stack([zero, near_constant], axis=-1), 20)
    for files in (
        out.thresh_zstat_files,
        out.survivor_pos_files,
        out.survivor_neg_files,
    ):
        for f in files:
            assert np.all(nib.load(f).get_fdata() == 0)


def test_output_names_match_ggm_threshold(tmp_path):
    K = 12
    z = np.random.default_rng(2).standard_normal(SHAPE[:2] + (4, K))
    z[..., 0] += 5 * (np.arange(4) == 2)[None, None, :]
    mask = np.ones(SHAPE[:2] + (4,), np.uint8)
    zfile = _save(tmp_path, "zstat.nii.gz", z)
    mfile = _save(tmp_path, "mask.nii.gz", mask)

    os.mkdir(tmp_path / "ggm")
    os.chdir(tmp_path / "ggm")
    ggm = GgmThreshold(zstat_file=zfile, mask_file=mfile).run().outputs
    os.mkdir(tmp_path / "spz")
    os.chdir(tmp_path / "spz")
    spz = (
        SpatialZThreshold(zstat_file=zfile, mask_file=mfile, min_cluster_voxels=5)
        .run()
        .outputs
    )

    ggm_names = [os.path.basename(f) for f in ggm.thresh_zstat_files]
    spz_names = [os.path.basename(f) for f in spz.thresh_zstat_files]
    assert spz_names == ggm_names
    assert spz_names[0] == "thresh_zstat01.nii.gz"
    assert spz_names[-1] == "thresh_zstat12.nii.gz"
    assert [os.path.basename(f) for f in spz.survivor_pos_files][10] == (
        "survivor_pos_zstat11.nii.gz"
    )
    assert [os.path.basename(f) for f in spz.survivor_neg_files][0] == (
        "survivor_neg_zstat01.nii.gz"
    )
    # Same grid and affine as the input z.
    assert nib.load(spz.thresh_zstat_files[0]).shape == z.shape[:3]
