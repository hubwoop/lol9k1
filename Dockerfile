FROM tiangolo/uwsgi-nginx-flask:python3.7
ENV TZ=Europe/Berlin
ENV LISTEN_PORT 80
EXPOSE 80
COPY lol9k1 /app
RUN pip install -r requirements.txt
