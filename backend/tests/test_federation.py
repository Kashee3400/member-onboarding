import base64
import time
import uuid

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.core.tenancy import organization_context
from apps.federation.models import ExternalIdentity, TrustedIssuer
from apps.hierarchy.models import Mcc, Mpp, MppAssignment, Plant
from apps.organizations.models import Membership

from .conftest import authenticated_client

pytestmark = pytest.mark.django_db(transaction=True)

EXCHANGE = "/api/v1/auth/exchange/"
ME = "/api/v1/auth/me/"
ISSUER = "erp-master"
AUDIENCE = "member-onboarding"


def new_private_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def pem(public_key):
    return public_key.public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()


@pytest.fixture(scope="module")
def private_key():
    return new_private_key()


@pytest.fixture
def issuer(org_a, private_key):
    return TrustedIssuer.objects.create(
        organization=org_a,
        name="ERP",
        issuer=ISSUER,
        audience=AUDIENCE,
        public_key=pem(private_key.public_key()),
        default_role_code="facilitator",
        syncs_mpp_assignments=True,
    )


@pytest.fixture
def mpps(org_a):
    with organization_context(org_a.id):
        plant = Plant.objects.create(code="P1", name="Plant")
        mcc = Mcc.objects.create(plant=plant, code="6", name="Bhadohi")
        return {
            "1305": Mpp.objects.create(
                mcc=mcc, code="1305", source_code="901305", name="One", village_code="00209982"
            ),
            "1152": Mpp.objects.create(
                mcc=mcc, code="1152", source_code="901152", name="Two", village_code="00211673"
            ),
        }


def assertion(private_key, **overrides):
    now = int(time.time())
    claims = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "42",
        "name": "Field Person",
        "iat": now,
        "exp": now + 120,
        "jti": uuid.uuid4().hex,
        "mpps": [],
    }
    claims.update(overrides)
    return jwt.encode({k: v for k, v in claims.items() if v is not None}, private_key, "RS256")


def exchange(private_key, **overrides):
    return APIClient().post(EXCHANGE, {"assertion": assertion(private_key, **overrides)})


def client_for(response):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
    return client


def visible_codes(response):
    results = client_for(response).get("/api/v1/hierarchy/mpps/").data["results"]
    return sorted(item["code"] for item in results)


def test_first_sign_in_creates_a_usable_facilitator(org_a, issuer, private_key):
    response = exchange(private_key)

    assert response.status_code == 200
    me = client_for(response).get(ME).data
    assert me["full_name"] == "Field Person"
    assert me["roles"] == ["facilitator"]
    assert me["organization"]["slug"] == org_a.slug


def test_no_refresh_token_is_issued(issuer, private_key):
    response = exchange(private_key)
    assert set(response.data) == {"access", "expires_in"}


def test_the_same_person_keeps_one_account(org_a, issuer, private_key):
    exchange(private_key)
    exchange(private_key)

    with organization_context(org_a.id):
        assert ExternalIdentity.objects.count() == 1


def test_a_changed_name_is_updated(issuer, private_key):
    exchange(private_key)
    response = exchange(private_key, name="New Name")
    assert client_for(response).get(ME).data["full_name"] == "New Name"


def test_a_host_cannot_take_over_a_local_account_by_email(org_a, issuer, private_key, admin_a):
    response = exchange(private_key, email=admin_a.email)

    me = client_for(response).get(ME).data
    assert me["id"] != str(admin_a.id)
    assert me["roles"] == ["facilitator"]


def test_external_users_cannot_log_in_with_a_password(issuer, private_key):
    exchange(private_key)
    user = User.objects.get(email__endswith="@external.invalid")
    assert not user.has_usable_password()


def test_a_blank_default_role_grants_nothing(issuer, private_key):
    TrustedIssuer.objects.filter(pk=issuer.pk).update(default_role_code="")
    assert client_for(exchange(private_key)).get(ME).data["permissions"] == []


def test_the_mpp_list_comes_from_the_host(issuer, private_key, mpps):
    assert visible_codes(exchange(private_key, mpps=["901305", "901152"])) == ["1152", "1305"]


def test_a_removed_mpp_is_taken_away_on_next_sign_in(org_a, issuer, private_key, mpps):
    exchange(private_key, mpps=["901305", "901152"])

    assert visible_codes(exchange(private_key, mpps=["901305"])) == ["1305"]

    with organization_context(org_a.id):
        assert MppAssignment.objects.filter(ended_at__isnull=False).count() == 1


def test_an_mpp_moves_when_the_host_gives_it_to_someone_else(issuer, private_key, mpps):
    first = exchange(private_key, sub="1", mpps=["901305"])

    second = exchange(private_key, sub="2", mpps=["901305"])

    assert visible_codes(second) == ["1305"]
    assert visible_codes(first) == []


def test_unknown_mpps_are_ignored(issuer, private_key, mpps):
    assert visible_codes(exchange(private_key, mpps=["901305", "9999"])) == ["1305"]


def test_mpp_sync_can_be_switched_off(issuer, private_key, mpps):
    TrustedIssuer.objects.filter(pk=issuer.pk).update(syncs_mpp_assignments=False)
    assert visible_codes(exchange(private_key, mpps=["901305"])) == []


def test_a_disabled_account_is_refused_and_audited(org_a, issuer, private_key):
    exchange(private_key)
    with organization_context(org_a.id):
        Membership.objects.update(is_active=False)

    assert exchange(private_key).status_code == 401

    with organization_context(org_a.id):
        assert AuditEvent.objects.filter(action="federation.exchange.refused").exists()


def test_a_replayed_assertion_is_refused(issuer, private_key):
    token = assertion(private_key)
    client = APIClient()
    assert client.post(EXCHANGE, {"assertion": token}).status_code == 200
    assert client.post(EXCHANGE, {"assertion": token}).status_code == 401


def test_every_refusal_looks_the_same(issuer, private_key):
    responses = [
        exchange(new_private_key()),
        exchange(private_key, iss="someone-else"),
        exchange(private_key, aud="other-service"),
        exchange(private_key, exp=int(time.time()) - 120, iat=int(time.time()) - 200),
        exchange(private_key, exp=int(time.time()) + 3600),
    ]
    for response in responses:
        assert response.status_code == 401
        assert response.data["error"]["code"] == "invalid_assertion"


@pytest.mark.parametrize("claim", ["sub", "exp", "iat", "jti"])
def test_required_claims_are_enforced(issuer, private_key, claim):
    assert exchange(private_key, **{claim: None}).status_code == 401


def test_an_unsigned_token_is_refused(issuer, private_key):
    now = int(time.time())
    token = jwt.encode(
        {"iss": ISSUER, "aud": AUDIENCE, "sub": "1", "iat": now, "exp": now + 60, "jti": "x"},
        None,
        algorithm="none",
    )
    assert APIClient().post(EXCHANGE, {"assertion": token}).status_code == 401


def test_the_public_key_cannot_be_used_as_a_shared_secret(issuer, private_key):
    """The classic RS256-to-HS256 confusion attack."""
    now = int(time.time())
    header = base64.urlsafe_b64encode(b'{"alg":"HS256","typ":"JWT"}').rstrip(b"=").decode()
    claims = {"iss": ISSUER, "aud": AUDIENCE, "sub": "1", "iat": now, "exp": now + 60, "jti": "y"}
    forged = (
        f"{header}.{jwt.utils.base64url_encode(jwt.api_jws.json.dumps(claims).encode()).decode()}."
    )
    assert APIClient().post(EXCHANGE, {"assertion": forged + "AAAA"}).status_code == 401


def test_garbage_is_refused(issuer):
    assert APIClient().post(EXCHANGE, {"assertion": "not-a-token"}).status_code == 401


def test_an_inactive_issuer_is_refused(issuer, private_key):
    TrustedIssuer.objects.filter(pk=issuer.pk).update(is_active=False)
    assert exchange(private_key).status_code == 401


# Issuer administration ---------------------------------------------------------------


ISSUERS = "/api/v1/auth/trusted-issuers/"


def issuer_payload(key, **overrides):
    return {
        "name": "Host",
        "issuer": "host-app",
        "audience": AUDIENCE,
        "public_key": pem(key.public_key()),
    } | overrides


def test_admins_can_register_an_issuer(org_a, admin_a, private_key):
    response = authenticated_client(org_a, admin_a).post(ISSUERS, issuer_payload(private_key))
    assert response.status_code == 201


def test_weak_or_invalid_keys_are_rejected(org_a, admin_a):
    client = authenticated_client(org_a, admin_a)
    weak = rsa.generate_private_key(public_exponent=65537, key_size=1024)

    assert client.post(ISSUERS, issuer_payload(weak)).status_code == 400
    invalid = issuer_payload(weak, public_key="not a key")
    assert client.post(ISSUERS, invalid).status_code == 400


def test_a_host_cannot_auto_assign_sensitive_roles(org_a, admin_a, private_key):
    client = authenticated_client(org_a, admin_a)
    payload = issuer_payload(private_key, default_role_code="finance")
    assert client.post(ISSUERS, payload).status_code == 400


def test_issuers_stay_within_their_organization(org_a, org_b, admin_b, issuer):
    client = authenticated_client(org_b, admin_b)

    assert client.get(ISSUERS).data["results"] == []
    assert client.get(f"{ISSUERS}{issuer.id}/").status_code == 404


def test_issuers_need_the_settings_permission(org_a, staff_a):
    assert authenticated_client(org_a, staff_a).get(ISSUERS).status_code == 403
