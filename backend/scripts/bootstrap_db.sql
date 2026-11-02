-- Run once as a PostgreSQL superuser, against the `postgres` database:
--   psql -U postgres -f scripts/bootstrap_db.sql \
--        -v owner_password='...' -v app_password='...'
--
-- Two roles keep tenant isolation enforceable:
--   onboarding_owner  owns the schema, used only for migrations
--   onboarding_app    used at runtime; subject to row level security

CREATE ROLE onboarding_owner LOGIN PASSWORD :'owner_password'
    NOSUPERUSER NOBYPASSRLS NOCREATEROLE NOCREATEDB;
CREATE ROLE onboarding_app LOGIN PASSWORD :'app_password'
    NOSUPERUSER NOBYPASSRLS NOCREATEROLE NOCREATEDB;

CREATE DATABASE member_onboarding OWNER onboarding_owner;

\connect member_onboarding

REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT ALL ON SCHEMA public TO onboarding_owner;
GRANT USAGE ON SCHEMA public TO onboarding_app;

ALTER DEFAULT PRIVILEGES FOR ROLE onboarding_owner IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO onboarding_app;
ALTER DEFAULT PRIVILEGES FOR ROLE onboarding_owner IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO onboarding_app;
