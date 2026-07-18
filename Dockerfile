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

COPY main.py .
COPY app/ ./app/

# Created with a default UID/GID of 1000; entrypoint.sh remaps this at
# container startup to match whatever PUID/PGID env vars are passed in,
# so it works regardless of what the host's data folder is owned by.
RUN useradd --uid 1000 --create-home --shell /bin/false appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 5055

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python3 -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:5055/healthz', timeout=3)" || exit 1

CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:5055 --workers 1 --threads 4 --timeout 60 main:app"]