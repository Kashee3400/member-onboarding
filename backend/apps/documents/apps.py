from django.apps import AppConfig


class DocumentsConfig(AppConfig):
    name = "apps.documents"
    label = "documents"

    def ready(self):
        from . import checks  # noqa: F401
