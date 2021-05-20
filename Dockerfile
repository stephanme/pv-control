FROM python:3.7-slim
ARG COMMIT_SHA_ARG
ENV COMMIT_SHA=$COMMIT_SHA_ARG

WORKDIR /usr/src/app

COPY requirements.txt ./

# build-essential needed for gpio library
# clean up after pip install to keep image small
# libffi-dev, libssl-dev, rust are required for Authlib>cryptography>cffi (seems missing on arm)
RUN apt-get update \
  && apt-get install -y --no-install-recommends build-essential \
  && pip install --no-cache-dir --extra-index-url https://www.piwheels.org/simple -r requirements.txt \
  && apt-get remove -y build-essential \
  && apt-get -y autoremove \
  && apt-get clean \
  && rm -rf /var/lib/apt-get/lists/*

COPY ./pvcontrol/*.py ./pvcontrol/
COPY /ui/dist/ui ./ui/dist/ui/

CMD [ "python", "-m", "pvcontrol" ]
EXPOSE 8080
