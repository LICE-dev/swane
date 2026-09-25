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
        # Intel macOS: antspyx versions before 0.6.2 do not provide the required
        # macOS 15 x86_64 wheels; 0.6.2 is the first verified compatible release.
        "antspyx>=0.6.2",
        # On intel macos the last published tensorflow version is 2.16.2
        # and it requires numpy <2
        "numpy>=2; not (sys_platform=='darwin' and platform_machine=='x86_64')",
        "numpy>=1.26,<2; sys_platform=='darwin' and platform_machine=='x86_64'",
        "tensorflow>=2.20.0; not (sys_platform=='darwin' and platform_machine=='x86_64')",
        "tensorflow>=2.16.2; sys_platform=='darwin' and platform_machine=='x86_64'",
        # Intel macOS: cryptography >=49 no longer provides x86_64 wheels.
        "cryptography<49; sys_platform=='darwin' and platform_machine=='x86_64'",
        "cryptography; not (sys_platform=='darwin' and platform_machine=='x86_64')",
        # Now direct dependencies, no longer transitive: threadpoolctl pins the
        # BLAS pool in DipyMotionCorrection, filelock serialises the HCP842 atlas
        # fetch in DipyAtlasSLR.
        "threadpoolctl==3.6.0",
        "filelock==3.17.0",
        "templateflow>=24.0.0",
        "vtk",
    ],
    python_requires=">=3.10",
    entry_points={"gui_scripts": ["swane = swane.__main__:main"]},
)
