import json

from django.db import models

from apps.core import crypto
from apps.organizations.models import OrganizationOwnedModel

from .schemas import INTEGRATION_SCHEMAS


class IntegrationConfig(OrganizationOwnedModel):
    """One organization's third-party connection, changeable without a deployment."""

    KIND_CHOICES = [(kind, kind) for kind in INTEGRATION_SCHEMAS]

    kind = models.CharField(max_length=30, choices=KIND_CHOICES)
    is_enabled = models.BooleanField(default=False)
    config = models.JSONField(default=dict, blank=True)
    encrypted_secrets = models.TextField(blank=True)

    class Meta:
        db_table = "integration_config"
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "kind"], name="unique_integration_per_organization"
            ),
        ]

    def __str__(self):
        return f"{self.kind} @ {self.organization_id}"

    @property
    def _encryption_context(self) -> str:
        return f"integration:{self.organization_id}:{self.kind}"

    def get_secrets(self) -> dict:
        if not self.encrypted_secrets:
            return {}
        return json.loads(crypto.decrypt(self.encrypted_secrets, self._encryption_context))

    def set_secrets(self, secrets: dict) -> None:
        self.encrypted_secrets = (
            crypto.encrypt(json.dumps(secrets).encode(), self._encryption_context)
            if secrets
            else ""
        )
