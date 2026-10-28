# Executor image: proxy, scheduler, executor and oracle (ARCHITECTURE.md §9).
# Our source is mounted read-only at run time; this image only carries pinned dependencies.
FROM python@sha256:5dde09372dfa8e7762892b2a12619fcf6c23b0b78bce1058a9fa5a3a7a40e68e

COPY requirements.lock /tmp/requirements.lock
RUN pip install --no-cache-dir --no-deps --require-hashes -r /tmp/requirements.lock \
    && rm /tmp/requirements.lock

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src:/app
WORKDIR /app
USER 65534:65534
ENTRYPOINT ["python", "-m", "mylonite.executor"]
