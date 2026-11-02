import uuid

from django.db import models


class UUIDModel(models.Model):
    """UUIDv7 primary key: safe to expose, and time-ordered so indexes stay compact."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)

    class Meta:
        abstract = True


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
