from django.conf import settings
from django.core.mail import EmailMessage, get_connection

from apps.configuration.models import IntegrationConfig


class MailNotConfigured(Exception):
    pass


def send_mail(to: str, subject: str, body: str) -> None:
    """Sends with the active organization's own settings, which can change without a deploy."""
    integration = IntegrationConfig.objects.filter(kind="mail", is_enabled=True).first()
    if integration is None:
        raise MailNotConfigured

    config = integration.config
    connection = get_connection(
        backend=settings.MAIL_BACKEND,
        host=config.get("host"),
        port=config.get("port"),
        username=config.get("username"),
        password=integration.get_secrets().get("password"),
        use_tls=bool(config.get("use_tls")),
        timeout=15,
    )
    EmailMessage(
        subject=subject,
        body=body,
        from_email=config.get("from_email") or config.get("username"),
        to=[to],
        connection=connection,
    ).send()
