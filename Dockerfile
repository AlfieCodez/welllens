# WellLens production image. Works on any container host (Fly.io, Render, etc.).
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY . .

EXPOSE 8080

# One worker + threads keeps SQLite happy; bump workers (and move to Postgres)
# when you scale. $PORT is honoured by hosts that inject it (e.g. Render).
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT:-8080} --workers 1 --threads 4 --worker-class gthread --timeout 60 wsgi:app"]
