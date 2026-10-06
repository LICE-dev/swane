import os
from pathlib import Path

import numpy as np

from swane.utils.templates import _SWANE_TEMPLATE_CACHE, get_swane_template

XFM_DIR = Path(__file__).parent.parent / "resources" / "priors"
XFM_AFFINE = "tpl-MNI152NLin6Asym_from-MNI152NLin2009cAsym_desc-swaneSyN_affine.mat"
XFM_WARP = "tpl-MNI152NLin6Asym_from-MNI152NLin2009cAsym_desc-swaneSyN_warp.nii.gz"
PRIOR = "tpl-MNI152NLin6Asym_res-02_label-WM_desc-fromNLin2009cAsymP95_mask.nii.gz"
WM_PROBSEG_THRESHOLD = 0.95


def nlin6_wm_prior(cache_dir: str | None = None) -> str:
    """
    Return the binary white-matter prior on the MNI152NLin6Asym 2 mm grid.

    The prior is built by fetching the MNI152NLin2009cAsym white-matter
    posterior probability map from TemplateFlow, moving it onto the
    MNI152NLin6Asym grid with SWANe's shipped ANTs transform, and
    thresholding the result at `WM_PROBSEG_THRESHOLD`. The output grid
    matches `get_swane_template("MNI152NLin6Asym", resolution=2,
    desc="brain", enforce_las=True)`, the same target used elsewhere for
    registration to the MNI152NLin6Asym atlas.

    The result is cached under `cache_dir` (default: SWANe's template
    cache) and reused on later calls without recomputation. A file lock
    serializes concurrent builds across processes, and the file is written
    under a temporary name and renamed, so a partial file is never returned.

    Parameters
    ----------
    cache_dir : str or None, optional
        Directory to cache the prior in. Defaults to SWANe's template
        cache directory.

    Returns
    -------
    str
        Path to the binary (uint8, 0/1) white-matter prior.
    """
    if cache_dir is None:
        cache_dir = str(_SWANE_TEMPLATE_CACHE)

    out = os.path.join(cache_dir, PRIOR)
    if os.path.exists(out):
        return out

    import ants
    import templateflow.api as tf
    from filelock import FileLock

    os.makedirs(cache_dir, exist_ok=True)

    # The fixed image only defines the output grid: ants.apply_transforms
    # resamples the moving image in physical space, so enforcing LAS on the
    # reference here does not affect the transform's correctness and keeps
    # this grid identical to the one used downstream for MNI152NLin6Asym
    # registration. It is fetched before taking the lock below, because
    # get_swane_template takes the same lock file in the default cache
    # directory, and a second lock on that file in this process would never
    # be acquired.
    ref_path = get_swane_template(
        name="MNI152NLin6Asym", resolution=2, desc="brain", enforce_las=True
    )

    lock_path = Path(cache_dir) / ".templateflow_fetch.lock"
    with FileLock(str(lock_path)):
        if os.path.exists(out):
            return out

        tf_path_obj = tf.get(
            "MNI152NLin2009cAsym", resolution=2, label="WM", suffix="probseg"
        )
        if isinstance(tf_path_obj, list):
            tf_path = str(tf_path_obj[0])
        else:
            tf_path = str(tf_path_obj)

        wm = ants.image_read(tf_path)

        ref_img = ants.image_read(ref_path)

        transformlist = [str(XFM_DIR / XFM_WARP), str(XFM_DIR / XFM_AFFINE)]

        wm_n6 = ants.apply_transforms(
            fixed=ref_img, moving=wm, transformlist=transformlist, interpolator="linear"
        )

        binary = (wm_n6.numpy() > WM_PROBSEG_THRESHOLD).astype(np.uint8)
        # Write next to the cached path and rename: the rename is atomic on
        # one filesystem, so the lock-free check above never sees a partial
        # file, and an interrupted write leaves nothing at the cached path.
        tmp = os.path.join(cache_dir, ".tmp-%d-%s" % (os.getpid(), PRIOR))
        try:
            ants.image_write(wm_n6.new_image_like(binary), tmp)
            os.replace(tmp, out)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)

    return out
