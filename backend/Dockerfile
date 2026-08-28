FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PHYSICS_ATLAS_FIXTURE_DIRECTORY=/app/fixtures \
    PHYSICS_ATLAS_REFERENCE_DATA_PATH=/app/reference/atlas.json

WORKDIR /app

COPY backend/pyproject.toml backend/README.md ./
COPY LICENSE NOTICE ./
COPY backend/src ./src
RUN python -m pip install --no-cache-dir .

COPY backend/alembic.ini ./alembic.ini
COPY backend/alembic ./alembic
COPY backend/fixtures ./fixtures
COPY src/data/demo/atlas.json ./reference/atlas.json

RUN addgroup --system atlas \
    && adduser --system --ingroup atlas atlas \
    && chown -R atlas:atlas /app
USER atlas

EXPOSE 8000

CMD ["uvicorn", "physics_atlas_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
