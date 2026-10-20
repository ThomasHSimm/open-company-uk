"""Shared DuckDB connection setup for local and optional fsspec-backed reads.

``native`` deliberately preserves DuckDB's existing behaviour, including its native
``httpfs`` autoload path for remote URIs.  ``fsspec`` is an explicit opt-in for Python
environments where ``httpfs`` cannot be installed or loaded.  In that mode extension
auto-install/load is disabled before any query runs, and the filesystem is registered on
the exact connection used by the caller.  The project adds no download fallback; fsspec
may still need a sequential read for formats or servers that cannot support ranges.

The optional Python filesystem packages are imported lazily.  Local/native users do not
need them installed.
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

DUCKDB_BACKENDS = frozenset({"native", "fsspec"})
FSSPEC_REMOTE_SCHEMES = frozenset({"http", "https", "s3"})
FSSPEC_SUPPORTED_SCHEMES = FSSPEC_REMOTE_SCHEMES | {"file"}
REMOTE_EXTRA = "open-company-uk[remote]"

PathValue = str | os.PathLike[str]
PathInput = PathValue | Sequence[PathValue]


def require_duckdb():
    try:
        import duckdb
    except ImportError as exc:
        raise RuntimeError("this operation requires the duckdb package") from exc
    return duckdb


def validate_duckdb_backend(backend: str) -> str:
    """Return a normalized backend name or raise an actionable error."""
    normalized = str(backend).strip().lower()
    if normalized not in DUCKDB_BACKENDS:
        choices = ", ".join(sorted(DUCKDB_BACKENDS))
        raise ValueError(f"unsupported DuckDB backend {backend!r}; choose one of: {choices}")
    return normalized


def uri_scheme(value: PathValue) -> str:
    """Return a URI scheme, treating ordinary and Windows-style paths as local."""
    text = os.fspath(value)
    parsed = urlsplit(text)
    scheme = parsed.scheme.lower()
    if len(scheme) == 1 and len(text) >= 2 and text[1] == ":":
        return ""
    return scheme


def is_remote_uri(value: PathValue) -> bool:
    return uri_scheme(value) in FSSPEC_REMOTE_SCHEMES


def _flatten_paths(values: Iterable[PathInput]) -> list[str]:
    flattened: list[str] = []
    for value in values:
        if isinstance(value, (str, os.PathLike)):
            flattened.append(os.fspath(value))
        else:
            flattened.extend(os.fspath(item) for item in value)
    return flattened


def sql_literal(value: PathValue) -> str:
    return "'" + os.fspath(value).replace("'", "''") + "'"


def duckdb_path_sql(value: PathInput) -> str:
    """Render one path/glob or an explicit path list for a DuckDB reader function."""
    if isinstance(value, (str, os.PathLike)):
        return sql_literal(value)
    paths = [os.fspath(item) for item in value]
    if not paths:
        raise ValueError("DuckDB input path list must not be empty")
    return "[" + ", ".join(sql_literal(item) for item in paths) + "]"


def require_local_path(value: PathValue, label: str) -> Path:
    """Convert a local path without silently mangling a remote URI through ``Path``."""
    scheme = uri_scheme(value)
    if scheme:
        raise ValueError(f"{label} must be a local path, got URI scheme {scheme!r}: {value}")
    return Path(value).expanduser()


def _options_for(
    filesystem_options: Mapping[str, Mapping[str, Any]] | None, protocol: str
) -> dict[str, Any]:
    if filesystem_options is None:
        return {}
    if not isinstance(filesystem_options, Mapping):
        raise ValueError("fsspec_options must be a mapping keyed by protocol")
    raw = filesystem_options.get(protocol, {})
    if not isinstance(raw, Mapping):
        raise ValueError(f"fsspec options for {protocol!r} must be a mapping")
    return dict(raw)


def _require_fsspec():
    try:
        import fsspec
    except ImportError as exc:
        raise RuntimeError(
            "DuckDB backend 'fsspec' requires optional dependencies; install "
            f"`{REMOTE_EXTRA}` (for example: pip install -e '.[remote]')"
        ) from exc
    return fsspec


def _make_filesystem(
    protocol: str, filesystem_options: Mapping[str, Mapping[str, Any]] | None
):
    fsspec = _require_fsspec()
    if protocol == "s3":
        try:
            import s3fs
        except ImportError as exc:
            raise RuntimeError(
                "s3:// input with DuckDB backend 'fsspec' requires s3fs; install "
                f"`{REMOTE_EXTRA}` (for example: pip install -e '.[remote]')"
            ) from exc
        # Empty options preserve s3fs/botocore's normal credential chain.  Library callers
        # can pass profile, key/secret/token, endpoint_url/client_kwargs, config_kwargs, etc.
        return s3fs.S3FileSystem(**_options_for(filesystem_options, "s3"))
    if protocol == "http":
        try:
            import aiohttp  # noqa: F401 -- HTTPFileSystem imports/uses it lazily
            from fsspec.implementations.http import HTTPFileSystem
        except ImportError as exc:
            raise RuntimeError(
                "HTTP(S) input with DuckDB backend 'fsspec' requires aiohttp; install "
                f"`{REMOTE_EXTRA}` (for example: pip install -e '.[remote]')"
            ) from exc
        options = _options_for(filesystem_options, "http")
        client_kwargs = dict(options.pop("client_kwargs", {}))
        # aiohttp otherwise ignores HTTP(S)_PROXY and NO_PROXY.  This preserves normal
        # environment proxy discovery without changing TLS verification (which remains on).
        client_kwargs.setdefault("trust_env", True)
        options["client_kwargs"] = client_kwargs

        class DuckDBHTTPFileSystem(HTTPFileSystem):
            """Supply the metadata method DuckDB requires but fsspec leaves optional."""

            def modified(self, path: str) -> datetime:
                info = self.info(path)
                value = (
                    info.get("mtime")
                    or info.get("Last-Modified")
                    or info.get("last-modified")
                )
                if isinstance(value, datetime):
                    return value
                if isinstance(value, str):
                    try:
                        return parsedate_to_datetime(value)
                    except (TypeError, ValueError):
                        try:
                            return datetime.fromisoformat(value)
                        except ValueError:
                            pass
                # Modification time is advisory for these read-only handles. An epoch
                # value gives DuckDB a stable answer when a server omits Last-Modified.
                return datetime.fromtimestamp(0, UTC)

        return DuckDBHTTPFileSystem(**options)
    if protocol == "file":
        return fsspec.filesystem("file", **_options_for(filesystem_options, "file"))
    raise ValueError(f"unsupported fsspec protocol: {protocol}")


def _ensure_required_extensions(connection, required_extensions: Iterable[str]) -> None:
    available = {
        row[0]: {"installed": bool(row[1]), "loaded": bool(row[2]), "mode": row[3]}
        for row in connection.execute(
            "SELECT extension_name, installed, loaded, install_mode FROM duckdb_extensions()"
        ).fetchall()
    }
    for extension in required_extensions:
        state = available.get(extension)
        if state is None:
            raise RuntimeError(
                f"DuckDB does not report the required {extension!r} extension; fsspec mode "
                "will not enable automatic extension installation"
            )
        if state["loaded"]:
            continue
        if not state["installed"]:
            raise RuntimeError(
                f"DuckDB's required {extension!r} extension is not built in or installed. "
                "fsspec mode disables automatic extension installation; use a DuckDB build "
                f"that includes {extension!r} or install it explicitly before entering the "
                "restricted environment"
            )
        # Loading an already-installed JSON/Parquet capability is permitted.  httpfs is
        # never included in required_extensions and is checked separately below.
        connection.load_extension(extension)


def connect_duckdb(
    *,
    memory_limit_gb: int,
    spill_dir: PathValue,
    backend: str = "native",
    input_paths: Iterable[PathInput] = (),
    filesystem_options: Mapping[str, Mapping[str, Any]] | None = None,
    preserve_insertion_order: bool | None = None,
    required_extensions: Iterable[str] = ("parquet",),
):
    """Create a bounded DuckDB connection and configure the selected filesystem backend.

    ``filesystem_options`` is keyed by ``s3``, ``http`` or ``file`` and passed through to
    the corresponding fsspec implementation.  HTTP and HTTPS share one HTTPFileSystem.
    Outputs and the spill directory remain local; callers pass only remote-capable inputs
    in ``input_paths``.
    """
    selected = validate_duckdb_backend(backend)
    spill_path = require_local_path(spill_dir, "DuckDB spill directory")
    spill_path.mkdir(parents=True, exist_ok=True)
    duckdb = require_duckdb()
    config = None
    if selected == "fsspec":
        # Set at connection construction so no earlier statement can trigger httpfs.
        config = {
            "autoinstall_known_extensions": "false",
            "autoload_known_extensions": "false",
        }
    # DuckDB 1.0's Python binding rejects an explicit ``config=None`` even though newer
    # signatures display it as the default, so preserve the native call shape exactly.
    connection = (
        duckdb.connect(":memory:")
        if config is None
        else duckdb.connect(":memory:", config=config)
    )
    try:
        connection.execute(f"SET memory_limit = '{int(memory_limit_gb)}GB'")
        connection.execute(f"SET temp_directory = {sql_literal(spill_path)}")
        if preserve_insertion_order is not None:
            value = "true" if preserve_insertion_order else "false"
            connection.execute(f"SET preserve_insertion_order = {value}")

        if selected == "fsspec":
            _require_fsspec()  # Selecting the backend is explicit and requires its base package.
            _ensure_required_extensions(connection, required_extensions)
            paths = _flatten_paths(input_paths)
            schemes = {uri_scheme(path) for path in paths}
            unsupported = sorted(
                scheme
                for scheme in schemes
                if scheme and scheme not in FSSPEC_SUPPORTED_SCHEMES
            )
            if unsupported:
                raise ValueError(
                    "DuckDB fsspec backend supports file, http(s), and s3 inputs; "
                    f"unsupported scheme(s): {unsupported}"
                )
            protocols = set()
            if "file" in schemes:
                protocols.add("file")
            if schemes & {"http", "https"}:
                protocols.add("http")
            if "s3" in schemes:
                protocols.add("s3")
            for protocol in sorted(protocols):
                connection.register_filesystem(
                    _make_filesystem(protocol, filesystem_options)
                )

            httpfs = connection.execute(
                "SELECT loaded FROM duckdb_extensions() WHERE extension_name = 'httpfs'"
            ).fetchone()
            if httpfs and httpfs[0]:
                raise RuntimeError(
                    "DuckDB httpfs is loaded on an fsspec connection; refusing to continue"
                )
        return connection
    except Exception:
        connection.close()
        raise
