# Backend Dockerfile (Week 18) — multi-stage: builder installs Python deps
# into a venv, runtime copies just that venv + source, so build tools
# (gcc, etc., needed by some C-extension wheels) never ship in the final
# image.

FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir poetry==1.8.3
ENV POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_NO_INTERACTION=1

WORKDIR /app
COPY pyproject.toml poetry.lock ./
RUN poetry install --only main --no-root


FROM python:3.11-slim AS runtime

# WeasyPrint (Week 14 PDF generation) needs Pango/cairo/gdk-pixbuf for
# real HTML/CSS rendering; curl is for the HEALTHCHECK below.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpango-1.0-0 libpangoft2-1.0-0 libpangocairo-1.0-0 \
        libcairo2 libgdk-pixbuf-2.0-0 libffi8 shared-mime-info fonts-liberation \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1

# Playwright's own Chromium binary + its OS-level deps (Week 13's map
# thumbnail rasterization, generate_pdf's embedded map image) — playwright
# itself is a real runtime dependency of this project now (see
# pyproject.toml), not just a test tool, so `--with-deps` here is what
# makes that feature actually work in the container rather than silently
# degrading (PDFs would still generate, just without the map image).
RUN playwright install --with-deps chromium

COPY src ./src

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8000/docs || exit 1

CMD ["uvicorn", "travel_agent.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
