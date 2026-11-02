import re
import uuid

import structlog
from rest_framework.settings import api_settings

from .context import RequestContext, reset_request_context, set_request_context
from .tenancy import clear_organization

REQUEST_ID_HEADER = "X-Request-ID"
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9-]{8,64}$")


def client_address(request) -> str | None:
    """Matches how DRF identifies callers, so the audit log and rate limits agree."""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    proxies = api_settings.NUM_PROXIES
    if forwarded and proxies:
        addresses = [address.strip() for address in forwarded.split(",")]
        return addresses[-min(proxies, len(addresses))]
    return request.META.get("REMOTE_ADDR")


class RequestContextMiddleware:
    """Gives each request a traceable ID and clears per-request state afterwards."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        supplied = request.headers.get(REQUEST_ID_HEADER, "")
        request_id = supplied if _VALID_REQUEST_ID.match(supplied) else uuid.uuid4().hex
        token = set_request_context(
            RequestContext(request_id=request_id, ip_address=client_address(request))
        )
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        try:
            response = self.get_response(request)
            response[REQUEST_ID_HEADER] = request_id
            return response
        finally:
            clear_organization()
            reset_request_context(token)
