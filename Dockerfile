# syntax=docker/dockerfile:1
FROM debian:bookworm-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 LANG=C.UTF-8 \
    PYTHONPATH=/opt/gramps:/opt/radici:/opt/radici/python-libs GRAMPSHOME=/data/config HOME=/data
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-gi python3-cairo python3-icu python3-cairosvg \
    python3-fonttools python3-lxml python3-pil python3-pypdf2 gir1.2-gtk-3.0 fonts-dejavu-core ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -g 10001 radici && useradd -u 10001 -g radici -d /data radici
ADD --checksum=sha256:8c7cb322801934537be9781b2c3bf8d50595591494eed5ac6d76b0dc3eb0a81e https://codeload.github.com/gramps-project/gramps/zip/refs/tags/v6.0.8 /tmp/gramps.zip
RUN echo '8c7cb322801934537be9781b2c3bf8d50595591494eed5ac6d76b0dc3eb0a81e  /tmp/gramps.zip' | sha256sum -c - \
    && python3 -m zipfile -e /tmp/gramps.zip /opt \
    && mv /opt/gramps-6.0.8 /opt/gramps && rm /tmp/gramps.zip \
    && mkdir -p /data /media /backups && chown radici:radici /data /media /backups
ADD --checksum=sha256:90005e959e1596c6e6c84c8b0ad383285b3e17011751cedd17f2ce8fcdfc86de https://files.pythonhosted.org/packages/55/f2/7ebe366f633f30a6ad105f650f44f24f98cb1335c4157d21ae47138b3482/pypdf-6.10.0-py3-none-any.whl /tmp/pypdf.whl
ADD --checksum=sha256:f9d4a5e041ae435b815e568537755773d05dac031fee6a57b4ba70897a44d9d2 https://files.pythonhosted.org/packages/bb/6a/e5bf7b70883f374710ad74faf99bacfc4b5b5a7797c1d5e130350e0e28a3/orjson-3.11.3-cp311-cp311-manylinux_2_17_x86_64.manylinux2014_x86_64.whl /tmp/orjson.whl
RUN python3 -m zipfile -e /tmp/pypdf.whl /opt/radici/python-libs && python3 -m zipfile -e /tmp/orjson.whl /opt/radici/python-libs && rm /tmp/pypdf.whl /tmp/orjson.whl
WORKDIR /opt/radici
COPY app ./app
COPY tests ./tests
COPY scripts ./scripts
COPY LICENSE NOTICE ./
USER 10001:10001
EXPOSE 8787
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s \
  CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8787/health', timeout=4)"
CMD ["python3", "-m", "app.server"]
