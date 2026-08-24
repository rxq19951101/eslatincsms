# Production `app_super` role

`app_super` is a PostgreSQL cluster role used only by explicit
`SuperSessionLocal` connections. Local and test containers provision it
idempotently during startup. Production startup intentionally does not create
or alter cluster roles.

Before deploying to production, a DBA must review and execute the statements
in `csms/scripts/ensure_app_super_role.sql` using a privileged administrative
connection. Do not place a database password in that file or in shell history.

Run the read-only readiness check as the same database login used by CSMS:

```bash
psql "$DATABASE_URL" --set=ON_ERROR_STOP=1 \
  --file=csms/scripts/check_app_super_role.sql
```

The check verifies that `app_super` is `NOLOGIN BYPASSRLS`, that the CSMS login
may assume it, and that it has the required schema, table, and sequence
privileges. A missing or unusable role is a deployment blocker: CSMS privileged
connections fail closed rather than silently continuing as the ordinary role.
