# syntax=docker/dockerfile:1
FROM python:3.11-slim
ENV PYTHONHASHSEED=0 PYTHONPATH=/app
WORKDIR /app
COPY requirements.runtime.lock /app/requirements.runtime.lock
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca; fi; \
    pip install --no-cache-dir -r requirements.runtime.lock
COPY pipeline /app/pipeline
RUN chmod -R a+rX /app/pipeline
ENTRYPOINT ["python", "/app/pipeline/processing_container/processing/main.py"]
