# syntax=docker/dockerfile:1
FROM python:3.13-bullseye AS builder
# install/compile wheels
WORKDIR /usr/src/app
COPY requirements.txt ./
RUN pip wheel --no-cache-dir --prefer-binary --wheel-dir /usr/wheels -r requirements.txt


FROM python:3.13-slim-bullseye
WORKDIR /usr/src/app

RUN --mount=type=cache,target=/usr/wheels,from=builder,source=/usr/wheels pip install --no-cache /usr/wheels/*

# see .dockerignore
COPY . ./

CMD [ "python", "-m", "pvcontrol" ]
EXPOSE 8080
