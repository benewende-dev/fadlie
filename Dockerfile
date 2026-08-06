# Fadlie's MCP server, as App Runner expects it: one container, one port, one
# health check, no state on disk.
#
# Two stages. The first builds a virtual environment, the second copies it into
# a clean image, so a build toolchain never ships to production.
#
# linux/amd64 explicitly. The development machine is arm64, and an image whose
# architecture does not match fails at *deploy* time — after the push, with a
# message about the manifest rather than about the CPU.

FROM --platform=linux/amd64 python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Dependencies resolve from pyproject.toml alone, so this layer is rebuilt only
# when they change — not on every edit to the source.
COPY pyproject.toml README.md ./
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --upgrade pip \
 && /opt/venv/bin/pip install .

COPY fadlie/ ./fadlie/
RUN /opt/venv/bin/pip install --no-deps .


FROM --platform=linux/amd64 python:3.12-slim

# Fadlie talks to DataHub and to Bedrock over TLS. python:slim generally ships a
# certificate store; installing it explicitly means the image does not depend on
# that staying true.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# An unprivileged user. Nothing this process does needs root, and a container
# that runs as root only has to be wrong once.
RUN useradd --create-home --uid 10001 fadlie

COPY --from=builder /opt/venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

USER fadlie
EXPOSE 8000

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
