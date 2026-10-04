# AGame server image. Code only: no data, no secrets. Real data lives on a mounted volume.
FROM python:3.12-slim

ARG INSTALL_COACH=0
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    AGAME_DATA_DIR=/data \
    AGAME_DIST_DIR=/data/dist \
    PORT=8080

RUN useradd --create-home --uid 10001 agame \
    && mkdir -p /data \
    && chown agame:agame /data \
    && if [ "$INSTALL_COACH" = "1" ]; then pip install --no-cache-dir anthropic; fi

WORKDIR /app
COPY config ./config
COPY schemas ./schemas
COPY scripts ./scripts
# Empty, schema-valid fixtures used only to seed an empty volume on first boot.
COPY data ./seed-data
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod 0755 /usr/local/bin/docker-entrypoint.sh && rm -rf /app/scripts/tests /app/scripts/e2e

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python3 -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:%s/healthz' % os.environ.get('PORT','8080'), timeout=4)"

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["python3", "scripts/fitness_server.py"]
