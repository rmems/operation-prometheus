# Cloud Agent / Dev Container base image for Operation Prometheus.
# Cursor checks out the workspace separately — do not COPY the project here.
FROM python:3.12-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        git \
        curl \
        ca-certificates \
        jq \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace
