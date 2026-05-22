"""Environment-based configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class ConnectionProfile:
    name: str
    dsn: str
    read_only: bool = True


@dataclass(frozen=True)
class Settings:
    connections: Dict[str, ConnectionProfile]
    default_connection: str
    max_rows: int
    hard_max_rows: int
    statement_timeout_ms: int
    allow_write: bool
    catalog_path: Optional[str]


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if raw == "":
        return default
    return raw in ("1", "true", "yes", "on")


def load_settings() -> Settings:
    names_raw = os.getenv("PRT_DB_MCP_CONNECTIONS", "local")
    names = [n.strip() for n in names_raw.split(",") if n.strip()]
    allow_write = _env_bool("PRT_DB_MCP_ALLOW_WRITE", False)

    connections: Dict[str, ConnectionProfile] = {}
    for name in names:
        key = f"PRT_DB_MCP_{name.upper()}_URL"
        dsn = os.getenv(key, "").strip()
        if not dsn:
            raise ValueError(f"Missing connection URL env var: {key}")
        connections[name] = ConnectionProfile(
            name=name,
            dsn=dsn,
            read_only=not allow_write,
        )

    if not connections:
        raise ValueError("PRT_DB_MCP_CONNECTIONS must list at least one profile")

    default = os.getenv("PRT_DB_MCP_DEFAULT_CONNECTION", names[0]).strip()
    if default not in connections:
        raise ValueError(
            f"PRT_DB_MCP_DEFAULT_CONNECTION={default!r} is not in {list(connections)}"
        )

    catalog = os.getenv("PRT_DB_MCP_CATALOG_PATH", "").strip() or None
    if catalog is None:
        repo_default = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "catalog",
            "generated.json",
        )
        if os.path.isfile(repo_default):
            catalog = repo_default

    return Settings(
        connections=connections,
        default_connection=default,
        max_rows=_env_int("PRT_DB_MCP_MAX_ROWS", 100),
        hard_max_rows=_env_int("PRT_DB_MCP_HARD_MAX_ROWS", 500),
        statement_timeout_ms=_env_int("PRT_DB_MCP_STATEMENT_TIMEOUT_MS", 10000),
        allow_write=allow_write,
        catalog_path=catalog,
    )
