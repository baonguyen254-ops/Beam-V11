FROM node:22-alpine AS frontend
WORKDIR /app/frontend
COPY beam-frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY beam-frontend/ ./
RUN npm run build

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8000 BEAM_DATA_DIR=/data
WORKDIR /app/backend
COPY beam-backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home beam && mkdir /data && chown beam:beam /data
COPY --chown=beam:beam beam-backend/ ./
COPY --from=frontend --chown=beam:beam /app/frontend/dist ./static
USER beam
VOLUME ["/data"]
EXPOSE 8000
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
