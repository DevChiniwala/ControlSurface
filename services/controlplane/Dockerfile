FROM python:3.15-alpine@sha256:d44b1254cb92329418d164b22b20d86bbd3869d48e80e09e476531a409a728bb AS build

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apk add --no-cache build-base libffi-dev linux-headers
COPY services/controlplane/pyproject.toml /app/pyproject.toml
COPY services/controlplane/runtime-constraints.txt /app/runtime-constraints.txt
COPY services/controlplane/src /app/src
RUN --mount=type=cache,target=/root/.cache/pip \
    pip wheel --wheel-dir /wheels --constraint /app/runtime-constraints.txt /app

FROM python:3.15-alpine@sha256:d44b1254cb92329418d164b22b20d86bbd3869d48e80e09e476531a409a728bb

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY --from=build /wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links=/wheels \
    /wheels/controlsurface_server-*.whl && rm -rf /wheels && \
    python -m pip uninstall --yes pip
COPY services/controlplane/migrations /app/migrations
RUN addgroup -g 10001 -S controlsurface && \
    adduser -u 10001 -S -D -H -G controlsurface controlsurface
USER controlsurface
