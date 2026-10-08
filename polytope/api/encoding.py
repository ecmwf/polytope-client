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
therefore reads the wire bytes itself (``decode_content=False``) and decodes them
with one of the streaming decoders below, whose state survives a resumed request.

Only the codecs this module can decode are ever advertised in ``Accept-Encoding``.
"""

import os
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

ZSTD_HINT = "install the 'zstandard' package (pip install 'polytope-client[zstd]')"


def zstandard_module():
    """Return the ``zstandard`` module, or None when it is not installed.

    The dependency is optional; it is imported lazily so that a client without
    it keeps working (it then neither advertises nor decodes zstd).
    """
    try:
        import zstandard  # type: ignore[import-not-found]
    except ImportError:
        return None
    return zstandard


def zstandard_available():
    return zstandard_module() is not None


def accept_encoding_header(compression):
    """Map the ``compression`` option onto an ``Accept-Encoding`` header value.

    Only codecs this client can decode are advertised. The Polytope server fixes
    the codec of a result when the request is submitted, so this header matters
    on the submit request.
    """
    value = IDENTITY if compression is None else str(compression).strip().lower()
    if value == AUTO:
        return "zstd, gzip" if zstandard_available() else GZIP
    if value == NONE:
        return IDENTITY
    if value in GZIP_ALIASES:
        return GZIP
    if value == ZSTD:
        if not zstandard_available():
            raise ValueError("compression='zstd' requires the zstandard package; " + ZSTD_HINT)
        return ZSTD
    raise ValueError(
        "Invalid compression option '%s'. Valid options are: %s" % (compression, ", ".join(COMPRESSION_OPTIONS))
    )


def unsupported_encoding_error(value, situation=None, reason=None):
    error = PolytopeError(situation=situation)
    description = "The server sent Content-Encoding '%s', which this client cannot decode" % value
    if reason:
        description += " (" + reason + ")"
    description += ". Either " + ZSTD_HINT + " if the data is zstd-encoded, "
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
        if not zstandard_available():
            return _raise(unsupported_encoding_error(value, situation, "the zstandard package is not installed"))
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


class IdentityDecoder:
    """Pass-through decoder for an unencoded body."""

    codec = IDENTITY

    #: Whether reaching the end of the codec's stream can be detected.
    verifies_end_of_stream = False

    def decompress(self, data):
        return data

    def flush(self):
        return b""

    @property
    def eof(self):
        return True


class GzipDecoder:
    """Streaming gzip decoder whose state survives a resumed request."""

    codec = GZIP
    verifies_end_of_stream = True

    def __init__(self):
        self._obj = zlib.decompressobj(31)

    def decompress(self, data):
        out = []
        while data:
            if self._obj.eof:
                # A new gzip member follows the one just finished.
                self._obj = zlib.decompressobj(31)
            out.append(self._obj.decompress(data))
            data = self._obj.unused_data if self._obj.eof else b""
        return b"".join(out)

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
        zstandard = zstandard_module()
        if zstandard is None:
            raise unsupported_encoding_error(ZSTD, reason="the zstandard package is not installed")
        self._new = zstandard.ZstdDecompressor().decompressobj
        self._obj = self._new()

    def decompress(self, data):
        out = []
        while data:
            if self._obj.eof:
                # A new zstd frame follows the one just finished.
                self._obj = self._new()
            out.append(self._obj.decompress(data))
            data = self._obj.unused_data if self._obj.eof else b""
        return b"".join(out)

    def flush(self):
        return b""

    @property
    def eof(self):
        return self._obj.eof


def make_decoder(codec):
    if codec == GZIP:
        return GzipDecoder()
    if codec == ZSTD:
        return ZstdDecoder()
    return IdentityDecoder()
