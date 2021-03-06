FROM python:3-alpine

COPY requirements.txt /requirements.txt
RUN pip install -r requirements.txt

RUN rm requirements.txt

COPY ./src /src