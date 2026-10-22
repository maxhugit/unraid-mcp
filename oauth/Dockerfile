FROM python:3.13-slim

ARG FASTMCP_VERSION=3.4.7

RUN pip install --no-cache-dir "fastmcp==${FASTMCP_VERSION}" \
    && useradd --uid 65532 --create-home mcp

WORKDIR /app
COPY gateway.py /app/gateway.py

USER 65532:65532
ENV HOME=/home/mcp
ENTRYPOINT ["python", "/app/gateway.py"]
