"""
The Hierarchy page has a permission of its own, apart from reading the masters for
filters, so it can stay with the organization's administrators. A custom role that
manages the hierarchy keeps the page; standard roles follow the catalog on deploy.
"""

from django.db import migrations

ADD = """
    UPDATE rbac_role
    SET permissions = ARRAY(
        SELECT DISTINCT code FROM unnest(permissions || ARRAY['masters.hierarchy']::varchar[]) AS code
        ORDER BY code
    )
    WHERE NOT is_system AND 'hierarchy.manage' = ANY(permissions)
"""
DROP = "UPDATE rbac_role SET permissions = array_remove(permissions, 'masters.hierarchy')"


def _each_organization(schema_editor, sql):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SELECT id FROM organization")
        for (organization_id,) in cursor.fetchall():
            # rbac_role is row-level secured: one organization at a time.
            cursor.execute("SELECT set_config('app.organization_id', %s, true)", [str(organization_id)])
            cursor.execute(sql)
        cursor.execute("SELECT set_config('app.organization_id', '', true)")


def forwards(apps, schema_editor):
    _each_organization(schema_editor, ADD)


def backwards(apps, schema_editor):
    _each_organization(schema_editor, DROP)


class Migration(migrations.Migration):
    dependencies = [("rbac", "0007_role_customized")]

    operations = [migrations.RunPython(forwards, backwards)]
