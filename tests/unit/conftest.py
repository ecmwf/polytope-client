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

import os
import tempfile

import pytest


class ValueStorage:
    config_path = tempfile.gettempdir()


@pytest.fixture(autouse=True)
def without_polytope_environment(monkeypatch):
    """Keep the environment of whoever runs the tests out of the configuration.

    A POLYTOPE_* variable exported in the shell (POLYTOPE_COMPRESSION, say) is
    read by every client the tests build, and would otherwise decide what the
    code under test does.
    """
    for name in list(os.environ):
        if name.startswith("POLYTOPE_"):
            monkeypatch.delenv(name, raising=False)
