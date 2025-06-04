# syntax=docker/dockerfile:1
FROM python:3.13-bookworm AS builder

# install uv, can't use image because arm7 is not provided
ADD https://astral.sh/uv/install.sh /uv-installer.sh
RUN sh /uv-installer.sh && rm /uv-installer.sh

ENV \
    PATH="/root/.local/bin/:$PATH" \
    UV_LINK_MODE=copy \
    UV_SYSTEM_PYTHON=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_COMPILE_BYTECODE=1 \
    UV_LOCKED=1

WORKDIR /app

# Install dependencies
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev

# copy app and sync project
# see .dockerignore
COPY . ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev



FROM python:3.13-slim-bookworm
WORKDIR /app

# Copy the environment, but not the source code
COPY --from=builder --chown=app:app /app/ /app/

ENV PATH="/app/.venv/bin:$PATH"
CMD [ "python", "-m", "pvcontrol" ]
EXPOSE 8080
