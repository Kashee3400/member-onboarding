from django.db import migrations

from apps.core.rls import enable_rls


class Migration(migrations.Migration):
    dependencies = [("audit", "0001_initial")]

    operations = [
        # Failed logins happen before any organization is known, so they stay unscoped.
        enable_rls("audit_event", allow_unscoped_insert=True),
        migrations.RunSQL(
            sql="""
                CREATE FUNCTION reject_audit_event_change() RETURNS trigger AS $$
                BEGIN
                    RAISE EXCEPTION 'audit_event is append-only';
                END;
                $$ LANGUAGE plpgsql;

                CREATE TRIGGER audit_event_append_only
                    BEFORE UPDATE OR DELETE ON audit_event
                    FOR EACH ROW EXECUTE FUNCTION reject_audit_event_change();
            """,
            reverse_sql="""
                DROP TRIGGER audit_event_append_only ON audit_event;
                DROP FUNCTION reject_audit_event_change();
            """,
        ),
    ]
