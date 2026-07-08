# AptenByte API — production image (Django + gunicorn, WhiteNoise for admin static).
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_DEBUG=False

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Bake admin/static into STATIC_ROOT so WhiteNoise can serve it without nginx.
RUN python manage.py collectstatic --noinput

EXPOSE 8000

# Run migrations on start (safe/idempotent — the DB may live on a mounted volume), then serve.
# gthread workers + a long timeout so streamed LLM (SSE) responses aren't cut off mid-flight.
CMD ["sh", "-c", "python manage.py migrate --noinput && exec gunicorn aptenbyte_api.wsgi:application --bind 0.0.0.0:8000 --workers 3 --threads 4 --worker-class gthread --timeout 120"]
