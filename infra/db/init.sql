-- tracer-ai db init script (D-2.09 + RESEARCH.md Pitfall 2)
-- Runs once per empty data volume as the `postgres` superuser.
-- Creates the application role without superuser privileges (so the Alembic
-- migration running as `tracer` cannot CREATE EXTENSION) -- extension creation
-- is this script's job, not the migration's.

-- 1. Application role (matches .env.example DATABASE_URL credentials)
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'tracer') THEN
        CREATE ROLE tracer
            LOGIN
            PASSWORD 'tracer'
            NOSUPERUSER
            NOCREATEROLE
            NOCREATEDB;
    END IF;
END
$$;

-- 2. Application database (owned by tracer)
SELECT 'CREATE DATABASE tracer_ai OWNER tracer'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'tracer_ai')
\gexec

-- 3. Connect into tracer_ai and enable pgvector (per D-2.09 + Pitfall 2)
\c tracer_ai
CREATE EXTENSION IF NOT EXISTS vector;

-- 4. Grant schema usage to tracer so the migration can CREATE TABLE
GRANT ALL ON SCHEMA public TO tracer;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO tracer;
