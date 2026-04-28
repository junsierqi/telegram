FROM python:3.12-slim

# Proxy plumbing: docker-compose.yml passes HTTP_PROXY/HTTPS_PROXY/NO_PROXY
# through as build args (lower- and upper-case) so RUN steps such as
# `pip install` can reach pypi.org through the host's egress proxy.
ARG HTTP_PROXY=""
ARG HTTPS_PROXY=""
ARG NO_PROXY=""
ARG http_proxy=""
ARG https_proxy=""
ARG no_proxy=""

ENV HTTP_PROXY=${HTTP_PROXY} \
    HTTPS_PROXY=${HTTPS_PROXY} \
    NO_PROXY=${NO_PROXY} \
    http_proxy=${http_proxy} \
    https_proxy=${https_proxy} \
    no_proxy=${no_proxy} \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TELEGRAM_HOST=0.0.0.0 \
    TELEGRAM_PORT=8787 \
    TELEGRAM_DB_FILE=/data/runtime.sqlite \
    TELEGRAM_ATTACHMENT_DIR=/data/attachments

WORKDIR /app

COPY server ./server
COPY scripts/validate_postgres_repository.py ./scripts/validate_postgres_repository.py
COPY scripts/validate_postgres_backup_restore.py ./scripts/validate_postgres_backup_restore.py

RUN python -m pip install --no-cache-dir "psycopg[binary]>=3.2,<4" \
    && mkdir -p /data/attachments

EXPOSE 8787

CMD ["python", "-m", "server.main", "--tcp-server"]
