# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-
import os

import nibabel as nib
import numpy as np
from nipype.interfaces.base import (
    BaseInterface,
    BaseInterfaceInputSpec,
    File,
    TraitedSpec,
    traits,
)
from scipy import ndimage

# Maps whose SD over the mask is below this fraction of their largest |z|
# carry no spatial contrast and give an empty result.
NEAR_CONSTANT_REL_SD = 1e-6


def spatial_z(z_v):
    """Spatial z of one map over the mask voxels: (z - mean) / SD.
    Near-constant maps give zeros."""
    sd = z_v.std()
    if sd <= NEAR_CONSTANT_REL_SD * max(1.0, float(np.abs(z_v).max(initial=0.0))):
        return np.zeros_like(z_v, dtype=np.float64)
    return (z_v - z_v.mean()) / sd


def cluster_filter(thr_v, mask, min_vox, connectivity=1):
    """Keep the clusters with at least ``min_vox`` voxels, labelled
    separately for positive and negative values. Returns the filtered values
    (V,) and the positive and negative survivor masks (V,) inside the mask."""
    st = ndimage.generate_binary_structure(3, connectivity)
    vol = np.zeros(mask.shape, np.float64)
    vol[mask] = thr_v
    keep = {}
    for name, sgn in (("pos", 1), ("neg", -1)):
        lab, n = ndimage.label(sgn * vol > 0, structure=st)
        keep[name] = np.zeros(mask.shape, bool)
        if n:
            sizes = np.bincount(lab.ravel())[1:]
            keep[name] = np.isin(lab, np.flatnonzero(sizes >= min_vox) + 1)
    pos, neg = keep["pos"][mask], keep["neg"][mask]
    return np.where(pos | neg, thr_v, 0.0), pos, neg


def spatial_z_threshold(z_v, mask, z_thr, min_vox, connectivity=1, masks=False):
    """Threshold one map (V,) at |spatial z| > ``z_thr`` and keep the
    clusters of at least ``min_vox`` voxels per sign. Surviving voxels keep
    their original z values; the sign of a cluster is the sign of those
    values. With ``masks`` also return the positive and negative survivor
    masks."""
    zs = spatial_z(z_v)
    out, pos, neg = cluster_filter(
        np.where(np.abs(zs) > z_thr, z_v, 0.0), mask, min_vox, connectivity
    )
    return (out, pos, neg) if masks else out


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
class SpatialZThresholdInputSpec(BaseInterfaceInputSpec):
    zstat_file = File(exists=True, mandatory=True, desc="Z-statistic 4D image")
    mask_file = File(exists=True, mandatory=True, desc="Brain mask")
    z_thr = traits.Float(
        1.95, usedefault=True, desc="Threshold on the absolute spatial z"
    )
    min_cluster_voxels = traits.Int(
        mandatory=True, desc="Minimum cluster size (voxels), per sign"
    )
    connectivity = traits.Int(
        1,
        usedefault=True,
        desc="Cluster connectivity rank: 1 = 6-, 2 = 18-, 3 = 26-connected",
    )


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class SpatialZThresholdOutputSpec(TraitedSpec):
    thresh_zstat_files = traits.List(
        File(), desc="Thresholded 3D maps (original z values), one per component"
    )
    survivor_pos_files = traits.List(
        File(), desc="uint8 masks of the surviving positive clusters, per component"
    )
    survivor_neg_files = traits.List(
        File(), desc="uint8 masks of the surviving negative clusters, per component"
    )


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class SpatialZThreshold(BaseInterface):
    """
    Spatial z threshold with a cluster-extent rule for IC maps.

    Each component map is spatially z-scored over the mask (map minus its
    mean, divided by its SD; the convention of Calhoun et al. 2001).
    Voxels with |spatial z| > ``z_thr`` are kept with their
    original z values, then clusters (``connectivity`` 1 = 6-connected) with
    fewer than ``min_cluster_voxels`` voxels are removed, separately for
    positive and negative values. ``min_cluster_voxels`` is meant to come
    from ``ClusterExtentMC`` (Forman et al. 1995 Monte Carlo on the
    subject's residual smoothness). A near-constant map (SD below 1e-6 of
    its largest |z|) has no spatial contrast and gives an empty result.

    Spatial z on IC maps is not an inferential statistic; k is a
    smoothness-derived extent, not a controlled false-positive rate.

    Outputs use the same names as ``GgmThreshold`` (``thresh_zstatNN``), plus
    per-component uint8 survivor masks (``survivor_pos_zstatNN``,
    ``survivor_neg_zstatNN``) for resampling the decision to another space.

    References:
    - Calhoun VD, Adali T, Pearlson GD, Pekar JJ (2001). A method for making
      group inferences from functional MRI data using independent component
      analysis. Hum Brain Mapp 14(3):140-151. doi:10.1002/hbm.1048
    - Forman SD, et al. (1995). Improved assessment of significant activation
      in functional magnetic resonance imaging (fMRI): use of a cluster-size
      threshold. Magn Reson Med 33:636-647. doi:10.1002/mrm.1910330508
    """

    input_spec = SpatialZThresholdInputSpec
    output_spec = SpatialZThresholdOutputSpec

    def _run_interface(self, runtime):
        out_dir = runtime.cwd
        z_img = nib.load(self.inputs.zstat_file)
        z_data = z_img.get_fdata()
        if z_data.ndim == 3:
            z_data = z_data[..., None]
        mask = np.asanyarray(nib.load(self.inputs.mask_file).dataobj) > 0
        z_masked = z_data[mask]  # (V, K)

        header = z_img.header.copy()
        header.set_data_shape(z_data.shape[:3])
        self._thresh_zstat_files = []
        self._survivor_pos_files = []
        self._survivor_neg_files = []
        for k in range(z_masked.shape[1]):
            thr, pos, neg = spatial_z_threshold(
                z_masked[:, k],
                mask,
                self.inputs.z_thr,
                self.inputs.min_cluster_voxels,
                self.inputs.connectivity,
                masks=True,
            )
            t_vol = np.zeros(mask.shape)
            t_vol[mask] = thr
            t_path = os.path.join(out_dir, f"thresh_zstat{k + 1:02d}.nii.gz")
            nib.save(nib.Nifti1Image(t_vol, z_img.affine, header), t_path)
            self._thresh_zstat_files.append(t_path)

            for name, sel, files in (
                ("pos", pos, self._survivor_pos_files),
                ("neg", neg, self._survivor_neg_files),
            ):
                m_vol = np.zeros(mask.shape, np.uint8)
                m_vol[mask] = sel
                m_img = nib.Nifti1Image(m_vol, z_img.affine)
                m_img.set_data_dtype(np.uint8)
                m_path = os.path.join(
                    out_dir, f"survivor_{name}_zstat{k + 1:02d}.nii.gz"
                )
                nib.save(m_img, m_path)
                files.append(m_path)
        return runtime

    def _list_outputs(self):
        outputs = self._outputs().get()
        outputs["thresh_zstat_files"] = self._thresh_zstat_files
        outputs["survivor_pos_files"] = self._survivor_pos_files
        outputs["survivor_neg_files"] = self._survivor_neg_files
        return outputs
