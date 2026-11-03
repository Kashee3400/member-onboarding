import smtplib

import structlog
from celery import shared_task
from django.utils import timezone

from apps.core.tenancy import organization_context

from .failures import record_failure
from .mail import MailNotConfigured, send_mail
from .models import Notification

logger = structlog.get_logger(__name__)

# People who sign in through a host app have no real address here.
NO_EMAIL_DOMAIN = "@external.invalid"


@shared_task
def deliver_email(notification_id: str, organization_id: str) -> None:
    with organization_context(organization_id):
        notification = Notification.objects.select_related("recipient__user").get(
            pk=notification_id
        )
        email = notification.recipient.user.email
        if email.endswith(NO_EMAIL_DOMAIN):
            return
        try:
            send_mail(email, notification.title, notification.body)
        except MailNotConfigured:
            return
        except smtplib.SMTPException, OSError:
            # The portal copy already exists, so a mail outage loses nothing.
            logger.warning("notification_email_failed", notification=notification_id)
            record_failure("mail", "A notification email could not be sent.")
            return
        notification.emailed_at = timezone.now()
        notification.save(update_fields=["emailed_at", "updated_at"])


@shared_task
def deliver_push(
    organization_id: str, membership_ids: list[str], title: str, body: str, data: dict
) -> int:
    """Sends to every active phone of these people. Returns how many phones it tried."""
    from .models import PushDevice
    from .push import PushFailed, PushNotConfigured, send

    with organization_context(organization_id):
        devices = list(PushDevice.objects.filter(membership_id__in=membership_ids, is_active=True))
        if not devices:
            return 0
        try:
            gone = send([device.token for device in devices], title=title, body=body, data=data)
        except PushNotConfigured:
            return 0
        except PushFailed as exc:
            # The portal notice already exists, so a push outage loses nothing.
            logger.warning("push_not_sent", reason=str(exc))
            record_failure("push", str(exc))
            return 0
        if gone:
            PushDevice.objects.filter(token__in=gone).update(is_active=False)
        return len(devices)


@shared_task
def send_invitation(
    organization_id: str, to: str, name: str, organization: str, inviter: str, link: str
) -> None:
    with organization_context(organization_id):
        try:
            send_mail(
                to,
                f"You are invited to {organization}",
                f"Hello {name},\n\n{inviter} has added you to the {organization} staff "
                "portal for member onboarding.\n\nOpen this link within 7 days to choose "
                f"your password and finish your account:\n\n{link}\n\n"
                "After that, sign in and add your signature under My account.\n\n"
                "If you were not expecting this, you can ignore this message.",
            )
        except MailNotConfigured, smtplib.SMTPException, OSError:
            logger.warning("invitation_email_failed")
            record_failure("mail", "An invitation email could not be sent.")


@shared_task
def send_password_reset(organization_id: str, to: str, link: str) -> None:
    with organization_context(organization_id):
        try:
            send_mail(
                to,
                "Reset your password",
                f"Open this link within an hour to set a new password:\n\n{link}\n\n"
                "If you did not ask for this, you can ignore this message.",
            )
        except MailNotConfigured, smtplib.SMTPException, OSError:
            logger.warning("password_reset_email_failed")
            record_failure("mail", "A password reset email could not be sent.")


@shared_task
def send_morning_summary() -> int:
    # Imported here: the summary reads applications, which import this module.
    from .summary import send_morning_summaries

    return send_morning_summaries()
