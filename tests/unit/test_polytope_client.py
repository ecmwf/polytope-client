import pytest
from conftest import ValueStorage
from packaging import version

import polytope


def test_version():
    try:
        ValueStorage.version = version.Version(polytope.__version__)
    except Exception:
        pytest.fail("Failed parsing polytope-client version.")
