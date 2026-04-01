# syntax=docker/dockerfile:1
# Debian bookworm + distro python3.11 so `unit-python3.11` and the uv `.venv` share one interpreter.
FROM debian:bookworm-slim

COPY --from=ghcr.io/astral-sh/uv:0.9.7 /uv /usr/local/bin/uv

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        curl \
        gnupg \
        libgomp1 \
        libglib2.0-0 \
        libgl1 \
        python3.11 \
        python3.11-venv \
        tini \
    ; \
    mkdir -p /etc/apt/keyrings; \
    curl -fsSL https://nginx.org/keys/nginx_signing.key \
        | gpg --dearmor -o /etc/apt/keyrings/nginx-keyring.gpg; \
    echo "deb [signed-by=/etc/apt/keyrings/nginx-keyring.gpg] https://packages.nginx.org/unit/debian/ bookworm unit" \
        > /etc/apt/sources.list.d/unit.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends unit unit-python3.11; \
    rm -rf /var/lib/apt/lists/*; \
    useradd --uid 1000 --create-home --shell /bin/bash app

WORKDIR /app
ENV PYTHONUNBUFFERED=1
ENV UV_COMPILE_BYTECODE=1
ENV UV_PYTHON=/usr/bin/python3.11
# uv default 30s times out on large wheels (e.g. scikit-image via easyocr) on slow networks.
ENV UV_HTTP_TIMEOUT=600

ENV HF_HOME=/app/.cache/huggingface
ENV TRANSFORMERS_CACHE=/app/.cache/huggingface/transformers
ENV HF_HUB_CACHE=/app/.cache/huggingface/hub
ENV XDG_CACHE_HOME=/app/.cache

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev \
    && uv run python -c "import fastapi"

RUN mkdir -p "$HF_HOME" "$TRANSFORMERS_CACHE" "$HF_HUB_CACHE" "$XDG_CACHE_HOME" \
    && chown -R app:app /app

COPY --chown=app:app main.py .
COPY --chown=app:app docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh \
    && uv run python -c "import main; assert main.app"

ENV PORT=80
EXPOSE 80

# Root so unitd can bind :80; ASGI workers run as `app` (see docker-entrypoint.sh).
ENTRYPOINT ["/usr/bin/tini", "--", "/docker-entrypoint.sh"]
