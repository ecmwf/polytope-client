import json

import pytest

from polytope.api import Client, helpers
from polytope.api.Config import Config

SAFE_HEADER = "Polytope-Mock-Roles"
SAFE_VALUE = "beta:viewer"


def test_extra_headers_from_constructor_config_file_and_env(tmp_path, monkeypatch):
    client = Client(config_path=tmp_path / "ctor", extra_headers={SAFE_HEADER: SAFE_VALUE})
    assert client.config.get()["extra_headers"] == {SAFE_HEADER: SAFE_VALUE}

    config_dir = tmp_path / "file"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text("extra_headers:\n  Polytope-Mock-Roles: beta:viewer\n")
    config = Config(config_path=config_dir)
    assert config.get()["extra_headers"] == {SAFE_HEADER: SAFE_VALUE}

    monkeypatch.setenv("POLYTOPE_EXTRA_HEADERS", json.dumps({SAFE_HEADER: SAFE_VALUE}))
    config = Config(config_path=tmp_path / "env")
    assert config.get()["extra_headers"] == {SAFE_HEADER: SAFE_VALUE}

    config = Config(config_path=tmp_path / "set")
    config.set("extra_headers", json.dumps({SAFE_HEADER: SAFE_VALUE}))
    assert config.get()["extra_headers"] == {SAFE_HEADER: SAFE_VALUE}

    config = Config(config_path=tmp_path / "set-dict")
    config.set("extra_headers", {SAFE_HEADER: SAFE_VALUE})
    assert config.get()["extra_headers"] == {SAFE_HEADER: SAFE_VALUE}


def test_extra_header_validation_rejects_invalid_names_duplicates_and_crlf(tmp_path, monkeypatch):
    with pytest.raises(ValueError):
        Client(config_path=tmp_path / "bad-name", extra_headers={"Bad Header": "value"})

    with pytest.raises(ValueError):
        Client(config_path=tmp_path / "bad-value", extra_headers={"X-Debug": "line\nbreak"})

    monkeypatch.setenv("POLYTOPE_EXTRA_HEADERS", '{"X-Debug":"one","x-debug":"two"}')
    with pytest.raises(ValueError):
        Config(config_path=tmp_path / "dup-env")
    monkeypatch.delenv("POLYTOPE_EXTRA_HEADERS")

    config_dir = tmp_path / "dup-file"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text("extra_headers:\n  X-Debug: one\n  x-debug: two\n")
    with pytest.raises(ValueError):
        Config(config_path=config_dir)

    config = Config(config_path=tmp_path / "bad-set-dict")
    with pytest.raises(ValueError):
        config.set("extra_headers", {"Authorization": "Bearer secret"})


def test_unsafe_extra_headers_blocked_case_insensitively(tmp_path):
    blocked = [
        "Authorization",
        "Proxy-Authorization",
        "Cookie",
        "Set-Cookie",
        "Host",
        "Content-Length",
        "Transfer-Encoding",
        "Connection",
        "Keep-Alive",
        "TE",
        "Trailer",
        "Upgrade",
        "Content-Type",
        "Content-Encoding",
        "Accept-Encoding",
        "Range",
        "X-Checksum",
        "X-Forwarded-For",
        "X-Real-IP",
        "Forwarded",
        "X-Proxy-Protocol-Addr",
    ]
    for name in blocked:
        variant = name.swapcase()
        with pytest.raises(ValueError):
            Client(config_path=tmp_path / (name.lower().replace("-", "_") or "header"), extra_headers={variant: "x"})


def test_request_headers_preserves_base_headers_and_rejects_base_duplicates(tmp_path):
    config = Config(config_path=tmp_path, extra_headers={SAFE_HEADER: SAFE_VALUE})
    headers = config.request_headers({"Authorization": "Bearer token", "Range": "bytes=10-"})
    assert headers["Authorization"] == "Bearer token"
    assert headers["Range"] == "bytes=10-"
    assert headers[SAFE_HEADER] == SAFE_VALUE

    config = Config(config_path=tmp_path / "dup", extra_headers={"x-custom": "extra"})
    with pytest.raises(ValueError):
        config.request_headers({"X-Custom": "base"})


def test_extra_headers_propagate_to_request_sites(monkeypatch, tmp_path):
    captured = []

    class Response:
        def __init__(self, status_code=200, headers=None, body=None, url="https://example.test/result"):
            self.status_code = status_code
            self.headers = headers or {}
            self._body = body or {"message": []}
            self.url = url
            self.content = b""

        def json(self):
            return self._body

        def close(self):
            pass

    def fake_try_request(*args, **kwargs):
        captured.append(
            (
                kwargs.get("situation"),
                kwargs.get("headers", {}),
                kwargs.get("url"),
                kwargs.get("method") or (args[0] if args else None),
            )
        )
        situation = kwargs.get("situation")
        if situation == "trying to list collections":
            return Response(body={"message": ["ecmwf-mars"]}), {}
        if situation in ("trying to list requests", "trying to describe a request"):
            return Response(body={"message": [{"id": "req-1", "status": "queued", "verb": "retrieve"}]}), {}
        if situation == "trying to submit a retrieval request":
            return Response(status_code=202, headers={"Location": "https://example.test/requests/req-2"}), {
                "message": "ok"
            }
        if situation == "trying to download data":
            return Response(status_code=200, headers={"Content-Length": "0", "Content-Type": "application/x-grib"}), {}
        if situation == "trying to revoke a request":
            return Response(), {"message": "revoked"}
        if situation == "trying to submit an archive request":
            return Response(status_code=303, headers={"location": "https://example.test/uploads/up-1"}), {
                "message": "archive"
            }
        if situation == "trying to upload data":
            return Response(status_code=202, headers={"Location": "https://example.test/uploads/up-1"}), {}
        raise AssertionError("unexpected situation " + str(situation))

    monkeypatch.setattr(helpers, "try_request", fake_try_request)

    client = Client(
        config_path=tmp_path,
        address="http://example.test",
        insecure=True,
        user_key="token",
        extra_headers={SAFE_HEADER: SAFE_VALUE},
    )

    client.list_collections()
    client.list_requests()
    client.retrieve("ecmwf-mars", {"param": "t"}, asynchronous=True)
    client.download("req-1", pointer=True)
    client.revoke("req-1")

    input_file = tmp_path / "payload.grib"
    input_file.write_bytes(b"data")
    client.upload("https://example.test/uploads/up-1", input_file=str(input_file), asynchronous=True)

    monkeypatch.setattr(client.request_manager.coll_visitor, "list", lambda: ["ecmwf-mars"])
    monkeypatch.setattr(client.request_manager, "upload", lambda *args, **kwargs: "uploaded")
    metadata_file = tmp_path / "metadata.yaml"
    metadata_file.write_text("class: od\n")
    client.archive("ecmwf-mars", str(metadata_file), "http://example.test/data.grib", inline_metadata=False)

    assert captured
    for _, headers, _, _ in captured:
        assert headers[SAFE_HEADER] == SAFE_VALUE
        assert headers.get("Authorization") == "Bearer token" or "Authorization" not in headers
        assert headers.get("Content-Type") != SAFE_VALUE
        assert headers.get("Range") != SAFE_VALUE
        assert headers.get("X-Checksum") != SAFE_VALUE
        for forbidden in ["Cookie", "Set-Cookie", "X-Forwarded-For", "X-Real-IP", "Forwarded", "X-Proxy-Protocol-Addr"]:
            assert forbidden not in headers

    situations = [item[0] for item in captured]
    assert "trying to list collections" in situations
    assert "trying to submit a retrieval request" in situations
    assert "trying to download data" in situations
    assert "trying to revoke a request" in situations
    assert "trying to submit an archive request" in situations
    assert "trying to upload data" in situations
