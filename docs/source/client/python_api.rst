.. _python_api:

Python API and CLI
====================================

A Python API for user-friendly interaction with a Polytope server is available at `polytope-client <https://github.com/ecmwf-projects/polytope-client>`_. It can be installed from source or from PyPI with ``python3 -m pip install polytope-client``.

Once the Python module is installed, it can either be used directly in Python scripts and sessions (i.e. ``from polytope import api``), or be used via the command-line tool that is installed together with the module (i.e. ``which polytope``).

More details on installation and usage can be found in the ``readme.md`` file in the source of `polytope-client <https://github.com/ecmwf-projects/polytope-client>`_, as well as in the documentation of the Python module (e.g. ``help(api)``) and in the documentation of the command-line tool (e.g. ``polytope --help``).

Extra HTTP headers
------------------

The Python client can attach additional HTTP headers to each request. Extra headers are intended only for non-secret, safe metadata/debug headers; do not use them for credentials, cookies, tokens, or other sensitive values.

Constructor usage:

.. code-block:: python

   from polytope.api import Client

   c = Client(extra_headers={"Polytope-Mock-Roles": "beta:viewer"})

Configuration file usage:

.. code-block:: yaml

   extra_headers:
     Polytope-Mock-Roles: beta:viewer

Environment variable usage. The value of ``POLYTOPE_EXTRA_HEADERS`` must be a JSON object string mapping header names to values:

.. code-block:: bash

   export POLYTOPE_EXTRA_HEADERS='{"Polytope-Mock-Roles":"beta:viewer"}'

Administrators can use this with server-side mocking/debug features, for example to test role-dependent behaviour with ``Polytope-Mock-Roles: beta:viewer``.

Unsafe or request-controlled headers are rejected case-insensitively. This includes authentication headers, cookies, hop-by-hop/protocol headers, content/range/checksum headers, and proxy/attribution IP headers. Blocked examples include ``Cookie``, ``Set-Cookie``, ``X-Forwarded-For``, ``X-Real-IP``, ``Forwarded``, and ``X-Proxy-Protocol-Addr``.
