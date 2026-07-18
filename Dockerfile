FROM python:3.12-slim

# Keep the image small and predictable
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY unmonitor_webhook.py .

# Run as a non-root user (isolated + follows least-privilege practice)
RUN useradd --create-home --shell /bin/false appuser
USER appuser

EXPOSE 5055

# Basic healthcheck against the /healthz endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python3 -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:5055/healthz', timeout=3)" || exit 1

CMD ["python3", "unmonitor_webhook.py"]
