FROM tiangolo/uwsgi-nginx-flask:python3.11

LABEL org.opencontainers.image.description="Organize your LAN party"

# pull in Debian security fixes newer than the base image
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

COPY lol9k1 /app/lol9k1

RUN pip install -r /app/lol9k1/requirements.txt

EXPOSE 9001

ENV FLASK_APP=lol9k1 \
    FLASK_RUN_PORT=9001

CMD flask run --host=0.0.0.0 --port=9001