FROM python:3.7-slim
ARG COMMIT_SHA_ARG
ENV COMMIT_SHA=$COMMIT_SHA_ARG

WORKDIR /usr/src/app

COPY requirements.txt ./
RUN pip install --no-cache-dir --extra-index-url https://www.piwheels.org/simple -r requirements.txt

COPY ./pvcontrol/*.py ./pvcontrol/
COPY /ui/dist/ui ./ui/dist/ui/

CMD [ "python", "-m", "pvcontrol" ]
EXPOSE 8080
