FROM python:3.12-slim

ARG NUITKA_BUILD=0

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Minimal build/runtime deps for Pillow and general Python packages.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libjpeg62-turbo-dev \
        zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

# Optional compiled mode: compile Web/app.py with Nuitka as a Python extension module.
# Gunicorn keeps the same service interface (`app:app`), but imports compiled code.
RUN if [ "$NUITKA_BUILD" = "1" ]; then \
      pip install --no-cache-dir nuitka ordered-set zstandard; \
      python -m nuitka --module /app/Web/app.py --output-dir=/app/Web; \
      mv /app/Web/app.py /app/Web/app.py.source; \
    fi

WORKDIR /app/Web
EXPOSE 8000

CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "60", "--graceful-timeout", "20", "--max-requests", "1000", "--max-requests-jitter", "100", "--log-level", "info", "--access-logfile", "-", "--error-logfile", "-"]
