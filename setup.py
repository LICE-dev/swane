# -*- coding: utf-8 -*-

from setuptools import setup, find_packages
import re


def get_property(prop):
    result = re.search(r'{}\s*=\s*[\'"]([^\'"]*)[\'"]'.format(prop), open('swane/__init__.py').read())
    return result.group(1)


setup(name='swane',
      version=get_property('__version__'),
      description='Standardized Workflow for Advanced Neuroimaging in Epilepsy',
      author='LICE - Commissione Neuroimmagini',
      author_email='dev@lice.it',
      packages=find_packages(),
      classifiers=[
          "Programming Language :: Python :: 3",
          "License :: OSI Approved :: MIT License",
          "Operating System :: MacOS",
          "Operating System :: POSIX :: Linux",
      ],
      license='MIT',
      install_requires=[
          "networkx<3",
          "nipype",
          "Pyside6",
          "pydicom",
          "configparser",
          "psutil",
          "pyshortcuts",
          "swane_supplement>=0.1.2",
          "matplotlib",
          "nibabel"
      ],
      python_requires=">=3.7",
      entry_points={
          'gui_scripts': [
              "swane = swane.__main__:main"
          ]
      }

      )
