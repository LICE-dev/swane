# -*- coding: utf-8 -*-

from setuptools import setup, find_packages
import re


def get_property(prop):
    with open("swane/__init__.py") as f:
        content = f.read()
    result = re.search(r'{}\s*=\s*[\'"]([^\'"]*)[\'"]'.format(prop), content)
    return result.group(1)


setup(
    name="swane",
    version=get_property("__version__"),
    description="Standardized Workflow for Advanced Neuroimaging in Epilepsy",
    author="LICE - Commissione Neuroimmagini",
    author_email="dev@lice.it",
    packages=find_packages(exclude=["swane.tests", "swane.tests.*"]),
    include_package_data=True,
    package_data={
        "swane": [
            "licenses/*.txt",
            "resources/icons/*",
            "resources/atlas/*",
            "resources/atlas/FLAT1/*",
        ]
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: MacOS",
        "Operating System :: POSIX :: Linux",
    ],
    # TODO: maybe we should cite all sublicenses
    # https://packaging.python.org/en/latest/guides/licensing-examples-and-user-scenarios/#my-package-includes-other-code-under-different-licenses
    license="MIT",
    install_requires=[
        "networkx==3.4.2",
        "nipype==1.12.0",
        "PySide6",
        "pydicom==3.0.2",
        "psutil==7.0.0",
        # 3.10.7 is the first release with CPython 3.14 wheels: the 3.10.1 pin
        # forces a source build there. Range keeps ica_aroma_py[plots] (>=3.10.1) valid.
        "matplotlib>=3.10.1,<3.11",
        # todo: SET NIBABEL 5.2 as minimum to be more inclusive?
        "nibabel>=5.3.0,<6",
        "nitransforms>=25.1.0",
        "dcm2niix>=1.0.20241211,<=1.0.20260724",
        "niimath==1.0.20260924",
        "packaging",
        "PySide6_VerticalQTabWidget==0.0.3",
        # 1.12.1, not 1.12.0: the 1.12.0 macosx_15_0_arm64 wheel (preferred by pip
        # on Apple Silicon with macOS >= 15) does not bundle libomp and links
        # /opt/homebrew/opt/libomp/lib/libomp.dylib, so importing dipy fails
        # without Homebrew libomp. 1.12.1 ships only macosx_11_0 wheels, which
        # bundle it.
        "dipy==1.12.1",
        "dicom-sequence-classifier==1.0.5",
        # 0.1.4 fixes AromaClassification returning a scalar (TraitError)
        # when exactly one component is classified as motion.
        "ica_aroma_py==0.1.4",
        "nilearn==0.10.4",
        "scikit-learn>=1.5.0",
        # Intel macOS: antspyx 0.6.1 provides x86_64 wheels for macOS 13 (Ventura)
        # and later (including 14 and 15). Versions >=0.6.2 only provide wheels
        # for macOS 15, which forces older Macs to build from source (taking hours).
        "antspyx==0.6.1; sys_platform=='darwin' and platform_machine=='x86_64'",
        "antspyx>=0.6.2; sys_platform!='darwin' or platform_machine!='x86_64'",
        # antspynet 0.3.2 requires antspyx >=0.6.1.
        # Keep >=0.3.2 to ensure compatibility with the antspyx version
        # required for Intel macOS.
        "antspynet>=0.3.2",
        # CA bundle for the antspynet weights download (python.org macOS builds
        # have no system certificates): see swane/utils/antspynet_weights.py.
        "certifi",
        # Nipype 1.12 requires numpy >= 2.2.0.
        "numpy>=2.2.0",
        # macOS Intel: PyPI has no TensorFlow >= 2.17 wheels; installer/install_swane.sh installs it from conda-forge.
        "tensorflow>=2.20.0; sys_platform!='darwin' or platform_machine!='x86_64'",
        # Intel macOS: cryptography >=49 no longer provides x86_64 wheels.
        "cryptography<49; sys_platform=='darwin' and platform_machine=='x86_64'",
        "cryptography>=0; sys_platform!='darwin' or platform_machine!='x86_64'",
        # Now direct dependencies, no longer transitive: threadpoolctl pins the
        # BLAS pool in DipyMotionCorrection, filelock serialises the HCP842 atlas
        # fetch in DipyAtlasSLR.
        "threadpoolctl==3.6.0",
        # scipy>=1.17.1 prevent a macos bug with PROPACK, but it conflicts
        # with antspyx < 0.6.4 (which forces scipy < 1.16). We now handle the
        # PROPACK bug with a monkeypatch in swane.patches.scipy_patches instead.
        "filelock>=3.20.3,<4",
        "templateflow>=24.0.0",
        "vtk",
    ],
    python_requires=">=3.12",
    entry_points={"gui_scripts": ["swane = swane.__main__:main"]},
)
