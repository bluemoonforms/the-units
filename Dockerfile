FROM python:3.6

LABEL project="the-units"
LABEL company="Blue Moon Software Demo"
LABEL version="0.1"
LABEL maintainer="Stephen Durham <sdurham@bluemoonforms.com>"

ENV PYTHONPATH=/usr/src/app

EXPOSE 8000

RUN python3.6 -m pip install pipenv chalice

WORKDIR /usr/src/app

COPY Pipfile ./
COPY Pipfile.lock ./

RUN pipenv sync
COPY . .

CMD ["pipenv", "run", "chalice", "local", "--host", "0.0.0.0"]
