import os
import sys
from datetime import timedelta
from pathlib import Path

import environ
import structlog
from celery.schedules import crontab

from apps.core.logging import redact_sensitive_values

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
# Tests set their own values, so a developer's .env never changes what they check.
if (BASE_DIR / ".env").exists() and not os.environ.get("IGNORE_DOTENV"):
    environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = False
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[])

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.postgres",
    "corsheaders",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "django_filters",
    "drf_spectacular",
    "apps.core",
    "apps.accounts",
    "apps.organizations",
    "apps.audit",
    "apps.configuration",
    "apps.rbac",
    "apps.hierarchy",
    "apps.federation",
    "apps.documents",
    "apps.applications",
    "apps.reports",
    "apps.notifications",
    "apps.branding",
]

MIDDLEWARE = [
    "apps.core.middleware.RequestContextMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"
AUTH_USER_MODEL = "accounts.User"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": []},
    }
]

# ATOMIC_REQUESTS is what scopes the tenant's RLS setting to one transaction,
# which keeps it safe behind PgBouncer in transaction-pooling mode.
# Migrations alone connect as the schema owner; the runtime role stays unprivileged.
_IS_MIGRATING = sys.argv[1:2] == ["migrate"]
DATABASES = {"default": env.db("MIGRATION_DATABASE_URL" if _IS_MIGRATING else "DATABASE_URL")}
DATABASES["default"].update(
    {
        "ATOMIC_REQUESTS": True,
        "CONN_MAX_AGE": env.int("DB_CONN_MAX_AGE", default=60),
        "CONN_HEALTH_CHECKS": True,
    }
)

REDIS_URL = env("REDIS_URL", default="")
if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
        }
    }
else:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.organizations.authentication.OrganizationJWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "apps.core.filters.TableSearch",
        "apps.core.filters.TableOrdering",
    ],
    "SEARCH_PARAM": "q",
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.DefaultPagination",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": env("THROTTLE_ANON", default="60/min"),
        "user": env("THROTTLE_USER", default="600/min"),
        "login": env("THROTTLE_LOGIN", default="10/min"),
        "mfa": env("THROTTLE_MFA", default="30/min"),
        # Field staff can share one mobile network address.
        "exchange": env("THROTTLE_EXCHANGE", default="600/min"),
    },
    "NUM_PROXIES": env.int("NUM_PROXIES", default=0),
    "EXCEPTION_HANDLER": "apps.core.exceptions.api_exception_handler",
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "SIGNING_KEY": env("JWT_SIGNING_KEY"),
    "ALGORITHM": "HS256",
    "UPDATE_LAST_LOGIN": False,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Member Onboarding API",
    "DESCRIPTION": "Multi-organization member onboarding platform.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": r"/api/v[0-9]+",
    "COMPONENT_SPLIT_REQUEST": True,
    "ENUM_NAME_OVERRIDES": {"ApplicationStatusEnum": "apps.applications.models.Status"},
}

CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])
EXPOSE_API_DOCS = env.bool("EXPOSE_API_DOCS", default=False)

# Links in emails point here.
PORTAL_URL = env("PORTAL_URL", default="http://localhost:3000")
PASSWORD_RESET_TIMEOUT = 60 * 60
MAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"

# First key encrypts; the rest stay available for decryption during rotation.
FIELD_ENCRYPTION_KEYS = env.list("FIELD_ENCRYPTION_KEYS")

# Keyed, so duplicate checks work without storing anything guessable.
BLIND_INDEX_KEY = env("BLIND_INDEX_KEY")

# Uploaded files. Must be outside the code, and backed up separately from it.
MEDIA_ROOT = Path(env("MEDIA_ROOT"))
DATA_UPLOAD_MAX_MEMORY_SIZE = 7 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 7 * 1024 * 1024

CELERY_BROKER_URL = REDIS_URL or "memory://"
# With no broker there is no worker, so background work runs in the request.
CELERY_TASK_ALWAYS_EAGER = not REDIS_URL
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_TASK_SOFT_TIME_LIMIT = 300
CELERY_TASK_TIME_LIMIT = 360
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TIMEZONE = TIME_ZONE
# Run by the `beat` service. Without it, cron can call `manage.py send_morning_summary`.
CELERY_BEAT_SCHEDULE = {
    "morning-summary": {
        "task": "apps.notifications.tasks.send_morning_summary",
        "schedule": crontab(hour=9, minute=0),
    },
}

# Make and store the printed forms as soon as a form is approved.
PRINT_FORMS_ON_APPROVAL = True

# Give each organization a starting checklist for every review step.
SEED_REVIEW_CHECKS = True

LOG_LEVEL = env("LOG_LEVEL", default="INFO")

_LOG_PROCESSORS = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_log_level,
    structlog.stdlib.add_logger_name,
    structlog.processors.TimeStamper(fmt="iso", utc=True),
    redact_sensitive_values,
]


def build_logging(renderer):
    structlog.configure(
        processors=[*_LOG_PROCESSORS, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "structured": {
                "()": structlog.stdlib.ProcessorFormatter,
                "processor": renderer,
                "foreign_pre_chain": _LOG_PROCESSORS,
            }
        },
        "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "structured"}},
        "root": {"handlers": ["console"], "level": LOG_LEVEL},
        # Both narrate every step of every PDF at INFO.
        "loggers": {"weasyprint": {"level": "WARNING"}, "fontTools": {"level": "WARNING"}},
    }


LOGGING = build_logging(structlog.processors.JSONRenderer())
