"""asyncpg connection pools per profile."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

import asyncpg

from .config import ConnectionProfile, Settings
from .query_guard import QueryRejectedError, apply_row_limit, validate_query


class DatabaseManager:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._pools: Dict[str, asyncpg.Pool] = {}

    async def open(self) -> None:
        for name, profile in self._settings.connections.items():
            self._pools[name] = await asyncpg.create_pool(
                dsn=profile.dsn,
                min_size=1,
                max_size=4,
                command_timeout=self._settings.statement_timeout_ms / 1000,
            )

    async def close(self) -> None:
        for pool in self._pools.values():
            await pool.close()
        self._pools.clear()

    def resolve_connection(self, name: Optional[str]) -> str:
        conn = name or self._settings.default_connection
        if conn not in self._pools:
            raise ValueError(
                f"Unknown connection {conn!r}. Available: {list(self._pools)}"
            )
        return conn

    def list_connections(self) -> List[Dict[str, Any]]:
        out = []
        for name, profile in self._settings.connections.items():
            out.append(
                {
                    "name": name,
                    "readOnly": profile.read_only,
                    "default": name == self._settings.default_connection,
                }
            )
        return out

    async def ping(self, connection: Optional[str] = None) -> int:
        conn = self.resolve_connection(connection)
        pool = self._pools[conn]
        async with pool.acquire() as conn_handle:
            row = await conn_handle.fetchval("SELECT 1")
            return int(row)

    async def _run(
        self,
        connection: Optional[str],
        sql: str,
        params: Optional[List[Any]] = None,
    ) -> List[asyncpg.Record]:
        conn = self.resolve_connection(connection)
        pool = self._pools[conn]
        async with pool.acquire() as conn_handle:
            timeout_ms = self._settings.statement_timeout_ms
            await conn_handle.execute(
                f"SET statement_timeout = {int(timeout_ms)}"
            )
            if params:
                return await conn_handle.fetch(sql, *params)
            return await conn_handle.fetch(sql)

    async def list_schemas(self, connection: Optional[str] = None) -> List[Dict[str, Any]]:
        rows = await self._run(
            connection,
            """
            SELECT schema_name
            FROM information_schema.schemata
            WHERE schema_name NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
            ORDER BY schema_name
            """,
        )
        return [{"schema": r["schema_name"]} for r in rows]

    async def list_tables(
        self,
        connection: Optional[str] = None,
        schema: str = "public",
        name_pattern: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        pattern = name_pattern or "%"
        rows = await self._run(
            connection,
            """
            SELECT table_schema, table_name, table_type
            FROM information_schema.tables
            WHERE table_schema = $1
              AND table_name ILIKE $2
            ORDER BY table_name
            """,
            [schema, pattern],
        )
        return [
            {
                "schema": r["table_schema"],
                "table": r["table_name"],
                "type": r["table_type"],
            }
            for r in rows
        ]

    async def describe_table(
        self,
        connection: Optional[str] = None,
        schema: str = "public",
        table: str = "",
    ) -> Dict[str, Any]:
        if not table:
            raise ValueError("table is required")

        columns = await self._run(
            connection,
            """
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema = $1 AND table_name = $2
            ORDER BY ordinal_position
            """,
            [schema, table],
        )
        pk_rows = await self._run(
            connection,
            """
            SELECT kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
            WHERE tc.constraint_type = 'PRIMARY KEY'
              AND tc.table_schema = $1
              AND tc.table_name = $2
            ORDER BY kcu.ordinal_position
            """,
            [schema, table],
        )
        fk_rows = await self._run(
            connection,
            """
            SELECT
                kcu.column_name,
                ccu.table_schema AS foreign_table_schema,
                ccu.table_name AS foreign_table_name,
                ccu.column_name AS foreign_column_name
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage AS ccu
              ON ccu.constraint_name = tc.constraint_name
             AND ccu.table_schema = tc.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND tc.table_schema = $1
              AND tc.table_name = $2
            """,
            [schema, table],
        )
        index_rows = await self._run(
            connection,
            """
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE schemaname = $1 AND tablename = $2
            ORDER BY indexname
            """,
            [schema, table],
        )

        return {
            "schema": schema,
            "table": table,
            "columns": [
                {
                    "name": c["column_name"],
                    "type": c["data_type"],
                    "nullable": c["is_nullable"] == "YES",
                    "default": c["column_default"],
                }
                for c in columns
            ],
            "primaryKey": [r["column_name"] for r in pk_rows],
            "foreignKeys": [
                {
                    "column": r["column_name"],
                    "references": f"{r['foreign_table_schema']}.{r['foreign_table_name']}.{r['foreign_column_name']}",
                }
                for r in fk_rows
            ],
            "indexes": [
                {"name": r["indexname"], "definition": r["indexdef"]} for r in index_rows
            ],
        }

    async def sample_rows(
        self,
        connection: Optional[str] = None,
        schema: str = "public",
        table: str = "",
        limit: int = 10,
    ) -> Dict[str, Any]:
        if not table:
            raise ValueError("table is required")
        if not re_valid_identifier(schema) or not re_valid_identifier(table):
            raise ValueError("Invalid schema or table name")

        lim = min(max(1, limit), 50)
        sql = f'SELECT * FROM "{schema}"."{table}" LIMIT {lim}'
        validate_query(sql, allow_write=self._settings.allow_write)
        rows = await self._run(connection, sql)
        return {
            "schema": schema,
            "table": table,
            "rowCount": len(rows),
            "rows": [_record_to_dict(r) for r in rows],
        }

    async def execute_query(
        self,
        connection: Optional[str] = None,
        sql: str = "",
        max_rows: Optional[int] = None,
    ) -> Dict[str, Any]:
        guard = validate_query(sql, allow_write=self._settings.allow_write)
        capped = apply_row_limit(
            guard.sql,
            max_rows or self._settings.max_rows,
            self._settings.hard_max_rows,
        )
        rows = await self._run(connection, capped)
        return {
            "sql": capped,
            "rowCount": len(rows),
            "rows": [_record_to_dict(r) for r in rows],
        }

    async def explain_query(
        self,
        connection: Optional[str] = None,
        sql: str = "",
    ) -> Dict[str, Any]:
        guard = validate_query(sql, allow_write=self._settings.allow_write)
        explain_sql = f"EXPLAIN (FORMAT JSON) {guard.sql}"
        rows = await self._run(connection, explain_sql)
        plan = rows[0][0] if rows else None
        if isinstance(plan, str):
            plan = json.loads(plan)
        return {"sql": guard.sql, "plan": plan}


def re_valid_identifier(name: str) -> bool:
    return bool(re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", name))


def _record_to_dict(record: asyncpg.Record) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key in record.keys():
        val = record[key]
        if hasattr(val, "isoformat"):
            val = val.isoformat()
        elif isinstance(val, (bytes, bytearray)):
            val = f"<bytes len={len(val)}>"
        out[key] = val
    return out
