FROM node:22-bookworm-slim AS web
WORKDIR /app
COPY package.json package-lock.json ./
COPY apps/web/package.json apps/web/package.json
RUN npm ci --ignore-scripts
COPY apps/web apps/web
COPY packages/contracts packages/contracts
COPY tests/fixtures/synthetic.scene.json tests/fixtures/synthetic.scene.json
COPY config/placement-30669-alt-02-v3.json config/placement-30669-alt-02-v3.json
COPY config/sets.json config/sets.json
RUN npm run build

FROM python:3.11-slim-bookworm AS runtime
COPY --from=ghcr.io/astral-sh/uv:0.9.2 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY apps/api/src apps/api/src
RUN uv sync --frozen --no-dev --extra cloud --no-editable
COPY config/sets.json config/sets.json
COPY config/release-sources.json config/release-sources.json
COPY --from=web /app/apps/web/dist apps/web/dist
RUN useradd --uid 10001 --create-home app && mkdir -p /app/var && chown app:app /app/var
USER 10001
ENV PYTHONPATH=/app/apps/api/src PATH=/app/.venv/bin:$PATH PYTHONUNBUFFERED=1 GUIDE2BUILD_WEB_DIST=/app/apps/web/dist
EXPOSE 8080
CMD ["sh", "-c", "exec uvicorn guide2build.public:app --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers --forwarded-allow-ips='*' --no-access-log"]
