from pathlib import Path

from django.conf import settings
from django.core.checks import Error, Tags, register


@register(Tags.files)
def media_root_is_outside_the_code(app_configs, **kwargs):
    media = Path(settings.MEDIA_ROOT).resolve()
    code = Path(settings.BASE_DIR).resolve()
    if media == code or code in media.parents:
        return [
            Error(
                "MEDIA_ROOT must be outside the code folder.",
                hint="Members' documents must not be deployed over or served with the code.",
                id="documents.E001",
            )
        ]
    return []
