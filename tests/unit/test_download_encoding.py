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

"""Downloads of results served with a Content-Encoding.

The responses come from a real HTTP server in a thread, so that the client sees
the same wire behaviour as it does against BOBS: Content-Length and byte ranges
over the *compressed* bytes, and a connection that can break mid-body.
"""

import gzip
import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import cast

import pytest
import requests
import urllib3
from urllib3 import response as urllib3_response

from polytope.api import encoding, helpers
from polytope.api.Client import Client
from polytope.api.RequestManager import RequestManager
from polytope.version import __version__

LOGGER = logging.getLogger("polytope.tests.download")

BODY = json.dumps({"type": "CoverageCollection", "coverages": [{"values": list(range(50000))}]}).encode()

CODECS = ["identity", "gzip", "zstd"]

needs_zstd = pytest.mark.skipif(not encoding.zstd_decoder_available(), reason="no zstd decoder is installed")


def zstd_compress(body):
    module = encoding.zstd_module()
    assert module is not None, "no zstd decoder is installed"
    if module.__name__ == "zstandard":
        return module.ZstdCompressor().compress(body)
    return module.compress(body)


def encode(body, codec):
    if codec == encoding.GZIP:
        # A fixed mtime keeps the compressed bytes comparable between calls.
        return gzip.compress(body, mtime=0)
    if codec == encoding.ZSTD:
        return zstd_compress(body)
    return body


def skip_unless_available(codec):
    if codec == encoding.ZSTD and not encoding.zstd_decoder_available():
        pytest.skip("no zstd decoder is installed")


def skip_unless_advertisable(codec):
    """A codec is only asked for when urllib3 can decode it too."""
    skip_unless_available(codec)
    if codec == encoding.ZSTD and not encoding.zstd_available():
        pytest.skip("urllib3 cannot decode zstd, so zstd is never advertised")


class Spec:
    """What the test server should answer."""

    def __init__(
        self,
        payload,
        content_encoding=None,
        content_length=True,
        honour_range=True,
        drop_after=None,
        content_type="application/prs.coverage+json",
        status=None,
        encode_per_accept_encoding=False,
        restart_payload=None,
        restart_content_encoding=None,
    ):
        self.payload = payload
        self.content_encoding = content_encoding
        self.content_length = content_length
        self.honour_range = honour_range
        # Number of body bytes to write on the first request before hanging up.
        self.drop_after = drop_after
        self.content_type = content_type
        #: Status code to answer with, instead of 200 (or 206 for a range).
        self.status = status
        #: Compress every body with the best codec the client advertised, the
        #: way the Polytope frontend's compression layer does.
        self.encode_per_accept_encoding = encode_per_accept_encoding
        #: Body served to every request after the first one, for a server that
        #: answers a Range with a different object than it first announced.
        self.restart_payload = restart_payload
        self.restart_content_encoding = restart_content_encoding


class RecordingServer(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False

    #: What to answer, and the headers of every request received so far.
    spec = Spec(b"")
    received = []

    def handle_error(self, request, client_address):
        # Several tests break the connection on purpose; a traceback per
        # dropped socket would only add noise.
        pass


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_POST(self):
        """Accept a request submission the way the Polytope frontend does."""
        server = cast(RecordingServer, self.server)
        self.rfile.read(_content_length(self.headers))
        self._record("post")
        if server.spec.encode_per_accept_encoding:
            self._send_encoded_like_the_frontend(server.spec)
            return
        body = b'{"message": "queued", "status": "queued"}'
        self.send_response(202)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Location", "http://127.0.0.1:%d/api/v1/requests/req-1" % server.server_port)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        server = cast(RecordingServer, self.server)
        spec = server.spec
        self._record("get")
        if spec.encode_per_accept_encoding:
            self._send_encoded_like_the_frontend(spec)
            return
        first_get = len([item for item in server.received if item["method"] == "get"]) == 1
        drop_after = spec.drop_after if first_get else None

        payload = spec.payload
        content_encoding = spec.content_encoding
        if not first_get and spec.restart_payload is not None:
            payload = spec.restart_payload
            content_encoding = spec.restart_content_encoding

        start = 0
        partial = False
        requested_range = self.headers.get("Range")
        if requested_range and spec.honour_range:
            start = _range_start(requested_range)
            partial = True
        body = payload[start:]

        self.send_response(spec.status or (206 if partial else 200))
        self.send_header("Content-Type", spec.content_type)
        if content_encoding:
            self.send_header("Content-Encoding", content_encoding)
        self.send_header("Accept-Ranges", "bytes")
        if spec.content_length:
            self.send_header("Content-Length", str(len(body)))
            if partial:
                self.send_header(
                    "Content-Range",
                    "bytes %d-%d/%d" % (start, len(payload) - 1, len(payload)),
                )
            self.end_headers()
            self.wfile.write(body if drop_after is None else body[:drop_after])
        else:
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            self._write_chunked(body, drop_after)
        if drop_after is not None:
            self.close_connection = True

    def _send_encoded_like_the_frontend(self, spec):
        """Compress the body per Accept-Encoding, JSON responses included.

        The frontend wraps every response in tower-http's compression layer, so
        a codec advertised for the sake of the result also comes back on the
        JSON of a submission, a poll or an error.
        """
        offered = [token.strip().lower() for token in (self.headers.get("Accept-Encoding") or "").split(",")]
        codec = encoding.IDENTITY
        for candidate in (encoding.ZSTD, encoding.GZIP):
            if candidate in offered:
                codec = candidate
                break
        body = encode(spec.payload, codec)
        self.send_response(spec.status or 200)
        self.send_header("Content-Type", spec.content_type)
        if codec != encoding.IDENTITY:
            self.send_header("Content-Encoding", codec)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _record(self, method):
        headers = {name.lower(): value for name, value in self.headers.items()}
        headers["method"] = method
        cast(RecordingServer, self.server).received.append(headers)

    def _write_chunked(self, body, drop_after):
        limit = len(body) if drop_after is None else drop_after
        written = 0
        while written < limit:
            piece = body[written : min(written + 8192, limit)]
            self.wfile.write(("%x\r\n" % len(piece)).encode() + piece + b"\r\n")
            written += len(piece)
        if drop_after is None:
            self.wfile.write(b"0\r\n\r\n")

    def log_message(self, format, *args):
        pass


def _range_start(value):
    try:
        return int(value.split("=", 1)[1].split("-")[0])
    except (IndexError, ValueError):
        return 0


def _content_length(headers):
    try:
        return int(headers.get("Content-Length") or 0)
    except ValueError:
        return 0


@pytest.fixture
def server():
    httpd = RecordingServer(("127.0.0.1", 0), Handler)
    httpd.received = []
    httpd.spec = Spec(BODY)
    thread = threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
    thread.start()
    try:
        yield httpd
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def url(server):
    return "http://127.0.0.1:%d/result" % server.server_port


def get(server, **kwargs):
    return requests.get(url(server), stream=True, timeout=30, **kwargs)


class RaisingAfterBody:
    """Wrap 'response.raw' so that the stream raises once the whole body arrived.

    A store behind a pool of connections can reset the connection right after
    the last byte, which urllib3 reports as a read error on a body that is in
    fact complete.
    """

    def __init__(self, raw, error=None):
        self._raw = raw
        self._error = error or requests.exceptions.ConnectionError("connection reset after the last byte")

    def __getattr__(self, name):
        return getattr(self._raw, name)

    def stream(self, amt, decode_content=False):
        for chunk in self._raw.stream(amt, decode_content=decode_content):
            yield chunk
        raise self._error


class FakeConfig:
    _cli = False

    def __init__(self, **overrides):
        self._config = {"quiet": True, "skip_tls": False, "compression": "auto", "decompress": True}
        self._config.update(overrides)

    def get(self):
        return dict(self._config)

    def request_headers(self, base=None):
        return {} if base is None else dict(base)


def manager(**overrides):
    request_manager = RequestManager(FakeConfig(**overrides), auth=None, coll_visitor=None, logger=LOGGER)
    request_manager._new_attempt_period = 0
    request_manager._http_max_attempts = 3
    request_manager._download_chunk_size = 4096
    return request_manager


@pytest.mark.parametrize("codec", CODECS)
@pytest.mark.parametrize("content_length", [True, False], ids=["content-length", "chunked"])
def test_download_decodes_every_codec(server, tmp_path, codec, content_length):
    skip_unless_available(codec)
    server.spec = Spec(
        encode(BODY, codec),
        content_encoding=None if codec == encoding.IDENTITY else codec,
        content_length=content_length,
    )

    output_file = str(tmp_path / "result.covjson")
    result = manager()._download_to_file(get(server), output_file, append=False)

    assert result == output_file
    assert Path(result).read_bytes() == BODY


@pytest.mark.parametrize("codec", [encoding.GZIP, encoding.ZSTD])
def test_progress_and_completeness_count_wire_bytes(server, tmp_path, codec, caplog):
    skip_unless_available(codec)
    payload = encode(BODY, codec)
    assert len(payload) < len(BODY)
    server.spec = Spec(payload, content_encoding=codec)

    output_file = str(tmp_path / "result.covjson")
    with caplog.at_level(logging.INFO, logger=LOGGER.name):
        manager()._download_to_file(get(server), output_file, append=False)

    assert Path(output_file).read_bytes() == BODY
    # The completeness check compared the compressed bytes against
    # Content-Length; the decoded bytes are what reached the file.
    written = [record.getMessage() for record in caplog.records if record.getMessage().startswith("Wrote ")]
    assert len(written) == 1
    assert codec in written[0]
    assert helpers.bytes_to_string(len(payload)) in written[0]
    assert helpers.bytes_to_string(len(BODY)) in written[0]


@pytest.mark.parametrize("codec", CODECS)
def test_interrupted_chunked_download_restarts_from_the_beginning(server, tmp_path, codec, monkeypatch):
    """Without a Content-Length there is no total to resume against."""
    skip_unless_available(codec)
    payload = encode(BODY, codec)
    server.spec = Spec(
        payload,
        content_encoding=None if codec == encoding.IDENTITY else codec,
        content_length=False,
        drop_after=len(payload) // 3,
    )

    decoders = []
    original_make_decoder = encoding.make_decoder
    monkeypatch.setattr(encoding, "make_decoder", lambda name: decoders.append(name) or original_make_decoder(name))

    output_file = str(tmp_path / "result.covjson")
    manager()._download_to_file(get(server), output_file, append=False)

    assert Path(output_file).read_bytes() == BODY
    assert len(server.received) == 2
    assert "range" not in server.received[1]
    assert decoders == [codec, codec]


@pytest.mark.parametrize("codec", CODECS)
def test_resume_keeps_the_decoder_state(server, tmp_path, codec, monkeypatch):
    skip_unless_available(codec)
    payload = encode(BODY, codec)
    server.spec = Spec(
        payload,
        content_encoding=None if codec == encoding.IDENTITY else codec,
        drop_after=len(payload) // 3,
    )

    decoders = []
    original_make_decoder = encoding.make_decoder
    monkeypatch.setattr(encoding, "make_decoder", lambda name: decoders.append(name) or original_make_decoder(name))

    output_file = str(tmp_path / "result.covjson")
    manager()._download_to_file(get(server), output_file, append=False)

    assert Path(output_file).read_bytes() == BODY
    # Exactly one resume, asking for the compressed bytes that were missing.
    assert len(server.received) == 2
    assert server.received[1]["range"] == "bytes=%d-" % (len(payload) // 3)
    # The decoder was built once and kept its state across the resume.
    assert decoders == [codec]


@pytest.mark.parametrize("codec", CODECS)
@pytest.mark.parametrize("append", [False, True])
def test_resume_restarts_when_the_server_ignores_the_range(server, tmp_path, codec, append, monkeypatch):
    skip_unless_available(codec)
    payload = encode(BODY, codec)
    server.spec = Spec(
        payload,
        content_encoding=None if codec == encoding.IDENTITY else codec,
        drop_after=len(payload) // 3,
        honour_range=False,
    )

    decoders = []
    original_make_decoder = encoding.make_decoder
    monkeypatch.setattr(encoding, "make_decoder", lambda name: decoders.append(name) or original_make_decoder(name))

    output_file = str(tmp_path / "result.covjson")
    prefix = b"already here\n"
    if append:
        Path(output_file).write_bytes(prefix)

    manager()._download_to_file(get(server), output_file, append=append)

    assert Path(output_file).read_bytes() == (prefix + BODY if append else BODY)
    assert len(server.received) == 2
    assert server.received[1]["range"] == "bytes=%d-" % (len(payload) // 3)
    # The Range was ignored (200), so the decoder was rebuilt and the partial
    # output discarded.
    assert decoders == [codec, codec]


@pytest.mark.parametrize("append", [False, True])
def test_reset_adopts_the_content_length_of_the_new_response(server, tmp_path, append):
    """The 200 that ignores the Range may serve a body of a different length."""
    compressed = encode(BODY, encoding.GZIP)
    assert len(compressed) != len(BODY)
    server.spec = Spec(
        compressed,
        content_encoding="gzip",
        drop_after=len(compressed) // 3,
        honour_range=False,
        restart_payload=BODY,
        restart_content_encoding=None,
    )

    output_file = str(tmp_path / "result.covjson")
    prefix = b"already here\n"
    if append:
        Path(output_file).write_bytes(prefix)

    result = manager()._download_to_file(get(server), output_file, append=append)

    assert Path(result).read_bytes() == (prefix + BODY if append else BODY)
    assert len(server.received) == 2


@pytest.mark.parametrize("codec", CODECS)
def test_complete_body_then_a_connection_error_is_a_success(server, tmp_path, codec):
    """All the announced bytes arrived, so the error afterwards says nothing."""
    skip_unless_available(codec)
    payload = encode(BODY, codec)
    server.spec = Spec(payload, content_encoding=None if codec == encoding.IDENTITY else codec)

    response = get(server)
    response.raw = RaisingAfterBody(response.raw)
    output_file = str(tmp_path / "result.covjson")
    result = manager()._download_to_file(response, output_file, append=False)

    assert Path(result).read_bytes() == BODY
    # No resume: the file is complete, and a Range at the end of the object
    # would earn a 416 from a store that validates it.
    assert len(server.received) == 1


@pytest.mark.parametrize("error", [requests.exceptions.ConnectionError, urllib3.exceptions.ProtocolError])
def test_connection_error_without_a_content_length_is_retried(server, tmp_path, error):
    """Nothing announced the length, so the body may well have been cut short."""
    server.spec = Spec(BODY, content_length=False)

    response = get(server)
    response.raw = RaisingAfterBody(response.raw, error("connection lost"))
    output_file = str(tmp_path / "result.covjson")
    result = manager()._download_to_file(response, output_file, append=False)

    assert Path(result).read_bytes() == BODY
    assert len(server.received) == 2
    assert "range" not in server.received[1]


def test_truncated_gzip_with_matching_content_length_fails(server, tmp_path):
    # The gzip trailer never arrives, but Content-Length matches what is sent.
    server.spec = Spec(gzip.compress(BODY)[:-8], content_encoding="gzip")
    request_manager = manager()
    request_manager._http_max_attempts = 1

    output_file = str(tmp_path / "result.covjson")
    with pytest.raises(helpers.PolytopeError):
        request_manager._download_to_file(get(server), output_file, append=False)


@pytest.mark.parametrize("codec", CODECS)
def test_decompress_false_keeps_the_stream_and_names_the_file(server, tmp_path, codec):
    skip_unless_available(codec)
    payload = encode(BODY, codec)
    server.spec = Spec(payload, content_encoding=None if codec == encoding.IDENTITY else codec)

    output_file = str(tmp_path / "result.covjson")
    result = manager()._download_to_file(get(server), output_file, append=False, decompress=False)

    assert result == output_file + encoding.suffix(codec)
    assert Path(result).read_bytes() == payload
    if codec != encoding.IDENTITY:
        assert not os.path.exists(output_file)


@pytest.mark.parametrize("codec", [encoding.GZIP, encoding.ZSTD])
def test_decompress_false_does_not_duplicate_an_existing_suffix(server, tmp_path, codec):
    skip_unless_available(codec)
    server.spec = Spec(encode(BODY, codec), content_encoding=codec)

    output_file = str(tmp_path / ("result.covjson" + encoding.suffix(codec)))
    result = manager()._download_to_file(get(server), output_file, append=False, decompress=False)

    assert result == output_file


@pytest.mark.parametrize("codec", CODECS)
def test_decompress_false_without_output_file(server, tmp_path, codec, monkeypatch):
    skip_unless_available(codec)
    server.spec = Spec(encode(BODY, codec), content_encoding=None if codec == encoding.IDENTITY else codec)
    monkeypatch.chdir(tmp_path)

    result = manager()._download(get(server), None, False, request_id="req-1", decompress=False)

    assert os.path.basename(result) == "req-1.covjson" + encoding.suffix(codec)
    assert Path(result).read_bytes() == encode(BODY, codec)


@pytest.mark.parametrize("codec", CODECS)
def test_download_without_output_file_decodes(server, tmp_path, codec, monkeypatch):
    skip_unless_available(codec)
    server.spec = Spec(encode(BODY, codec), content_encoding=None if codec == encoding.IDENTITY else codec)
    monkeypatch.chdir(tmp_path)

    result = manager()._download(get(server), None, False, request_id="req-1")

    assert os.path.basename(result) == "req-1.covjson"
    assert Path(result).read_bytes() == BODY


@pytest.mark.parametrize("header", ["br", "deflate", "gzip, br", "compress"])
def test_unsupported_content_encoding_is_refused(server, tmp_path, header):
    server.spec = Spec(BODY, content_encoding=header)

    output_file = str(tmp_path / "result.covjson")
    with pytest.raises(helpers.PolytopeError):
        manager()._download_to_file(get(server), output_file, append=False)

    assert not os.path.exists(output_file)


def test_zstd_content_encoding_without_a_decoder_is_refused(server, tmp_path, monkeypatch):
    monkeypatch.setattr(encoding, "zstd_module", lambda: None)
    server.spec = Spec(BODY, content_encoding="zstd")

    output_file = str(tmp_path / "result.covjson")
    with pytest.raises(helpers.PolytopeError):
        manager()._download_to_file(get(server), output_file, append=False)

    assert not os.path.exists(output_file)


def test_grib_download(server, tmp_path):
    server.spec = Spec(encode(BODY, encoding.GZIP), content_encoding="gzip", content_type="application/x-grib")

    output_file = str(tmp_path / "result.grib")
    manager()._download(get(server), output_file, False)

    assert Path(output_file).read_bytes() == BODY


def test_grib_decompress_false_keeps_the_stream(server, tmp_path):
    payload = encode(BODY, encoding.GZIP)
    server.spec = Spec(payload, content_encoding="gzip", content_type="application/x-grib")

    output_file = str(tmp_path / "result.grib")
    result = manager()._download(get(server), output_file, False, decompress=False)

    assert result == output_file + ".gz"
    assert Path(result).read_bytes() == payload
    assert not os.path.exists(output_file)


def test_grib_decompress_false_without_output_file(server, tmp_path, monkeypatch):
    payload = encode(BODY, encoding.GZIP)
    server.spec = Spec(payload, content_encoding="gzip", content_type="application/x-grib")
    monkeypatch.chdir(tmp_path)

    result = manager()._download(get(server), None, False, request_id="req-1", decompress=False)

    assert os.path.basename(result) == "req-1.grib.gz"
    assert Path(result).read_bytes() == payload


def test_octet_stream_download(server, tmp_path):
    server.spec = Spec(encode(BODY, encoding.GZIP), content_encoding="gzip", content_type="application/octet-stream")

    output_file = str(tmp_path / "result.bin")
    manager()._download(get(server), output_file, False)

    assert Path(output_file).read_bytes() == BODY


def test_buffered_body_is_still_written(server, tmp_path):
    """A response whose body was already read is written from memory."""
    server.spec = Spec(encode(BODY, encoding.GZIP), content_encoding="gzip")
    response = get(server)
    assert response.content  # consumes and decodes the body

    output_file = str(tmp_path / "result.covjson")
    manager()._download_to_file(response, output_file, append=False)

    assert Path(output_file).read_bytes() == BODY


# Request headers
###


def test_accept_encoding_header_values(monkeypatch):
    assert encoding.accept_encoding_header("none") == "identity"
    assert encoding.accept_encoding_header("gzip") == "gzip"
    with pytest.raises(ValueError):
        encoding.accept_encoding_header("br")

    # urllib3 decodes every response that is not a result, so what it can do
    # with zstd decides whether zstd is advertised at all.
    monkeypatch.setattr(urllib3_response, "HAS_ZSTD", True)
    assert encoding.accept_encoding_header("auto") == "zstd, gzip"
    assert encoding.accept_encoding_header("zstd") == "zstd"

    monkeypatch.setattr(urllib3_response, "HAS_ZSTD", False)
    assert encoding.accept_encoding_header("auto") == "gzip"


def test_accept_encoding_header_without_a_has_zstd_attribute(monkeypatch):
    """An urllib3 too old to know about zstd is treated as unable to decode it."""
    monkeypatch.delattr(urllib3_response, "HAS_ZSTD", raising=False)
    assert encoding.accept_encoding_header("auto") == "gzip"


def test_explicit_zstd_without_urllib3_support_is_refused(monkeypatch):
    monkeypatch.setattr(urllib3_response, "HAS_ZSTD", False)

    with pytest.raises(helpers.PolytopeError) as raised:
        encoding.accept_encoding_header("zstd")

    hint = encoding.zstd_hint()
    # The hint names the decoder this urllib3 looks for, not just any package.
    assert any(package in hint for package in ["backports.zstd", "compression.zstd", "zstandard"])
    assert hint in str(raised.value)


def test_json_error_compressed_by_the_frontend_is_still_parsed(server, tmp_path):
    """The frontend compresses every response per Accept-Encoding, errors included.

    A codec advertised for the sake of the result therefore also comes back on
    the JSON of a failed submission, and that body is decoded by urllib3 before
    the client sees it. Advertising zstd to an urllib3 that cannot decode it
    left response.json() with raw zstd bytes and buried the server's message.
    """
    message = "invalid request: 'class: d1' is missing keys"
    server.spec = Spec(
        json.dumps({"message": message}).encode(),
        content_type="application/json",
        status=400,
        encode_per_accept_encoding=True,
    )

    client = Client(
        config_path=tmp_path / "config",
        address="http://127.0.0.1:%d" % server.server_port,
        insecure=True,
        user_key="token",
        quiet=True,
    )
    with pytest.raises(helpers.HTTPResponseError) as raised:
        client.retrieve("ecmwf-mars", {"param": "t"}, str(tmp_path / "result.covjson"), asynchronous=True)

    assert message in str(raised.value)
    submit = server.received[0]
    assert submit["method"] == "post"
    assert submit["accept-encoding"] == encoding.accept_encoding_header("auto")
    # zstd is offered only when urllib3 brought a decoder of its own.
    assert ("zstd" in submit["accept-encoding"]) == encoding.zstd_available()


@pytest.mark.parametrize(
    "compression,expected",
    [("none", "identity"), ("gzip", "gzip"), ("auto", None)],
)
def test_headers_sent_on_the_wire(server, compression, expected):
    server.spec = Spec(b'{"message": "ok"}', content_type="application/json")
    expected = expected or encoding.accept_encoding_header("auto")

    helpers.try_request(
        "get",
        situation="trying to download data",
        expected=[requests.codes.ok],
        logger=LOGGER,
        url=url(server),
        headers={"Accept-Encoding": encoding.accept_encoding_header(compression)},
    )

    sent = server.received[-1]
    assert sent["accept-encoding"] == expected
    expected_user_agent = "polytope-client/%s python-requests/%s" % (__version__, requests.__version__)
    assert sent["user-agent"] == expected_user_agent


def test_default_headers_are_explicit(server):
    server.spec = Spec(b'{"message": "ok"}', content_type="application/json")

    helpers.try_request(
        "get",
        situation="trying to list requests",
        expected=[requests.codes.ok],
        logger=LOGGER,
        url=url(server),
    )

    sent = server.received[-1]
    # Explicitly gzip only: 'deflate', which requests would offer by default,
    # is not something this client can decode on the download path.
    assert sent["accept-encoding"] == "gzip"
    assert sent["user-agent"].startswith("polytope-client/")


def test_compression_option_reaches_the_submit_and_download_requests(monkeypatch, tmp_path):
    captured = []

    class Response:
        status_code = requests.codes.accepted
        headers = {"Location": "https://example.test/requests/req-1"}
        url = "https://example.test/requests/req-1"

        def json(self):
            return {"message": "ok"}

        def close(self):
            pass

    def fake_try_request(*args, **kwargs):
        captured.append((kwargs.get("situation"), kwargs.get("headers", {})))
        if kwargs.get("situation") == "trying to download data":
            response = Response()
            response.status_code = requests.codes.ok
            response.headers = {"Content-Length": "0", "Content-Type": "application/x-grib"}
            return response, {}
        return Response(), {"message": "ok"}

    monkeypatch.setattr(helpers, "try_request", fake_try_request)

    client = Client(
        config_path=tmp_path,
        address="http://example.test",
        insecure=True,
        user_key="token",
        compression="none",
    )
    client.retrieve("ecmwf-mars", {"param": "t"}, asynchronous=True)
    client.download("req-1", pointer=True)
    client.download("req-1", pointer=True, compression="gzip")

    assert [headers["Accept-Encoding"] for _, headers in captured] == ["identity", "identity", "gzip"]


# Configuration
###


def test_compression_and_decompress_configuration(tmp_path, monkeypatch):
    client = Client(config_path=tmp_path / "ctor", compression="zstd", decompress=False)
    assert client.config.get()["compression"] == "zstd"
    decompress = client.config.get()["decompress"]
    assert isinstance(decompress, bool) and not decompress
    assert not client.request_manager._decompress_option()
    assert client.request_manager._compression_option() == "zstd"
    assert client.request_manager._compression_option("none") == "none"

    config_dir = tmp_path / "file"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text("compression: gzip\ndecompress: false\n")
    client = Client(config_path=config_dir)
    assert client.config.get()["compression"] == "gzip"
    assert not client.config.get()["decompress"]

    monkeypatch.setenv("POLYTOPE_COMPRESSION", "none")
    monkeypatch.setenv("POLYTOPE_DECOMPRESS", "False")
    client = Client(config_path=tmp_path / "env")
    assert client.config.get()["compression"] == "none"
    assert not client.config.get()["decompress"]
    monkeypatch.delenv("POLYTOPE_COMPRESSION")
    monkeypatch.delenv("POLYTOPE_DECOMPRESS")

    with pytest.raises(ValueError):
        Client(config_path=tmp_path / "bad", compression="brotli")


@needs_zstd
def test_zstd_multiple_frames():
    stream = zstd_compress(b"first ") + zstd_compress(b"second")
    decoder = encoding.make_decoder(encoding.ZSTD)
    assert decoder.decompress(stream) == b"first second"
    assert decoder.eof


def test_gzip_multiple_members():
    stream = gzip.compress(b"first ") + gzip.compress(b"second")
    decoder = encoding.make_decoder(encoding.GZIP)
    assert decoder.decompress(stream) == b"first second"
    assert decoder.eof


# End to end through the Client
###


@pytest.mark.parametrize("codec", CODECS)
def test_retrieve_submits_and_downloads_an_encoded_result(server, tmp_path, codec):
    """Submit, poll and download through the public API, server and all."""
    skip_unless_advertisable(codec)
    server.spec = Spec(encode(BODY, codec), content_encoding=None if codec == encoding.IDENTITY else codec)

    client = Client(
        config_path=tmp_path / "config",
        address="http://127.0.0.1:%d" % server.server_port,
        insecure=True,
        user_key="token",
        quiet=True,
    )
    output_file = str(tmp_path / "result.covjson")
    results = client.retrieve(
        "ecmwf-mars",
        {"param": "t"},
        output_file,
        compression="gzip" if codec == encoding.IDENTITY else codec,
    )

    assert results == [output_file]
    assert Path(output_file).read_bytes() == BODY
    submit = server.received[0]
    assert submit["method"] == "post"
    assert submit["accept-encoding"] == ("gzip" if codec == encoding.IDENTITY else codec)
    assert submit["user-agent"].startswith("polytope-client/")
