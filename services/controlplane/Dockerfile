FROM python:3.13-alpine@sha256:79e7a9b9ff1cbceff819f856fb374477792a5967759d94df266de7b7b4120e6f AS build

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apk add --no-cache build-base libffi-dev linux-headers
COPY services/controlplane/pyproject.toml /app/pyproject.toml
COPY services/controlplane/runtime-constraints.txt /app/runtime-constraints.txt
COPY services/controlplane/src /app/src
RUN --mount=type=cache,target=/root/.cache/pip \
    pip wheel --wheel-dir /wheels --constraint /app/runtime-constraints.txt /app

FROM python:3.13-alpine@sha256:79e7a9b9ff1cbceff819f856fb374477792a5967759d94df266de7b7b4120e6f

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
