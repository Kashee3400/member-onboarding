from django.db import migrations

ORGANIZATION_MATCH = (
    "organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid"
)


def enable_rls(table: str, *, allow_unscoped_insert: bool = False) -> migrations.RunSQL:
    """
    Migration operation that isolates a table by organization_id.

    FORCE makes the policy apply to the table owner as well. Superusers and
    BYPASSRLS roles still skip it, so the runtime role must be neither.
    """
    write_check = ORGANIZATION_MATCH
    if allow_unscoped_insert:
        write_check = f"({ORGANIZATION_MATCH}) OR organization_id IS NULL"

    return migrations.RunSQL(
        sql=f"""
            ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
            ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
            CREATE POLICY organization_isolation ON {table}
                USING ({ORGANIZATION_MATCH})
                WITH CHECK ({write_check});
        """,
        reverse_sql=f"""
            DROP POLICY organization_isolation ON {table};
            ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;
            ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;
        """,
    )
