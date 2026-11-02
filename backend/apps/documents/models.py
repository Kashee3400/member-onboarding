from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.organizations.models import Membership, OrganizationOwnedModel


class DocumentType(models.TextChoices):
    PHOTO = "photo", "Member photo"
    MEMBER_SIGNATURE = "member_signature", "Member signature"
    MEMBER_THUMBPRINT = "member_thumbprint", "Member thumbprint"
    AADHAAR_FRONT = "aadhaar_front", "Aadhaar front"
    AADHAAR_BACK = "aadhaar_back", "Aadhaar back"
    PASSBOOK = "passbook", "Bank passbook"
    PAYMENT_PROOF = "payment_proof", "Payment proof"


REQUIRED_DOCUMENTS = (
    DocumentType.PHOTO,
    DocumentType.AADHAAR_FRONT,
    DocumentType.AADHAAR_BACK,
    DocumentType.PASSBOOK,
)
# A member who cannot write gives a thumbprint instead.
SIGNATURE_DOCUMENTS = (DocumentType.MEMBER_SIGNATURE, DocumentType.MEMBER_THUMBPRINT)


class Document(OrganizationOwnedModel):
    """A file attached to an application. Replacing one keeps the old file and row."""

    application = models.ForeignKey(
        "applications.Application", on_delete=models.PROTECT, related_name="documents"
    )
    document_type = models.CharField(max_length=30, choices=DocumentType.choices)
    relative_path = models.CharField(max_length=300, unique=True)
    content_type = models.CharField(max_length=50)
    size_bytes = models.PositiveIntegerField()
    is_current = models.BooleanField(default=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    uploaded_by_name = models.CharField(max_length=200)

    class Meta:
        db_table = "application_document"
        constraints = [
            models.UniqueConstraint(
                fields=["application", "document_type"],
                condition=Q(is_current=True),
                name="unique_current_document",
            ),
        ]

    def __str__(self):
        return f"{self.document_type} for {self.application_id}"


class StaffSignature(OrganizationOwnedModel):
    """
    A staff member's signature. Rows are never edited: an application points at the
    exact signature used, so replacing one cannot change a form already signed.
    """

    membership = models.ForeignKey(Membership, on_delete=models.PROTECT, related_name="signatures")
    relative_path = models.CharField(max_length=300, unique=True)
    is_current = models.BooleanField(default=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        db_table = "staff_signature"
        constraints = [
            models.UniqueConstraint(
                fields=["membership"],
                condition=Q(is_current=True),
                name="unique_current_signature",
            ),
        ]

    def __str__(self):
        return f"Signature of {self.membership_id}"
