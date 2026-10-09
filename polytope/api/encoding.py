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

"""Content-Encoding support for Polytope downloads.

The Polytope server may store and serve a result compressed, in which case the
HTTP response carries ``Content-Encoding`` and a ``Content-Length`` counting the
*compressed* bytes, and byte ranges address the *compressed* stream. The client
therefore counts the bytes as received, before decoding
(``decode_content=False``), and decodes them with one of the streaming decoders
below, whose state survives a resumed request.

A codec is advertised in ``Accept-Encoding`` only when this module can decode a
result body with it *and* urllib3 can decode the other responses with it, since
those are decoded before the client sees them.
"""

import importlib
import logging
import os
import sys
import zlib

from .helpers import PolytopeError

IDENTITY = "identity"
GZIP = "gzip"
ZSTD = "zstd"

AUTO = "auto"
NONE = "none"

#: Values accepted by the ``compression`` option.
COMPRESSION_OPTIONS = (AUTO, NONE, GZIP, ZSTD)

#: Aliases a server may use for a gzip-encoded body.
GZIP_ALIASES = (GZIP, "x-gzip")

#: File name suffix used when the compressed stream is kept as received.
SUFFIXES = {GZIP: ".gz", ZSTD: ".zst"}

#: Largest amount of data a decoder is asked to produce in one call, so that a
#: single compressed chunk as received cannot expand into gigabytes of memory.
MAX_DECODED_SLICE = 8 * 1024 * 1024

#: Modules that provide a streaming zstd decompressor, in the order urllib3
#: itself tries them: the standard library module (Python 3.14+) and its
#: backport. One of the two is always installed, since 'backports.zstd' is a
#: dependency of this client on every earlier interpreter.
ZSTD_MODULES = ("compression.zstd", "backports.zstd")


def _import(name):
    try:
        return importlib.import_module(name)
    except ImportError:
        return None


def _urllib3_version():
    """Return the installed urllib3 version as (major, minor), or () when unknown."""
    urllib3 = _import("urllib3")
    pieces = str(getattr(urllib3, "__version__", "")).split(".")[:2]
    try:
        return tuple(int(piece) for piece in pieces)
    except ValueError:
        return ()


def zstd_hint():
    """How to give the installed urllib3 a zstd decoder."""
    if sys.version_info >= (3, 14):
        return (
            "use a Python built with zstd support (urllib3 decodes zstd with the standard library's "
            "compression.zstd on Python 3.14 and later)"
        )
    return "reinstall 'backports.zstd', the dependency of this client that urllib3 decodes zstd with"


def zstd_module():
    """Return the module to decode zstd with, or None when none is installed.

    The candidates are tried in the order urllib3 uses them, so that a result
    body is decoded by the same implementation as every other response.
    """
    for name in ZSTD_MODULES:
        module = _import(name)
        if module is not None:
            return module
    return None


def zstd_decoder_available():
    """Whether this module can decode a zstd result body."""
    return zstd_module() is not None


def zstd_decompressobj():
    """Return a streaming zstd decompressor for a single frame.

    Both backends expose ``decompress(data, max_length)``, ``needs_input`` and
    ``eof``, which is what bounds how much a single call may produce.
    """
    module = zstd_module()
    if module is None:
        raise unsupported_encoding_error(ZSTD, reason="no zstd decoder is installed")
    return module.ZstdDecompressor()


def zstd_available():
    """Whether zstd may be advertised in ``Accept-Encoding``.

    This module decodes result bodies only. Every other response (the JSON of
    a submission, a poll, an error) is decoded by urllib3 before the client
    sees it, so advertising a codec urllib3 cannot decode turns those bodies
    into undecodable bytes. urllib3 therefore has the last word, whatever this
    module could decode, and ``BaseHTTPResponse.CONTENT_DECODERS`` is the list
    urllib3 itself consults: ``HAS_ZSTD`` is absent on urllib3 2.0 and 2.1,
    which do decode zstd (through the 'zstandard' package), and on 1.26, which
    does not.
    """
    urllib3_response = _import("urllib3.response")
    if urllib3_response is None:
        return False
    decoders = getattr(getattr(urllib3_response, "BaseHTTPResponse", None), "CONTENT_DECODERS", None)
    if decoders is not None:
        return ZSTD in decoders
    return bool(getattr(urllib3_response, "HAS_ZSTD", False))


def zstd_unavailable_error(situation=None):
    error = PolytopeError(situation=situation)
    error.description = (
        "compression='zstd' needs an urllib3 that can decode zstd, because responses other than a "
        "result are decoded by urllib3 and not by this client. Either " + zstd_hint() + ", "
        "or submit the request with compression='gzip' or compression='auto'."
    )
    return error


def accept_encoding_header(compression, situation=None, logger=None):
    """Map the ``compression`` option onto an ``Accept-Encoding`` header value.

    Only codecs this client can decode are advertised. The Polytope server fixes
    the codec of a result when the request is submitted, so this header matters
    on the submit request.
    """
    value = IDENTITY if compression is None else str(compression).strip().lower()
    if value == AUTO:
        if zstd_available():
            return "zstd, gzip"
        # The dependencies of this client give every supported interpreter a
        # zstd decoder, so getting here means the environment was built around
        # them (an urllib3 older than the pin, say). gzip still works.
        (logger or logging.getLogger(__name__)).warning(
            "Asking for gzip only: the installed urllib3 has no zstd decoder (%s)" % zstd_hint()
        )
        return GZIP
    if value == NONE:
        return IDENTITY
    if value in GZIP_ALIASES:
        return GZIP
    if value == ZSTD:
        if not zstd_available():
            raise zstd_unavailable_error(situation)
        return ZSTD
    raise ValueError(
        "Invalid compression option '%s'. Valid options are: %s" % (compression, ", ".join(COMPRESSION_OPTIONS))
    )


def unsupported_encoding_error(value, situation=None, reason=None):
    error = PolytopeError(situation=situation)
    description = "The server sent Content-Encoding '%s', which this client cannot decode" % value
    if reason:
        description += " (" + reason + ")"
    description += ". Either " + zstd_hint() + " if the data is zstd-encoded, "
    description += "or submit the request with compression='none' to receive the data uncompressed."
    error.description = description
    return error


def content_encoding_codec(value, situation=None):
    """Return the canonical codec name of a ``Content-Encoding`` header value.

    An absent, empty or identity header means no encoding. Anything this client
    cannot decode (deflate, br, several stacked encodings) raises, so that a
    wrongly decoded file is never written.
    """
    if value is None:
        return IDENTITY
    tokens = [token.strip().lower() for token in str(value).split(",")]
    tokens = [token for token in tokens if token and token != IDENTITY]
    if not tokens:
        return IDENTITY
    if len(tokens) > 1:
        return _raise(unsupported_encoding_error(value, situation, "several stacked encodings"))
    token = tokens[0]
    if token in GZIP_ALIASES:
        return GZIP
    if token == ZSTD:
        if not zstd_decoder_available():
            return _raise(unsupported_encoding_error(value, situation, "no zstd decoder is installed"))
        return ZSTD
    return _raise(unsupported_encoding_error(value, situation, "unknown codec"))


def _raise(error):
    raise error


def suffix(codec):
    return SUFFIXES.get(codec, "")


def add_suffix(path, codec):
    """Append the codec's file name suffix, unless the path already carries it."""
    extension = suffix(codec)
    if not extension or os.path.basename(path).lower().endswith(extension):
        return path
    return path + extension


class GzipDecoder:
    """Streaming gzip decoder whose state survives a resumed request."""

    codec = GZIP
    verifies_end_of_stream = True

    def __init__(self):
        self._obj = zlib.decompressobj(31)

    def pieces(self, data):
        """Decode 'data' into slices of at most MAX_DECODED_SLICE bytes."""
        while data:
            if self._obj.eof:
                # A new gzip member follows the one just finished.
                self._obj = zlib.decompressobj(31)
            out = self._obj.decompress(data, MAX_DECODED_SLICE)
            if out:
                yield out
            # What did not fit in the slice above waits in unconsumed_tail.
            while self._obj.unconsumed_tail:
                out = self._obj.decompress(self._obj.unconsumed_tail, MAX_DECODED_SLICE)
                if out:
                    yield out
            data = self._obj.unused_data if self._obj.eof else b""

    def flush(self):
        return self._obj.flush()

    @property
    def eof(self):
        return self._obj.eof


class ZstdDecoder:
    """Streaming zstd decoder whose state survives a resumed request."""

    codec = ZSTD
    verifies_end_of_stream = True

    def __init__(self):
        self._new = zstd_decompressobj
        self._obj = self._new()

    def pieces(self, data):
        """Decode 'data' into slices of at most MAX_DECODED_SLICE bytes."""
        while data:
            if self._obj.eof:
                # A new zstd frame follows the one just finished.
                self._obj = self._new()
            out = self._obj.decompress(data, MAX_DECODED_SLICE)
            if out:
                yield out
            # What the slice above left behind is decoded without more input.
            while not self._obj.needs_input and not self._obj.eof:
                out = self._obj.decompress(b"", MAX_DECODED_SLICE)
                if out:
                    yield out
            data = self._obj.unused_data if self._obj.eof else b""

    def flush(self):
        return b""

    @property
    def eof(self):
        return self._obj.eof


def make_decoder(codec):
    """A streaming decoder for ``codec``; the identity codec needs none (the caller writes the bytes)."""
    if codec == GZIP:
        return GzipDecoder()
    if codec == ZSTD:
        return ZstdDecoder()
    raise unsupported_encoding_error(codec, reason="unknown codec")
