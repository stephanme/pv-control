# syntax=docker/dockerfile:1
FROM python:3.14.1-bookworm AS builder

#renovate: datasource=github-releases depName=astral-sh/uv
ARG UV_VERSION=0.9.14
RUN curl -fsSL https://astral.sh/uv/${UV_VERSION}/install.sh | sh

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



FROM python:3.14.1-slim-bookworm
ARG VCS_REF
LABEL org.opencontainers.image.revision=$VCS_REF
WORKDIR /app

# Copy the environment, but not the source code
COPY --from=builder --chown=app:app /app/ /app/

ENV PATH="/app/.venv/bin:$PATH"
CMD [ "python", "-m", "pvcontrol" ]
EXPOSE 8080
