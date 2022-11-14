FROM python:3.9-bullseye as builder
WORKDIR /usr/src/app
COPY requirements.txt ./
RUN pip wheel --no-cache-dir --prefer-binary --extra-index-url https://www.piwheels.org/simple --wheel-dir /usr/wheels -r requirements.txt


FROM python:3.9-slim-bullseye
ARG COMMIT_SHA_ARG
ENV COMMIT_SHA=$COMMIT_SHA_ARG

WORKDIR /usr/src/app

COPY --from=builder /usr/wheels /usr/wheels
RUN pip install --no-cache /usr/wheels/*

COPY ./pvcontrol/*.py ./pvcontrol/
COPY /ui/dist/ui ./ui/dist/ui/

CMD [ "python", "-m", "pvcontrol" ]
EXPOSE 8080
