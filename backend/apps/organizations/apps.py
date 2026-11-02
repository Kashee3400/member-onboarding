from django.apps import AppConfig


class OrganizationsConfig(AppConfig):
    name = "apps.organizations"
    label = "organizations"

    def ready(self):
        from . import schema  # noqa: F401
