# syntax=docker/dockerfile:1.7
# One image, two roles: `api` (default) and `worker` (see docker-entrypoint.sh).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

RUN pip install --no-cache-dir uv==0.12.22

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY threadeye ./threadeye
COPY alembic.ini ./
RUN uv sync --frozen --no-dev --no-editable

ARG GIT_SHA=dev
ENV THREADEYE_GIT_SHA=${GIT_SHA}

COPY --chmod=755 docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN useradd --system --uid 10001 --home-dir /app threadeye \
    && mkdir -p /data/storage /data/datasets \
    && chown -R threadeye /data
USER threadeye

EXPOSE 8000
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["api"]
