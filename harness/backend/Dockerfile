FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv/backend
# The container is the PostgreSQL deployment, so it takes the optional file as well:
# psycopg lives there because the desktop application is SQLite and never opens a
# Postgres connection, while deploy/compose.yaml points HARNESS_DATABASE_URL at one.
# playwright also arrives here; the browser tool needs ``playwright install chromium``
# on top of the package, so an image that wants it must add that step.
COPY backend/requirements.txt backend/requirements-optional.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-optional.txt \
    && useradd --uid 10001 --create-home harness
COPY backend/app ./app
COPY backend/legal ./legal
COPY backend/scripts ./scripts
# ``web/`` and ``model/`` are not under backend/, and they are not optional:
# app/resources.py::resource_root() walks two parents up from app/, which is /srv here, so
# WEB_DIR resolves to /srv/web. Built with a backend/-only context those directories were
# unreachable, and the container answered 404 at / and /playground while the desktop
# bundle served both - the exact divergence package.py exists to prevent.
# ``legal/`` is different: config.legal_dir() resolves relative to app/ (parents[1]), so it
# stays at /srv/backend/legal and must not be moved.
COPY web /srv/web
COPY model /srv/model
RUN mkdir -p /srv/backend/.data && chown -R harness:harness /srv/backend
USER harness
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--proxy-headers", "--forwarded-allow-ips", "127.0.0.1"]
