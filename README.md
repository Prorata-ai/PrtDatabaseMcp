# PrtDatabase MCP Server

MCP server for **ProRata PostgreSQL** (`PrtDatabaseService`). Gives safe, read-only schema discovery and SQL queries against local (and optional remote) Postgres.

## TODO: 
sync with newly-added PrtSchemas for schema defintions and metadata

## Prerequisites

1. **PrtDatabaseService** running:

   ```bash
   cd ../PrtDatabaseService
   docker-compose up -d
   ```

2. **Python 3.12+** and `uv` or `pip`.

3. (Recommended) Read-only DB role:

   ```bash
   psql postgresql://postgres:password@localhost:54321/postgres \
     -f scripts/create_readonly_role.sql
   ```

## Install

```bash
cd PrtDatabaseMcp
cp .env.example .env
python3.13 -m venv .venv    # or python3.12+
.venv/bin/pip install mcp asyncpg sqlparse pytest pytest-asyncio
python scripts/build_catalog.py
```

Optional editable install (requires hatchling): `.venv/bin/pip install -e ".[dev]"`

## Run

### stdio (Cursor local)

```bash
export PRT_DB_MCP_CONNECTIONS=local
export PRT_DB_MCP_LOCAL_URL=postgresql://postgres:password@localhost:54321/postgres
python -m prt_database_mcp --transport stdio
```

### HTTP (cloud / remote clients)

```bash
export PRT_DB_MCP_LOCAL_URL=postgresql://postgres:password@localhost:54321/postgres
export PRT_MCP_API_KEY=your-secret
python -m prt_database_mcp --transport http --port 8080
```

- MCP endpoint: `http://<host>:8080/mcp` with `Authorization: Bearer <PRT_MCP_API_KEY>`
- Health: `GET /healthz`, `GET /readyz` (checks Postgres when ready)

Requires `pip install -e ../PrtMcpCommon` (see [MCP_PLATFORM.md](../MCP_PLATFORM.md)).

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PRT_DB_MCP_CONNECTIONS` | `local` | Comma-separated profile names |
| `PRT_DB_MCP_{NAME}_URL` | — | Postgres DSN per profile |
| `PRT_DB_MCP_DEFAULT_CONNECTION` | first profile | Default when omitted |
| `PRT_DB_MCP_MAX_ROWS` | `100` | Default query row cap |
| `PRT_DB_MCP_HARD_MAX_ROWS` | `500` | Hard cap |
| `PRT_DB_MCP_STATEMENT_TIMEOUT_MS` | `10000` | Per-query timeout |
| `PRT_DB_MCP_ALLOW_WRITE` | `false` | Must stay false in v1 |
| `PRT_DB_MCP_CATALOG_PATH` | `catalog/generated.json` | Schema catalog |

## Security

- Only **SELECT** statements are accepted.
- **DDL/DML** keywords are rejected.
- Multiple statements (`;`) are rejected.
- Missing `LIMIT` gets one appended automatically.

## Tests

```bash
pytest -q
```

## Catalog regeneration

When Prisma or inference models change:

```bash
python scripts/build_catalog.py
```

## Example use-case: Cursor configuration

Merge into `~/.cursor/mcp.json` (or project `.cursor/mcp.json`):

See [mcp.json.example](mcp.json.example). Adjust the `--project` path to your machine.

After saving, restart Cursor or reload MCP servers. You should see **prt-database** with tools:

| Tool | Description |
|------|-------------|
| `list_connections` | Configured profiles |
| `ping_database` | `SELECT 1` health check |
| `list_schemas` | Non-system schemas |
| `list_tables` | Tables in a schema |
| `describe_table` | Columns, PKs, FKs, indexes |
| `sample_rows` | Up to 50 rows |
| `execute_query` | Read-only SELECT (auto `LIMIT`) |
| `explain_query` | `EXPLAIN (FORMAT JSON)` |
| `search_catalog` | Search Prisma/inference table catalog |

Resources: `prt-db://catalog`, `prt-db://domain/publishers`, `prt-db://domain/inference`.
