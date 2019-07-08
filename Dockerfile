FROM python:3.7-slim

WORKDIR /usr/src/app

ENV TZ=Europe/Berlin

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD python -B -O main.py
