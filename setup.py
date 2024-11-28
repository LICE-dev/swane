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
      packages=find_packages(exclude=["swane.tests"]),
      classifiers=[
          "Programming Language :: Python :: 3",
          "License :: OSI Approved :: MIT License",
          "Operating System :: MacOS",
          "Operating System :: POSIX :: Linux",
      ],
      license='MIT',
      install_requires=[
          "networkx<3", # check compatibility with nipype before upgrading
          "nipype==1.8.6",
          "Pyside6",
          "pydicom<=3.0.1",
          "configparser<=7.1.0",
          "psutil<=6.0.0",
          "swane_supplement>=0.1.2",
          "matplotlib<=3.9.2",
          "nibabel<=5.3.0",
          "packaging",
          "PySide6_VerticalQTabWidget==0.0.3",
          "GPUtil==1.4.0",
          "numpy<=2", # check compatibility with nibabel e CropFov node before upgrading!
            #Error for fmri art with numpy>=2
            # File "site-packages/nipype/algorithms/rapidart.py", line 693, in _run_interface
            # 	    self._detect_outliers_core(imgf, motparamlist[i], i, cwd=os.getcwd())
            # 	  File "site-packages/nipype/algorithms/rapidart.py", line 610, in _detect_outliers_core
            # 	    np.savetxt(artifactfile, outliers, fmt=b"%d", delimiter=" ")
            # 	  File "site-packages/numpy/lib/_npyio_impl.py", line 1627, in savetxt
            # 	    raise ValueError('invalid fmt: %r' % (fmt,))
            # 	ValueError: invalid fmt: b'%d'
          "cryptography"
      ],
      python_requires=">=3.7",
      entry_points={
          'gui_scripts': [
              "swane = swane.__main__:main"
          ]
      }

      )
