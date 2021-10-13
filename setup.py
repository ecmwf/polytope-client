# (C) Copyright 1996- ECMWF.
#
# This software is licensed under the terms of the Apache Licence Version 2.0
# which can be obtained at http://www.apache.org/licenses/LICENSE-2.0.
# In applying this licence, ECMWF does not waive the privileges and immunities
# granted to it by virtue of its status as an intergovernmental organisation
# nor does it submit to any jurisdiction.

from setuptools import setup, find_packages
import re, io

__version__ = re.search(
    r'__version__\s*=\s*[\'"]([^\'"]*)[\'"]',
    io.open('polytope/version.py', encoding='utf_8_sig').read()
).group(1)

setup(
    name = 'polytope-client',
    version = __version__,
    description = 'A Python and command-line client to communicate with a Polytope API server.',
    url = 'https://github.com/ecmwf-projects/polytope-client',
    author = 'ECMWF',
    author_email = 'software.support@ecmwf.int',
    packages = find_packages(exclude = ("tests")),
    install_requires = [],
    zip_safe = False,
    include_package_data = True,
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: Apache Software License",
        "Natural Language :: English",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3 :: Only",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
    ],
)
