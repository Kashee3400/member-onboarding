FROM python:3.14-slim AS base

# Pango and its fonts are what WeasyPrint draws the printed form with.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/ ./

RUN useradd --system --create-home --uid 10001 onboarding \
    && mkdir -p /var/lib/member-onboarding/media \
    && chown -R onboarding /var/lib/member-onboarding
USER onboarding

ENV PATH="/app/.venv/bin:$PATH" \
    DJANGO_SETTINGS_MODULE=config.settings.production \
    PYTHONUNBUFFERED=1

EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--threads", "4", "--timeout", "60"]
