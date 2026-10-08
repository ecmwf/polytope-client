# Changes on branch `feat/content-encoding-downloads`

## Compressed (Content-Encoding) results are downloaded correctly

Downloads now read the bytes as they arrive on the wire and decode them in
memory, instead of counting the decoded bytes `requests` hands back against a
`Content-Length` that counts compressed ones. A result served with
`Content-Encoding: gzip` or `zstd` is written correctly and no longer fails with
`Download failed: downloaded X byte(s) out of Y` after writing a complete file.

Behaviour changes a user can notice:

- Interrupted downloads resume with a `Range` over the compressed bytes and keep
  decoding where they left off; no temporary files are used. If the server
  answers `200` to the `Range` request, the output is truncated back to its
  pre-download size (`append` is honoured) and the download starts over.
- A missing `Content-Length` is no longer a `KeyError`: the download runs to the
  end of the stream, and an encoded body must reach its gzip trailer or zstd
  frame end to count as complete.
- A `Content-Encoding` this client cannot decode (`deflate`, `br`, several
  stacked encodings, or `zstd` with no zstd decoder installed) raises instead of
  writing a wrongly decoded file.
- A stream that ends before the gzip trailer or zstd frame end is treated as
  incomplete even when `Content-Length` matches.
- Result bodies (`application/x-grib`, `application/prs.coverage+json`,
  `application/octet-stream`) are no longer buffered and JSON-parsed by the
  response pre-processing. CovJSON results used to be read into memory and
  parsed before being written; they are now streamed.
- Every request sends an explicit `User-Agent`
  (`polytope-client/<version> python-requests/<version>`) and `Accept-Encoding`.
  `Accept-Encoding` was previously left to `requests` (`gzip, deflate`);
  `deflate` is no longer advertised because the client cannot decode it on the
  download path.
- The final log lines report the bytes written, the compression ratio when the
  body was encoded, and the download rate over wire bytes.

New options, `compression` (`auto` | `none` | `gzip` | `zstd`, default `auto`)
and `decompress` (default `True`), are settable as configuration items
(defaults, config file, `POLYTOPE_COMPRESSION` / `POLYTOPE_DECOMPRESS`, `Client`
constructor) and per call on `Client.retrieve` / `Client.download`, plus
`--compression` and `--decompress/--no-decompress` on the CLI.

`zstd` is only advertised when the installed `urllib3` can decode zstd
(`urllib3.response.HAS_ZSTD`), and `compression='zstd'` is refused otherwise
with a message naming the package that urllib3 looks for. The client decodes a
result body itself, but every other response (the JSON of a submission, a poll
or an error) is decoded by urllib3 before the client sees it, so a codec urllib3
does not know would turn those bodies into unparseable bytes: against a frontend
that compresses every response per `Accept-Encoding`, a `400` error body came
back as raw zstd and the server's message was lost.

The optional `zstd` extra therefore installs `backports.zstd` rather than
`zstandard`: urllib3 2.5 and later decode zstd with `compression.zstd` (Python
3.14+) or its `backports.zstd` backport, and only urllib3 before 2.5 used
`zstandard`. Result bodies are decoded with whichever of the three is installed:
`pip install 'polytope-client[zstd]'`.

With `pointer = True` the `contentLength` reported by the server is the size of
the compressed result when the result is stored compressed. This is documented,
not changed.

### Server-side follow-up (out of scope here)

The v1 API does not forward `Accept-Encoding` to the request, so results are
still stored uncompressed today; this client change is the prerequisite for
turning that on, gated server-side on the `User-Agent` this client now sends.
