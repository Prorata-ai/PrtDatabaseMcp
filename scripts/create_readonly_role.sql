-- Run against local PrtDatabaseService (localhost:54321) as superuser.
-- Example: psql postgresql://postgres:password@localhost:54321/postgres -f scripts/create_readonly_role.sql

DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'prt_mcp_readonly') THEN
    CREATE ROLE prt_mcp_readonly LOGIN PASSWORD 'prt_mcp_readonly';
  END IF;
END
$$;

GRANT CONNECT ON DATABASE postgres TO prt_mcp_readonly;
GRANT USAGE ON SCHEMA public TO prt_mcp_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO prt_mcp_readonly;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO prt_mcp_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO prt_mcp_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON SEQUENCES TO prt_mcp_readonly;
