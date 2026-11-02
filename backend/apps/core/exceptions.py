import structlog
from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from rest_framework import exceptions, serializers
from rest_framework.response import Response
from rest_framework.views import exception_handler, set_rollback

from .context import get_request_context

logger = structlog.get_logger(__name__)


class Conflict(exceptions.APIException):
    status_code = 409
    default_detail = "The request conflicts with the current state."
    default_code = "conflict"


class StaleVersion(Conflict):
    default_detail = "Someone else changed this. Reload and try again."
    default_code = "stale_version"


class DuplicateRecord(Conflict):
    default_code = "duplicate_record"


class Gone(exceptions.APIException):
    status_code = 410
    default_detail = "This is no longer available."
    default_code = "gone"


class ErrorDetailSerializer(serializers.Serializer):
    code = serializers.CharField()
    message = serializers.CharField()
    details = serializers.JSONField(required=False, allow_null=True)
    request_id = serializers.CharField()


class ErrorResponseSerializer(serializers.Serializer):
    """The body of every non-2xx API response."""

    error = ErrorDetailSerializer()


def error_body(code: str, message: str, details=None) -> dict:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details,
            "request_id": get_request_context().request_id,
        }
    }


def api_exception_handler(exc, context):
    if isinstance(exc, DjangoValidationError):
        exc = exceptions.ValidationError(detail=exc.messages)
    elif isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, PermissionDenied):
        exc = exceptions.PermissionDenied()

    response = exception_handler(exc, context)

    if response is None:
        logger.exception("unhandled_api_exception")
        set_rollback()
        return Response(error_body("internal_error", "Something went wrong."), status=500)

    if isinstance(exc, exceptions.ValidationError):
        response.data = error_body("validation_error", "Invalid input.", details=exc.detail)
    else:
        message = exc.detail if isinstance(exc.detail, str) else exc.default_detail
        response.data = error_body(exc.default_code, str(message))
    return response
