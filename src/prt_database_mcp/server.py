"""MCP server implementation."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, List, Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Resource, TextContent, Tool

from .catalog import catalog_markdown, load_catalog, search_catalog
from .config import load_settings
from .connections import DatabaseManager
from .query_guard import QueryRejectedError

_db: Optional[DatabaseManager] = None
_catalog: Dict[str, Any] = {"tables": {}}


def _get_db() -> DatabaseManager:
    if _db is None:
        raise RuntimeError("Database manager not initialized")
    return _db


@asynccontextmanager
async def server_lifespan(_app: Server) -> AsyncIterator[None]:
    global _db, _catalog
    settings = load_settings()
    _catalog = load_catalog(settings.catalog_path)
    _db = DatabaseManager(settings)
    await _db.open()
    try:
        yield
    finally:
        await _db.close()
        _db = None


def create_server() -> Server:
    """Build MCP Server with lifespan (database pool + catalog)."""
    return Server("prt-database", lifespan=server_lifespan)


server = create_server()


async def readiness_check() -> str | None:
    """Used by HTTP /readyz when transport=http."""
    try:
        db = _get_db()
        await db.ping()
        return None
    except Exception as exc:
        return str(exc)


@server.list_tools()
async def list_tools() -> List[Tool]:
    return [
        Tool(
            name="list_connections",
            description="List configured database connection profiles (local, dev, etc.).",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="ping_database",
            description="Run SELECT 1 on a connection profile to verify connectivity.",
            inputSchema={
                "type": "object",
                "properties": {
                    "connection": {
                        "type": "string",
                        "description": "Profile name (default from PRT_DB_MCP_DEFAULT_CONNECTION)",
                    }
                },
            },
        ),
        Tool(
            name="list_schemas",
            description="List PostgreSQL schemas.",
            inputSchema={
                "type": "object",
                "properties": {
                    "connection": {"type": "string"},
                },
            },
        ),
        Tool(
            name="list_tables",
            description="List tables and views in a schema.",
            inputSchema={
                "type": "object",
                "properties": {
                    "connection": {"type": "string"},
                    "schema": {"type": "string", "default": "public"},
                    "name_pattern": {
                        "type": "string",
                        "description": "SQL ILIKE pattern, e.g. %publisher%",
                    },
                },
            },
        ),
        Tool(
            name="describe_table",
            description="Column definitions, primary keys, foreign keys, and indexes.",
            inputSchema={
                "type": "object",
                "properties": {
                    "connection": {"type": "string"},
                    "schema": {"type": "string", "default": "public"},
                    "table": {"type": "string"},
                },
                "required": ["table"],
            },
        ),
        Tool(
            name="sample_rows",
            description="SELECT * FROM a table with a safe row limit (max 50).",
            inputSchema={
                "type": "object",
                "properties": {
                    "connection": {"type": "string"},
                    "schema": {"type": "string", "default": "public"},
                    "table": {"type": "string"},
                    "limit": {"type": "integer", "default": 10},
                },
                "required": ["table"],
            },
        ),
        Tool(
            name="execute_query",
            description="Run a read-only SELECT query with automatic LIMIT and timeout.",
            inputSchema={
                "type": "object",
                "properties": {
                    "connection": {"type": "string"},
                    "sql": {"type": "string"},
                    "max_rows": {"type": "integer"},
                },
                "required": ["sql"],
            },
        ),
        Tool(
            name="explain_query",
            description="EXPLAIN (FORMAT JSON) for a read-only SELECT.",
            inputSchema={
                "type": "object",
                "properties": {
                    "connection": {"type": "string"},
                    "sql": {"type": "string"},
                },
                "required": ["sql"],
            },
        ),
        Tool(
            name="search_catalog",
            description="Search table names and descriptions from the ProRata schema catalog.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                },
                "required": ["query"],
            },
        ),
    ]


def _text_result(payload: Any) -> List[TextContent]:
    return [TextContent(type="text", text=json.dumps(payload, indent=2, default=str))]


@server.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
    db = _get_db()
    args = arguments or {}

    try:
        if name == "list_connections":
            return _text_result(db.list_connections())

        if name == "ping_database":
            val = await db.ping(args.get("connection"))
            return _text_result({"ok": True, "result": val})

        if name == "list_schemas":
            return _text_result(await db.list_schemas(args.get("connection")))

        if name == "list_tables":
            return _text_result(
                await db.list_tables(
                    args.get("connection"),
                    args.get("schema", "public"),
                    args.get("name_pattern"),
                )
            )

        if name == "describe_table":
            return _text_result(
                await db.describe_table(
                    args.get("connection"),
                    args.get("schema", "public"),
                    args.get("table", ""),
                )
            )

        if name == "sample_rows":
            return _text_result(
                await db.sample_rows(
                    args.get("connection"),
                    args.get("schema", "public"),
                    args.get("table", ""),
                    int(args.get("limit", 10)),
                )
            )

        if name == "execute_query":
            return _text_result(
                await db.execute_query(
                    args.get("connection"),
                    args.get("sql", ""),
                    args.get("max_rows"),
                )
            )

        if name == "explain_query":
            return _text_result(
                await db.explain_query(args.get("connection"), args.get("sql", ""))
            )

        if name == "search_catalog":
            hits = search_catalog(_catalog, args.get("query", ""))
            return _text_result({"query": args.get("query"), "hits": hits})

        raise ValueError(f"Unknown tool: {name}")

    except QueryRejectedError as e:
        return _text_result({"error": str(e), "type": "QueryRejectedError"})
    except Exception as e:
        return _text_result({"error": str(e), "type": type(e).__name__})


@server.list_resources()
async def list_resources() -> List[Resource]:
    return [
        Resource(
            uri="prt-db://catalog",
            name="Schema catalog",
            description="Merged ProRata table catalog (Publisher Portal, Document Inference, indexing)",
            mimeType="text/markdown",
        ),
        Resource(
            uri="prt-db://domain/publishers",
            name="Publishers domain",
            description="Publisher Portal core tables",
            mimeType="text/markdown",
        ),
        Resource(
            uri="prt-db://domain/inference",
            name="Inference domain",
            description="Document Inference batch and request tables",
            mimeType="text/markdown",
        ),
    ]


@server.read_resource()
async def read_resource(uri: str) -> str:
    if uri == "prt-db://catalog":
        return catalog_markdown(_catalog)

    if uri == "prt-db://domain/publishers":
        return (
            "# Publisher Portal domain\n\n"
            "- **publishers** — publisher accounts (`publisher_group_id`, `name`, `enabled`, `config`)\n"
            "- **publisher_groups** — org grouping, tiers, GPA settings\n"
            "- **sites** — crawl targets per publisher\n"
            "- **channels**, **publisher_networks** — distribution / network membership\n"
            "- **users**, **tokens**, **invitations** — portal auth\n"
        )

    if uri == "prt-db://domain/inference":
        return (
            "# Document Inference domain\n\n"
            "- **inference_requests** — per-document inference lifecycle (`status`, `document_id`)\n"
            "- **batch_jobs** / **batch_documents** — Gemini batch processing\n"
            "- **realtime_requests** — low-latency path\n"
            "- **cron_locks** — orchestrator mutual exclusion\n"
        )

    raise ValueError(f"Unknown resource: {uri}")


async def run_stdio_server() -> None:
    """Legacy entry; prefer __main__ with --transport stdio."""
    from mcp.server.stdio import stdio_server

    srv = create_server()
    async with stdio_server() as (read_stream, write_stream):
        await srv.run(
            read_stream,
            write_stream,
            srv.create_initialization_options(),
        )
