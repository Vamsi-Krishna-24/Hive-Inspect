# ---------- Build stage ----------
FROM python:3.12-slim as builder

WORKDIR /app

# Install system deps needed for some Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install --user -r requirements.txt


# ---------- Runtime stage ----------
FROM python:3.12-slim

WORKDIR /app

# Runtime system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Copy project code
COPY . .

# Collect static files (WhiteNoise will serve them)
RUN python manage.py collectstatic --noinput

# Cloud Run expects the app to listen on $PORT (default 8080)
ENV PORT=8080
EXPOSE 8080

# Use Gunicorn
CMD exec gunicorn --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120 hiveinspect.wsgi:application