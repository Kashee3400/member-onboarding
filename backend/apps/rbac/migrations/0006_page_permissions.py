"""
Every sidebar page now has a permission of its own. Roles keep what they could
already open: settings.manage becomes each settings page, the application lists
follow applications.view and Locations follows hierarchy.view. The PDF Center is
the exception, left to the standard roles that sync_system_roles fills.
"""

from django.db import migrations

SETTINGS = [
    "settings.branding",
    "settings.review_steps",
    "settings.integrations",
    "settings.connected_apps",
    "settings.member_code",
    "settings.form_lists",
    "settings.banks",
]
LISTS = ["applications.list_pending", "applications.list_approved", "applications.list_rejected"]

# (a permission the role holds, what it gains, whether the old code goes)
SPLITS = [
    ("settings.manage", SETTINGS, True),
    ("applications.view", LISTS, False),
    ("hierarchy.view", ["locations.view"], False),
]

ADD = """
    UPDATE rbac_role
    SET permissions = ARRAY(
        SELECT DISTINCT code FROM unnest(permissions || %s::varchar[]) AS code ORDER BY code
    )
    WHERE %s = ANY(permissions)
"""
DROP = "UPDATE rbac_role SET permissions = array_remove(permissions, %s) WHERE %s = ANY(permissions)"


def split(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SELECT id FROM organization")
        for (organization_id,) in cursor.fetchall():
            # rbac_role is row-level secured: work inside one organization at a time.
            cursor.execute("SELECT set_config('app.organization_id', %s, true)", [str(organization_id)])
            for held, gained, retire in SPLITS:
                cursor.execute(ADD, [gained, held])
                if retire:
                    cursor.execute(DROP, [held, held])
        cursor.execute("SELECT set_config('app.organization_id', '', true)")


def join(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SELECT id FROM organization")
        for (organization_id,) in cursor.fetchall():
            cursor.execute("SELECT set_config('app.organization_id', %s, true)", [str(organization_id)])
            cursor.execute(
                """
                UPDATE rbac_role SET permissions = ARRAY(
                    SELECT DISTINCT code FROM unnest(permissions || ARRAY['settings.manage']::varchar[]) AS code
                    ORDER BY code
                )
                WHERE permissions && %s::varchar[]
                """,
                [SETTINGS],
            )
            new = SETTINGS + LISTS + ["locations.view", "applications.pdf_center"]
            cursor.execute(
                """
                UPDATE rbac_role SET permissions = ARRAY(
                    SELECT code FROM unnest(permissions) AS code WHERE code <> ALL(%s::varchar[])
                    ORDER BY code
                )
                """,
                [new],
            )
        cursor.execute("SELECT set_config('app.organization_id', '', true)")


class Migration(migrations.Migration):
    dependencies = [("rbac", "0005_staff_invitation_rls")]

    operations = [migrations.RunPython(split, join)]
