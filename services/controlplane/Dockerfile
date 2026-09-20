FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY services/controlplane/pyproject.toml /app/pyproject.toml
COPY services/controlplane/src /app/src
COPY services/controlplane/migrations /app/migrations
RUN --mount=type=cache,target=/root/.cache/pip pip install /app
COPY benchmarks /app/benchmarks
RUN useradd --create-home --uid 10001 controlsurface
USER controlsurface
