"""Test-only override of the shipped FSL dependency policy.

TEMPORARY: remove this module, its two callers (``swane/tests/conftest.py`` and
``swane/tests/prerelease/__main__.py``), its test
``swane/tests/config/test_fsl_policy_override.py`` and the
``SWANE_TEST_FSL_MANDATORY`` variable of ``.github/workflows/windows-tests.yml``
once ``dependency_policy.FSL_MANDATORY`` ships as ``False`` again, or Windows
support no longer requires FSL.

FSL has no Windows build, so with the shipped ``FSL_MANDATORY = True`` a Windows
test run treats FSL as a missing mandatory dependency (e.g. the prerelease plan
blocks on it). Setting ``SWANE_TEST_FSL_MANDATORY=0`` (only the Windows CI
runner does) makes the test process behave as if FSL were only recommended.
The application code path never reads the variable.
"""

import os

ENV_VAR = "SWANE_TEST_FSL_MANDATORY"


def fsl_policy_overridden() -> bool:
    """Return True when the test run asks for the FSL-recommended policy."""
    return os.environ.get(ENV_VAR) == "0"


def apply_fsl_policy_override() -> bool:
    """
    Switch this process to ``FSL_MANDATORY = False`` when requested.

    Patches the constant and every value derived from it at import time:
    ``preference_list.DEFAULT_ENGINES`` (updated in place) and the default of
    each engine ``PreferenceEntry``. The other readers look the constant up at
    call time.

    Returns
    -------
    True if the override was applied.
    """
    if not fsl_policy_overridden():
        return False

    from swane.config import dependency_policy, preference_list
    from swane.config.config_enums import GlobalPrefCategoryList

    dependency_policy.FSL_MANDATORY = False
    engines = dependency_policy.default_engines(False)
    preference_list.DEFAULT_ENGINES.update(engines)
    synth = preference_list.GLOBAL_PREFERENCES[GlobalPrefCategoryList.SYNTH]
    for key, engine in engines.items():
        synth[key].default = engine
    return True
