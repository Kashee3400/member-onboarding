import threading
import uuid
from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from PIL import Image, ImageDraw
from rest_framework.test import APIClient

from apps.applications import form
from apps.applications.models import (
    Application,
    Member,
    MemberCodeSettings,
    ReviewStepAccess,
    Signatory,
    Status,
)
from apps.audit.models import AuditEvent
from apps.core.tenancy import organization_context
from apps.documents.services import set_staff_signature
from apps.hierarchy.models import Mcc, Mpp, Plant
from apps.hierarchy.services import assign_mpp
from apps.organizations.models import Membership
from apps.rbac.models import Role
from apps.rbac.services import grant_role

from .conftest import authenticated_client, make_member

pytestmark = pytest.mark.django_db(transaction=True)

URL = "/api/v1/applications/"
AADHAAR = "234123412346"
OTHER_AADHAAR = "496858245229"
ACCOUNT = "656302010000644"
PAYMENT = {
    "bank_name": "Indian Bank",
    "branch_name": "Station Road",
    "reference": "",
    "amount": 50,
    "deposited_on": "2026-01-15",
}


def jpeg_bytes():
    buffer = BytesIO()
    Image.new("RGB", (40, 40), "lightblue").save(buffer, "JPEG")
    return buffer.getvalue()


def png_bytes():
    """A signature as a scanner app gives it: ink on a clear background."""
    image = Image.new("RGBA", (120, 40), (0, 0, 0, 0))
    ImageDraw.Draw(image).line([(10, 30), (60, 8), (110, 30)], fill="navy", width=4)
    buffer = BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def complete_form():
    return {
        "applicant": {
            "full_name": "Test Applicant",
            "relation_type": "husband",
            "relation_name": "Test Husband",
            "gender": "female",
            "date_of_birth": "1984-01-15",
            "education": "12th",
            "category": "obc",
        },
        "address": {
            "post_office": "Mondh",
            "tehsil": "Bhadohi",
            "district": "Sant Ravidas Nagar",
            "state": "Uttar Pradesh",
            "pincode": "221406",
            "mobile": "9170800000",
        },
        "location": {"latitude": 25.41507, "longitude": 82.51469},
        "family": [{"name": "Test Husband", "gender": "male", "age": 44, "relation": "husband"}],
        "animals": {
            "buffalo_heifer": 1,
            "buffalo_in_milk": 2,
            "production_lpd": 12,
            "consumption_lpd": 4,
        },
        "bank": {
            "holder_name": "Test Applicant",
            "ifsc": "UBIN0572161",
            "bank_name": "Union Bank of India",
            "branch_name": "Siyarha",
        },
        "nominee": {
            "name": "Test Husband",
            "relation": "husband",
            "date_of_birth": "1982-01-01",
            "address": "Same village",
        },
        "declaration": {
            "accepted_terms": True,
            "no_household_member": True,
            "not_sahayak_or_employee": True,
        },
    }


REVIEW_STEPS = {
    "member": ["cs_legal"],
    "address": ["cs_legal"],
    "milk": ["area_manager"],
    "bank": ["finance"],
    "household": ["area_manager"],
    "nominee": ["cs_legal"],
    "village": ["area_manager"],
    "fee": ["finance"],
}


def choose_review_steps(steps=None):
    roles = {role.code: role for role in Role.objects.all()}
    ReviewStepAccess.objects.all().delete()
    for step, codes in (steps or REVIEW_STEPS).items():
        for code in codes:
            ReviewStepAccess.objects.create(step=step, role=roles[code])


class World:
    """One MPP with one person at each workflow stage."""

    def __init__(self, org):
        self.org = org
        self.admin = make_member(org, "admin@a.test", "org_admin")
        self.facilitator = self.member("field@a.test", "facilitator")
        self.manager = self.member("am@a.test", "area_manager")
        self.legal = self.member("cs@a.test", "cs_legal")
        self.finance = self.member("finance@a.test", "finance")
        with organization_context(org.id):
            choose_review_steps()
            for stage, user in (
                (Status.PENDING_CS, self.legal),
                (Status.PENDING_FINANCE, self.finance),
            ):
                Signatory.objects.create(stage=stage, membership=Membership.objects.get(user=user))
            plant = Plant.objects.create(code="P1", name="Plant")
            mcc = Mcc.objects.create(plant=plant, code="6", name="Bhadohi")
            self.mpp = Mpp.objects.create(
                mcc=mcc, code="1305", name="Dudwa", village_code="00209982"
            )
            self.other_mpp = Mpp.objects.create(
                mcc=mcc, code="1152", name="Tilthi", village_code="00211673"
            )
            assign_mpp(
                mpp=self.mpp,
                membership=Membership.objects.get(user=self.facilitator),
                responsibility="facilitator",
                actor=self.admin,
            )
            assign_mpp(
                mpp=self.mpp,
                membership=Membership.objects.get(user=self.manager),
                responsibility="area_manager",
                actor=self.admin,
            )

    def member(self, email, role):
        """Staff who can act: everyone needs a signature on file."""
        user = make_member(self.org, email, role)
        with organization_context(self.org.id):
            set_staff_signature(
                Membership.objects.get(user=user), raw=png_bytes(), actor=self.admin
            )
        return user

    def client(self, user):
        return authenticated_client(self.org, user)

    def attach_documents(self, client, application_id):
        for kind in ("photo", "member_signature", "aadhaar_front", "aadhaar_back", "passbook"):
            response = client.post(
                f"{URL}{application_id}/documents/",
                {"document_type": kind, "file": SimpleUploadedFile("x.jpg", jpeg_bytes())},
                format="multipart",
            )
            assert response.status_code == 201, response.content

    def draft(self, client=None, **extra):
        client = client or self.client(self.facilitator)
        response = client.post(URL, {"client_id": uuid.uuid4().hex, "mpp": str(self.mpp.id)})
        assert response.status_code == 201, response.content
        return response.data

    def filled(self, aadhaar=AADHAAR):
        client = self.client(self.facilitator)
        application = self.draft(client)
        data = complete_form()
        # Each member needs her own mobile number, so it follows the Aadhaar number.
        data["address"]["mobile"] = f"9{aadhaar[-9:]}"
        response = client.patch(
            f"{URL}{application['id']}/",
            {"data": data, "aadhaar_number": aadhaar, "account_number": ACCOUNT},
        )
        assert response.status_code == 200, response.content
        self.attach_documents(client, application["id"])
        return response.data

    def submitted(self, aadhaar=AADHAAR):
        application = self.filled(aadhaar)
        response = self.client(self.facilitator).post(f"{URL}{application['id']}/submit/")
        assert response.status_code == 200, response.content
        return response.data

    def prepare_payment(self, application):
        client = self.client(self.finance)
        response = client.post(
            f"{URL}{application['id']}/documents/",
            {"document_type": "payment_proof", "file": SimpleUploadedFile("p.jpg", jpeg_bytes())},
            format="multipart",
        )
        assert response.status_code == 201, response.content
        response = client.post(f"{URL}{application['id']}/payment/", PAYMENT)
        assert response.status_code == 200, response.content

    def approve(self, application, user):
        if user is self.finance:
            current = self.client(user).get(f"{URL}{application['id']}/")
            if current.status_code == 200 and current.data["status"] == "pending_finance":
                self.prepare_payment(application)
        return self.client(user).post(f"{URL}{application['id']}/decide/", {"decision": "approved"})

    def fully_approved(self, aadhaar=AADHAAR):
        application = self.submitted(aadhaar)
        for user in (self.manager, self.legal, self.finance):
            response = self.approve(application, user)
            assert response.status_code == 200, response.content
        return response.data


@pytest.fixture
def world(org_a):
    return World(org_a)


# Drafts ------------------------------------------------------------------------------


def test_partial_answers_save_as_a_draft(world):
    client = world.client(world.facilitator)
    application = world.draft(client)

    response = client.patch(
        f"{URL}{application['id']}/", {"data": {"applicant": {"full_name": "Half Done"}}}
    )

    assert response.status_code == 200
    assert response.data["status"] == "draft"
    assert response.data["applicant_name"] == "Half Done"


def test_sections_save_independently(world):
    client = world.client(world.facilitator)
    url = f"{URL}{world.draft(client)['id']}/"

    client.patch(url, {"data": {"applicant": {"full_name": "A"}}})
    response = client.patch(url, {"data": {"address": {"tehsil": "B"}}})

    assert response.data["data"]["applicant"]["full_name"] == "A"
    assert response.data["data"]["address"]["tehsil"] == "B"


def test_a_retried_create_returns_the_same_draft(world):
    client = world.client(world.facilitator)
    body = {"client_id": "device-draft-1", "mpp": str(world.mpp.id)}

    first = client.post(URL, body)
    second = client.post(URL, body)

    assert first.status_code == 201
    assert second.status_code == 200
    assert first.data["id"] == second.data["id"]


def test_an_old_device_cannot_overwrite_newer_work(world):
    client = world.client(world.facilitator)
    application = world.draft(client)
    url = f"{URL}{application['id']}/"
    stale = application["version"]

    client.patch(url, {"version": stale, "data": {"applicant": {"full_name": "New"}}})
    response = client.patch(url, {"version": stale, "data": {"applicant": {"full_name": "Old"}}})

    assert response.status_code == 409
    assert client.get(url).data["applicant_name"] == "New"


def test_a_draft_can_be_discarded(world):
    client = world.client(world.facilitator)
    application = world.draft(client)

    assert client.post(f"{URL}{application['id']}/discard/").status_code == 204
    assert client.get(f"{URL}{application['id']}/").status_code == 404


# Sensitive numbers -------------------------------------------------------------------


def test_sensitive_numbers_are_encrypted_and_never_returned(world, org_a):
    application = world.filled()
    client = world.client(world.facilitator)

    body = client.get(f"{URL}{application['id']}/").content.decode()

    assert AADHAAR not in body
    assert ACCOUNT not in body
    assert application["aadhaar_last4"] == AADHAAR[-4:]
    with organization_context(org_a.id):
        with connection.cursor() as cursor:
            cursor.execute("SELECT row_to_json(application)::text FROM application")
            stored = cursor.fetchone()[0]
    assert AADHAAR not in stored
    assert ACCOUNT not in stored


def test_invalid_aadhaar_is_rejected_by_checksum(world):
    client = world.client(world.facilitator)
    url = f"{URL}{world.draft(client)['id']}/"

    response = client.patch(url, {"aadhaar_number": "234123412345"})

    assert response.status_code == 400


def test_a_duplicate_aadhaar_is_caught_while_filling(world):
    world.filled()
    client = world.client(world.facilitator)

    response = client.patch(f"{URL}{world.draft(client)['id']}/", {"aadhaar_number": AADHAAR})

    assert response.status_code == 409


def test_a_discarded_draft_frees_its_aadhaar(world):
    client = world.client(world.facilitator)
    first = world.filled()
    client.post(f"{URL}{first['id']}/discard/")

    assert world.filled()["aadhaar_last4"] == AADHAAR[-4:]


def test_aadhaar_can_repeat_across_organizations(world, org_b):
    world.filled()
    admin_b = make_member(org_b, "b@b.test", "org_admin")
    with organization_context(org_b.id):
        plant = Plant.objects.create(code="P1", name="Plant")
        mcc = Mcc.objects.create(plant=plant, code="1", name="M")
        mpp = Mpp.objects.create(mcc=mcc, code="1", name="X", village_code="00000001")
    facilitator = make_member(org_b, "f@b.test", "facilitator")
    with organization_context(org_b.id):
        assign_mpp(
            mpp=mpp,
            membership=Membership.objects.get(user=facilitator),
            responsibility="facilitator",
            actor=admin_b,
        )

    client = authenticated_client(org_b, facilitator)
    draft = client.post(URL, {"client_id": "x", "mpp": str(mpp.id)}).data

    assert client.patch(f"{URL}{draft['id']}/", {"aadhaar_number": AADHAAR}).status_code == 200


# Submission rules --------------------------------------------------------------------


def test_an_incomplete_form_cannot_be_submitted(world):
    client = world.client(world.facilitator)
    application = world.draft(client)

    response = client.post(f"{URL}{application['id']}/submit/")

    assert response.status_code == 400
    details = response.data["error"]["details"]
    assert "applicant.full_name" in details
    assert "applicant.aadhaar_number" in details
    assert "bank.account_number" in details


@pytest.mark.parametrize(
    ("change", "path"),
    [
        (lambda d: d["applicant"].update(date_of_birth="2015-01-01"), "applicant.date_of_birth"),
        (lambda d: d["address"].update(mobile="12345"), "address.mobile"),
        (lambda d: d["address"].update(pincode="12"), "address.pincode"),
        (lambda d: d["bank"].update(ifsc="BAD"), "bank.ifsc"),
        (lambda d: d["animals"].update(consumption_lpd=50), "animals.consumption_lpd"),
        (
            lambda d: d["animals"].update(buffalo_heifer=0, buffalo_in_milk=0),
            "animals.indigenous_heifer",
        ),
        (lambda d: d["declaration"].update(accepted_terms=False), "declaration.accepted_terms"),
        (lambda d: d["nominee"].update(date_of_birth="2020-01-01"), "nominee.guardian_name"),
        (lambda d: d["nominee"].update(guardian_name="Someone"), "nominee.guardian_name"),
        (lambda d: d["location"].update(latitude=500), "location.latitude"),
        (lambda d: d["location"].update(latitude=""), "location.latitude"),
        (lambda d: d["applicant"].update(category="unknown"), "applicant.category"),
        (lambda d: d["family"][0].update(name=""), "family.0.name"),
        (lambda d: d["family"][0].update(age=500), "family.0.age"),
        (lambda d: d["family"][0].update(relation="friend"), "family.0.relation"),
        (lambda d: d.update(family=d["family"] * 7), "family"),
    ],
)
def test_form_policies_are_enforced(world, change, path):
    client = world.client(world.facilitator)
    application = world.filled()
    data = complete_form()
    change(data)
    client.patch(f"{URL}{application['id']}/", {"data": data})

    response = client.post(f"{URL}{application['id']}/submit/")

    assert response.status_code == 400
    assert path in response.data["error"]["details"]


def test_totals_are_computed_by_the_server(world):
    assert world.filled()["computed"] == {
        "total_animals": 3,
        "total_in_milk": 2,
        "surplus_lpd": 8.0,
    }


def test_a_name_mismatch_warns_but_does_not_block(world):
    client = world.client(world.facilitator)
    application = world.filled()
    data = complete_form()
    data["bank"]["holder_name"] = "Tést Different"
    response = client.patch(f"{URL}{application['id']}/", {"data": data})

    assert response.data["warnings"]
    assert client.post(f"{URL}{application['id']}/submit/").status_code == 200


def test_submitting_assigns_a_form_number_and_goes_to_the_area_manager(world):
    application = world.submitted()

    assert application["status"] == "pending_am"
    assert application["form_number"] == "A00001"
    assert application["revision"] == 1


def test_a_submitted_form_cannot_be_edited(world):
    application = world.submitted()
    response = world.client(world.facilitator).patch(
        f"{URL}{application['id']}/", {"data": {"applicant": {"full_name": "Changed"}}}
    )
    assert response.status_code == 409


# Workflow ----------------------------------------------------------------------------


def test_the_form_passes_through_every_stage_in_order(world):
    application = world.submitted()

    assert world.approve(application, world.manager).data["status"] == "pending_cs"
    assert world.approve(application, world.legal).data["status"] == "pending_finance"
    final = world.approve(application, world.finance)

    assert final.data["status"] == "approved"
    assert [d["stage"] for d in final.data["decisions"]] == [
        "pending_am",
        "pending_cs",
        "pending_finance",
    ]


def test_no_stage_can_be_skipped(world):
    application = world.submitted()

    assert world.approve(application, world.legal).status_code == 403
    assert world.approve(application, world.finance).status_code == 403


def test_a_stage_cannot_decide_twice(world):
    application = world.submitted()
    world.approve(application, world.manager)
    assert world.approve(application, world.manager).status_code == 403


def test_an_admin_cannot_approve(world):
    application = world.submitted()
    assert world.approve(application, world.admin).status_code == 403


def test_the_preparer_cannot_approve_their_own_form(world):
    both = world.member("both@a.test", "area_manager")
    with organization_context(world.org.id):
        membership = Membership.objects.get(user=both)
        grant_role(membership, "facilitator")
        assign_mpp(
            mpp=world.mpp, membership=membership, responsibility="area_manager", actor=world.admin
        )

    client = world.client(both)
    application = world.draft(client)
    client.patch(
        f"{URL}{application['id']}/",
        {"data": complete_form(), "aadhaar_number": AADHAAR, "account_number": ACCOUNT},
    )
    world.attach_documents(client, application["id"])
    assert client.post(f"{URL}{application['id']}/submit/").status_code == 200

    response = client.post(f"{URL}{application['id']}/decide/", {"decision": "approved"})

    assert response.status_code == 403


def test_rejecting_needs_a_reason(world):
    application = world.submitted()
    response = world.client(world.manager).post(
        f"{URL}{application['id']}/decide/", {"decision": "rejected", "reason": "  "}
    )
    assert response.status_code == 400


@pytest.mark.parametrize("stages", [1, 2, 3])
def test_rejection_at_any_stage_returns_to_the_facilitator_and_restarts(world, stages):
    application = world.submitted()
    people = [world.manager, world.legal, world.finance]
    for user in people[: stages - 1]:
        world.approve(application, user)

    field = ["animals.production_lpd", "applicant.full_name", "bank.ifsc"][stages - 1]
    rejected = world.client(people[stages - 1]).post(
        f"{URL}{application['id']}/decide/",
        {"decision": "rejected", "reason": "Please correct this", "rejected_fields": [field]},
    )
    assert rejected.data["status"] == "rejected"
    assert rejected.data["rejection_reason"] == "Please correct this"
    assert rejected.data["rejected_fields"] == [field]

    client = world.client(world.facilitator)
    data = complete_form()
    data["bank"]["ifsc"] = "UBIN0572162"
    assert client.patch(f"{URL}{application['id']}/", {"data": data}).status_code == 200

    resubmitted = client.post(f"{URL}{application['id']}/submit/")
    assert resubmitted.data["status"] == "pending_am"
    assert resubmitted.data["revision"] == 2
    assert resubmitted.data["rejection_reason"] == ""
    assert resubmitted.data["form_number"] == application["form_number"]
    assert len(resubmitted.data["revisions"]) == 2


def test_a_resubmission_can_be_compared_with_what_was_rejected(world):
    application = world.submitted()
    marked = "animals.production_lpd"
    rejected = world.client(world.manager).post(
        f"{URL}{application['id']}/decide/",
        {"decision": "rejected", "reason": "Milk looks wrong", "rejected_fields": [marked]},
    )
    assert rejected.status_code == 200, rejected.content
    client = world.client(world.facilitator)
    data = complete_form()
    data["bank"]["ifsc"] = "UBIN0572162"
    client.patch(f"{URL}{application['id']}/", {"data": data})

    client.post(f"{URL}{application['id']}/submit/")
    detail = world.client(world.manager).get(f"{URL}{application['id']}/").data

    rejection = detail["decisions"][-1]
    assert rejection["rejected_fields"] == [marked]
    assert detail["rejected_fields"] == []
    current, previous = detail["revisions"]
    assert current["data"]["bank"]["ifsc"] != previous["data"]["bank"]["ifsc"]
    assert current["aadhaar_last4"] == previous["aadhaar_last4"] != ""


# MPP ownership -----------------------------------------------------------------------


def test_a_transfer_moves_applications_and_keeps_the_author(world):
    application = world.filled()
    replacement = world.member("next@a.test", "facilitator")
    leaver = world.client(world.facilitator)
    assert leaver.get(f"{URL}{application['id']}/").status_code == 200

    with organization_context(world.org.id):
        assign_mpp(
            mpp=world.mpp,
            membership=Membership.objects.get(user=replacement),
            responsibility="facilitator",
            actor=world.admin,
        )

    new_client = world.client(replacement)
    assert leaver.get(f"{URL}{application['id']}/").status_code == 404

    continued = new_client.post(f"{URL}{application['id']}/submit/")
    assert continued.status_code == 200
    assert continued.data["created_by_name"] == "field@a.test"
    assert continued.data["revisions"][0]["submitted_by_name"] == "next@a.test"


def test_rejected_forms_reach_the_current_facilitator(world):
    application = world.submitted()
    world.client(world.manager).post(
        f"{URL}{application['id']}/decide/", {"decision": "rejected", "reason": "Fix it"}
    )
    replacement = world.member("next@a.test", "facilitator")
    with organization_context(world.org.id):
        assign_mpp(
            mpp=world.mpp,
            membership=Membership.objects.get(user=replacement),
            responsibility="facilitator",
            actor=world.admin,
        )

    listed = world.client(replacement).get(URL, {"status": "rejected"}).data["results"]

    assert [item["id"] for item in listed] == [application["id"]]


def test_an_unassigned_mpp_cannot_be_used(world):
    response = world.client(world.facilitator).post(
        URL, {"client_id": "x", "mpp": str(world.other_mpp.id)}
    )
    assert response.status_code == 403


def test_an_area_manager_only_sees_their_mpps(world):
    application = world.submitted()
    other = world.member("am2@a.test", "area_manager")

    assert world.client(other).get(f"{URL}{application['id']}/").status_code == 404
    assert world.approve(application, other).status_code == 404


def test_applications_stay_within_their_organization(world, org_b, admin_b):
    application = world.submitted()
    other = authenticated_client(org_b, admin_b)
    assert other.get(f"{URL}{application['id']}/").status_code == 404


# Member code -------------------------------------------------------------------------


def test_final_approval_creates_the_member_and_code(world, org_a):
    final = world.fully_approved()

    assert final["tr_code"] == "1000209982010001"
    with organization_context(org_a.id):
        member = Member.objects.get()
    assert member.full_name == "Test Applicant"
    assert len(member.tr_code) == 16


def test_no_code_exists_before_final_approval(world, org_a):
    application = world.submitted()
    world.approve(application, world.manager)
    world.approve(application, world.legal)

    with organization_context(org_a.id):
        assert not Member.objects.exists()


def test_rejected_forms_consume_no_serial(world):
    application = world.submitted()
    world.client(world.manager).post(
        f"{URL}{application['id']}/decide/", {"decision": "rejected", "reason": "No"}
    )
    assert world.fully_approved(OTHER_AADHAAR)["tr_code"].endswith("0001")


def test_serials_increase_within_an_mpp(world):
    assert world.fully_approved(AADHAAR)["tr_code"].endswith("0001")
    assert world.fully_approved(OTHER_AADHAAR)["tr_code"].endswith("0002")


def test_code_policy_comes_from_settings(world, org_a):
    admin = world.client(world.admin)
    response = admin.put(
        "/api/v1/settings/member-code/",
        {"state_code": "09", "hamlet_code": "02", "form_prefix": "A"},
    )
    assert response.status_code == 200

    assert world.fully_approved()["tr_code"] == "0900209982020001"


def test_a_new_series_starts_serials_again(world, org_a):
    world.fully_approved(AADHAAR)
    with organization_context(org_a.id):
        MemberCodeSettings.objects.update(state_code="11")

    assert world.fully_approved(OTHER_AADHAAR)["tr_code"] == "1100209982010001"


def test_parallel_final_approvals_never_share_a_code(world, org_a):
    first = world.submitted(AADHAAR)
    second = world.submitted(OTHER_AADHAAR)
    for application in (first, second):
        world.approve(application, world.manager)
        world.approve(application, world.legal)
    world.prepare_payment(first)
    world.prepare_payment(second)
    auth = world.client(world.finance)._credentials["HTTP_AUTHORIZATION"]
    results = []

    def approve(application):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=auth)
        results.append(
            client.post(f"{URL}{application['id']}/decide/", {"decision": "approved"}).status_code
        )
        connection.close()

    threads = [threading.Thread(target=approve, args=(a,)) for a in (first, second)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert results == [200, 200]
    with organization_context(org_a.id):
        codes = sorted(Member.objects.values_list("tr_code", flat=True))
    assert codes == ["1000209982010001", "1000209982010002"]


def test_double_clicking_approve_acts_once(world):
    application = world.submitted()
    client = world.client(world.manager)
    url = f"{URL}{application['id']}/decide/"

    assert client.post(url, {"decision": "approved"}).status_code == 200
    assert client.post(url, {"decision": "approved"}).status_code == 403


def test_members_are_listed_by_mpp_access(world):
    world.fully_approved()

    assert len(world.client(world.finance).get("/api/v1/members/").data["results"]) == 1
    outsider = world.member("pib@a.test", "pib")
    assert len(world.client(outsider).get("/api/v1/members/").data["results"]) == 1


# Audit and form ----------------------------------------------------------------------


def test_every_step_is_audited_without_sensitive_numbers(world, org_a):
    world.fully_approved()

    with organization_context(org_a.id):
        events = list(AuditEvent.objects.filter(action__startswith="application."))
    assert {event.action for event in events} >= {
        "application.created",
        "application.submitted",
        "application.decided",
    }
    assert AADHAAR not in str([event.metadata for event in events])


def test_the_form_definition_is_served(world):
    response = world.client(world.facilitator).get(f"{URL}form/")
    assert response.data["version"] == form.FORM_VERSION
    assert [s["key"] for s in response.data["sections"]][0] == "applicant"


@pytest.mark.parametrize("number", ["234123412346", "496858245229"])
def test_valid_aadhaar_checksums_pass(number):
    assert form.is_valid_aadhaar(number)


@pytest.mark.parametrize("number", ["234123412345", "123412341234", "12345", "abcdabcdabcd"])
def test_invalid_aadhaar_numbers_fail(number):
    assert not form.is_valid_aadhaar(number)


def test_applications_are_org_scoped_at_the_database(world, org_a):
    world.filled()
    assert Application.objects.count() == 0


# Payment -----------------------------------------------------------------------------


def at_finance(world):
    application = world.submitted()
    world.approve(application, world.manager)
    world.approve(application, world.legal)
    return application


def test_final_approval_needs_the_payment_and_its_proof(world):
    application = at_finance(world)
    client = world.client(world.finance)

    response = client.post(f"{URL}{application['id']}/decide/", {"decision": "approved"})

    assert response.status_code == 400
    assert set(response.data["error"]["details"]) == {"payment", "payment_proof"}


def test_a_deposit_without_a_reference_is_accepted(world):
    application = at_finance(world)
    response = world.client(world.finance).post(f"{URL}{application['id']}/payment/", PAYMENT)
    assert response.status_code == 200
    assert response.data["payment"]["recorded_by_name"] == "finance@a.test"


def test_only_finance_records_a_payment(world):
    application = at_finance(world)
    response = world.client(world.legal).post(f"{URL}{application['id']}/payment/", PAYMENT)
    assert response.status_code == 403


def test_payment_waits_for_the_finance_stage(world):
    application = world.submitted()
    response = world.client(world.finance).post(f"{URL}{application['id']}/payment/", PAYMENT)
    assert response.status_code == 409


def test_the_area_manager_can_add_the_payment_proof(world):
    application = world.submitted()
    response = world.client(world.manager).post(
        f"{URL}{application['id']}/documents/",
        {"document_type": "payment_proof", "file": SimpleUploadedFile("p.jpg", jpeg_bytes())},
        format="multipart",
    )
    assert response.status_code == 201


def test_the_area_manager_cannot_change_form_documents(world):
    application = world.submitted()
    response = world.client(world.manager).post(
        f"{URL}{application['id']}/documents/",
        {"document_type": "aadhaar_front", "file": SimpleUploadedFile("p.jpg", jpeg_bytes())},
        format="multipart",
    )
    assert response.status_code == 409


def test_choices_carry_labels_for_every_client(world):
    schema = world.client(world.facilitator).get(f"{URL}form/").data
    category = next(
        field
        for section in schema["sections"]
        for field in section["fields"]
        if field["key"] == "category"
    )
    assert {"value": "obc", "label": "OBC", "label_hi": "अन्य पिछड़ा वर्ग (OBC)"} in category[
        "options"
    ]


def test_men_cannot_apply_while_membership_is_for_women(world):
    client = world.client(world.facilitator)
    application = world.filled()
    data = complete_form()
    data["applicant"]["gender"] = "male"
    client.patch(f"{URL}{application['id']}/", {"data": data})

    response = client.post(f"{URL}{application['id']}/submit/")

    assert response.status_code == 400
    assert "applicant.gender" in response.data["error"]["details"]


def test_the_women_only_rule_is_a_setting(world, org_a):
    client = world.client(world.facilitator)
    application = world.filled()
    data = complete_form()
    data["applicant"]["gender"] = "male"
    client.patch(f"{URL}{application['id']}/", {"data": data})
    admin = world.client(world.admin)
    profile = admin.get("/api/v1/settings/organization-profile/").data
    admin.put("/api/v1/settings/organization-profile/", {**profile, "members_female_only": False})

    assert client.post(f"{URL}{application['id']}/submit/").status_code == 200


def test_clients_can_tell_a_stale_edit_from_a_duplicate(world):
    client = world.client(world.facilitator)
    world.filled()
    application = world.draft(client)
    url = f"{URL}{application['id']}/"

    duplicate = client.patch(url, {"aadhaar_number": AADHAAR})
    stale = client.patch(url, {"version": 99, "data": {}})

    assert duplicate.data["error"]["code"] == "duplicate_record"
    assert stale.data["error"]["code"] == "stale_version"
