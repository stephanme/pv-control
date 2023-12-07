# syntax=docker/dockerfile:1
FROM python:3.11-bullseye as builder
# install/compile wheels
WORKDIR /usr/src/app
COPY requirements.txt ./
RUN pip wheel --no-cache-dir --prefer-binary --extra-index-url https://www.piwheels.org/simple --wheel-dir /usr/wheels -r requirements.txt


FROM python:3.11-slim-bullseye
WORKDIR /usr/src/app

RUN --mount=type=cache,target=/usr/wheels,from=builder,source=/usr/wheels pip install --no-cache /usr/wheels/*

# see .dockerignore
COPY . ./

CMD [ "python", "-m", "pvcontrol" ]
EXPOSE 8080
