import os
import shutil
from pathlib import Path
import logging

import nibabel as nib
from filelock import FileLock

_LOCK_TIMEOUT_SECONDS = 3600
_SWANE_TEMPLATE_CACHE = Path.home() / ".cache" / "swane" / "templates"
_SWANE_TEMPLATE_CACHE.mkdir(parents=True, exist_ok=True)


def template_cache_path(
    name: str, resolution: int, desc: str, suffix: str = "T1w"
) -> Path:
    """Return where the LAS version of a template lives in the SWANe cache."""
    return (
        _SWANE_TEMPLATE_CACHE
        / f"{name}_res-{resolution}_desc-{desc}_{suffix}_LAS.nii.gz"
    )


def is_template_cached(
    name: str, resolution: int, desc: str, suffix: str = "T1w"
) -> bool:
    """Return True if the LAS version of a template is already in the cache.

    A cheap filesystem check that never touches TemplateFlow. The cache is only
    ever populated by an atomic rename (see :func:`_atomic_save`), so a file
    found here is complete.
    """
    return template_cache_path(name, resolution, desc, suffix).exists()


def _atomic_save(final_path: Path, write) -> None:
    """Create ``final_path`` by calling ``write(tmp_path)`` and renaming.

    The cache is read without a lock (``is_template_cached``), so the final name
    must never exist half-written: a process killed during the write would leave
    a truncated file that every later call trusts. The temporary file lives in
    the same directory, where ``os.replace`` is atomic on Linux, macOS and
    Windows, and keeps the ``.nii.gz`` ending so nibabel picks the format.

    Parameters
    ----------
    final_path : Path
        Destination, replaced if present.
    write : callable
        Called with the temporary path, which it must create.
    """
    tmp_path = final_path.with_name(f".{final_path.name}.{os.getpid()}.tmp.nii.gz")
    try:
        write(tmp_path)
        os.replace(tmp_path, final_path)
    finally:
        tmp_path.unlink(missing_ok=True)


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
    # Check SWANe cache first if enforcing LAS to avoid slow TemplateFlow initialization
    if enforce_las and is_template_cached(name, resolution, desc, suffix):
        return str(template_cache_path(name, resolution, desc, suffix))

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
                raise ValueError(
                    f"TemplateFlow returned no matches for {name} res-{resolution} {desc} {suffix}"
                )
            tf_path = str(tf_path_obj[0])
        else:
            tf_path = str(tf_path_obj)

        if not tf_path or not os.path.exists(tf_path):
            raise FileNotFoundError(
                f"Failed to retrieve template: {name} from TemplateFlow."
            )

        if not enforce_las:
            return tf_path

        # Handle LAS enforcement
        # We save the LAS converted file in the SWANe cache to avoid modifying TemplateFlow's cache
        las_path = template_cache_path(name, resolution, desc, suffix)

        # If it was cached during another process's lock hold, return it
        if las_path.exists():
            return str(las_path)

        # Convert to LAS
        img = nib.load(tf_path)
        axcodes = nib.aff2axcodes(img.affine)

        if axcodes == ("L", "A", "S"):
            # Already LAS: copy it (the file is small). Not a symlink: it would
            # dangle if the TemplateFlow cache is purged and some filesystems
            # (Windows without Developer Mode) refuse it.
            _atomic_save(las_path, lambda tmp: shutil.copyfile(tf_path, tmp))
            return str(las_path)

        logging.getLogger(__name__).info(f"Reorienting {name} to LAS convention...")

        # Find the transform from current orientation to LAS
        current_ornt = nib.orientations.io_orientation(img.affine)
        target_ornt = nib.orientations.axcodes2ornt(("L", "A", "S"))
        transform = nib.orientations.ornt_transform(current_ornt, target_ornt)

        # Apply the transform
        las_img = img.as_reoriented(transform)

        las_path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_save(las_path, lambda tmp: nib.save(las_img, str(tmp)))

        return str(las_path)


def _compute_brain_template(name: str, resolution: int, enforce_las: bool) -> str:
    """Compute a skull-stripped template by multiplying the T1w and brain mask."""

    if enforce_las:
        out_path = template_cache_path(name, resolution, "brain")
    else:
        out_path = (
            _SWANE_TEMPLATE_CACHE / f"{name}_res-{resolution}_desc-brain_T1w.nii.gz"
        )
    if out_path.exists():
        return str(out_path)

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
            raise ValueError(
                f"TemplateFlow returned no matches for {name} res-{resolution} T1w"
            )
        t1w_obj = t1w_obj[0]

    if isinstance(mask_obj, list):
        if not mask_obj:
            raise ValueError(
                f"TemplateFlow returned no matches for {name} res-{resolution} brain mask"
            )
        mask_obj = mask_obj[0]

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
    _atomic_save(out_path, lambda tmp: nib.save(brain_img, str(tmp)))
    return str(out_path)
