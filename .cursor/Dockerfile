# Cloud Agent / Dev Container base image for Operation Prometheus.
# Cursor checks out the workspace separately — do not COPY the project here.
FROM python:3.12-bookworm

# Versions are Debian bookworm (python:3.12-bookworm). Pin for Hadolint DL3008 /
# Codacy "Pin versions in apt get install".
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        git=1:2.39.5-0+deb12u3 \
        curl=7.88.1-10+deb12u15 \
        ca-certificates=20230311+deb12u1 \
        jq=1.6-2.1+deb12u2 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for container security.
RUN groupadd -r prometheus && useradd -r -g prometheus -m -d /home/prometheus prometheus \
    && chown -R prometheus:prometheus /workspace /usr/local

WORKDIR /workspace

USER prometheus
