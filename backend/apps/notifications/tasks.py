import smtplib

import structlog
from celery import shared_task
from django.utils import timezone

from apps.core.tenancy import organization_context

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
            return
        notification.emailed_at = timezone.now()
        notification.save(update_fields=["emailed_at", "updated_at"])


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


@shared_task
def send_morning_summary() -> int:
    # Imported here: the summary reads applications, which import this module.
    from .summary import send_morning_summaries

    return send_morning_summaries()
