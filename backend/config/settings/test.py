import base64
import os
import tempfile

os.environ["IGNORE_DOTENV"] = "1"
os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-secret-key-not-used-anywhere-else-000000")
os.environ.setdefault("JWT_SIGNING_KEY", "test-only-jwt-signing-key-not-used-anywhere-else-00")
os.environ.setdefault(
    "FIELD_ENCRYPTION_KEYS",
    "t1:" + base64.b64encode(b"0" * 32).decode(),
)

os.environ.setdefault("BLIND_INDEX_KEY", "test-only-blind-index-key-not-used-anywhere-else")

os.environ.setdefault("MEDIA_ROOT", tempfile.mkdtemp(prefix="onboarding-media-"))

from .base import *  # noqa: E402, F403
from .base import REST_FRAMEWORK  # noqa: E402

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CELERY_TASK_ALWAYS_EAGER = True
# Rendering at every approval would triple the suite. Tests of it turn it back on.
PRINT_FORMS_ON_APPROVAL = False
# Most tests approve without ticking a checklist. Tests of the checklists turn it back on.
SEED_REVIEW_CHECKS = False
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_THROTTLE_RATES": {
        "anon": "1000/min",
        "user": "1000/min",
        # The isolation sweep alone sends thousands of requests from one organization.
        "organization": "100000/min",
        "login": "5/min",
        "mfa": "1000/min",
        "exchange": "1000/min",
    },
}
