FROM python:3.7-alpine

RUN apk add --update --no-cache openssl-dev libffi-dev build-base

WORKDIR /usr/src/app

COPY . .

RUN pip install --no-cache-dir -r requirements.txt

CMD python -B -O -OO main.py
