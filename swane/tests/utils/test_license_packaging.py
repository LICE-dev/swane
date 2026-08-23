import os
from swane.utils import LicenseReference as LR


def test_all_bundled_licenses_declared_and_present():
    licenses_dir = os.path.normpath(
        os.path.join(os.path.dirname(LR.__file__), "..", "licenses")
    )
    for info in LR.LICENSES.values():
        assert os.path.isfile(os.path.join(licenses_dir, info.bundled_filename))
