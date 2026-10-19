FROM lemanjo/unraid-mcp@sha256:93c7f8c5d688d52d1912011fb509e48023080fdcf93fec0b7d606c526bfa2325

USER 0
COPY docker-scope-patch.cjs /app/docker-scope-patch.cjs
RUN ["/nodejs/bin/node", "/app/docker-scope-patch.cjs"]
USER 65532:65532
