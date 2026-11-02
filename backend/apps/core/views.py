from django.conf import settings
from django.core.cache import cache
from django.db import connection, transaction
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .exceptions import error_body

HealthSerializer = inline_serializer(
    name="Health",
    fields={
        "status": serializers.CharField(),
        "checks": serializers.DictField(child=serializers.CharField(), required=False),
    },
)


def _check_database() -> str:
    with connection.cursor() as cursor:
        cursor.execute("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user")
        bypasses_isolation = cursor.fetchone()[0]
    return "unsafe_role" if bypasses_isolation and not settings.DEBUG else "ok"


def _check_cache() -> str:
    cache.set("health:ready", "1", timeout=5)
    return "ok" if cache.get("health:ready") == "1" else "failed"


@method_decorator(transaction.non_atomic_requests, name="dispatch")
class LivenessView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = []

    @extend_schema(auth=[], responses={200: HealthSerializer})
    def get(self, request):
        return Response({"status": "ok"})


@method_decorator(transaction.non_atomic_requests, name="dispatch")
class ReadinessView(APIView):
    """Reports 503 unless the service can safely take traffic."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = []

    @extend_schema(auth=[], responses={200: HealthSerializer, 503: HealthSerializer})
    def get(self, request):
        checks = {}
        for name, check in (("database", _check_database), ("cache", _check_cache)):
            try:
                checks[name] = check()
            except Exception:
                checks[name] = "failed"
        healthy = all(result == "ok" for result in checks.values())
        return Response(
            {"status": "ok" if healthy else "unavailable", "checks": checks},
            status=200 if healthy else 503,
        )


def not_found(request, exception):
    return JsonResponse(error_body("not_found", "Not found."), status=404)


def server_error(request):
    return JsonResponse(error_body("internal_error", "Something went wrong."), status=500)
