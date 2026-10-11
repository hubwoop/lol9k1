FROM python:3.14-slim-trixie

LABEL org.opencontainers.image.description="Organize your LAN party"

# pull in Debian security fixes newer than the base image
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY lol9k1/requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt 'gunicorn>=23,<24'

COPY lol9k1 /app/lol9k1

RUN useradd --system --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin lol9k1 \
    && mkdir /data \
    && chown lol9k1:lol9k1 /data
VOLUME /data
USER lol9k1

ENV FLASK_APP=lol9k1 \
    LOL9K1_DB_PATH=/data/lol9k1.db

EXPOSE 9001

# migrate the database before serving, so a new image brings its schema along.
# a failing migration is rolled back and keeps the container from starting.
# a single worker process: without LOL9K1_SECRET_KEY each process would
# generate its own random secret and sessions would not survive across workers
CMD ["sh", "-c", "flask db upgrade && exec gunicorn --bind 0.0.0.0:9001 --workers 1 --threads 4 \
     --access-logfile - 'lol9k1:create_app()'"]
