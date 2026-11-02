from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework import exceptions, serializers, status
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.applications import review_steps
from apps.applications.models import Application, Status
from apps.applications.services import EDITABLE_STATUSES, display_name, visible_applications
from apps.audit.services import record_event
from apps.core.exceptions import Conflict, ErrorResponseSerializer
from apps.organizations.models import Membership
from apps.rbac.catalog import APPROVE_ALL
from apps.rbac.permissions import require_permission

from . import storage
from .models import Document, DocumentType
from .serializers import (
    DocumentSerializer,
    DocumentUploadSerializer,
    SignatureStatusSerializer,
    SignatureUploadSerializer,
)
from .services import (
    attach_document,
    current_signature,
    remove_staff_photo,
    set_staff_photo,
    set_staff_signature,
)

# The Area Manager or Finance adds the proof, which reaches them outside the form.
PROOF_STAGES = {
    Status.PENDING_AM: "applications.approve_am",
    Status.PENDING_FINANCE: "applications.approve_finance",
}


def _application_for(request, pk) -> Application:
    """Visibility follows the MPP, so a transferred facilitator loses documents as well."""
    user = request.user
    return get_object_or_404(
        visible_applications(user.active_membership, user.active_permissions), pk=pk
    )


def _private_file(content: bytes, content_type: str) -> HttpResponse:
    response = HttpResponse(content, content_type=content_type)
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Disposition"] = "inline"
    return response


def _ensure_can_attach(application, document_type, permissions, membership) -> None:
    """Form documents belong to the facilitator; payment proof can also arrive later."""
    if application.status in EDITABLE_STATUSES and "applications.edit" in permissions:
        return
    if document_type == DocumentType.PAYMENT_PROOF:
        stage_permission = PROOF_STAGES.get(application.status)
        if stage_permission in permissions:
            return
        if stage_permission and APPROVE_ALL in permissions:
            return
        if review_steps.FEE_STEP in review_steps.actionable(application, membership):
            return
    if application.status in EDITABLE_STATUSES:
        raise exceptions.PermissionDenied("You cannot change this application.")
    raise Conflict("This application can no longer be edited.")


class ApplicationDocumentsView(APIView):
    parser_classes = [MultiPartParser]

    def get_permissions(self):
        if self.request.method != "GET":
            # Who may upload depends on the document and the stage: see `_ensure_can_attach`.
            return [IsAuthenticated()]
        return [IsAuthenticated(), require_permission("applications.view")()]

    @extend_schema(responses={200: DocumentSerializer(many=True)})
    def get(self, request, pk):
        documents = _application_for(request, pk).documents.filter(is_current=True)
        return Response(DocumentSerializer(documents.order_by("created_at"), many=True).data)

    @extend_schema(
        request={"multipart/form-data": DocumentUploadSerializer},
        responses={
            201: DocumentSerializer,
            400: ErrorResponseSerializer,
            409: ErrorResponseSerializer,
        },
    )
    def post(self, request, pk):
        serializer = DocumentUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        application = _application_for(request, pk)
        _ensure_can_attach(
            application,
            data["document_type"],
            request.user.active_permissions,
            request.user.active_membership,
        )

        document = attach_document(
            application,
            document_type=data["document_type"],
            raw=data["file"].read(),
            user=request.user,
            user_name=display_name(request.user),
        )
        return Response(DocumentSerializer(document).data, status=status.HTTP_201_CREATED)


class DocumentFileView(APIView):
    """Files are only ever reached here, after the same checks as the application."""

    permission_classes = [IsAuthenticated, require_permission("applications.view")]

    @extend_schema(responses={(200, "image/*"): OpenApiTypes.BINARY})
    def get(self, request, pk):
        user = request.user
        document = get_object_or_404(
            Document.objects.filter(
                application__in=visible_applications(
                    user.active_membership, user.active_permissions
                )
            ),
            pk=pk,
        )
        record_event(
            "document.viewed",
            actor=user,
            target=document,
            metadata={"type": document.document_type},
        )
        return _private_file(storage.read(document.relative_path), document.content_type)


def _own_or_managed(request, pk):
    """Staff set their own signature. Whoever manages staff can set anyone's."""
    membership = get_object_or_404(Membership, pk=pk)
    own = membership.pk == request.user.active_membership.pk
    if not own and "staff.manage" not in request.user.active_permissions:
        raise exceptions.PermissionDenied("You can change only your own signature.")
    return membership


class StaffSignatureView(APIView):
    parser_classes = [MultiPartParser]
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: SignatureStatusSerializer})
    def get(self, request, pk):
        membership = _own_or_managed(request, pk)
        return Response({"has_signature": current_signature(membership) is not None})

    @extend_schema(
        request={"multipart/form-data": SignatureUploadSerializer},
        responses={200: SignatureStatusSerializer, 400: ErrorResponseSerializer},
    )
    def post(self, request, pk):
        membership = _own_or_managed(request, pk)
        serializer = SignatureUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        set_staff_signature(
            membership, raw=serializer.validated_data["file"].read(), actor=request.user
        )
        return Response({"has_signature": True})


class StaffSignatureFileView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={(200, "image/png"): OpenApiTypes.BINARY})
    def get(self, request, pk):
        membership = _own_or_managed(request, pk)
        signature = current_signature(membership)
        if signature is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return _private_file(storage.read(signature.relative_path), "image/png")


class PhotoUploadSerializer(serializers.Serializer):
    file = serializers.FileField()


class PhotoUrlSerializer(serializers.Serializer):
    photo_url = serializers.CharField()


class StaffPhotoView(APIView):
    """Everyone in the organization can see a photo. Staff change their own, admins anyone's."""

    parser_classes = [MultiPartParser]

    def _editable(self, request, pk):
        membership = get_object_or_404(Membership, pk=pk)
        own = membership.pk == request.user.active_membership.pk
        if not own and "staff.manage" not in request.user.active_permissions:
            raise exceptions.PermissionDenied("You can change only your own photo.")
        return membership

    @extend_schema(responses={(200, "image/webp"): OpenApiTypes.BINARY})
    def get(self, request, pk):
        membership = get_object_or_404(Membership, pk=pk)
        if not membership.photo_path:
            return Response(status=status.HTTP_404_NOT_FOUND)
        response = HttpResponse(
            storage.read_public(membership.photo_path), content_type="image/webp"
        )
        response["Cache-Control"] = "private, max-age=31536000, immutable"
        response["X-Content-Type-Options"] = "nosniff"
        return response

    @extend_schema(
        request={"multipart/form-data": PhotoUploadSerializer},
        responses={
            200: PhotoUrlSerializer,
            400: ErrorResponseSerializer,
            403: ErrorResponseSerializer,
        },
    )
    def post(self, request, pk):
        membership = self._editable(request, pk)
        serializer = PhotoUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        set_staff_photo(
            membership, raw=serializer.validated_data["file"].read(), actor=request.user
        )
        return Response({"photo_url": membership.photo_url})

    @extend_schema(responses={204: None, 403: ErrorResponseSerializer})
    def delete(self, request, pk):
        remove_staff_photo(self._editable(request, pk), actor=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)
