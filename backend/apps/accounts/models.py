from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models

from apps.core.models import TimeStampedModel, UUIDModel


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required.")
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.update(is_staff=True, is_superuser=True)
        return self.create_user(email, password, **extra_fields)


class User(UUIDModel, TimeStampedModel, AbstractBaseUser, PermissionsMixin):
    """A person. Their access to an organization comes from a Membership."""

    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    must_change_password = models.BooleanField(default=False)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        db_table = "account_user"

    def __str__(self):
        return self.email

    def save(self, *args, **kwargs):
        # Stored lowercase, so the unique constraint is effectively case-insensitive.
        self.email = self.email.strip().lower()
        super().save(*args, **kwargs)


class MfaDevice(UUIDModel, TimeStampedModel):
    """An authenticator app. Unusable until a first code confirms it."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="mfa_device")
    encrypted_secret = models.TextField()
    confirmed_at = models.DateTimeField(null=True, blank=True)
    last_used_step = models.BigIntegerField(
        default=0, help_text="Newest TOTP time step accepted, so a code works only once."
    )

    class Meta:
        db_table = "account_mfa_device"

    def __str__(self):
        return f"MFA for {self.user_id}"


class MfaRecoveryCode(UUIDModel, TimeStampedModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="mfa_recovery_codes")
    code_hash = models.CharField(max_length=64)
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "account_mfa_recovery_code"
        constraints = [
            models.UniqueConstraint(fields=["user", "code_hash"], name="unique_recovery_code"),
        ]

    def __str__(self):
        return f"Recovery code for {self.user_id}"
