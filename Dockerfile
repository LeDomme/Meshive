FROM node:25-alpine AS frontend-build

WORKDIR /build/frontend
COPY frontend/package*.json ./
RUN npm ci --include=dev --ignore-scripts
COPY frontend/ ./
COPY resources/ /build/resources/
RUN npm run build

FROM python:3.14-slim-trixie AS runtime

LABEL org.opencontainers.image.source="https://github.com/ledomme/meshive" \
      org.opencontainers.image.licenses="AGPL-3.0-only"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MESHIVE_ENVIRONMENT=production \
    MESHIVE_DATA_DIR=/app/data \
    MESHIVE_CACHE_DIR=/app/cache \
    MESHIVE_BACKUP_DIR=/backups \
    MESHIVE_FRONTEND_DIST=/app/frontend

RUN sed -i 's/Components: main$/Components: main non-free/' \
      /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install --no-install-recommends --yes 7zip 7zip-rar gosu \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend ./backend
RUN pip install --no-cache-dir ./backend

COPY --from=frontend-build /build/frontend/dist ./frontend
COPY docker/entrypoint.sh ./entrypoint.sh
RUN chmod 0755 ./entrypoint.sh \
    && mkdir -p /app/data /app/cache /backups /models

RUN groupadd --gid 10001 meshive \
    && useradd --create-home --uid 10001 --gid 10001 meshive \
    && chown -R meshive:meshive /app/data /app/cache /backups

EXPOSE 8000
VOLUME ["/app/data", "/app/cache", "/backups"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"]

ENTRYPOINT ["/app/entrypoint.sh"]
