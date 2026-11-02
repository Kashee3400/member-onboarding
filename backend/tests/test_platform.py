from io import StringIO
from pathlib import Path

import pytest
from django.conf import settings
from django.core.management import call_command

from apps.core.logging import REDACTED, redact_sensitive_values

pytestmark = pytest.mark.django_db


def test_liveness_needs_no_dependencies(api_client):
    assert api_client.get("/health/live/").data == {"status": "ok"}


def test_readiness_reports_its_checks(api_client):
    response = api_client.get("/health/ready/")
    assert response.status_code == 200
    assert response.data["checks"] == {"database": "ok", "cache": "ok"}


def test_every_response_carries_a_request_id(api_client):
    assert api_client.get("/health/live/").headers["X-Request-ID"]


def test_a_valid_request_id_is_reused(api_client):
    response = api_client.get("/health/live/", headers={"X-Request-ID": "trace-12345678"})
    assert response.headers["X-Request-ID"] == "trace-12345678"


def test_an_unsafe_request_id_is_replaced(api_client):
    response = api_client.get("/health/live/", headers={"X-Request-ID": "bad id<script>"})
    assert response.headers["X-Request-ID"] != "bad id<script>"


def test_api_errors_share_one_shape(api_client):
    response = api_client.get("/api/v1/auth/me/")
    assert response.status_code == 401
    assert set(response.data["error"]) == {"code", "message", "details", "request_id"}
    assert response.data["error"]["request_id"] == response.headers["X-Request-ID"]


def test_validation_errors_list_the_fields(api_client):
    response = api_client.post("/api/v1/auth/login/", {})
    assert response.status_code == 400
    assert "email" in response.data["error"]["details"]


def test_unknown_urls_return_json(client):
    response = client.get("/nope/")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_logs_never_contain_sensitive_values():
    event = {
        "event": "x",
        "password": "a",
        "aadhaar_number": "b",
        "nested": {"api_key": "c", "safe": "d"},
        "items": [{"access_token": "e"}],
    }
    assert redact_sensitive_values(None, "info", event) == {
        "event": "x",
        "password": REDACTED,
        "aadhaar_number": REDACTED,
        "nested": {"api_key": REDACTED, "safe": "d"},
        "items": [{"access_token": REDACTED}],
    }


def test_no_model_change_is_missing_a_migration():
    call_command("makemigrations", "--check", "--dry-run", stdout=StringIO())


def test_the_committed_contract_matches_the_code():
    output = StringIO()
    call_command("spectacular", "--validate", "--fail-on-warn", stdout=output)
    contract = Path(settings.BASE_DIR, "openapi.yaml").read_text(encoding="utf-8")
    assert output.getvalue().strip() == contract.strip(), (
        "Run: python manage.py spectacular --file openapi.yaml --validate"
    )
