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

Compressed results
------------------

A Polytope server may compress a result and serve it with a ``Content-Encoding``. The client decodes the stream while downloading it, so the file on disk is the same whether the result travelled compressed or not.

Two options control this, both settable per client, per call (``retrieve``, ``download``), in the configuration file, or through the environment (``POLYTOPE_COMPRESSION``, ``POLYTOPE_DECOMPRESS``):

``compression``
   Codec advertised to the server: ``auto`` (default), ``none``, ``gzip`` or ``zstd``. ``auto`` offers ``zstd, gzip``, the codecs the client can decode, and falls back to ``gzip`` alone when the installed ``urllib3`` has no zstd decoder. The codec a result is stored with is settled when the request is submitted, and an asynchronous ``Result`` remembers it so that its ``download()`` asks for the same one.

``decompress``
   Whether to decompress the result while downloading it (``True``, default). With ``False`` the compressed stream is saved as received and the suffix of the codec the server used (``.gz`` or ``.zst``) is appended to the output file name; a result that was not compressed keeps the name asked for.

.. code-block:: python

   from polytope.api import Client

   c = Client(compression='zstd')
   c.retrieve('ecmwf-mars', request, 'output.grib', compression = 'none')
   c.retrieve('ecmwf-mars', request, 'output.covjson', decompress = False)  # writes output.covjson.gz or .zst

zstd needs nothing installed by hand: ``urllib3 >= 2.5`` and ``backports.zstd`` (on Python before 3.14, which provides ``compression.zstd`` in the standard library) are dependencies of this client, so every supported installation can decode zstd. ``urllib3`` 2.5 is the first version that decodes zstd with either of those two; ``urllib3`` before 2.5 used the ``zstandard`` package instead, which the client still decodes results with when it finds it. ``zstd`` is only advertised when ``urllib3`` itself can decode it, which the client settles by asking ``urllib3`` which codecs it found decoders for, because every response other than a result (the JSON of a submission, a poll or an error) is decoded by ``urllib3`` and not by this client; an installation that pushed ``urllib3`` below the pin asks for ``gzip`` alone, with a warning.

A result served with an encoding the client cannot decode (for example ``br`` or ``deflate``), or ``zstd`` without a zstd decoder, is an error rather than a wrongly decoded file. With ``pointer = True`` the ``contentLength`` reported by the server is the size of the compressed result when the result is stored compressed.
