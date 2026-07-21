-- Idempotent local/test provisioning for the NOLOGIN role used by SuperSessionLocal.
-- Production role ownership and grants remain an explicit DBA responsibility.

DO $provision_app_super$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_super') THEN
        CREATE ROLE app_super NOLOGIN BYPASSRLS;
    ELSE
        ALTER ROLE app_super NOLOGIN BYPASSRLS;
    END IF;
END
$provision_app_super$;

GRANT app_super TO CURRENT_USER;
GRANT USAGE ON SCHEMA public TO app_super;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_super;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO app_super;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_super;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO app_super;
