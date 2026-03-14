# -*- coding: utf-8 -*-

from setuptools import setup, find_packages
import re


def get_property(prop):
    result = re.search(
        r'{}\s*=\s*[\'"]([^\'"]*)[\'"]'.format(prop), open("swane/__init__.py").read()
    )
    return result.group(1)


setup(
    name="swane",
    version=get_property("__version__"),
    description="Standardized Workflow for Advanced Neuroimaging in Epilepsy",
    author="LICE - Commissione Neuroimmagini",
    author_email="dev@lice.it",
    packages=find_packages(exclude=["swane.tests"]),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: MacOS",
        "Operating System :: POSIX :: Linux",
    ],
    # TODO: forse dobbiamo citare tutte le sottolicenze
    # https://packaging.python.org/en/latest/guides/licensing-examples-and-user-scenarios/#my-package-includes-other-code-under-different-licenses
    license="MIT",
    install_requires=[
        "networkx==3.4.2",
        "nipype==1.10.0",
        "PySide6",
        "pydicom==3.0.1",
        "configparser<=7.1.0",
        "psutil==7.0.0",
        # TODO: passare a swane_supplement 0.2
        "swane_supplement>=0.1.2",
        "matplotlib==3.10.1",
        # todo: METTIAMO NIBABEL 5.2 come minima per essere più inclusivi?
        "nibabel>=5.3.0,<6",
        "packaging",
        "PySide6_VerticalQTabWidget==0.0.3",
        "numpy==2.2.4",
        "cryptography",
        "dicom-sequence-classifier==1.0.4",
        "ica_aroma_py==0.1.2",
        "SimpleITK>=2.5.0",
    ],
    python_requires=">=3.10",
    entry_points={"gui_scripts": ["swane = swane.__main__:main"]},
)
