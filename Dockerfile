# syntax=docker/dockerfile:1.7

FROM python:3.13-slim-bookworm AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        build-essential \
        libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY . .

RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip setuptools wheel \
    && /opt/venv/bin/pip install .


FROM python:3.13-slim-bookworm AS runtime

ARG APP_VERSION=dev

LABEL org.opencontainers.image.title="Gestão Rural" \
      org.opencontainers.image.description="Sistema de gestão de gado leiteiro" \
      org.opencontainers.image.version="${APP_VERSION}"

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings.production \
    PORT=8000

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        fonts-dejavu-core \
        libgdk-pixbuf-2.0-0 \
        libharfbuzz-subset0 \
        libharfbuzz0b \
        libjpeg62-turbo \
        libopenjp2-7 \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        shared-mime-info \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --create-home --home-dir /home/app app \
    && install --directory --owner=app --group=app /app /app/data /app/media /app/staticfiles

COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY --chown=app:app . .

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready/', timeout=3)" || exit 1

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "1", "--timeout", "120", "--access-logfile", "-", "--error-logfile", "-"]
