# B.E.A.M. v8 production image: Vite build + FastAPI/WebSocket on one origin.
FROM node:22-alpine AS frontend
WORKDIR /app/frontend
COPY beam-frontend/package*.json ./
RUN npm install
COPY beam-frontend/ ./
RUN npm run build

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8000
WORKDIR /app/backend
COPY beam-backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY beam-backend/ ./
COPY --from=frontend /app/frontend/dist ./static
EXPOSE 8000
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
