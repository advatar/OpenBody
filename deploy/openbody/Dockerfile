# OpenBody reference host.
#
# The image copies the whole repository on purpose. `openbody_ref` resolves
# `schemas/`, `registry/` and `examples/` relative to the checkout root
# (`ROOT = Path(__file__).resolve().parents[3]`), so an installed wheel on its own
# cannot serve the contract. Repository layout is a runtime dependency here.
#
# Build from the repository root:
#   docker build -f deploy/openbody/Dockerfile -t openbody-host .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# requirements-dev.txt is the pinned set CI validates against, and it is installed
# whole so the running image can re-run its own conformance suite:
#   docker run --rm -e PYTHONPATH=/app/reference/python openbody-host \
#     pytest -q reference/python/tests -k "not identity_changes_when_an_artifact_changes"
# That one test mutates the registry to prove the contract digest tracks it, which
# this image's read-only application tree correctly forbids.
COPY requirements-dev.txt ./
RUN python -m pip install --no-cache-dir --upgrade pip \
 && python -m pip install --no-cache-dir -r requirements-dev.txt

COPY . /app

# Read-only application tree owned by root, run as an unprivileged user: the host
# keeps all protocol state in memory and writes nothing to disk.
RUN useradd --system --uid 10001 --create-home openbody
USER 10001

ENV PYTHONPATH=/app/reference/python:/app/deploy/openbody
EXPOSE 8797

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8797/healthz', timeout=4)"

CMD ["uvicorn", "openbody_asgi:create_app_from_env", "--factory", "--host", "0.0.0.0", "--port", "8797"]
