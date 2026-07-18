FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# gosu lets the entrypoint drop from root to appuser cleanly after fixing
# up permissions - usermod/groupmod need root, so we can't set USER here.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY unmonitor_webhook.py .
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Created with a default UID/GID of 1000; entrypoint.sh remaps this at
# container startup to match whatever PUID/PGID env vars are passed in,
# so it works regardless of what the host's data folder is owned by.
RUN useradd --uid 1000 --create-home --shell /bin/false appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app

EXPOSE 5055

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python3 -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:5055/healthz', timeout=3)" || exit 1

# Container starts as root (needed for usermod/chown in entrypoint.sh),
# then entrypoint.sh drops to appuser (remapped to PUID:PGID) via gosu.
ENTRYPOINT ["/entrypoint.sh"]
CMD ["python3", "unmonitor_webhook.py"]