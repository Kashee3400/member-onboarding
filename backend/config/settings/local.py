import structlog

from .base import *  # noqa: F403
from .base import build_logging

DEBUG = True
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
LOGGING = build_logging(structlog.dev.ConsoleRenderer())
