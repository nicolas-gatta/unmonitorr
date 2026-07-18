FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
COPY app/ ./app/

# Fixed UID 1000. This host doesn't allow runtime UID switching inside the
# container (chown/setuid as "root" fails - likely userns-remap or similar
# restriction), so the host-side data folder just needs to be chown'd to
# 1000:1000 once, from the host itself:
#   chown -R 1000:1000 /opt/unmonitorr/data
RUN useradd --uid 1000 --create-home --shell /bin/false appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 5055

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python3 -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:5055/healthz', timeout=3)" || exit 1

CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:5055 --workers 1 --threads 4 --timeout 60 main:app"]