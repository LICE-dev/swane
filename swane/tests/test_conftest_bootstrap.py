"""Guard the ordering contract of the repository-root ``conftest.py``.

pytest imports the ``swane`` package (and with it ``nipype.interfaces.fsl``)
before ``swane/tests/conftest.py`` runs. Nipype picks FILMGLS's input spec at
that first import from the detected FSL version, so the nipype version fallback
must be installed by the root ``conftest.py``; otherwise a box without FSL gets
the reduced spec that lacks ``tcon_file``/``fcon_file``.
"""

import subprocess
import sys
import textwrap

from nipype.interfaces.fsl.model import FILMGLS


def test_filmgls_uses_the_full_input_spec():
    assert "tcon_file" in FILMGLS().inputs.trait_names()


def test_root_conftest_runs_before_swane_import(tmp_path):
    """Fresh interpreter without FSL: loading the root conftest first must give
    the full FILMGLS spec even though importing swane pulls nipype's FSL
    package in."""
    import os

    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    code = textwrap.dedent("""
        import sys
        sys.path.insert(0, %r)
        import conftest  # repository-root bootstrap
        assert "swane" not in sys.modules
        import swane  # noqa: F401  (imports nipype.interfaces.fsl)
        from nipype.interfaces.fsl.model import FILMGLS
        assert "tcon_file" in FILMGLS().inputs.trait_names()
        """ % root)
    env = {
        k: v for k, v in os.environ.items() if not k.startswith("FSL") and k != "FSLDIR"
    }
    env["PATH"] = os.pathsep.join(
        p for p in env.get("PATH", "").split(os.pathsep) if "fsl" not in p.lower()
    )
    result = subprocess.run(
        [sys.executable, "-c", code], env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
