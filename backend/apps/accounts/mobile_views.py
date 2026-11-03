from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.core.exceptions import ErrorResponseSerializer

from . import mobile_login


class MobileStartSerializer(serializers.Serializer):
    mobile = serializers.CharField(max_length=20)


class MobileStartResponseSerializer(serializers.Serializer):
    challenge = serializers.CharField()
    expires_in = serializers.IntegerField()


class MobileVerifySerializer(serializers.Serializer):
    challenge = serializers.CharField(max_length=64)
    code = serializers.CharField(max_length=10)
    organization = serializers.SlugField(
        required=False, allow_blank=True, help_text="Only when asked to choose one."
    )


class OrganizationChoiceSerializer(serializers.Serializer):
    slug = serializers.CharField()
    name = serializers.CharField()


class MobileVerifyResponseSerializer(serializers.Serializer):
    access = serializers.CharField(required=False)
    refresh = serializers.CharField(required=False)
    organization = OrganizationChoiceSerializer(required=False)
    choose = OrganizationChoiceSerializer(many=True, required=False)


class _MobileView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "mobile_login"


class MobileStartView(_MobileView):
    """Sends a sign-in code to a staff member's mobile. Unknown numbers get the same reply."""

    @extend_schema(
        auth=[],
        request=MobileStartSerializer,
        responses={200: MobileStartResponseSerializer, 409: ErrorResponseSerializer},
    )
    def post(self, request):
        serializer = MobileStartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(mobile_login.start(serializer.validated_data["mobile"]))


class MobileVerifyView(_MobileView):
    """
    Swaps the code for tokens. A number in several organizations first gets the list
    to choose from, then sends the same challenge and code again with one of them.
    """

    @extend_schema(
        auth=[],
        request=MobileVerifySerializer,
        responses={200: MobileVerifyResponseSerializer, 401: ErrorResponseSerializer},
    )
    def post(self, request):
        serializer = MobileVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        return Response(
            mobile_login.verify(data["challenge"], data["code"], data.get("organization", ""))
        )
