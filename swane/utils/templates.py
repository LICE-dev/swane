import os
from pathlib import Path
import logging

import nibabel as nib
from filelock import FileLock

_LOCK_TIMEOUT_SECONDS = 3600
_SWANE_TEMPLATE_CACHE = Path.home() / ".cache" / "swane" / "templates"
_SWANE_TEMPLATE_CACHE.mkdir(parents=True, exist_ok=True)


def get_swane_template(
    name: str, resolution: int, desc: str, suffix: str = "T1w", enforce_las: bool = True
) -> str:
    """
    Fetch a template from TemplateFlow, with thread/process-safe locking.
    Optionally reorients the template to LAS (radiological) convention.

    Parameters
    ----------
    name : str
        Template name (e.g. 'MNI152NLin6Asym')
    resolution : int
        Resolution in mm (e.g. 1 or 2)
    desc : str
        Description (e.g. 'brain')
    suffix : str
        Suffix (e.g. 'T1w')
    enforce_las : bool
        If True, ensures the returned NIfTI is in LAS orientation.

    Returns
    -------
    str
        Path to the requested template (in LAS if requested).
    """
    
    # We use a global lock file to prevent concurrent TemplateFlow downloads
    # and concurrent RAS-to-LAS conversions.
    lock_path = _SWANE_TEMPLATE_CACHE / ".templateflow_fetch.lock"
    lock = FileLock(str(lock_path))

    with lock.acquire(timeout=_LOCK_TIMEOUT_SECONDS):
        try:
            import templateflow.api as tf
        except ImportError:
            raise ImportError(
                "templateflow is required but not installed. Please install it."
            )

        # Download or retrieve from TemplateFlow cache
        # tf.get returns a string or Path depending on version, we force it to string.
        # It handles the download if it's missing.
        try:
            tf_path_obj = tf.get(name, resolution=resolution, desc=desc, suffix=suffix)
        except Exception:
            tf_path_obj = []
        
        # tf.get might return a list if multiple files match. We want a single file.
        if isinstance(tf_path_obj, list):
            if not tf_path_obj:
                if desc == "brain" and suffix == "T1w":
                    # Fallback: compute it from the whole-head T1w and brain mask
                    return _compute_brain_template(name, resolution, enforce_las)
                raise ValueError(f"TemplateFlow returned no matches for {name} res-{resolution} {desc} {suffix}")
            tf_path = str(tf_path_obj[0])
        else:
            tf_path = str(tf_path_obj)
            
        if not tf_path or not os.path.exists(tf_path):
            raise FileNotFoundError(f"Failed to retrieve template: {name} from TemplateFlow.")

        if not enforce_las:
            return tf_path

        # Handle LAS enforcement
        # We save the LAS converted file in the SWANe cache to avoid modifying TemplateFlow's cache
        las_filename = f"{name}_res-{resolution}_desc-{desc}_{suffix}_LAS.nii.gz"
        las_path = _SWANE_TEMPLATE_CACHE / las_filename

        if las_path.exists():
            return str(las_path)

        # Convert to LAS
        img = nib.load(tf_path)
        axcodes = nib.aff2axcodes(img.affine)

        if axcodes == ("L", "A", "S"):
            # It is already LAS, just create a symlink to avoid copying
            os.symlink(tf_path, str(las_path))
            return str(las_path)

        logging.getLogger(__name__).info(f"Reorienting {name} to LAS convention...")
        
        # Find the transform from current orientation to LAS
        current_ornt = nib.orientations.io_orientation(img.affine)
        target_ornt = nib.orientations.axcodes2ornt(("L", "A", "S"))
        transform = nib.orientations.ornt_transform(current_ornt, target_ornt)

        # Apply the transform
        las_img = img.as_reoriented(transform)
        
        las_path.parent.mkdir(parents=True, exist_ok=True)
        nib.save(las_img, str(las_path))

        return str(las_path)


def _compute_brain_template(name: str, resolution: int, enforce_las: bool) -> str:
    """Compute a skull-stripped template by multiplying the T1w and brain mask."""
    import templateflow.api as tf
    import nibabel as nib
    
    try:
        t1w_obj = tf.get(name, resolution=resolution, desc=None, suffix="T1w")
    except Exception:
        t1w_obj = []
    try:
        mask_obj = tf.get(name, resolution=resolution, desc="brain", suffix="mask")
    except Exception:
        mask_obj = []
        
    if isinstance(t1w_obj, list):
        if not t1w_obj:
            raise ValueError(f"TemplateFlow returned no matches for {name} res-{resolution} T1w")
        t1w_obj = t1w_obj[0]
        
    if isinstance(mask_obj, list):
        if not mask_obj:
            raise ValueError(f"TemplateFlow returned no matches for {name} res-{resolution} brain mask")
        mask_obj = mask_obj[0]

    cache_name = f"{name}_res-{resolution}_desc-brain_T1w"
    if enforce_las:
        cache_name += "_LAS.nii.gz"
    else:
        cache_name += ".nii.gz"
        
    out_path = _SWANE_TEMPLATE_CACHE / cache_name
    if out_path.exists():
        return str(out_path)
        
    # Multiply
    t1w_img = nib.load(str(t1w_obj))
    mask_img = nib.load(str(mask_obj))
    
    data = t1w_img.get_fdata() * (mask_img.get_fdata() > 0)
    
    brain_img = nib.Nifti1Image(data, t1w_img.affine, t1w_img.header)
    
    if enforce_las:
        current_axcodes = nib.orientations.aff2axcodes(brain_img.affine)
        if current_axcodes != ("L", "A", "S"):
            current_ornt = nib.orientations.io_orientation(brain_img.affine)
            las_ornt = nib.orientations.axcodes2ornt(("L", "A", "S"))
            transform = nib.orientations.ornt_transform(current_ornt, las_ornt)
            brain_img = brain_img.as_reoriented(transform)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    nib.save(brain_img, str(out_path))
    return str(out_path)
