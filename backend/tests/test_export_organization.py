import json
import tarfile
from io import StringIO

import pytest
from django.core.management import call_command

from apps.applications.models import Application
from apps.core.tenancy import organization_context
from apps.documents.models import Document

from .conftest import make_member
from .test_applications import AADHAAR, World

pytestmark = pytest.mark.django_db(transaction=True)


def export(slug, folder):
    out = StringIO()
    call_command("export_organization", slug, "--out", str(folder), stdout=out)
    archive = next(folder.glob(f"{slug}_*.tar.gz"))
    with tarfile.open(archive) as opened:
        manifest = json.load(opened.extractfile("manifest.json"))
        data = json.load(opened.extractfile("data.json"))
        files = [name for name in opened.getnames() if name.startswith("media/")]
    return manifest, data, files


def test_an_export_holds_the_organization_and_nothing_else(org_a, org_b, tmp_path):
    world = World(org_a)
    done = world.fully_approved()
    make_member(org_b, "someone@b.test", "org_admin")

    manifest, data, files = export("org-a", tmp_path)

    with organization_context(org_a.id):
        assert manifest["rows"]["applications.application"] == Application.objects.count()
        documents = Document.objects.count()
    assert manifest["rows"]["documents.document"] == documents
    assert files and len(files) == manifest["files"]
    ids = {row["pk"] for row in data}
    assert done["id"] in ids
    emails = {row["fields"]["email"] for row in data if row["model"] == "accounts.user"}
    assert "admin@a.test" in emails
    assert "someone@b.test" not in emails
    assert str(org_b.id) not in json.dumps(data)


def test_an_export_keeps_secrets_sealed(org_a, tmp_path):
    World(org_a).fully_approved()

    _, data, files = export("org-a", tmp_path)

    users = [row for row in data if row["model"] == "accounts.user"]
    assert users and all("password" not in row["fields"] for row in users)
    application = next(row for row in data if row["model"] == "applications.application")
    assert application["fields"]["aadhaar_encrypted"]
    assert AADHAAR not in json.dumps(data)
    # Uploaded documents travel exactly as stored, sealed.
    sealed = next(name for name in files if name.endswith(".enc"))
    assert sealed


def test_an_unknown_organization_is_refused(db, tmp_path):
    with pytest.raises(Exception, match="No organization"):
        call_command("export_organization", "nobody", "--out", str(tmp_path))
