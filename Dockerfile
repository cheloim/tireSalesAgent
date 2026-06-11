# Tire Sales Agent - Backend
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py .
COPY inventory.py .

ENV PYTHONUNBUFFERED=1
ENV PORT=5000

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -sf http://localhost:5000/api/estado || exit 1

CMD ["gunicorn", "-w", "1", "-k", "gthread", "--threads", "4", "--timeout", "300", "app:app", "-b", "0.0.0.0:5000"]