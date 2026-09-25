# -*- coding: utf-8 -*-

from setuptools import setup, find_packages
import re
import sys
import platform

if sys.platform == "darwin" and platform.machine() == "x86_64":
    try:
        import tensorflow
    except ImportError:
        import os

        is_conda = "CONDA_PREFIX" in os.environ

        msg = (
            "\n"
            "========================================================================\n"
            "ERROR: TensorFlow is missing on macOS Intel.\n"
            "Because PyPI does not provide pre-compiled wheels for TensorFlow >= 2.17\n"
            "on this architecture, pip will fail to install it or try to compile it\n"
            "from source (which takes hours).\n\n"
        )

        if is_conda:
            msg += "Please install TensorFlow using Conda before installing SWANe:\n"
        else:
            msg += (
                "You MUST use a Conda environment to install SWANe on this architecture.\n"
                "Please create one, activate it, and install TensorFlow via conda-forge:\n"
                "    conda create -n swane_env python=3.12\n"
                "    conda activate swane_env\n"
            )

        msg += (
            '    conda install -c conda-forge "tensorflow>=2.18"\n'
            "    pip install swane\n"
            "========================================================================\n"
        )
        print(msg)
        sys.exit(1)


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
        "pydicom==3.0.1",
        "psutil==7.0.0",
        "matplotlib==3.10.1",
        # todo: SET NIBABEL 5.2 as minimum to be more inclusive?
        "nibabel>=5.3.0,<6",
        "nitransforms>=25.1.0",
        "dcm2niix>=1.0.20241211,<=1.0.20260724",
        "niimath==1.0.20260720",
        "packaging",
        "PySide6_VerticalQTabWidget==0.0.3",
        "dipy==1.12.0",
        "dicom-sequence-classifier==1.0.5",
        "ica_aroma_py==0.1.2",
        # Intel macOS: antspyx 0.6.2 is the first verified release with macOS 15
        # x86_64 wheels, matching our minimum macOS Sequoia requirement.
        "antspyx>=0.6.2",
        # antspynet 0.3.2 requires antspyx >=0.6.1.
        # Keep >=0.3.2 to ensure compatibility with the antspyx version
        # required for Intel macOS 15.
        "antspynet>=0.3.2",
        # Nipype 1.12 requires numpy >= 2.2.0.
        "numpy>=2.2.0",
        # For macOS Intel, TensorFlow is checked at the top of this script
        # and should be pre-installed via conda-forge.
        "tensorflow>=2.20.0; sys_platform!='darwin' or platform_machine!='x86_64'",
        # Intel macOS: cryptography >=49 no longer provides x86_64 wheels.
        "cryptography<49; sys_platform=='darwin' and platform_machine=='x86_64'",
        "cryptography>=0; sys_platform!='darwin' or platform_machine!='x86_64'",
        # Now direct dependencies, no longer transitive: threadpoolctl pins the
        # BLAS pool in DipyMotionCorrection, filelock serialises the HCP842 atlas
        # fetch in DipyAtlasSLR.
        "threadpoolctl==3.6.0",
        "filelock==3.17.0",
        "templateflow>=24.0.0",
        "vtk",
    ],
    python_requires=">=3.12",
    entry_points={"gui_scripts": ["swane = swane.__main__:main"]},
)
