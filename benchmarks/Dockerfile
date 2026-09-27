FROM python:3.13-alpine@sha256:79e7a9b9ff1cbceff819f856fb374477792a5967759d94df266de7b7b4120e6f

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apk add --no-cache build-base libffi-dev linux-headers
COPY services/controlplane/pyproject.toml /app/server/pyproject.toml
COPY services/controlplane/src /app/server/src
COPY services/controlplane/runtime-constraints.txt /app/runtime-constraints.txt
COPY sdk/python/pyproject.toml /app/sdk/pyproject.toml
COPY sdk/python/src /app/sdk/src
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --constraint /app/runtime-constraints.txt /app/server /app/sdk
COPY benchmarks /app/benchmarks
RUN addgroup -g 10001 -S controlsurface && \
    adduser -u 10001 -S -D -H -G controlsurface controlsurface
USER controlsurface
ENTRYPOINT ["python", "/app/benchmarks/system.py"]
