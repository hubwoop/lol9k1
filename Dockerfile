FROM tiangolo/uwsgi-nginx-flask:python3.6
ENV TZ=Europe/Berlin
ENV LISTEN_PORT 80
EXPOSE 80
COPY ./app /app
RUN pip install -r requirements.txt
