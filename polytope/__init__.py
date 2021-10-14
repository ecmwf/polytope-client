# (C) Copyright 1996- ECMWF.
#
# This software is licensed under the terms of the Apache Licence Version 2.0
# which can be obtained at http://www.apache.org/licenses/LICENSE-2.0.
# In applying this licence, ECMWF does not waive the privileges and immunities
# granted to it by virtue of its status as an intergovernmental organisation
# nor does it submit to any jurisdiction.

"""This module, the Polytope client, aids in interacting with a
Polytope-managed platform by providing a Command Line Interface
that sends HTTP requests behind the scenes to communicate
with the RESTful API exposed by the Polytope frontend."""

# imports here if needed
from .version import __version__

__all__ = [
    "__version__",
]
