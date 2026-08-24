-- Read-only production readiness check. This script never creates or alters roles.
DO $check_app_super$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_roles
        WHERE rolname = 'app_super' AND NOT rolcanlogin AND rolbypassrls
    ) THEN
        RAISE EXCEPTION 'app_super must exist with NOLOGIN and BYPASSRLS';
    END IF;

    IF NOT pg_has_role(current_user, 'app_super', 'MEMBER') THEN
        RAISE EXCEPTION 'current deployment role must be a member of app_super';
    END IF;

    IF NOT has_schema_privilege('app_super', 'public', 'USAGE') THEN
        RAISE EXCEPTION 'app_super lacks USAGE on schema public';
    END IF;

    IF EXISTS (
        SELECT 1 FROM pg_tables
        WHERE schemaname = 'public'
          AND NOT has_table_privilege(
              'app_super', quote_ident(schemaname) || '.' || quote_ident(tablename),
              'SELECT,INSERT,UPDATE,DELETE'
          )
    ) THEN
        RAISE EXCEPTION 'app_super lacks required privileges on one or more public tables';
    END IF;

    IF EXISTS (
        SELECT 1 FROM pg_sequences
        WHERE schemaname = 'public'
          AND NOT has_sequence_privilege(
              'app_super', quote_ident(schemaname) || '.' || quote_ident(sequencename),
              'USAGE,SELECT,UPDATE'
          )
    ) THEN
        RAISE EXCEPTION 'app_super lacks required privileges on one or more public sequences';
    END IF;
END
$check_app_super$;
