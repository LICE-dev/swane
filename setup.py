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
          "nipype==1.8.6",
          "Pyside6==6.4.3",
          "pydicom==2.3.1",
          "configparser==5.3.0",
          "psutil==5.9.4",
          "pyshortcuts==1.8.3",
          "swane_supplement>=0.1.2",
          "matplotlib==3.5.2",
          "nibabel==5.0.0"
      ],
      python_requires=">=3.7",
      entry_points={
          'gui_scripts': [
              "swane = swane.__main__:main"
          ]
      }

      )
