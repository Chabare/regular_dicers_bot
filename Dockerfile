FROM python:3.7-slim

WORKDIR /usr/src/app

ENV TZ=Europe/Berlin

COPY . .

RUN pip install --no-cache-dir -r requirements.txt

CMD python -B -O main.py
