"""
The form number counter becomes one per prefix. The existing counter belonged to the
organization's prefix at the time, so it carries on under that series.
"""

from django.db import migrations

MOVE = """
    UPDATE application_sequence
    SET key = 'form_number:' || COALESCE(
        (SELECT form_prefix FROM member_code_settings LIMIT 1), 'A'
    )
    WHERE key = 'form_number'
"""
BACK = """
    UPDATE application_sequence SET key = 'form_number' WHERE key LIKE 'form_number:%%'
"""


def _each_organization(schema_editor, sql):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SELECT id FROM organization")
        for (organization_id,) in cursor.fetchall():
            # Both tables are row-level secured: one organization at a time.
            cursor.execute("SELECT set_config('app.organization_id', %s, true)", [str(organization_id)])
            cursor.execute(sql)
        cursor.execute("SELECT set_config('app.organization_id', '', true)")


class Migration(migrations.Migration):
    dependencies = [("applications", "0030_fee_collection_bank")]

    operations = [
        migrations.RunPython(
            lambda apps, editor: _each_organization(editor, MOVE),
            lambda apps, editor: _each_organization(editor, BACK),
        )
    ]
