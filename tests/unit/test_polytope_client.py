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

import pytest
from conftest import ValueStorage
from packaging import version

import polytope
from polytope.api import Client


def test_version():
    try:
        ValueStorage.version = version.Version(polytope.__version__)
    except Exception:
        pytest.fail("Failed parsing polytope-client version.")


def test_session_config():
    # address, port
    a = "aaa.com"
    p = 123
    c = Client(address=a, port=p, config_path=ValueStorage.config_path)
    assert c.config.get()["address"] == a
    assert c.config.get()["port"] == p
    assert c.config.get_url("api_root").startswith("https://" + a + ":" + str(p))

    # username
    u = "a"
    c = Client(username=u, config_path=ValueStorage.config_path)
    assert c.config.get()["username"] == u


def test_session_config_port_in_address():
    a = "aaa.com:123"
    p = 200
    c = Client(address=a, port=p, config_path=ValueStorage.config_path)
    url = c.config.get_url("api_root")
    assert url.startswith("https://" + a)


def test_session_config_http():
    a = "https://aaa.com"
    c = Client(address=a, config_path=ValueStorage.config_path)
    url = c.config.get_url("api_root")
    assert url.startswith(a)
    # HTTP is still elevated to HTTPS port by default
    assert ":443" in url


def test_session_config_address_path():
    a = "aaa.com:32/abc"
    c = Client(address=a, config_path=ValueStorage.config_path)
    url = c.config.get_url("api_root")
    assert url.startswith("https://" + a)
    assert "/abc" in url
    assert ":32" in url


def test_session_config_address_path_with_port():
    a = "aaa.com/abc"
    c = Client(address=a, port=32, config_path=ValueStorage.config_path)
    url = c.config.get_url("api_root")
    assert url.startswith("https://aaa.com:32/abc")


def test_session_config_invalid_scheme():
    a = "ftp://aaa.com/abc"
    c = Client(address=a, config_path=ValueStorage.config_path)
    with pytest.raises(ValueError):
        c.config.get_url("api_root")


def test_session_config_invalid_host():
    a = "ftp:aaa.com/abc"
    c = Client(address=a, config_path=ValueStorage.config_path)
    with pytest.raises(ValueError):
        c.config.get_url("api_root")
