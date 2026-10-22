FROM docker:28.5.1-cli

RUN apk add --no-cache python3

COPY agent.py /app/agent.py

EXPOSE 8320
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -q -O - http://127.0.0.1:8320/health >/dev/null || exit 1

ENTRYPOINT ["python3", "/app/agent.py"]
