"""
Proving a member's mobile number and email: a six-digit code is sent, the facilitator
types back what the member received, and the form is marked verified. A changed number
or address needs proving again (see `save_draft`).
"""

import hashlib
import hmac
import secrets
import smtplib
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework import exceptions

from apps.audit.services import record_event
from apps.core.exceptions import Conflict

from .mail import MailNotConfigured, send_mail
from .models import ContactOtp
from .sms import SmsFailed, SmsNotConfigured, normalize_mobile, send_otp_sms

CODE_DIGITS = 6
VALID_FOR = timedelta(minutes=10)
RESEND_AFTER = timedelta(seconds=30)
SENDS_PER_HOUR = 5
MAX_TRIES = 5
EDITABLE = {"draft", "rejected"}

STAMP = {
    ContactOtp.Channel.MOBILE: "mobile_verified_at",
    ContactOtp.Channel.EMAIL: "email_verified_at",
}


def _target(application, channel) -> str:
    address = application.data.get("address", {})
    value = (
        address.get("mobile") if channel == ContactOtp.Channel.MOBILE else address.get("email")
    ) or ""
    value = str(value).strip()
    return normalize_mobile(value) if channel == ContactOtp.Channel.MOBILE else value.lower()


def _hash(otp_id, code: str) -> str:
    return hmac.new(
        settings.SECRET_KEY.encode(), f"{otp_id}:{code}".encode(), hashlib.sha256
    ).hexdigest()


def _ensure_editable(application):
    if application.status not in EDITABLE:
        raise Conflict("The form has been submitted. Contact details can no longer be verified.")


def send_code(application, channel: str, *, user) -> ContactOtp:
    """Sends a new code. Earlier codes for this channel stop working."""
    _ensure_editable(application)
    target = _target(application, channel)
    if not target:
        field = "mobile number" if channel == ContactOtp.Channel.MOBILE else "email"
        raise exceptions.ValidationError(
            {"detail": [f"Enter the {field} first, then send the code."]}
        )

    now = timezone.now()
    recent = ContactOtp.objects.filter(
        application=application, channel=channel, created_at__gte=now - timedelta(hours=1)
    ).order_by("-created_at")
    last = recent.first()
    if last and now - last.created_at < RESEND_AFTER:
        wait = int((RESEND_AFTER - (now - last.created_at)).total_seconds()) + 1
        raise Conflict(f"Wait {wait} seconds before sending another code.")
    if recent.count() >= SENDS_PER_HOUR:
        raise Conflict("Too many codes in the last hour. Try again later.")

    code = f"{secrets.randbelow(10**CODE_DIGITS):0{CODE_DIGITS}d}"
    otp = ContactOtp(
        organization_id=application.organization_id,
        application=application,
        channel=channel,
        sent_to=target,
        code_hash="",
        expires_at=now + VALID_FOR,
        sent_by=user,
    )
    otp.code_hash = _hash(otp.id, code)

    try:
        if channel == ContactOtp.Channel.MOBILE:
            send_otp_sms(target, code)
        else:
            send_mail(
                target,
                "Kashee member verification code",
                f"Your verification code is {code}. It works for 10 minutes. Do not share it.\n\n"
                f"आपका सत्यापन कोड {code} है। यह 10 मिनट तक मान्य है। किसी से साझा न करें।",
            )
    except SmsNotConfigured:
        raise Conflict(
            "SMS is not set up yet. An admin can set it up under Integrations."
        ) from None
    except MailNotConfigured:
        raise Conflict(
            "Mail is not set up yet. An admin can set it up under Integrations."
        ) from None
    except SmsFailed as exc:
        raise Conflict(str(exc)) from None
    except smtplib.SMTPException, OSError:
        raise Conflict("The code could not be emailed. Try again in a few minutes.") from None

    ContactOtp.objects.filter(
        application=application, channel=channel, verified_at__isnull=True
    ).update(expires_at=now)
    otp.save()
    record_event(
        "application.contact_otp_sent",
        actor=user,
        target=application,
        metadata={"channel": channel},
    )
    return otp


def verify_code(application, channel: str, code: str, *, user) -> str | None:
    """
    Marks the number or address proven when the code matches the latest one sent.
    A wrong code returns what to tell the person instead of raising: raising would roll
    the request back and forget the try, so codes could be guessed without end.
    """
    _ensure_editable(application)
    now = timezone.now()
    otp = (
        ContactOtp.objects.select_for_update()
        .filter(application=application, channel=channel, verified_at__isnull=True)
        .order_by("-created_at")
        .first()
    )
    if otp is None or otp.expires_at <= now:
        raise Conflict("The code has expired. Send a new one.")
    if otp.sent_to != _target(application, channel):
        raise Conflict("The number or email changed after the code was sent. Send a new one.")
    if otp.tries >= MAX_TRIES:
        raise Conflict("Too many wrong tries. Send a new code.")

    otp.tries += 1
    if not hmac.compare_digest(otp.code_hash, _hash(otp.id, str(code).strip())):
        otp.save(update_fields=["tries", "updated_at"])
        left = MAX_TRIES - otp.tries
        return (
            f"That code is wrong. {left} tries left."
            if left
            else "That code is wrong. Send a new one."
        )

    otp.verified_at = now
    otp.save(update_fields=["tries", "verified_at", "updated_at"])
    # Not a form edit: the version stays, so the phone's next autosave is not refused.
    setattr(application, STAMP[channel], now)
    application.save(update_fields=[STAMP[channel], "updated_at"])
    record_event(
        "application.contact_verified",
        actor=user,
        target=application,
        metadata={"channel": channel},
    )
    return None
