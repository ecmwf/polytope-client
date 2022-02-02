# Copyright 2021 European Centre for Medium-Range Weather Forecasts (ECMWF)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# In applying this licence, ECMWF does not waive the privileges and immunities
# granted to it by virtue of its status as an intergovernmental organisation nor
# does it submit to any jurisdiction.

import io
import re

from setuptools import find_packages, setup

__version__ = re.search(
    r'__version__\s*=\s*[\'"]([^\'"]*)[\'"]', io.open("polytope/version.py", encoding="utf_8_sig").read()
).group(1)

setup(
    name="polytope-client",
    version=__version__,
    description="A Python and command-line client to communicate with a Polytope API server.",
    url="https://github.com/ecmwf-projects/polytope-client",
    author="ECMWF",
    author_email="software.support@ecmwf.int",
    packages=find_packages(exclude=("docs", "tests")),
    install_requires=["Click", "requests", "pyyaml", "jsonschema", "docstring_parser", "tqdm"],
    zip_safe=False,
    include_package_data=True,
    entry_points={
        "console_scripts": [
            "polytope = polytope.cli.cli:cli",
        ]
    },
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
