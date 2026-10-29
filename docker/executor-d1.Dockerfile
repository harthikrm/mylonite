# D1 executor image: executor.Dockerfile plus a pinned gRPC client for the OTel cart.
# A separate image so the D2/D3 executor (and the pilot's and A2's provenance) stay unchanged.
FROM python@sha256:5dde09372dfa8e7762892b2a12619fcf6c23b0b78bce1058a9fa5a3a7a40e68e

COPY requirements-d1.lock /tmp/requirements.lock
RUN pip install --no-cache-dir --no-deps --require-hashes -r /tmp/requirements.lock \
    && rm /tmp/requirements.lock

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src:/app
WORKDIR /app
USER 65534:65534
ENTRYPOINT ["python", "-m", "mylonite.executor"]
