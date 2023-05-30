FROM tiangolo/uwsgi-nginx-flask:python3.9

LABEL org.opencontainers.image.description="Organize your LAN party"

EXPOSE 80

COPY lol9k1 /app/lol9k1

ENV FLASK_APP=lol9k1

RUN pip install -r requirements.txt
