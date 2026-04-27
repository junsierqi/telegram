FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
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
