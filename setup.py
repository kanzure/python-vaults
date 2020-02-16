#!/usr/bin/env python3

from setuptools import setup, find_packages
import os

from vaults.__version__ import __version__

here = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(here, "README.md")) as fd:
    README = fd.read()

# see requirements.txt for explanations
install_requires = [
    #"python-bitcoinlib==0.11.0dev",
    "click>=7.0",
]

setup(name="python-vaults",
      version=__version__,
      description="Bitcoin cold storage system focused on theft minimization.",
      long_description=README,
      long_description_content_type="text/markdown",
      classifiers=[
        "Programming Language :: Python",
      ],
      url="https://github.com/kanzure/python-vaults",
      keywords="bitcoin",
      packages=find_packages(),
      zip_safe=False,
      include_package_data=True,
      install_requires=install_requires,
      test_suite="vaults.tests",
      entry_points="""
        [console_scripts]
        vault=vaults.cli:cli
      """,
)
